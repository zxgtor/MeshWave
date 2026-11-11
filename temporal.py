"""Pose-compensated sequence smoothing with optional local speed adaptation."""
import numpy as np
from brush_support import prepare_brush
from surface import TriangleSurface, FlipGuard, vertex_normals
from wrap_core import parse_obj, similarity, exclusion_masks
from point_constraints import positions


def temporal_settings(value):
    if not isinstance(value,dict):raise ValueError('时序平滑参数无效。')
    strength,distance=value.get('strength',35),value.get('distancePercent',1)
    if type(strength) not in (int,float) or not np.isfinite(strength) or not 1<=strength<=90 or type(distance) not in (int,float) or not np.isfinite(distance) or not .1<=distance<=5:
        raise ValueError('时序平滑强度为 1–90，最大修正距离为目标尺寸的 0.1%–5%。')
    mode=value.get('mode','causal')
    if mode not in ('causal','bidirectional'):raise ValueError('时序模式必须为单向或双向。')
    adaptive=value.get('adaptive',False);speed=value.get('speedPercent',1)
    if type(adaptive) is not bool or type(speed) not in (int,float) or not np.isfinite(speed) or not .1<=speed<=10:raise ValueError('自适应开关必须为布尔值，速度阈值为目标尺寸的 0.1%–10% / 帧。')
    detect=value.get('detectAnomalies',False);threshold=value.get('anomalyPercent',2)
    if type(detect) is not bool or type(threshold) not in (int,float) or not np.isfinite(threshold) or not .1<=threshold<=20:raise ValueError('异常检测开关必须为布尔值，异常阈值为 0.1%–20%。')
    repair=value.get('repairAnomalies',False);gap=value.get('repairMaxGap',3)
    if type(repair) is not bool or type(gap) is not int or not 1<=gap<=5 or (repair and not detect):raise ValueError('异常修复需要开启检测，连续修复上限为 1–5 帧。')
    return {'strength':strength,'distancePercent':distance,'mode':mode,'adaptive':adaptive,'speedPercent':speed,'detectAnomalies':detect,'anomalyPercent':threshold,'repairAnomalies':repair,'repairMaxGap':gap}


def coherent_motion(delta,faces):
    """One-ring vector average reduces isolated vertex noise in the speed estimate."""
    edges=np.unique(np.sort(np.vstack([faces[:,[0,1]],faces[:,[1,2]],faces[:,[2,0]]]),axis=1),axis=0)
    total=delta*2;degree=np.full(len(delta),2.)
    np.add.at(total,edges[:,0],delta[edges[:,1]]);np.add.at(total,edges[:,1],delta[edges[:,0]])
    np.add.at(degree,edges[:,0],1);np.add.at(degree,edges[:,1],1)
    return total/degree[:,None]


