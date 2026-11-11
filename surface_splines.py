"""Interpolating cubic splines projected to the connected, normal-compatible surface."""
import numpy as np
from scipy import sparse
from scipy.interpolate import CubicSpline
from scipy.sparse.csgraph import connected_components
from surface import TriangleSurface,vertex_normals,face_vectors
from point_constraints import positions,support,point_key


def projected_spline(vertices,faces,controls,count,closed,excluded,path_only=False):
    if len(controls)<2:return list(controls),[]
    closed=closed and len(controls)>=3
    unit=max(float(np.linalg.norm(np.ptp(vertices,axis=0))),1e-30);origin=vertices.mean(0);v=(vertices-origin)/unit
    blocked=np.unique(faces[excluded]) if len(excluded) else np.array([],int)
    allowed=np.flatnonzero(~np.isin(faces,blocked).any(axis=1))
    edges=np.vstack([faces[allowed][:,[0,1]],faces[allowed][:,[1,2]],faces[allowed][:,[2,0]]])
    graph=sparse.coo_matrix((np.ones(len(edges)*2),(np.r_[edges[:,0],edges[:,1]],np.r_[edges[:,1],edges[:,0]])),shape=(len(v),len(v))).tocsr()
    _,labels=connected_components(graph);component=labels[support(controls[0],faces)[0]]
    if any(any(labels[i]!=component for i in support(p,faces)) for p in controls):raise ValueError('曲线节点间没有可用表面路径，可能跨越了断开的网格或排除区。')
    allowed=allowed[np.all(labels[faces[allowed]]==component,axis=1)]
    surface=TriangleSurface(v,faces[allowed]);points=positions(v,faces,controls)
    vn=vertex_normals(v,faces);fn=face_vectors(v,faces);fn/=np.maximum(np.linalg.norm(fn,axis=1)[:,None],1e-30)
    normals=np.array([vn[p] if type(p) is int else fn[p['face']] for p in controls])
    if closed:points=np.vstack([points,points[0]]);normals=np.vstack([normals,normals[0]])
    steps=np.linalg.norm(np.diff(points,axis=0),axis=1)
    if np.any(steps<1e-12):raise ValueError('曲线控制点位置重合，请调整节点。')
    t=np.r_[0,np.cumsum(steps)];t/=t[-1]
    curve=CubicSpline(t,points,axis=0,bc_type='periodic' if closed else 'natural')
    u=np.unique(np.r_[np.linspace(0,1,min(2048,max(96,len(controls)*48))),t]);proposed=curve(u)
    def project(samples,directions):
        directions=directions/np.maximum(np.linalg.norm(directions,axis=1)[:,None],1e-30)
        q,d,ids=surface.query(samples,directions,0.)
        if not np.isfinite(d).all() or np.any(d>max(float(steps.max())*.75,.005)):
            raise ValueError('样条偏离可用表面，请增加控制点或调整曲线。')
        handles=[]
        for point,local_id in zip(q,ids):
            face=int(allowed[local_id]);a,b,c=v[faces[face]];e1,e2=b-a,c-a;delta=point-a
            d00,d01,d11=np.dot(e1,e1),np.dot(e1,e2),np.dot(e2,e2);den=d00*d11-d01*d01
            y=(np.dot(delta,e1)*d11-np.dot(delta,e2)*d01)/den;z=(np.dot(delta,e2)*d00-np.dot(delta,e1)*d01)/den
            bary=np.clip([1-y-z,y,z],0,1);bary/=sum(bary);handles.append({'face':face,'bary':bary.tolist()})
        return q,handles
    directions=np.column_stack([np.interp(u,t,normals[:,i]) for i in range(3)])
    projected,path=project(proposed,directions)
    if np.any(np.linalg.norm(np.diff(projected,axis=0),axis=1)>np.maximum(np.linalg.norm(np.diff(proposed,axis=0),axis=1)*4,.002)):
        raise ValueError('样条投射出现表面跳变，请增加控制点并检查曲线走向。')
    path[0]=controls[0];path[-1]=controls[0] if closed else controls[-1]
    if path_only:return path,[]
    distance=np.r_[0,np.cumsum(np.linalg.norm(np.diff(projected,axis=0),axis=1))]
    if distance[-1]<=1e-12:raise ValueError('曲线长度为零。')
    keep=np.r_[True,np.diff(distance)>1e-14];distance=distance[keep];projected=projected[keep];directions=directions[keep]
    sample_at=np.linspace(0,distance[-1],count,endpoint=not closed)
    raw=np.column_stack([np.interp(sample_at,distance,projected[:,i]) for i in range(3)])
    normal=np.column_stack([np.interp(sample_at,distance,directions[:,i]) for i in range(3)])
    _,samples=project(raw,normal);samples[0]=controls[0]
    if not closed:samples[-1]=controls[-1]
    if len({point_key(p,faces) for p in samples})!=len(samples):raise ValueError('样条采样位置重复，请调整控制点或减少采样数。')
    return path,samples
