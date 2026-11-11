"""Independent landmark-guided, Laplacian-regularized nonrigid ICP prototype."""
import numpy as np
from scipy import sparse
from scipy.sparse.linalg import splu
from time import perf_counter
from surface import TriangleSurface, FlipGuard, vertex_normals
from multires import solve_stages

MAX_SOURCE = 100000
MAX_TARGET = 200000


def parse_obj(text, with_uv=False):
    vertices, faces, uvs, uv_faces = [], [], [], []
    for line in text.splitlines():
        parts = line.split('#', 1)[0].split()
        if not parts:
            continue
        if parts[0] == 'v':
            if len(parts) < 4:
                raise ValueError('OBJ 顶点必须包含 x、y、z。')
            vertices.append([float(x) for x in parts[1:4]])
        elif parts[0] == 'vt' and with_uv:
            if len(parts) < 3:
                raise ValueError('OBJ UV 必须包含 u、v。')
            uvs.append([float(x) for x in parts[1:3]])
        elif parts[0] == 'f':
            ids = [int(x.split('/')[0]) for x in parts[1:]]
            if len(ids) < 3 or 0 in ids:
                raise ValueError('OBJ 面索引无效。')
            ids = [i - 1 if i > 0 else len(vertices) + i for i in ids]
            if with_uv:
                uv_ids = []
                for token in parts[1:]:
                    fields = token.split('/')
                    if len(fields) < 2 or not fields[1]:
                        uv_ids.append(-1)
                    else:
                        index = int(fields[1])
                        resolved = index - 1 if index > 0 else len(uvs) + index
                        if index == 0 or resolved < 0:
                            raise ValueError('OBJ UV 索引无效。')
                        uv_ids.append(resolved)
            for j in range(1, len(ids) - 1):
                faces.append([ids[0], ids[j], ids[j + 1]])
                if with_uv:
                    uv_faces.append([uv_ids[0], uv_ids[j], uv_ids[j + 1]])
    v = np.asarray(vertices, dtype=float)
    f = np.asarray(faces, dtype=np.int64)
    if v.ndim != 2 or v.shape[1] != 3 or len(v) < 3 or not np.isfinite(v).all():
        raise ValueError('需要至少三个有限坐标的 OBJ 顶点。')
    if not len(f) or f.min() < 0 or f.max() >= len(v):
        raise ValueError('需要有效的多边形面；不支持只有点云的 OBJ。')
    if len(v) > MAX_TARGET or len(f) > 500000:
        raise ValueError('首版上限为 200,000 顶点、500,000 三角面。')
    if with_uv:
        uv = np.asarray(uvs, dtype=float).reshape(-1, 2)
        uf = np.asarray(uv_faces, dtype=np.int64)
        if not np.isfinite(uv).all() or (uf >= len(uv)).any():
            raise ValueError('OBJ UV 坐标或索引无效。')
        return v, f, uv, uf
    return v, f


def mesh_data(text):
    v, f, uv, uf = parse_obj(text, with_uv=True)
    return {'vertices': v.tolist(), 'faces': f.tolist(), 'uvs': uv.tolist(),
            'uvFaces': uf.tolist(), 'hasUV': bool(len(uv) and np.all(uf >= 0))}


def export_obj(text, vertices):
    """Retain vertex order, original polygons and UVs; drop stale normal references."""
    original, _ = parse_obj(text)
    v = np.asarray(vertices, dtype=float)
    if v.shape != original.shape or not np.isfinite(v).all():
        raise ValueError('导出顶点数量或坐标无效。')
    lines, index = [], 0
    for line in text.splitlines():
        p = line.strip().split()
        if p and p[0] == 'v':
            suffix = (' ' + ' '.join(p[4:])) if len(p) > 4 else ''
            lines.append('v ' + ' '.join(format(x, '.10g') for x in v[index]) + suffix)
            index += 1
        elif p and p[0] == 'vn':
            continue
        elif p and p[0] == 'f':
            tokens = line.split('#', 1)[0].split()[1:]
            lines.append('f ' + ' '.join('/'.join(t.split('/')[:2]).rstrip('/') for t in tokens))
        else:
            lines.append(line)
    return '\n'.join(lines) + '\n'


