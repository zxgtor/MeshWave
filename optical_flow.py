"""Texture-guided refinement with visible-surface optical flow and guarded mesh updates."""
from time import perf_counter
import numpy as np
from scipy import sparse
from scipy.sparse.linalg import splu
from brush_support import prepare_brush
from flow_settings import flow_settings
from surface import TriangleSurface, FlipGuard, vertex_normals, face_vectors
from texture import read_texture, prepare_image, sample_image
from wrap_core import parse_obj, exclusion_masks


def cv_module():
    try:import cv2
    except ImportError as exc:raise ValueError('缺少 OpenCV，请安装 requirements.txt 后重启服务。') from exc
    return cv2


def cameras(vertices,target,world,views):
    matrix=np.asarray(world,dtype=float)
    if matrix.shape!=(16,) or not np.isfinite(matrix).all():raise ValueError('纹理细化相机无效，请重置左侧视图。')
    matrix=matrix.reshape(4,4,order='F');rotation=matrix[:3,:3]
    if not np.allclose(rotation.T@rotation,np.eye(3),atol=1e-5) or np.linalg.det(rotation)<.99:raise ValueError('纹理细化相机方向无效。')
    right,up,front=rotation.T;combined=np.vstack([vertices,target]);result=[]
    for angle in ([0] if views==1 else [0,-25,25]):
        t=np.deg2rad(angle);r=right*np.cos(t)-front*np.sin(t);f=front*np.cos(t)+right*np.sin(t)
        basis=np.array([r,up,f]);points=combined@basis.T;lo,hi=points[:,:2].min(0),points[:,:2].max(0)
        result.append({'basis':basis,'center':(lo+hi)/2,'extent':max(float(np.max(hi-lo))*1.1,1e-8)})
    return result


def screen_points(vertices,camera,resolution):
    p=vertices@camera['basis'].T
    xy=(p[:,:2]-camera['center'])/camera['extent']*resolution
    return xy*[1,-1]+(resolution-1)/2,p[:,2]


def barycentric(point,tri):
    a,b,c=tri;ab=b-a;ac=c-a;d=point-a;det=ab[0]*ac[1]-ab[1]*ac[0]
    if abs(det)<1e-12:return None
    u=(d[...,0]*ac[1]-d[...,1]*ac[0])/det;v=(ab[0]*d[...,1]-ab[1]*d[...,0])/det
    return np.stack([1-u-v,u,v],axis=-1)


def render_mesh(vertices,faces,uv,uf,image,camera,resolution,excluded=()):
    cv=cv_module();xy,z=screen_points(vertices,camera,resolution);vectors=face_vectors(vertices,faces)
    facing=vectors@camera['basis'][2]>np.linalg.norm(vectors,axis=1)*.05
    face_map=np.full((resolution,resolution),-1,np.int32);depth=np.full((resolution,resolution),-np.inf);uv_map=np.zeros((resolution,resolution,2))
    work=0
    for face_id in range(len(faces)):
        ids=faces[face_id];tri=xy[ids];lo=np.maximum(np.ceil(tri.min(0)).astype(int),0);hi=np.minimum(np.floor(tri.max(0)).astype(int),resolution-1)
        if np.any(hi<lo):continue
        work+=int(np.prod(hi-lo+1))
        if work>80000000:raise ValueError('纹理视图栅格化开销过高，请降低分辨率或先清理重叠网格。')
        x,y=np.meshgrid(np.arange(lo[0],hi[0]+1),np.arange(lo[1],hi[1]+1));b=barycentric(np.stack([x,y],axis=-1),tri)
        if b is None:continue
        inside=np.min(b,axis=-1)>=-1e-8;x,y,b=x[inside],y[inside],b[inside]
        d=b@z[ids];keep=d>depth[y,x];x,y,b,d=x[keep],y[keep],b[keep],d[keep]
        face_map[y,x]=face_id;depth[y,x]=d;uv_map[y,x]=b@uv[uf[face_id]]
    rgba=np.zeros((resolution,resolution,4),np.uint8);visible=face_map>=0
    rgba[visible]=sample_image(image,uv_map[visible])
    valid=visible&facing[np.maximum(face_map,0)]&(rgba[:,:,3]>=250)&~np.isin(face_map,np.asarray(excluded,dtype=int))
    # Excluded and back-facing faces still occlude deeper surfaces.
    for axis in [0,1]:
        near=np.roll(depth,1,axis);jump=visible&np.roll(visible,1,axis)&(np.abs(np.where(visible,depth,0)-np.where(np.roll(visible,1,axis),near,0))>.01)
        valid&=~jump&~np.roll(jump,-1,axis)
    valid=cv.erode(valid.astype(np.uint8),np.ones((5,5),np.uint8)).astype(bool)
    gray=cv.cvtColor(rgba[:,:,:3],cv.COLOR_RGB2GRAY).astype(np.float32)
    local=cv.boxFilter(gray**2,-1,(7,7))-cv.boxFilter(gray,-1,(7,7))**2
    if valid.sum()>=16:
        mean,std=float(gray[valid].mean()),float(gray[valid].std());gray=np.clip((gray-mean)*40/max(std,3)+128,0,255)
    gray=np.where(visible,gray,0).astype(np.uint8)
    return {'gray':gray,'valid':valid,'face':face_map,'depth':depth,'xy':xy,'z':z,'textured':local>16}


