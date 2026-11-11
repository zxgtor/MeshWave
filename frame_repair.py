"""Rebuild an isolated frame from normal neighbors, then refit with a strong seed prior."""
from time import perf_counter
import numpy as np
from scipy import sparse
from scipy.sparse.linalg import splu
from wrap_core import parse_obj,similarity,exclusion_masks
from surface import TriangleSurface,FlipGuard,vertex_normals
from brush_support import prepare_brush


def repair_frame(body,before,after,fraction):
    started=perf_counter();source,faces=parse_obj(body['source']);target,tf=parse_obj(body['target']);pairs=body['pairs']
    if type(fraction) not in (int,float) or not np.isfinite(fraction) or not 0<fraction<1:raise ValueError('修复帧必须位于前后正常帧之间。')
    p=np.asarray(pairs,int);left,right=p[:,0],p[:,1];masks=exclusion_masks(faces,tf,body['excludedFaces'],pairs)
    r,k,a,b=similarity(source[left],target[right]);reference=(source-a)@r*k+b
    aligned=[]
    for neighbor in [before,after]:
        neighbor=np.asarray(neighbor,float)
        if neighbor.shape!=source.shape or not np.isfinite(neighbor).all():raise ValueError('修复参考帧顶点无效。')
        r,k,a,b=similarity(neighbor[left],target[right]);aligned.append((neighbor-a)@r*k+b)
    interpolated=aligned[0]*(1-fraction)+aligned[1]*fraction
    weights=body.get('brushWeights')
    if weights is None:weights=np.ones(len(source))
    elif not isinstance(weights,list) or len(weights)!=len(source) or any(type(v) not in (int,float) or not np.isfinite(v) or not 0<=v<=1 for v in weights):raise ValueError('修复软权重无效。')
    weights=np.asarray(weights,float);protected=np.flatnonzero(weights==0);excluded=masks['source'][1]
    existing=body.get('vertices');existing=reference.copy() if existing is None else np.asarray(existing,float)
    if existing.shape!=source.shape or not np.isfinite(existing).all():raise ValueError('待修复几何无效。')
    expected=interpolated.copy();expected[protected]=existing[protected];expected[excluded]=reference[excluded];expected[left]=target[right]
    locked=np.unique(np.r_[protected,excluded,left]);free=np.setdiff1d(np.arange(len(source)),locked)
    if not len(free):raise ValueError('全部模板顶点被约束锁定，无法重建异常结果。')
    unit=float(np.linalg.norm(np.ptp(target,axis=0)));center=target.mean(0)
    if not np.isfinite(unit) or unit<1e-12:raise ValueError('修复目标尺寸无效。')
    initial=(interpolated-center)/unit;fixed=(target-center)/unit;ref=(reference-center)/unit
    edges=np.unique(np.sort(np.vstack([faces[:,[0,1]],faces[:,[1,2]],faces[:,[2,0]]]),axis=1),axis=0)
    n=len(source);adj=sparse.coo_matrix((np.ones(len(edges)*2),(np.r_[edges[:,0],edges[:,1]],np.r_[edges[:,1],edges[:,0]])),shape=(n,n)).tocsr()
    degree=np.asarray(adj.sum(1)).ravel();laplacian=sparse.eye(n)-sparse.diags(1/np.maximum(degree,1))@adj;regularizer=(laplacian.T@laplacian).tocsc()
    correction=np.zeros_like(initial);correction[locked]=(expected[locked]-interpolated[locked])/unit
    matrix=regularizer+1e-4*sparse.eye(n);correction[free]=splu(matrix[free][:,free].tocsc()).solve(-matrix[free][:,locked]@correction[locked])
    seed=initial+correction;seed[locked]=(expected[locked]-center)/unit;guard=FlipGuard(ref,faces)
    if guard.safe_step(ref,seed)<1:raise ValueError('插值与本帧约束会导致翻面，未采用修复。')
    settings=body['settings'];iterations=settings['iterations'];smoothness=settings['smoothness'];angle=settings['normalAngle'];distance=body['distanceRatio']
    if type(iterations) is not int or not 5<=iterations<=50 or not .001<=distance<=.05:raise ValueError('修复迭代或最大修正距离无效。')
    allowed=np.delete(np.arange(len(tf)),masks['target'][0]);tri=fixed[tf[allowed]];normals=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]);normals/=np.maximum(np.linalg.norm(normals,axis=1)[:,None],1e-30)
    seed_surface=TriangleSurface(seed,faces);_,face_distance,_=seed_surface.query(tri.mean(1),normals,np.cos(np.deg2rad(angle)))
    keep=np.isfinite(face_distance)&(face_distance<=distance)
    # Target faces incident to hard landmarks cannot be silently excluded.
    keep|=np.any(np.isin(tf[allowed],right),axis=1)
    trusted=allowed[keep]
    if len(trusted)<3:raise ValueError('插值附近的可信扫描面不足，未采用修复。')
    excluded_target=np.setdiff1d(np.arange(len(tf)),trusted)
    surface=TriangleSurface(fixed,tf[trusted]);current=seed.copy();limited=0;history=[];last_matches=0
    for _ in range(iterations):
        closest,distances,_=surface.query(current[free],vertex_normals(current,faces)[free],np.cos(np.deg2rad(angle)))
        eligible=np.isfinite(distances)&(np.linalg.norm(closest-seed[free],axis=1)<=distance)
        if eligible.sum()<max(3,int(len(free)*.01)):raise ValueError('修复后的可信表面匹配不足，保留隔离。')
        weight=np.zeros(n);weight[free[eligible]]=weights[free[eligible]]
        rhs=np.zeros_like(seed);rhs[free[eligible]]=weight[free[eligible],None]*(closest[eligible]-seed[free[eligible]])
        # The seed prior prevents a noisy target from immediately destroying interpolation.
        system=(sparse.diags(weight+4)+smoothness*regularizer).tocsc();delta=np.zeros_like(seed);delta[free]=splu(system[free][:,free].tocsc()).solve(rhs[free])
        delta*=weights[:,None];length=np.linalg.norm(delta,axis=1);delta*=np.minimum(1,distance/np.maximum(length,1e-30))[:,None]
        proposal=seed+delta;proposal[locked]=seed[locked];step=guard.safe_step(current,proposal)
        if step<1:limited+=1
        if step<1e-6:raise ValueError('防翻面限制阻止修复，保留隔离。')
        previous=current;current=current+(proposal-current)*step;current[locked]=seed[locked];last_matches=int(eligible.sum())
        history.append(float(np.mean(surface.query(current[free])[1])*unit))
        if np.linalg.norm(current-previous,axis=1).max()<1e-7:break
    result=current*unit+center;result[locked]=expected[locked]
    prepare_brush({**body,'vertices':result.tolist()})
    if np.any(np.linalg.norm(result[protected]-expected[protected],axis=1)>unit*1e-12):raise ValueError('修复违反软权重保护，未采用。')
    final_distance=surface.query(current[free],vertex_normals(current,faces)[free],np.cos(np.deg2rad(angle)))[1]
    valid=np.isfinite(final_distance)&(final_distance<=distance)
    if valid.sum()<max(3,int(len(free)*.01)):raise ValueError('修复复检的可信表面覆盖不足。')
    return {'vertices':result.tolist(),'excludedTargetFaces':excluded_target.tolist(),'stats':{'fraction':fraction,'solverMethod':'seed-prior-full-mesh','iterations':len(history),'requestedIterations':iterations,'surfaceMatches':last_matches,'surfaceDistanceHistory':history,'seedPriorWeight':4,'maxSeedDeviation':float(np.linalg.norm(current-seed,axis=1).max()*unit),'maxRefitDistance':distance*unit,'minimumProjectedAreaRatio':guard.minimum_ratio(current),'flipLimitedSteps':limited,'protectedVertices':len(protected),'trustedTargetFaces':len(trusted),'autoExcludedTargetFaces':int(np.count_nonzero(~keep)),'trustedVertexCount':int(valid.sum()),'trustedFitDistancePercent':float(np.quantile(final_distance[valid],.95)*100),'seconds':perf_counter()-started}}
