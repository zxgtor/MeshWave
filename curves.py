"""Cubic surface splines and backward-compatible mesh-edge polylines."""
import numpy as np
from scipy import sparse
from scipy.sparse.csgraph import dijkstra
from wrap_core import parse_obj, index_list, exclusion_masks, MAX_SOURCE
from point_constraints import validate_pairs,point_key


def validate_curves(value, meshes, excluded):
    if not isinstance(value,list) or len(value)>12:
        raise ValueError('最多支持 12 对曲线。')
    result=[]
    for curve in value:
        if not isinstance(curve,dict) or not isinstance(curve.get('name'),str) or not 1<=len(curve['name'].strip())<=80:
            raise ValueError('曲线名称必须为 1–80 个字符。')
        count,closed=curve.get('count',8),curve.get('closed',False)
        if type(count) is not int or not 2<=count<=30 or type(closed) is not bool or (closed and count<3):
            raise ValueError('曲线采样数为 2–30；闭合曲线至少 3 点。')
        item={'name':curve['name'].strip(),'count':count,'closed':closed}
        spline=curve.get('type','polyline')=='spline'
        if curve.get('type','polyline') not in ('polyline','spline'):raise ValueError('曲线类型无效。')
        if spline:item['type']='spline'
        for side in ['source','target']:
            vertices,faces=meshes[side]
            ids=curve.get(side,[])
            if not isinstance(ids,list) or len(ids)>32:
                raise ValueError('每侧曲线最多 32 个控制节点。')
            if spline:
                mesh={key:(vertices,faces) for key in ['source','target']}
                checked=validate_pairs([[p,p] for p in ids],mesh,0,{key:excluded.get(side,[]) for key in mesh})
                item[side]=[p[0] for p in checked];continue
            index_list(ids,len(vertices),'曲线控制节点')
            item[side]=list(ids)
            if len(set(ids))!=len(ids):
                raise ValueError('曲线节点重复；闭合曲线请勾选闭合，不要重复起点。')
            blocked=set(np.unique(faces[excluded.get(side,[])]).tolist()) if len(faces) else set()
            if blocked.intersection(ids):
                raise ValueError('曲线控制节点位于排除区域，请先恢复区域。')
        result.append(item)
    return result


def surface_graph(vertices, faces, excluded):
    blocked=np.unique(faces[excluded]) if len(excluded) else np.array([],dtype=int)
    edges=np.unique(np.sort(np.vstack([faces[:,[0,1]],faces[:,[1,2]],faces[:,[2,0]]]),axis=1),axis=0)
    keep=~np.isin(edges,blocked).any(axis=1)
    edges=edges[keep]
    unit=max(float(np.linalg.norm(np.ptp(vertices,axis=0))),1e-30)
    weights=np.linalg.norm((vertices[edges[:,0]]-vertices[edges[:,1]])/unit,axis=1)
    valid=weights>1e-14;edges,weights=edges[valid],weights[valid]
    return sparse.coo_matrix((np.r_[weights,weights],(np.r_[edges[:,0],edges[:,1]],np.r_[edges[:,1],edges[:,0]])),shape=(len(vertices),len(vertices))).tocsr()


def trace_path(graph, controls, closed=False):
    if len(controls)<2:return list(controls)
    path=[controls[0]]
    stops=controls[1:]+([controls[0]] if closed else [])
    for end in stops:
        start=path[-1];distance,previous=dijkstra(graph,indices=start,return_predecessors=True)
        if not np.isfinite(distance[end]):
            raise ValueError('曲线节点间没有可用表面路径，可能跨越了断开的网格或排除区。')
        segment=[end]
        while segment[-1]!=start:segment.append(int(previous[segment[-1]]))
        path.extend(reversed(segment[:-1]))
    body=path[:-1] if closed else path
    if len(set(body))!=len(body):
        raise ValueError('曲线路径回折或重复经过顶点，请调整控制节点顺序。')
    return path


def sample_path(vertices,path,count,closed):
    if len(path)<(4 if closed else 2):
        raise ValueError('开放曲线每侧至少 2 个节点，闭合曲线每侧至少 3 个节点。')
    points=vertices[path];distances=np.r_[0,np.cumsum(np.linalg.norm(np.diff(points,axis=0),axis=1))]
    if distances[-1]<=1e-14:raise ValueError('曲线长度为零。')
    positions=np.linspace(0,distances[-1],count,endpoint=not closed)
    ids=[path[int(np.argmin(np.abs(distances-p)))] for p in positions]
    if len(set(ids))!=len(ids):
        raise ValueError('采样后顶点重复，请减少采样数或在更细的网格上绘制。')
    return ids


def generate_curve_pairs(body):
    meshes={side:parse_obj(body[side]) for side in ['source','target']}
    if len(meshes['source'][0])>MAX_SOURCE:raise ValueError('模板超过 100,000 顶点。')
    pairs=body.get('pairs',[])
    if not isinstance(pairs,list) or len(pairs)>100 or any(not isinstance(p,list) or len(p)!=2 for p in pairs):
        raise ValueError('现有对应点格式无效。')
    pairs=validate_pairs(pairs,meshes)
    masks=exclusion_masks(meshes['source'][1],meshes['target'][1],body.get('excludedFaces',{}),pairs)
    excluded={side:masks[side][0].tolist() for side in meshes}
    curves=validate_curves(body.get('curves',[]),meshes,excluded)
    path_only=body.get('pathOnly',False)
    if type(path_only) is not bool:raise ValueError('曲线路径模式无效。')
    graphs={side:surface_graph(*meshes[side],excluded[side]) for side in meshes} if any(c.get('type')!='spline' for c in curves) else {}
    paths=[];generated=[]
    left={point_key(a,meshes['source'][1]):point_key(b,meshes['target'][1]) for a,b in pairs}
    right={b:a for a,b in left.items()}
    for curve in curves:
        if curve.get('type')=='spline':
            from surface_splines import projected_spline
            results={side:projected_spline(*meshes[side],curve[side],curve['count'],curve['closed'],excluded[side],path_only) for side in meshes}
            item={side:results[side][0] for side in meshes}
        else:item={side:trace_path(graphs[side],curve[side],curve['closed'] and len(curve[side])>=3) for side in meshes}
        paths.append(item)
        if path_only:continue
        if any(len(curve[side])<(3 if curve['closed'] else 2) for side in meshes):
            raise ValueError(f'“{curve["name"]}”两侧控制节点不足。')
        samples=[results[side][1] if curve.get('type')=='spline' else sample_path(meshes[side][0],item[side],curve['count'],curve['closed']) for side in ['source','target']]
        for a,b in zip(*samples):
            ka,kb=point_key(a,meshes['source'][1]),point_key(b,meshes['target'][1])
            if (ka in left and left[ka]!=kb) or (kb in right and right[kb]!=ka):
                raise ValueError('曲线采样与已有点对或其他曲线冲突，请检查方向、节点顺序或减少采样数。')
            if ka in left:continue
            left[ka]=kb;right[kb]=ka;generated.append([a,b])
    if len(left)>100:raise ValueError('合并后超过 100 对对应点，请减少采样数或曲线数量。')
    return {'paths':paths,'pairs':generated}
