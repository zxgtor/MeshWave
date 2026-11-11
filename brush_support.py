"""Prepare locked vertices and the original aligned orientation reference."""
import numpy as np
from surface import FlipGuard
from wrap_core import parse_obj, similarity, exclusion_masks, MAX_SOURCE


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
    pairs=body['pairs']
    if not isinstance(pairs,list) or not 3<=len(pairs)<=100 or any(not isinstance(p,list) or len(p)!=2 or any(type(i) is not int for i in p) for p in pairs):
        raise ValueError('笔刷需要有效的对应点。')
    p=np.asarray(pairs,dtype=int);left,right=p[:,0],p[:,1]
    if left.min()<0 or left.max()>=len(source) or right.min()<0 or right.max()>=len(target) or len(np.unique(left))!=len(left) or len(np.unique(right))!=len(right):
        raise ValueError('对应点索引无效或重复。')
    vertices=np.asarray(body['vertices'],dtype=float)
    if vertices.shape!=source.shape or not np.isfinite(vertices).all():
        raise ValueError('贴合结果顶点无效。')
    masks=exclusion_masks(faces,target_faces,body.get('excludedFaces',{}),pairs)
    r,k,a,b=similarity(source[left],target[right]);reference=(source-a)@r*k+b
    unit=float(np.linalg.norm(np.ptp(target,axis=0)))
    if not np.isfinite(unit) or unit<1e-12:
        raise ValueError('模型尺寸无效。')
    center=target.mean(0)
    guard=FlipGuard((reference-center)/unit,faces)
    if guard.minimum_ratio((vertices-center)/unit)<.01-1e-9:
        raise ValueError('当前结果未通过防翻面检查，请重新贴合后再使用笔刷。')
    locked=np.r_[left,masks['source'][1]]
    expected=np.vstack([target[right],reference[masks['source'][1]]])
    if np.any(np.linalg.norm(vertices[locked]-expected,axis=1)>unit*1e-7):
        raise ValueError('当前结果的对应点或固定区已偏离约束，请重新贴合。')
    return {'reference':reference.tolist(),'locked':locked.tolist(),'unit':unit}
