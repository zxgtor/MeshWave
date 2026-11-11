"""Topology-connected aggregates and smoothed deformation prolongation.

Original mesh vertices/faces are never replaced. Only the early solve space and
correspondence quadrature are reduced; the last stage has every free vertex.
"""
import numpy as np
from scipy import sparse


def aggregate(graph, target):
    graph=graph.tocsr().copy();graph.setdiag(0);graph.eliminate_zeros()
    labels=np.arange(graph.shape[0])
    while graph.shape[0]>target:
        groups=np.full(graph.shape[0],-1,dtype=int);count=0
        for seed in range(graph.shape[0]):
            if groups[seed]>=0:
                continue
            neighbors=graph.indices[graph.indptr[seed]:graph.indptr[seed+1]]
            neighbors=neighbors[groups[neighbors]<0][:7]
            groups[seed]=count;groups[neighbors]=count;count+=1
        if count==graph.shape[0]:
            break
        labels=groups[labels]
        assignment=sparse.csr_matrix((np.ones(len(groups)),(np.arange(len(groups)),groups)),shape=(len(groups),count))
        graph=(assignment.T@graph@assignment).tocsr()
        graph.setdiag(0);graph.eliminate_zeros();graph.data[:]=1
    return labels


def reduced_basis(adjacency, free, positions, target, data_weights=None):
    graph=adjacency[free][:,free].tocsr()
    labels=aggregate(graph,target);k=int(labels.max()+1) if len(labels) else 0
    tentative=sparse.csr_matrix((np.ones(len(free)),(np.arange(len(free)),labels)),shape=(len(free),k))
    degree=np.asarray(graph.sum(1)).ravel()
    smoothing=sparse.diags(np.where(degree>0,.33,1))+.67*sparse.diags(1/np.maximum(degree,1))@graph
    interpolation=(smoothing@smoothing@tentative).tocoo()
    prolongation=sparse.csr_matrix((interpolation.data,(free[interpolation.row],interpolation.col)),shape=(len(positions),k))
    # One representative closest to each aggregate centroid, with aggregate mass.
    mass=np.bincount(labels,minlength=k)
    if not k:
        return prolongation,np.array([],dtype=int),np.array([],dtype=float)
    centers=np.column_stack([np.bincount(labels,weights=positions[free,axis],minlength=k)/mass for axis in range(3)])
    distance=np.sum((positions[free]-centers[labels])**2,axis=1)
    order=np.lexsort((np.arange(len(free)),distance,labels))
    _,first=np.unique(labels[order],return_index=True)
    representatives=order[first]
    if data_weights is not None:
        # Keep deformation variables in follow regions, but never use those
        # regions as surface samples or count them in aggregate quadrature.
        weighted=np.asarray(data_weights)[free]
        data_mass=np.bincount(labels,weights=weighted,minlength=k)
        order=np.lexsort((np.arange(len(free)),distance,weighted<=0,labels))
        _,first=np.unique(labels[order],return_index=True)
        representatives=order[first];valid=data_mass>0
        return prolongation,free[representatives[valid]],data_mass[valid]
    return prolongation,free[representatives],mass.astype(float)


def solve_stages(adjacency, free, positions, left, active, iterations, mode, data_weights=None):
    stages=[]
    if mode=='multistage' and len(free)>512:
        for name,target in [('粗配准',384),('中层贴合',2048)]:
            if target>=len(free):
                continue
            basis,ids,mass=reduced_basis(adjacency,free,positions,target,data_weights)
            if basis.shape[1]>=len(free) or (stages and basis.shape[1]<=stages[-1]['basis'].shape[1]):
                continue
            ids=np.r_[ids,left];mass=np.r_[mass,np.ones(len(left)) if data_weights is None else data_weights[left]]
            if data_weights is not None:
                keep=mass>0;ids=ids[keep];mass=mass[keep]
            stages.append({'name':name,'basis':basis,'ids':ids,'mass':mass})
    basis=sparse.csr_matrix((np.ones(len(free)),(free,np.arange(len(free)))),shape=(len(positions),len(free)))
    ids=np.flatnonzero(active)
    stages.append({'name':'全顶点精修' if mode=='multistage' else '单阶段','basis':basis,'ids':ids,'mass':np.ones(len(ids)) if data_weights is None else data_weights[ids]})
    # Keep a fixed total iteration budget; reserve at least 40% for full detail.
    if len(stages)==3:
        budgets=[max(1,iterations//4),max(1,iterations*3//10)]
    elif len(stages)==2:
        budgets=[max(1,iterations*2//5)]
    else:
        budgets=[]
    budgets.append(iterations-sum(budgets))
    for stage,count in zip(stages,budgets):
        stage['budget']=count
    return stages
