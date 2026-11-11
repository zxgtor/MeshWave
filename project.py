"""Validate portable project files before replacing any browser state."""
import numpy as np
from wrap_core import mesh_data, MAX_SOURCE, index_list, exclusion_masks
from texture import normalize_texture
from brush_support import brush_settings
from curves import validate_curves
from flow_settings import flow_settings
from point_constraints import validate_pairs,handle_shape,point_key,support


def validate_project(project):
    if not isinstance(project, dict) or project.get('format') != 'facewrap-lite' or type(project.get('version')) is not int or project['version'] not in (1,2):
        raise ValueError('不是支持的 Mesh Wave 工程文件（版本 1 或 2）。')
    models = project.get('models')
    if not isinstance(models, dict):
        raise ValueError('工程缺少模型信息。')
    parsed, meshes = {}, {}
    for side in ['source', 'target']:
        model = models.get(side)
        if model is None:
            parsed[side] = None
            meshes[side] = (np.empty((0, 3)), np.empty((0, 3), dtype=int))
            continue
        if not isinstance(model, dict) or not isinstance(model.get('text'), str) or not isinstance(model.get('name'), str):
            raise ValueError('工程模型内容或名称无效。')
        if len(model['text'].encode('utf-8')) > 18 * 1024 * 1024 or len(model['name']) > 500:
            raise ValueError('工程模型超过大小限制。')
        data = mesh_data(model['text'])
        v, f = np.asarray(data['vertices']), np.asarray(data['faces'])
        if side == 'source' and len(v) > MAX_SOURCE:
            raise ValueError('模板超过 100,000 顶点。')
        parsed[side] = {'text': model['text'], 'name': model['name'], **data}
        if model.get('texture') is not None:
            if not data['hasUV']:
                raise ValueError('带贴图的模型需要完整 UV。')
            parsed[side]['texture'] = normalize_texture(model['texture'])
        meshes[side] = (v, f)
    if not any(parsed.values()):
        raise ValueError('工程至少需要一个模型。')
    brush_weights=project.get('brushWeights')
    if brush_weights is not None:
        if not isinstance(brush_weights,list) or len(brush_weights)!=len(meshes['source'][0]) or not parsed['source'] or any(type(x) not in (int,float) or not np.isfinite(x) or not 0<=x<=1 for x in brush_weights):
            raise ValueError('笔刷权重必须与模板顶点一一对应，范围为 0–1。')
    pairs = project.get('pairs', [])
    if not isinstance(pairs, list) or len(pairs) > 100 or any(not isinstance(p, list) or len(p) != 2 for p in pairs):
        raise ValueError('工程点对格式无效。')
    pairs=validate_pairs(pairs,meshes)
    excluded = project.get('excludedFaces', {})
    if not isinstance(excluded, dict):
        raise ValueError('工程排除区域格式无效。')
    normalized_excluded = {}
    for side in ['source', 'target']:
        normalized_excluded[side] = index_list(excluded.get(side, []), len(meshes[side][1]), '排除面').tolist()
    # A missing target is valid for an unfinished project.
    if parsed['target']:
        exclusion_masks(meshes['source'][1], meshes['target'][1], normalized_excluded, pairs)
    curves=validate_curves(project.get('curves',[]),meshes,normalized_excluded)
    curve_pairs=project.get('curvePairs',[])
    curve_pairs=validate_pairs(curve_pairs,meshes)
    key=lambda p:(point_key(p[0],meshes['source'][1]),point_key(p[1],meshes['target'][1]))
    pair_lookup={key(p):p for p in pairs}
    if any(key(p) not in pair_lookup for p in curve_pairs):
        raise ValueError('曲线生成点记录与现有点对不一致。')
    curve_pairs=[pair_lookup[key(p)] for p in curve_pairs]
    pending = project.get('pending')
    if pending is not None:
        pending=handle_shape(pending,len(meshes['source'][0]),meshes['source'][1])
        masked = np.unique(meshes['source'][1][normalized_excluded['source']])
        if any(point_key(pending,meshes['source'][1])==point_key(p[0],meshes['source'][1]) for p in pairs) or np.intersect1d(support(pending,meshes['source'][1]),masked).size:
            raise ValueError('待配对点与现有点对或排除区域冲突。')
    settings = project.get('settings', {})
    if not isinstance(settings, dict):
        raise ValueError('工程参数格式无效。')
    iterations, smoothness = settings.get('iterations', 20), settings.get('smoothness', 4)
    if type(iterations) is not int or not 5 <= iterations <= 50 or type(smoothness) not in (int, float) or not np.isfinite(smoothness) or not .1 <= smoothness <= 30:
        raise ValueError('工程贴合参数超出范围。')
    normal_angle = settings.get('normalAngle', 60)
    if type(normal_angle) not in (int, float) or not np.isfinite(normal_angle) or not 10 <= normal_angle <= 89:
        raise ValueError('工程法线夹角必须为 10–89 度。')
    solver_mode=settings.get('solverMode','single')
    if solver_mode not in ('single','multistage'):
        raise ValueError('工程求解模式无效。')
    result = project.get('result')
    if result is not None:
        if not all(parsed.values()) or len(pairs) < 3 or pending is not None or not isinstance(result, dict):
            raise ValueError('工程贴合结果缺少模型或完整点对。')
        vertices = np.asarray(result.get('vertices'), dtype=float)
        if vertices.shape != meshes['source'][0].shape or not np.isfinite(vertices).all():
            raise ValueError('工程结果顶点数量或坐标无效。')
        result = {'vertices': vertices.tolist()}
        manual_edits=project['result'].get('manualEdits',False)
        if type(manual_edits) is not bool:
            raise ValueError('手动修正标记无效。')
        if manual_edits:
            result['manualEdits']=True
        refined=project['result'].get('textureRefined',False)
        if type(refined) is not bool:raise ValueError('纹理细化结果标记无效。')
        if refined:result['textureRefined']=True
        if project['result'].get('texture') is not None:
            if not parsed['source']['hasUV']:
                raise ValueError('带烘焙贴图的结果需要模板 UV。')
            result['texture'] = normalize_texture(project['result']['texture'], baked=True)
    bake = settings.get('bake', {})
    if not isinstance(bake, dict):
        raise ValueError('工程烘焙参数无效。')
    resolution, padding, ratio = bake.get('resolution', 1024), bake.get('padding', 8), bake.get('distanceRatio', .02)
    if type(resolution) is not int or resolution not in (256, 512, 1024, 2048) or type(padding) is not int or not 0 <= padding <= 16 or type(ratio) not in (float, int) or not np.isfinite(ratio) or not .001 <= ratio <= .2:
        raise ValueError('工程烘焙参数超出范围。')
    return {'models': parsed, 'pairs': pairs, 'pending': pending, 'excludedFaces': normalized_excluded,'brushWeights':brush_weights,'curves':curves,'curvePairs':curve_pairs,
            'settings': {'iterations': iterations, 'smoothness': smoothness, 'normalAngle': normal_angle,'solverMode':solver_mode,
                         'bake': {'resolution': resolution, 'padding': padding, 'distanceRatio': ratio},
                         'brush':brush_settings(settings.get('brush',{})),'flow':flow_settings(settings.get('flow',{}))}, 'result': result}