def similarity(source, target):
    a, b = source - source.mean(0), target - target.mean(0)
    if np.linalg.matrix_rank(a) < 2 or np.linalg.matrix_rank(b) < 2:
        raise ValueError('对应点不能重合或位于同一直线上，请分散选择。')
    u, s, vt = np.linalg.svd(a.T @ b)
    sign = np.ones(3)
    sign[-1] = np.sign(np.linalg.det(u @ vt))
    rotation = u @ np.diag(sign) @ vt
    scale = float(s @ sign / np.sum(a * a))
    if scale < 1e-9 or not np.isfinite(scale):
        raise ValueError('对应点产生了无效的尺度。')
    return rotation, scale, source.mean(0), target.mean(0)


def index_list(values, limit, label):
    if not isinstance(values, list) or any(type(i) is not int or i < 0 or i >= limit for i in values):
        raise ValueError(f'{label}索引无效。')
    return np.array(sorted(set(values)), dtype=np.int64)


def exclusion_masks(source_faces, target_faces, excluded_faces, pairs):
    from point_constraints import pair_support
    if not isinstance(excluded_faces, dict):
        raise ValueError('排除区域格式无效。')
    mode = excluded_faces.get('sourceMode', 'fixed')
    if mode not in ('fixed', 'follow'):
        raise ValueError('模板区域模式无效。')
    masks = {}
    for side, faces, column in [('source', source_faces, 0), ('target', target_faces, 1)]:
        selected = index_list(excluded_faces.get(side, []), len(faces), '排除面')
        vertices = np.unique(faces[selected]) if len(selected) else np.array([], dtype=np.int64)
        if len(pairs) and np.intersect1d(vertices, pair_support(pairs,column,faces)).size:
            raise ValueError('排除区域包含对应点，请先移动或删除冲突的点对。')
        if side == 'target' and len(selected) == len(faces):
            raise ValueError('不能排除全部目标面。')
        masks[side] = (selected, vertices)
    masks['fixedSource'] = masks['source'][1] if mode == 'fixed' else np.array([], dtype=np.int64)
    return masks


