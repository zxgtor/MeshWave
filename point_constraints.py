"""Vertex and barycentric surface handles, with exact affine equality solves."""
import numpy as np
from scipy import sparse
from scipy.linalg import qr
from scipy.sparse.linalg import splu


def surface_pairs(pairs):
    return any(isinstance(point,dict) for pair in pairs for point in pair)


def handle_shape(point, vertex_count, faces=None):
    if type(point) is int:
        if not 0<=point<vertex_count:raise ValueError('对应点超出模型范围。')
        return point
    if not isinstance(point,dict) or set(point)!={'face','bary'}:
        raise ValueError('表面点必须包含三角面编号和三个重心坐标。')
    face,bary=point['face'],point['bary']
    if type(face) is not int or face<0 or (faces is not None and face>=len(faces)):
        raise ValueError('表面点三角面编号无效。')
    if not isinstance(bary,list) or len(bary)!=3 or any(type(x) not in (int,float) or not np.isfinite(x) or x<0 or x>1 for x in bary) or abs(sum(bary)-1)>1e-8:
        raise ValueError('表面点重心坐标必须非负且总和为 1。')
    weights=np.asarray(bary,float)
    if abs(float(weights.sum())-1)>1e-12:weights/=weights.sum()
    if faces is not None and np.count_nonzero(weights>1e-12)==1:return int(faces[face][np.argmax(weights)])
    return {'face':face,'bary':weights.tolist()}


def support(point,faces):
    return [int(point)] if isinstance(point,(int,np.integer)) else [int(i) for i,w in zip(faces[point['face']],point['bary']) if w>1e-12]


def pair_support(pairs,column,faces):
    return np.asarray(sorted({i for pair in pairs for i in support(pair[column],faces)}),dtype=int)


def point_key(point,faces):
    if isinstance(point,(int,np.integer)):return ((int(point),1.),)
    return tuple(sorted((int(i),round(float(w),11)) for i,w in zip(faces[point['face']],point['bary']) if w>1e-12))


def validate_pairs(pairs,meshes,minimum=0,excluded=None):
    if not isinstance(pairs,list) or not minimum<=len(pairs)<=100 or any(not isinstance(p,list) or len(p)!=2 for p in pairs):
        raise ValueError('请选取 3–100 对对应点，建议至少 6 对。' if minimum else '现有对应点格式无效。')
    result=[[] for _ in pairs]
    for column,side in enumerate(['source','target']):
        vertices,faces=meshes[side];seen=set()
        blocked=set(np.unique(faces[(excluded or {}).get(side,[])]).tolist()) if len(faces) else set()
        for pair,out in zip(pairs,result):
            point=handle_shape(pair[column],len(vertices),faces)
            if isinstance(point,dict):
                tri=vertices[faces[point['face']]];unit=max(np.linalg.norm(np.ptp(vertices,axis=0)),1e-30)
                if np.linalg.norm(np.cross((tri[1]-tri[0])/unit,(tri[2]-tri[0])/unit))<1e-14:raise ValueError('表面点不能位于退化三角面。')
            key=point_key(point,faces)
            if key in seen:raise ValueError('对应点索引无效或重复。')
            if blocked.intersection(support(point,faces)):raise ValueError('排除区域包含对应点，请先移动或删除冲突的点对。')
            seen.add(key);out.append(point)
    return result


def point_matrix(points,faces,count):
    rows=[];columns=[];weights=[]
    for row,point in enumerate(points):
        ids,values=([point],[1.]) if isinstance(point,(int,np.integer)) else (faces[point['face']],point['bary'])
        for i,w in zip(ids,values):
            if w>1e-12:rows.append(row);columns.append(int(i));weights.append(w)
    return sparse.csr_matrix((weights,(rows,columns)),shape=(len(points),count))


def positions(vertices,faces,points):
    return point_matrix(points,faces,len(vertices))@vertices


def solve_affine(matrix,rhs,constraints,values):
    """Solve a positive system subject to C*x=d; remove only consistent redundancy."""
    if not constraints.shape[0]:return splu(matrix.tocsc()).solve(rhs)
    gram=(constraints@constraints.T).toarray()
    _,r,order=qr(gram,pivoting=True)
    diagonal=np.abs(np.diag(r));rank=int(np.count_nonzero(diagonal>max(float(diagonal.max(initial=0))*1e-10,1e-13)))
    if rank:
        selected=order[:rank];c=constraints[selected].tocsc()
        system=sparse.bmat([[matrix,c.T],[c,None]],format='csc')
        solution=splu(system).solve(np.vstack([rhs,values[selected]]))[:matrix.shape[0]]
    else:solution=splu(matrix.tocsc()).solve(rhs)
    if np.max(np.abs(constraints@solution-values),initial=0)>1e-7:
        raise ValueError('表面对应约束相互冲突，或与固定区不兼容；请调整点或减少采样数。')
    return solution