def bilinear(array,points):
    h,w=array.shape[:2];p=np.clip(points,[0,0],[w-1.000001,h-1.000001]);ix,iy=np.floor(p).astype(int).T;tx,ty=(p-np.floor(p)).T
    if array.ndim==3:tx,ty=tx[:,None],ty[:,None]
    return array[iy,ix]*(1-tx)*(1-ty)+array[iy,ix+1]*tx*(1-ty)+array[iy+1,ix]*(1-tx)*ty+array[iy+1,ix+1]*tx*ty


def visible_correspondences(current,faces,target,target_faces,source_render,target_render,camera,max_distance,cosine):
    cv=cv_module();a,b=source_render,target_render;resolution=len(a['gray'])
    forward=cv.calcOpticalFlowFarneback(a['gray'],b['gray'],None,.5,4,21,5,7,1.5,0)
    backward=cv.calcOpticalFlowFarneback(b['gray'],a['gray'],None,.5,4,21,5,7,1.5,0)
    xy,z=screen_points(current,camera,resolution);rounded=np.rint(xy).astype(int);inside=(rounded>=0).all(1)&(rounded<resolution).all(1)
    ids=np.flatnonzero(inside);x,y=rounded[ids].T;source_faces=a['face'][y,x]
    eligible=a['valid'][y,x]&a['textured'][y,x]&(source_faces>=0)
    eligible&=np.any(faces[np.maximum(source_faces,0)]==ids[:,None],axis=1)
    eligible&=np.abs(a['depth'][y,x]-z[ids])<.005
    ids=ids[eligible]
    if not len(ids):return ids,np.empty((0,3)),np.empty(0)
    motion=bilinear(forward,xy[ids]);q=xy[ids]+motion;in_bounds=(q>=2).all(1)&(q<resolution-3).all(1)
    back=bilinear(backward,q);fb=np.linalg.norm(motion+back,axis=1);error=np.abs(bilinear(b['gray'].astype(float),q)-bilinear(a['gray'].astype(float),xy[ids]))
    qi=np.clip(np.rint(q).astype(int),0,resolution-1);valid=in_bounds&b['valid'][qi[:,1],qi[:,0]]&b['textured'][qi[:,1],qi[:,0]]&(fb<=1.25)&(error<25)
    normal=vertex_normals(current,faces);target_normal=vertex_normals(target,target_faces)
    matched=[];positions=[];weights=[]
    for index in np.flatnonzero(valid):
        vertex=ids[index];point=q[index];ix,iy=np.floor(point).astype(int);candidate_ids=set(b['face'][iy:iy+2,ix:ix+2].ravel())
        best=None;best_z=-np.inf
        for face_id in candidate_ids:
            if face_id<0:continue
            tri=target_faces[face_id];bc=barycentric(point,b['xy'][tri])
            if bc is None or np.min(bc)<-1e-6:continue
            n=bc@target_normal[tri];size=np.linalg.norm(n)
            if size<1e-12 or normal[vertex]@n/size<cosine:continue
            position=bc@target[tri];distance=np.linalg.norm(position-current[vertex]);depth=float(bc@b['z'][tri])
            if distance<=max_distance and depth>best_z:best=position;best_z=depth
        if best is not None:
            matched.append(vertex);positions.append(best);weights.append(max(.05,(1-fb[index]/1.25)*(1-error[index]/25)))
    return np.asarray(matched,dtype=int),np.asarray(positions).reshape(-1,3),np.asarray(weights)


