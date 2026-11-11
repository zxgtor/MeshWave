"""Local 2D face detection with ray-based mapping onto the actual OBJ meshes."""
import hashlib
from pathlib import Path
import numpy as np
from texture import read_texture
from wrap_core import parse_obj, MAX_SOURCE, exclusion_masks

MODEL = Path(__file__).parent / 'models' / 'face_landmarker.task'
MODEL_SHA256 = '64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff'
# Sparse anatomical anchors; never use the model's inferred z as OBJ coordinates.
FEATURES = [(1,'鼻尖'), (168,'鼻根'), (33,'右眼外角'), (133,'右眼内角'),
            (362,'左眼内角'), (263,'左眼外角'), (70,'右眉外侧'), (107,'右眉内侧'),
            (336,'左眉内侧'), (300,'左眉外侧'), (98,'右鼻翼'), (327,'左鼻翼'),
            (61,'右嘴角'), (291,'左嘴角'), (0,'上唇中点'), (17,'下唇中点'),
            (152,'下巴'), (10,'额头中点')]
_DETECTOR = None


def detector():
    global _DETECTOR
    if _DETECTOR is None:
        if not MODEL.is_file():
            raise ValueError('缺少人脸模型，请在项目目录运行 python setup_landmarks.py。')
        if hashlib.sha256(MODEL.read_bytes()).hexdigest() != MODEL_SHA256:
            raise ValueError('人脸模型校验失败，请运行 python setup_landmarks.py 重新获取。')
        try:
            import mediapipe as mp
            from mediapipe.tasks.python import vision
        except ImportError as exc:
            raise ValueError('缺少 MediaPipe，请运行 python -m pip install -r requirements.txt。') from exc
        options = vision.FaceLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(model_asset_path=str(MODEL)),
            running_mode=vision.RunningMode.IMAGE, num_faces=2,
            min_face_detection_confidence=.5, min_face_presence_confidence=.5)
        _DETECTOR = vision.FaceLandmarker.create_from_options(options)
    return _DETECTOR


def image_landmarks(snapshot, label):
    import mediapipe as mp
    if not isinstance(snapshot, dict):
        raise ValueError('检测截图格式无效。')
    image = read_texture(snapshot.get('image')).convert('RGB')
    if not (128 <= image.width <= 1024 and 128 <= image.height <= 1024):
        raise ValueError('检测截图边长需为 128–1024 像素。')
    result = detector().detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=np.array(image)))
    if len(result.face_landmarks) != 1:
        message = '未检测到人脸' if not result.face_landmarks else '检测到多个人脸'
        raise ValueError(f'{label}{message}，请将单个人脸调到正面并放大，或使用手动选点。')
    landmarks = np.array([[p.x, p.y] for p in result.face_landmarks[0]])
    if len(landmarks) < 468 or not np.isfinite(landmarks).all():
        raise ValueError('人脸检测返回无效坐标。')
    eye = landmarks[263] - landmarks[33]
    span = float(np.linalg.norm(eye))
    nose_position = float((landmarks[1]-landmarks[33]) @ eye / max(span*span, 1e-12))
    if span < .07 or not .15 <= nose_position <= .85 or abs(eye[1]) > span*.5:
        raise ValueError(f'{label}人脸过小、偏转或倾斜较大，请放大并调到正面后重试。')
    return landmarks


def camera_rays(camera, coordinates):
    if not isinstance(camera, dict):
        raise ValueError('检测相机参数无效。')
    inverse = np.asarray(camera.get('inverseProjection'), dtype=float)
    world = np.asarray(camera.get('world'), dtype=float)
    if inverse.shape != (16,) or world.shape != (16,) or not np.isfinite(inverse).all() or not np.isfinite(world).all():
        raise ValueError('检测相机矩阵无效。')
    inverse, world = inverse.reshape(4,4).T, world.reshape(4,4).T
    try:
        project = np.linalg.inv(inverse) @ np.linalg.inv(world)
    except np.linalg.LinAlgError as exc:
        raise ValueError('检测相机矩阵不可逆。') from exc
    xy = np.asarray(coordinates, dtype=float)*[2,-2]+[-1,1]
    near = np.column_stack([xy, -np.ones(len(xy)), np.ones(len(xy))]) @ (world@inverse).T
    far = np.column_stack([xy, np.ones(len(xy)), np.ones(len(xy))]) @ (world@inverse).T
    if np.any(np.abs(near[:,3]) < 1e-14) or np.any(np.abs(far[:,3]) < 1e-14):
        raise ValueError('检测相机投影无效。')
    near, far = near[:,:3]/near[:,3:], far[:,:3]/far[:,3:]
    ray = far-near; length = np.linalg.norm(ray,axis=1)
    if np.any(length < 1e-12):
        raise ValueError('检测相机射线无效。')
    return near, ray/length[:,None], length, project