def smooth_frame(body,previous=None,following=None):
    settings=temporal_settings(body.get('settings',{}));reference=prepare_brush(body)
    source,faces=parse_obj(body['source']);target,tf=parse_obj(body['target'])
    current=np.asarray(body['vertices'],float);unit=reference['unit'];center=target.mean(0)
    weights=body.get('brushWeights')
    if weights is None:weights=np.ones(len(source))
    elif not isinstance(weights,list) or len(weights)!=len(source) or any(type(v) not in (int,float) or not np.isfinite(v) or not 0<=v<=1 for v in weights):raise ValueError('时序平滑软权重无效。')
    weights=np.asarray(weights,float);locked=np.unique(np.r_[reference['locked'],np.flatnonzero(weights==0)]).astype(int)
    bidirectional=settings['mode']=='bidirectional';seed=previous is None or (bidirectional and following is None)
    stats={'seed':seed,'mode':settings['mode'],'adaptive':settings['adaptive'],'effectiveStrengthMean':0.,'effectiveStrengthMin':0.,'effectiveStrengthMax':0.,'speedMeanPercent':0.,'speedMaxPercent':0.,'fastVertices':0,'changedVertices':0,'matchedVertices':0,'meanCorrection':0.,'maxCorrection':0.,'beforeFrameDistance':0.,'afterFrameDistance':0.,'step':1.}
    if seed:return {'vertices':current.tolist(),'stats':stats}
    previous=np.asarray(previous,float)
    if previous.shape!=current.shape or not np.isfinite(previous).all():raise ValueError('上一帧模板顶点无效。')
    # Align the previous output to this frame; global pose/scale should not trail behind.
    anchors=[p[0] for p in body['pairs']];sample=lambda v:positions(v,faces,anchors)
    rotation,scale,a,b=similarity(sample(previous),sample(current));aligned=(previous-a)@rotation*scale+b
    motion_aligned=aligned
    if settings['adaptive'] and not bidirectional and body.get('motionPrevious') is not None:
        motion_previous=np.asarray(body['motionPrevious'],float)
        if motion_previous.shape!=current.shape or not np.isfinite(motion_previous).all():raise ValueError('上一帧速度参考无效。')
        rotation,scale,a,b=similarity(sample(motion_previous),sample(current));motion_aligned=(motion_previous-a)@rotation*scale+b
    motions=[motion_aligned-current]
    if bidirectional:
        following=np.asarray(following,float)
        if following.shape!=current.shape or not np.isfinite(following).all():raise ValueError('下一帧模板顶点无效。')
        rotation,scale,a,b=similarity(sample(following),sample(current));next_aligned=(following-a)@rotation*scale+b;motions.append(next_aligned-current);aligned=(aligned+next_aligned)/2
    strength=np.full(len(current),settings['strength'],dtype=float)
    if settings['adaptive']:
        speed=np.maximum.reduce([np.linalg.norm(coherent_motion(motion,faces),axis=1) for motion in motions])/unit*100
        ratio=np.clip(speed/settings['speedPercent'],0,1);strength*=1-ratio*ratio*(3-2*ratio)
        free=np.setdiff1d(np.arange(len(current)),locked)
        if len(free):stats.update(speedMeanPercent=float(speed[free].mean()),speedMaxPercent=float(speed[free].max()),fastVertices=int(np.count_nonzero(speed[free]>=settings['speedPercent'])))
    else:free=np.setdiff1d(np.arange(len(current)),locked)
    if len(free):stats.update(effectiveStrengthMean=float(strength[free].mean()),effectiveStrengthMin=float(strength[free].min()),effectiveStrengthMax=float(strength[free].max()))
    delta=(aligned-current)*(strength[:,None]/100);limit=unit*settings['distancePercent']/100
    lengths=np.linalg.norm(delta,axis=1);delta*=np.minimum(1,limit/np.maximum(lengths,1e-30))[:,None]
    moving=np.setdiff1d(np.flatnonzero(np.linalg.norm(delta,axis=1)>unit*1e-12),locked)
    proposal=current.copy();matched=0
    if len(moving):
        angle=body.get('normalAngle',60)
        if type(angle) not in (int,float) or not np.isfinite(angle) or not 10<=angle<=89:raise ValueError('法线夹角必须为 10–89 度。')
        masks=exclusion_masks(faces,tf,body.get('excludedFaces',{}),body['pairs'])
        following=np.intersect1d(moving,masks['source'][1]) if body.get('excludedFaces',{}).get('sourceMode')=='follow' else np.array([],dtype=int)
        proposal[following]=current[following]+delta[following]*weights[following,None]
        moving=np.setdiff1d(moving,following)
        allowed=np.delete(np.arange(len(tf)),masks['target'][0]);surface=TriangleSurface((target-center)/unit,tf[allowed])
        q,d,_=surface.query((current[moving]+delta[moving]-center)/unit,vertex_normals(current,faces)[moving],np.cos(np.deg2rad(angle)))
        q=q*unit+center;valid=np.isfinite(d)&(d*unit<=limit)&(np.linalg.norm(q-current[moving],axis=1)<=limit+unit*1e-12)
        ids=moving[valid];proposal[ids]=current[ids]+(q[valid]-current[ids])*weights[ids,None];matched=len(ids)
    proposal[locked]=current[locked]
    guard=FlipGuard((np.asarray(reference['reference'])-center)/unit,faces)
    step=guard.safe_step((current-center)/unit,(proposal-center)/unit)
    result=current+(proposal-current)*step;result[locked]=current[locked]
    correction=np.linalg.norm(result-current,axis=1);free=np.setdiff1d(np.arange(len(current)),locked)
    stats.update(changedVertices=int(np.count_nonzero(correction>unit*1e-10)),matchedVertices=matched,meanCorrection=float(correction.mean()),maxCorrection=float(correction.max()),step=float(step),beforeFrameDistance=float(np.linalg.norm(current[free]-aligned[free],axis=1).mean()) if len(free) else 0.,afterFrameDistance=float(np.linalg.norm(result[free]-aligned[free],axis=1).mean()) if len(free) else 0.)
    return {'vertices':result.tolist(),'stats':stats}