def photo_score(renders,targets,masks):
    values=[]
    for a,b,mask in zip(renders,targets,masks):
        if mask.sum()<32:continue
        error=np.abs(a['gray'].astype(float)-b['gray']);error[~a['valid']]=255
        values.extend(np.minimum(error[mask],80).tolist())
    return float(np.mean(values)) if values else float('inf')


def refine_texture(body):
    started=perf_counter();settings=flow_settings(body.get('settings',{}));cv_module()
    source,faces,uv,uf=parse_obj(body['source'],True);target,tf,tuv,tuf=parse_obj(body['target'],True)
    if not len(uv) or np.any(uf<0) or not len(tuv) or np.any(tuf<0):raise ValueError('纹理细化需要两侧都有完整 OBJ UV。')
    reference=prepare_brush(body);unit=reference['unit'];center=target.mean(0)
    current=(np.asarray(body['vertices'],float)-center)/unit;initial=current.copy();fixed=(target-center)/unit
    original=(np.asarray(reference['reference'])-center)/unit;guard=FlipGuard(original,faces)
    weights=body.get('brushWeights')
    if weights is None:weights=np.ones(len(source))
    elif not isinstance(weights,list) or len(weights)!=len(source) or any(type(v) not in (int,float) or not np.isfinite(v) or not 0<=v<=1 for v in weights):raise ValueError('纹理细化软权重无效。')
    weights=np.asarray(weights,float);locked=np.unique(np.r_[reference['locked'],np.flatnonzero(weights==0)]).astype(int);locked_set=set(locked.tolist());free=np.setdiff1d(np.arange(len(source)),locked)
    if not len(free):raise ValueError('所有模板顶点均被锁定，无法纹理细化。')
    masks=exclusion_masks(faces,tf,body.get('excludedFaces',{}),body['pairs'])
    source_image=prepare_image(read_texture(body['sourceTexture']));target_image=prepare_image(read_texture(body['targetTexture']))
    camera_list=cameras(current,fixed,body.get('cameraWorld'),settings['views']);angle=body.get('normalAngle',60)
    if type(angle) not in (int,float) or not np.isfinite(angle) or not 10<=angle<=89:raise ValueError('法线夹角必须为 10–89 度。')
    cosine=np.cos(np.deg2rad(angle))
    surface=TriangleSurface(fixed,np.delete(tf,masks['target'][0],axis=0))
    edges=np.unique(np.sort(np.vstack([faces[:,[0,1]],faces[:,[1,2]],faces[:,[2,0]]]),axis=1),axis=0)
    adjacency=sparse.coo_matrix((np.ones(len(edges)*2),(np.r_[edges[:,0],edges[:,1]],np.r_[edges[:,1],edges[:,0]])),shape=(len(source),len(source))).tocsr()
    degree=np.asarray(adjacency.sum(1)).ravel();laplacian=sparse.eye(len(source))-sparse.diags(1/np.maximum(degree,1))@adjacency
    regularizer=(laplacian.T@laplacian).tocsc();max_distance=settings['distancePercent']/100
    def render_source(v,res):return [render_mesh(v,faces,uv,uf,source_image,c,res,masks['source'][0]) for c in camera_list]
    def render_target(res):return [render_mesh(fixed,tf,tuv,tuf,target_image,c,res,masks['target'][0]) for c in camera_list]
    final_res=settings['resolution'];final_target=render_target(final_res);initial_render=render_source(initial,final_res)
    reference_masks=[a['valid']&b['valid']&(a['textured']|b['textured']) for a,b in zip(initial_render,final_target)]
    before_photo=photo_score(initial_render,final_target,reference_masks)
    if not np.isfinite(before_photo):raise ValueError('共同可见区域缺少可用纹理，请检查朝向、UV、透明区和纹理细节。')
    before_geometry=float(surface.query(initial[free])[1].mean()*unit)
    history=[];limited=0;all_matched=set();accepted_total=0
    for iteration in range(settings['iterations']):
        res=256 if iteration==0 and final_res>256 and settings['iterations']>1 else final_res
        target_render=final_target if res==final_res else render_target(res);renders=render_source(current,res)
        positions=np.zeros_like(current);confidence=np.zeros(len(current));observations=[[] for _ in current];used_count=0
        for a,b,c in zip(renders,target_render,camera_list):
            ids,points,w=visible_correspondences(current,faces,fixed,tf,a,b,c,max_distance,cosine)
            for i,p,weight in zip(ids,points,w):observations[i].append((p,weight))
        for i,items in enumerate(observations):
            if not items or i in locked_set:continue
            points=np.array([p for p,_ in items]);w=np.array([w for _,w in items]);median=np.median(points,axis=0);valid=np.linalg.norm(points-median,axis=1)<=max_distance*.5
            if valid.any():positions[i]=np.average(points[valid],axis=0,weights=w[valid]);confidence[i]=float(w[valid].mean())*weights[i];used_count+=int(valid.sum())
        matched=np.flatnonzero(confidence>0)
        if len(matched)<max(3,int(len(free)*.005)):
            if not history:raise ValueError('可靠光流对应不足，未修改结果；请检查是否同一人物、贴图是否相似以及左侧朝向。')
            break
        matrix=(sparse.diags(confidence+.05)+.5*regularizer).tocsc();rhs=confidence[:,None]*(positions-current)
        delta=np.zeros_like(current);delta[free]=splu(matrix[free][:,free].tocsc()).solve(rhs[free])
        size=np.linalg.norm(delta,axis=1);delta*=np.minimum(1,max_distance/np.maximum(size,1e-30))[:,None]
        proposal=current+delta*(settings['strength']/100)*weights[:,None]
        moving=free[np.linalg.norm(proposal[free]-current[free],axis=1)>1e-10]
        if len(moving):
            q,d,_=surface.query(proposal[moving],vertex_normals(current,faces)[moving],cosine)
            valid=np.isfinite(d)&(np.linalg.norm(q-current[moving],axis=1)<=max_distance)
            proposal[moving[valid]]=q[valid];proposal[moving[~valid]]=current[moving[~valid]]
        proposal[locked]=current[locked];step=guard.safe_step(current,proposal)
        if step<1:limited+=1
        if step<1e-6:break
        stage_mask=[a['valid']&b['valid']&(a['textured']|b['textured']) for a,b in zip(renders,target_render)];old_score=photo_score(renders,target_render,stage_mask);accepted=False
        for damping in [1,.5]:
            candidate=current+(proposal-current)*step*damping;trial=render_source(candidate,res);score=photo_score(trial,target_render,stage_mask)
            if score<old_score-1e-4:
                current=candidate;all_matched.update(matched.tolist());accepted_total+=used_count
                history.append({'resolution':res,'matches':len(matched),'before':old_score,'after':score,'step':step*damping});accepted=True;break
        if not accepted:break
    after_photo=photo_score(render_source(current,final_res),final_target,reference_masks)
    if not history or after_photo>=before_photo-1e-4:raise ValueError('没有找到可验证的纹理误差改善，未修改原结果。可尝试调整视角、降低强度或重新检查贴图。')
    result=current*unit+center;result[locked]=np.asarray(body['vertices'])[locked]
    return {'vertices':result.tolist(),'stats':{'beforePhotoError':before_photo,'afterPhotoError':after_photo,'matchedVertices':len(all_matched),'correspondences':accepted_total,'views':len(camera_list),'iterations':len(history),'history':history,'flipLimitedSteps':limited,'minProjectedAreaRatio':guard.minimum_ratio(current),'beforeMeanDistance':before_geometry,'afterMeanDistance':float(surface.query(current[free])[1].mean()*unit),'seconds':perf_counter()-started}}
