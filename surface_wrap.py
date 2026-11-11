"""Coarse-to-fine fitting with exact barycentric point equalities."""
from time import perf_counter
import numpy as np
from scipy import sparse
from surface import TriangleSurface,FlipGuard,vertex_normals
from multires import solve_stages
from local_guard import local_safe_solve
from point_constraints import validate_pairs,point_matrix,pair_support,solve_affine


def wrap_surface(source_text,target_text,pairs,iterations,smoothness,excluded_faces,normal_angle,solver_mode,brush_weights=None,progress=None):
    from wrap_core import parse_obj,similarity,exclusion_masks,MAX_SOURCE
    started=perf_counter();source,faces=parse_obj(source_text);target,tf=parse_obj(target_text)
    if len(source)>MAX_SOURCE:raise ValueError('模板超过 100,000 顶点。')
    if solver_mode not in ('single','multistage') or (solver_mode=='single' and len(source)>25000):raise ValueError('超过 25,000 顶点的模板请使用多阶段求解。')
    iterations,smoothness=int(iterations),float(smoothness)
    if not 5<=iterations<=50 or not np.isfinite(smoothness) or not .1<=smoothness<=30:raise ValueError('迭代次数或平滑参数超出范围。')
    if type(normal_angle) not in (int,float) or not np.isfinite(normal_angle) or not 10<=normal_angle<=89:raise ValueError('法线夹角必须为 10–89 度。')
    pairs=validate_pairs(pairs,{'source':(source,faces),'target':(target,tf)},3)
    masks=exclusion_masks(faces,tf,excluded_faces if excluded_faces is not None else {},pairs)
    if brush_weights is not None and (not isinstance(brush_weights,list) or len(brush_weights)!=len(source) or any(type(w) not in (int,float) or not np.isfinite(w) or not 0<=w<=1 for w in brush_weights)):
        raise ValueError('几何软权重必须与模板顶点一一对应，范围为 0–1。')
    weights=np.ones(len(source)) if brush_weights is None else np.asarray(brush_weights,float).copy()
    # Hard correspondences take precedence over painted protection, including
    # triangle supports of continuous points; region/point overlap remains invalid.
    weights[pair_support(pairs,0,faces)]=1
    excluded=np.union1d(masks['fixedSource'],np.flatnonzero(weights==0))
    weights[masks['source'][1]]=0
    c=point_matrix([p[0] for p in pairs],faces,len(source));ct=point_matrix([p[1] for p in pairs],tf,len(target))
    destination=ct@target;r,k,a,b=similarity(c@source,destination);aligned=(source-a)@r*k+b
    unit=float(np.linalg.norm(np.ptp(target,axis=0)));center=target.mean(0)
    if not np.isfinite(unit) or unit<1e-12:raise ValueError('目标模型尺寸为零。')
    base=(aligned-center)/unit;fixed=(target-center)/unit;goal=(destination-center)/unit
    surface=TriangleSurface(fixed,np.delete(tf,masks['target'][0],axis=0));guard=FlipGuard(base,faces);cosine=np.cos(np.deg2rad(normal_angle));n=len(source)
    edges=np.unique(np.sort(np.vstack([faces[:,[0,1]],faces[:,[1,2]],faces[:,[2,0]]]),axis=1),axis=0);edges=edges[edges[:,0]!=edges[:,1]]
    adjacency=sparse.coo_matrix((np.ones(len(edges)*2),(np.r_[edges[:,0],edges[:,1]],np.r_[edges[:,1],edges[:,0]])),shape=(n,n)).tocsr()
    degree=np.asarray(adjacency.sum(1)).ravel();laplacian=sparse.eye(n)-sparse.diags(1/np.maximum(degree,1))@adjacency;regularizer=(laplacian.T@laplacian).tocsc()
    free=np.setdiff1d(np.arange(n),excluded);active=weights>0
    displacement=np.zeros_like(base);initial_system=regularizer+1e-4*sparse.eye(n)
    displacement[free]=solve_affine(initial_system[free][:,free].tocsc(),np.zeros((len(free),3)),c[:,free],goal-c@base)
    if guard.safe_step(base,base+displacement)!=1:raise ValueError('对应点与固定区域约束会导致翻面或严重压扁，请重选对应点或缩小排除区域。')
    _,initial_distance,initial_nearest=surface.query(base)
    if not active.any():raise ValueError('全部模板顶点被约束锁定，无法重建异常结果。')
    facing=np.sum(vertex_normals(base,faces)*surface.face_normals[initial_nearest],axis=1)
    if np.mean(facing[active]<-.1)>.6:raise ValueError('两侧表面法线方向大多相反，请先在建模软件中统一面朝向。')
    hierarchy=perf_counter();stages=solve_stages(adjacency,free,base,pair_support(pairs,0,faces),active,iterations,solver_mode,data_weights=weights);hierarchy_seconds=perf_counter()-hierarchy
    stage_reports=[];history=[];global_step=0;queries=0;limited=0;smallest=1.;retries=0;stopped=False
    local_faces=set();local_vertices=set();local_rounds=0
    stage_distance=float(surface.query((base+displacement)[active])[1].mean()*unit)
    for stage_index,stage in enumerate(stages):
        if progress:progress({'phase':'solving','stage':stage['name'],'stageIndex':stage_index+1,'stageCount':len(stages),'iteration':global_step,'requestedIterations':iterations},(base+displacement)*unit+center)
        start=perf_counter();basis=stage['basis'];ids=stage['ids'];mass=stage['mass'];anchor=displacement.copy();sample=basis[ids].tocsr()
        reg=(basis.T@regularizer@basis).tocsc();identity=(basis.T@basis).tocsc();reg_anchor=basis.T@(regularizer@anchor);identity_anchor=basis.T@anchor
        equality=c@basis;residual=goal-c@(base+anchor);before=stage_distance;completed=0;blocked=False
        coefficients=np.zeros((basis.shape[1],3));frozen=np.zeros(basis.shape[1],bool)
        for step in range(stage['budget']):
            current=base+displacement;closest,distance,_=surface.query(current[ids],vertex_normals(current,faces)[ids],cosine);queries+=len(ids);eligible=np.isfinite(distance)
            if eligible.sum()<max(3,int(len(ids)*.05)):raise ValueError('法线匹配不足，请检查两侧面的朝向是否一致，或适当增大法线夹角。')
            cutoff=max(float(np.quantile(distance[eligible],.85))*2,.005);weight=np.zeros(len(ids));weight[eligible]=mass[eligible]*np.minimum(1,cutoff/np.maximum(distance[eligible],1e-12))
            data_matrix=(sample.T@sparse.diags(weight)@sample).tocsc();data_rhs=sample.T@(weight[:,None]*(closest-base[ids]-anchor[ids]));alpha=smoothness*10**(-2*(global_step+step)/max(iterations-1,1))
            locally_limited=False
            for attempt in range(5):
                stiffness=alpha*4**attempt;matrix=data_matrix+stiffness*reg+1e-6*identity;rhs=data_rhs-stiffness*reg_anchor-1e-6*identity_anchor
                candidate,scale,faces_limited,rounds=local_safe_solve(matrix,rhs,equality,residual,basis,base,anchor,coefficients,frozen,guard)
                if faces_limited:
                    locally_limited=True;local_faces.update(faces_limited);local_rounds+=rounds
                    local_vertices.update(np.flatnonzero(basis[:,frozen].getnnz(axis=1)).tolist())
                if scale>=.125 or attempt==4:break
                retries+=1
            if scale<1 or attempt or locally_limited:limited+=1;smallest=min(smallest,scale)
            if scale<1e-6:blocked=True;stopped=stage is stages[-1];break
            coefficients+=scale*(candidate-coefficients)
            displacement=anchor+basis@coefficients;displacement[excluded]=0;completed+=1
            history.append(float(np.average(surface.query((base+displacement)[ids])[1],weights=mass)*unit))
            if progress:progress({'phase':'solving','stage':stage['name'],'stageIndex':stage_index+1,'stageCount':len(stages),'iteration':global_step+completed,'requestedIterations':iterations,'meanDistance':history[-1]})
        _,stage_distances,stage_nearest=surface.query(base+displacement)
        stage_distance=float(stage_distances[active].mean()*unit)
        stage_reports.append({'name':stage['name'],'controlVertices':basis.shape[1],'sampleVertices':len(ids),'iterations':completed,'requestedIterations':stage['budget'],'initialMeanDistance':before,'finalMeanDistance':stage_distance,'blockedByFlipGuard':blocked,'locallyFrozenControls':int(frozen.sum()),'seconds':perf_counter()-start})
        if progress:progress({'phase':'stage_complete','stage':stage['name'],'stageIndex':stage_index+1,'stageCount':len(stages),'iteration':global_step+completed,'requestedIterations':iterations,'meanDistance':stage_distance},(base+displacement)*unit+center)
        global_step+=stage['budget']
    result=(base+displacement)*unit+center;normals=vertex_normals(base+displacement,faces);nearest=stage_nearest
    normal_distance=surface.query(base+displacement,normals,cosine)[1]
    return {'vertices':result.tolist(),'stats':{'initialMeanDistance':float(initial_distance[active].mean()*unit),'finalMeanDistance':stage_distance,'landmarkMaxError':float(np.linalg.norm(c@result-destination,axis=1).max()),'surfaceConstraintCount':sum(isinstance(p[0],dict) or isinstance(p[1],dict) for p in pairs),'iterations':len(history),'requestedIterations':iterations,'history':history,'solverMode':solver_mode,'stages':stage_reports,'stageCount':len(stages),'historyScope':'stage-sample' if len(stages)>1 else 'full-active-mesh','correspondenceQueries':queries,'hierarchySeconds':hierarchy_seconds,'totalSeconds':perf_counter()-started,'sampledSurface':False,'normalFilteredNearestVertices':int(np.count_nonzero(np.sum(normals*surface.face_normals[nearest],axis=1)[active]<cosine)),'flipLimitedSteps':limited,'minimumStepScale':smallest,'vertices':n,'triangles':len(faces),'distanceMethod':'exact-triangle-bvh','normalAngle':normal_angle,'normalRejectedVertices':int(np.count_nonzero(~np.isfinite(normal_distance[active]))),'minimumProjectedAreaRatio':guard.minimum_ratio(base+displacement),'ignoredDegenerateTargetFaces':surface.ignored_degenerate,'excludedSourceVertices':len(masks['source'][1]),'fixedSourceVertices':len(masks['fixedSource']),'followingSourceVertices':len(masks['source'][1]) if (excluded_faces or {}).get('sourceMode')=='follow' else 0,'protectedWeightVertices':int(np.count_nonzero((np.asarray(brush_weights)==0))) if brush_weights is not None else 0,'weightedGeometry':brush_weights is not None,'excludedTargetFaces':len(masks['target'][0]),'stoppedByFlipGuard':stopped,'stabilizationRetries':retries,'localGuardFaces':len(local_faces),'localGuardVertices':len(local_vertices),'localGuardRounds':local_rounds}}
