"""Conservative sequence quality signals; never edits geometry or constraints."""
import numpy as np
from temporal import coherent_motion
from surface import TriangleSurface
from wrap_core import parse_obj,exclusion_masks,similarity
from point_constraints import pair_support,positions


def scan_quality(text,excluded,pairs):
    v,f=parse_obj(text);lo,hi=np.quantile(v,[.02,.98],axis=0);unit=float(np.linalg.norm(hi-lo))
    if not np.isfinite(unit) or unit<1e-12:raise ValueError('扫描尺寸无效，无法检测异常。')
    edges=np.sort(np.vstack([f[:,[0,1]],f[:,[1,2]],f[:,[2,0]]]),axis=1);unique,counts=np.unique(edges,axis=0,return_counts=True)
    boundary=np.unique(unique[counts==1]);blocked=np.unique(np.r_[boundary,f[np.asarray(excluded,int)].ravel(),pair_support(pairs,1,f)])
    if len(blocked):blocked=np.unique(f[np.any(np.isin(f,blocked),axis=1)])
    active=np.setdiff1d(np.arange(len(v)),blocked)
    if not len(active):return {'roughnessPercent':None,'sampleVertices':0}
    rough=np.linalg.norm(v-coherent_motion(v,f),axis=1)/unit*100
    return {'roughnessPercent':float(np.quantile(rough[active],.99)),'sampleVertices':len(active)}


def fit_quality(source,target,vertices,pairs,excluded,weights):
    sv,sf=parse_obj(source);tv,tf=parse_obj(target);v=np.asarray(vertices,float)
    if v.shape!=sv.shape or not np.isfinite(v).all():raise ValueError('待检测的贴合顶点无效。')
    masks=exclusion_masks(sf,tf,excluded,pairs);blocked=np.r_[pair_support(pairs,0,sf),masks['source'][1],np.flatnonzero(np.asarray(weights)==0) if weights is not None else []].astype(int)
    active=np.setdiff1d(np.arange(len(v)),blocked)
    if not len(active):return {'distancePercent':None,'sampleVertices':0}
    active=active[np.linspace(0,len(active)-1,min(2048,len(active)),dtype=int)];unit=float(np.linalg.norm(np.ptp(tv,axis=0)))
    if unit<1e-12:raise ValueError('扫描尺寸无效，无法检测贴合质量。')
    center=tv.mean(0);allowed=np.delete(tf,masks['target'][0],axis=0);surface=TriangleSurface((tv-center)/unit,allowed)
    distances=surface.query((v[active]-center)/unit)[1]*100
    return {'distancePercent':float(np.quantile(distances,.95)),'sampleVertices':len(active)}


def classify_frame(body,previous=None,following=None):
    """Compare immutable neighbors; high coherent expression speed alone never rejects."""
    threshold=body['threshold'];reasons=[];source,faces=parse_obj(body['source']);current=np.asarray(body['vertices'],float) if body.get('vertices') is not None else None
    scan=body.get('scanQuality',{});fit=body.get('fitQuality',{});neighbors=body.get('neighbors',[])
    scan_baselines=[n['scanQuality']['roughnessPercent'] for n in neighbors if n.get('scanQuality',{}).get('topologyHash')==scan.get('topologyHash') and n.get('scanQuality',{}).get('roughnessPercent') is not None]
    fit_baselines=[n['fitQuality']['distancePercent'] for n in neighbors if n.get('fitQuality',{}).get('distancePercent') is not None]
    rough=scan.get('roughnessPercent');distance=fit.get('distancePercent')
    if rough is not None and scan_baselines and rough>threshold and rough>3*min(scan_baselines)+.01:reasons.append('scan_noise')
    if distance is not None and fit_baselines and distance>threshold and distance>3*min(fit_baselines)+.01:reasons.append('surface_jump')
    stats={'scanRoughnessPercent':rough,'scanBaselinePercent':min(scan_baselines) if scan_baselines else None,'fitDistancePercent':distance,'fitBaselinePercent':min(fit_baselines) if fit_baselines else None,'motionResidualPercent':None,'motionIncoherence':None,'neighborAgreementPercent':None,'reasons':reasons,'thresholdPercent':threshold,'neighborFrames':[n['name'] for n in neighbors]}
    if current is not None and previous is not None and following is not None:
        target,_=parse_obj(body['target']);unit=float(np.linalg.norm(np.ptp(target,axis=0)));anchors=[p[0] for p in body['pairs']];anchor_support=pair_support(body['pairs'],0,faces)
        aligned=[]
        for v in [previous,following]:
            v=np.asarray(v,float)
            if v.shape!=current.shape or not np.isfinite(v).all():raise ValueError('异常检测邻帧顶点无效。')
            r,k,a,b=similarity(positions(v,faces,anchors),positions(current,faces,anchors));aligned.append((v-a)@r*k+b)
        delta=current-(aligned[0]+aligned[1])/2;residual=delta-coherent_motion(delta,faces)
        masks=exclusion_masks(faces,parse_obj(body['target'])[1],body['excludedFaces'],body['pairs'])
        weights=body.get('brushWeights');blocked=np.r_[anchor_support,masks['source'][1],np.flatnonzero(np.asarray(weights)==0) if weights is not None else []].astype(int)
        if len(blocked):blocked=np.unique(faces[np.any(np.isin(faces,blocked),axis=1)])
        active=np.setdiff1d(np.arange(len(current)),blocked)
        if len(active):
            amplitude=float(np.quantile(np.linalg.norm(delta[active],axis=1),.99));error=float(np.quantile(np.linalg.norm(residual[active],axis=1),.99));agreement=float(np.quantile(np.linalg.norm((aligned[0]-aligned[1])[active],axis=1),.99))
            incoherence=error/max(amplitude,1e-30);stats.update(motionResidualPercent=error/unit*100,motionIncoherence=incoherence,neighborAgreementPercent=agreement/unit*100)
            if error/unit*100>threshold and incoherence>.35 and agreement<amplitude*.75:reasons.append('incoherent_jump')
    status='rejected' if reasons else 'clear' if current is not None and previous is not None and following is not None and rough is not None and distance is not None and stats['motionResidualPercent'] is not None and scan_baselines and fit_baselines else 'limited'
    return {'status':status,'stats':stats}