def wrap(source_text, target_text, pairs, iterations=20, smoothness=4.0, excluded_faces=None, normal_angle=60, solver_mode='single', brush_weights=None):
    from point_constraints import surface_pairs
    if (brush_weights is not None
            or isinstance(excluded_faces,dict) and excluded_faces.get('sourceMode')=='follow'
            or isinstance(pairs,list) and all(isinstance(p,list) and len(p)==2 for p in pairs) and surface_pairs(pairs)):
        from surface_wrap import wrap_surface
        return wrap_surface(source_text,target_text,pairs,iterations,smoothness,excluded_faces,normal_angle,solver_mode,brush_weights)
    started=perf_counter()
    source, faces = parse_obj(source_text)
    target, target_faces = parse_obj(target_text)
    if len(source) > MAX_SOURCE:
        raise ValueError('模板上限为 100,000 顶点；请先简化模板。')
    if solver_mode not in ('single','multistage'):
        raise ValueError('求解模式无效。')
    if solver_mode=='single' and len(source)>25000:
        raise ValueError('超过 25,000 顶点的模板请使用多阶段求解。')
    if not 3 <= len(pairs) <= 100:
        raise ValueError('请选取 3–100 对对应点，建议至少 6 对。')
    pair = np.asarray(pairs)
    if pair.shape != (len(pairs), 2) or not np.issubdtype(pair.dtype, np.integer):
        raise ValueError('对应点必须使用整数顶点索引。')
    left, right = pair[:, 0], pair[:, 1]
    if left.min() < 0 or left.max() >= len(source) or right.min() < 0 or right.max() >= len(target):
        raise ValueError('对应点超出模型范围。')
    if len(set(left)) != len(left) or len(set(right)) != len(right):
        raise ValueError('每个顶点只能用于一组对应点。')
    masks = exclusion_masks(faces, target_faces, excluded_faces if excluded_faces is not None else {}, pairs)
    excluded_source = masks['source'][1]
    allowed_target = np.delete(target_faces, masks['target'][0], axis=0)
    iterations, smoothness = int(iterations), float(smoothness)
    if not 5 <= iterations <= 50 or not np.isfinite(smoothness) or not 0.1 <= smoothness <= 30:
        raise ValueError('迭代次数或平滑参数超出范围。')
    if type(normal_angle) not in (int, float) or not np.isfinite(normal_angle) or not 10 <= normal_angle <= 89:
        raise ValueError('法线夹角必须为 10–89 度。')
    cosine = float(np.cos(np.deg2rad(normal_angle)))
    rotation, scale, origin, destination = similarity(source[left], target[right])
    aligned = (source - origin) @ rotation * scale + destination
    # Work in normalized coordinates so the regularizer is independent of model units.
    unit = float(np.linalg.norm(np.ptp(target, axis=0)))
    if unit < 1e-12:
        raise ValueError('目标模型尺寸为零。')
    center = target.mean(0)
    base, fixed = (aligned - center) / unit, (target - center) / unit
    surface = TriangleSurface(fixed, allowed_target)
    guard = FlipGuard(base, faces)
    n = len(source)
    edges = np.vstack([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]])
    edges = np.unique(np.sort(edges, axis=1), axis=0)
    edges = edges[edges[:, 0] != edges[:, 1]]
    adjacency = sparse.coo_matrix((np.ones(2 * len(edges)),
        (np.r_[edges[:, 0], edges[:, 1]], np.r_[edges[:, 1], edges[:, 0]])), shape=(n, n)).tocsr()
    degree = np.asarray(adjacency.sum(1)).ravel()
    laplacian = sparse.eye(n) - sparse.diags(1 / np.maximum(degree, 1)) @ adjacency
    regularizer = (laplacian.T @ laplacian).tocsc()
    constrained = np.r_[left, excluded_source]
    free = np.setdiff1d(np.arange(n), constrained)
    pins = np.vstack([fixed[right] - base[left], np.zeros((len(excluded_source), 3))])
    active = np.ones(n, dtype=bool)
    active[excluded_source] = False
    # Spread hard landmark corrections smoothly before ICP. Abruptly moving only
    # the landmark vertices can invert their incident faces before the first step.
    displacement = np.zeros_like(base)
    displacement[constrained] = pins
    if len(free):
        init_matrix = (regularizer + 1e-4 * sparse.eye(n)).tocsc()
        displacement[free] = splu(init_matrix[free][:, free].tocsc()).solve(-init_matrix[free][:, constrained] @ pins)
    if guard.safe_step(base, base + displacement) != 1:
        raise ValueError('对应点与固定区域约束会导致翻面或严重压扁，请重选对应点或缩小排除区域。')
    history = []
    _, initial_distances, nearest = surface.query(base)
    initial_normals = vertex_normals(base, faces)
    facing = np.sum(initial_normals * surface.face_normals[nearest], axis=1)
    if np.mean(facing[active] < -.1) > .6:
        raise ValueError('两侧表面法线方向大多相反，请先在建模软件中统一面朝向。')
    initial = float(np.mean(initial_distances[active]) * unit)
    limited_steps, smallest_step, stopped, stabilization_retries = 0, 1., False, 0
    hierarchy_started=perf_counter()
    stages=solve_stages(adjacency,free,base,left,active,iterations,solver_mode)
    hierarchy_seconds=perf_counter()-hierarchy_started
    stage_reports=[];global_step=0;correspondence_queries=0
    stage_distance=float(np.mean(surface.query((base+displacement)[active])[1])*unit)
    for stage in stages:
        stage_started=perf_counter();basis=stage['basis'];ids=stage['ids'];mass=stage['mass']
        anchor=displacement.copy();sample_basis=basis[ids].tocsr()
        projected_regularizer=(basis.T@regularizer@basis).tocsc()
        projected_identity=(basis.T@basis).tocsc()
        regularizer_anchor=basis.T@(regularizer@anchor)
        identity_anchor=basis.T@anchor
        before=stage_distance;completed=0;blocked=False
        for local_step in range(stage['budget']):
            current=base+displacement
            normals=vertex_normals(current,faces)
            closest,distance,_=surface.query(current[ids],normals[ids],cosine)
            correspondence_queries+=len(ids)
            eligible=np.isfinite(distance)
            if eligible.sum()<max(3,int(len(ids)*.05)):
                raise ValueError('法线匹配不足，请检查两侧面的朝向是否一致，或适当增大法线夹角。')
            cutoff=max(float(np.quantile(distance[eligible],.85))*2,.005)
            weight=np.zeros(len(ids))
            weight[eligible]=mass[eligible]*np.minimum(1.,cutoff/np.maximum(distance[eligible],1e-12))
            alpha=smoothness*10**(-2*(global_step+local_step)/max(iterations-1,1))
            data_matrix=(sample_basis.T@sparse.diags(weight)@sample_basis).tocsc()
            data_rhs=sample_basis.T@(weight[:,None]*(closest-base[ids]-anchor[ids]))
            for attempt in range(5):
                stiffness=alpha*4**attempt
                matrix=data_matrix+stiffness*projected_regularizer+1e-6*projected_identity
                rhs=data_rhs-stiffness*regularizer_anchor-1e-6*identity_anchor
                proposal=anchor.copy()
                if basis.shape[1]:
                    proposal+=basis@splu(matrix.tocsc()).solve(rhs)
                proposal[constrained]=pins
                if not np.isfinite(proposal).all():
                    raise ValueError('求解失败；请检查模型和对应点。')
                step_scale=guard.safe_step(current,base+proposal)
                if step_scale>=.125 or attempt==4:
                    break
                stabilization_retries+=1
            if step_scale<1 or attempt:
                limited_steps+=1;smallest_step=min(smallest_step,step_scale)
            if step_scale<1e-6:
                blocked=True
                # A restricted coarse space may be blocked while fine variables
                # can still move safely. Only the final stage stops the solve.
                stopped=stage is stages[-1]
                break
            displacement+=step_scale*(proposal-displacement)
            displacement[constrained]=pins;completed+=1
            sample_distance=surface.query((base+displacement)[ids])[1]
            history.append(float(np.average(sample_distance,weights=mass)*unit))
        _,stage_distances,stage_nearest=surface.query(base+displacement)
        stage_distance=float(np.mean(stage_distances[active])*unit)
        stage_reports.append({'name':stage['name'],'controlVertices':basis.shape[1],
            'sampleVertices':len(ids),'iterations':completed,'requestedIterations':stage['budget'],
            'initialMeanDistance':before,'finalMeanDistance':stage_distance,
            'blockedByFlipGuard':blocked,'seconds':perf_counter()-stage_started})
        global_step+=stage['budget']
    result = (base + displacement) * unit + center
    final_normals = vertex_normals(base + displacement, faces)
    distances,nearest=stage_distances,stage_nearest
    final_distance = float(np.mean(distances[active]) * unit)
    filtered_nearest = np.sum(final_normals * surface.face_normals[nearest], axis=1) < cosine
    _, final_normal_distance, _ = surface.query(base + displacement, final_normals, cosine)
    return {'vertices': result.tolist(), 'stats': {
        'initialMeanDistance': initial, 'finalMeanDistance': final_distance,
        'landmarkMaxError': float(np.max(np.linalg.norm(result[left] - target[right], axis=1))),
        'iterations': len(history), 'requestedIterations': iterations, 'history': history,
        'solverMode':solver_mode,'stages':stage_reports,'stageCount':len(stage_reports),
        'historyScope':'stage-sample' if len(stages)>1 else 'full-active-mesh',
        'correspondenceQueries':correspondence_queries,'hierarchySeconds':hierarchy_seconds,
        'totalSeconds':perf_counter()-started,
        'vertices': n, 'triangles': len(faces), 'sampledSurface': False,
        'distanceMethod': 'exact-triangle-bvh', 'normalAngle': normal_angle,
        'normalRejectedVertices': int(np.sum(active & ~np.isfinite(final_normal_distance))),
        'normalFilteredNearestVertices': int(np.sum(active & filtered_nearest)),
        'flipLimitedSteps': limited_steps, 'minimumStepScale': smallest_step,
        'stabilizationRetries': stabilization_retries,
        'stoppedByFlipGuard': stopped, 'minimumProjectedAreaRatio': guard.minimum_ratio(base + displacement),
        'ignoredDegenerateTargetFaces': surface.ignored_degenerate,
        'excludedSourceVertices': len(excluded_source), 'excludedTargetFaces': len(masks['target'][0])}}
