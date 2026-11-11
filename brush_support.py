"""Prepare locked vertices and the original aligned orientation reference."""
import numpy as np
from surface import FlipGuard
from wrap_core import parse_obj, similarity, exclusion_masks, MAX_SOURCE
from point_constraints import validate_pairs,positions,pair_support


def brush_settings(value):
    if not isinstance(value,dict):
        raise ValueError('笔刷参数格式无效。')
    radius,strength=value.get('radiusPercent',5),value.get('strength',30)
    if type(radius) not in (int,float) or not np.isfinite(radius) or not .2<=radius<=20 or type(strength) not in (int,float) or not np.isfinite(strength) or not 1<=strength<=100:
        raise ValueError('笔刷半径为 0.2%–20%，强度为 1–100。')
    return {'radiusPercent':radius,'strength':strength}


def prepare_brush(body):
    source,faces=parse_obj(body['source']);target,target_faces=parse_obj(body['target'])
    if len(source)>MAX_SOURCE:
        raise ValueError('模板超过 100,000 顶点。')
    pairs=validate_pairs(body['pairs'],{'source':(source,faces),'target':(target,target_faces)},3)
    left=pair_support(pairs,0,faces)
    source_points=positions(source,faces,[p[0] for p in pairs]);target_points=positions(target,target_faces,[p[1] for p in pairs])
    vertices=np.asarray(body['vertices'],dtype=float)
    if vertices.shape!=source.shape or not np.isfinite(vertices).all():
        raise ValueError('贴合结果顶点无效。')
    masks=exclusion_masks(faces,target_faces,body.get('excludedFaces',{}),pairs)
    r,k,a,b=similarity(source_points,target_points);reference=(source-a)@r*k+b
    unit=float(np.linalg.norm(np.ptp(target,axis=0)))
    if not np.isfinite(unit) or unit<1e-12:
        raise ValueError('模型尺寸无效。')
    center=target.mean(0)
    guard=FlipGuard((reference-center)/unit,faces)
    if guard.minimum_ratio((vertices-center)/unit)<.01-1e-9:
        raise ValueError('当前结果未通过防翻面检查，请重新贴合后再使用笔刷。')
    locked=np.r_[left,masks['source'][1]]
    error=positions(vertices,faces,[p[0] for p in pairs])-target_points
    fixed_error=vertices[masks['source'][1]]-reference[masks['source'][1]]
    if np.any(np.linalg.norm(error,axis=1)>unit*1e-7) or np.any(np.linalg.norm(fixed_error,axis=1)>unit*1e-7):
        raise ValueError('当前结果的对应点或固定区已偏离约束，请重新贴合。')
    return {'reference':reference.tolist(),'locked':locked.tolist(),'unit':unit}