def map_landmarks(vertices, faces, coordinates, camera, excluded_vertices=(), snap_limit=.025):
    coordinates = np.asarray(coordinates, dtype=float)
    if coordinates.ndim != 2 or coordinates.shape[1] != 2 or not np.isfinite(coordinates).all():
        raise ValueError('二维特征点格式无效。')
    near, directions, lengths, projection = camera_rays(camera, coordinates)
    # Normalize mesh/rays to avoid scale-dependent ray/triangle tolerances.
    origin = vertices.mean(0); unit = float(np.linalg.norm(np.ptp(vertices,axis=0)))
    if unit < 1e-12 or not np.isfinite(unit):
        raise ValueError('模型尺寸无效。')
    tri = (vertices[faces]-origin)/unit
    edge1,edge2 = tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]
    excluded = set(int(i) for i in excluded_vertices)
    used, mapped, skipped = set(), {}, {}
    for feature, (xy, start, direction, far) in enumerate(zip(coordinates, (near-origin)/unit, directions, lengths/unit)):
        if np.any(xy < 0) or np.any(xy > 1):
            skipped[feature]='超出画面';continue
        h=np.cross(np.broadcast_to(direction,edge2.shape),edge2)
        determinant=np.sum(edge1*h,axis=1)
        valid=np.abs(determinant)>1e-14
        inv=np.divide(1,determinant,out=np.zeros_like(determinant),where=valid)
        s=start-tri[:,0];u=np.sum(s*h,axis=1)*inv
        q=np.cross(s,edge1);v=(q@direction)*inv
        distance=np.sum(edge2*q,axis=1)*inv
        valid &= (u>=-1e-9)&(v>=-1e-9)&(u+v<=1+1e-9)&(distance>=0)&(distance<=far)
        if not valid.any():
            skipped[feature]='未命中可见表面';continue
        distance[~valid]=np.inf
        face=int(np.argmin(distance));hit=start+direction*distance[face]
        candidates=faces[face]
        vertex=int(candidates[np.argmin(np.sum(((vertices[candidates]-origin)/unit-hit)**2,axis=1))])
        if vertex in excluded:
            skipped[feature]='位于排除区域';continue
        clip=projection@np.r_[vertices[vertex],1.]
        if abs(clip[3]) < 1e-14 or np.linalg.norm((clip[:2]/clip[3]*[.5,-.5]+[.5,.5])-xy)>snap_limit:
            skipped[feature]='顶点吸附偏差过大';continue
        if vertex in used:
            skipped[feature]='吸附到重复顶点';continue
        mapped[feature]=vertex;used.add(vertex)
    return mapped, skipped


def generate_pairs(body):
    if not isinstance(body,dict):
        raise ValueError('自动检测请求无效。')
    source,sf=parse_obj(body['source']);target,tf=parse_obj(body['target'])
    if len(source)>MAX_SOURCE:
        raise ValueError('模板超过 100,000 顶点。')
    masks=exclusion_masks(sf,tf,body.get('excludedFaces',{}),[])
    detector()  # Explain missing dependencies before any image processing.
    mapped, dropped = {}, {}
    for side,label,vertices,faces in [('source','模板',source,sf),('target','目标',target,tf)]:
        snapshot=body.get(side+'View')
        detected=image_landmarks(snapshot,label)
        coordinates=np.array([detected[i] for i,_ in FEATURES])
        mapped[side], dropped[side]=map_landmarks(vertices,faces,coordinates,snapshot.get('camera'),masks[side][1])
    pairs,names,skipped=[],[],[]
    for i,(_,name) in enumerate(FEATURES):
        if i in mapped['source'] and i in mapped['target']:
            pairs.append([mapped['source'][i],mapped['target'][i]]);names.append(name)
        else:
            reasons=[label+': '+dropped[side][i] for side,label in [('source','模板'),('target','目标')] if i in dropped[side]]
            skipped.append({'name':name,'reason':'；'.join(reasons)})
    if len(pairs)<6:
        raise ValueError(f'只得到 {len(pairs)} 对可用表面点，需要至少 6 对；请放大正面视图、检查排除区或手动选点。')
    for vertices,column in [(source,0),(target,1)]:
        points=vertices[np.array(pairs)[:,column]]
        if np.linalg.matrix_rank(points-points.mean(0))<2:
            raise ValueError('自动对应点分布退化，请调整视角或手动选点。')
    return {'pairs':pairs,'names':names,'skipped':skipped,'detector':'MediaPipe Face Landmarker',
            'note':'检测来自二维正面渲染并吸附到可见三角面顶点，请检查后采用；不是原生三维特征点预测。'}
