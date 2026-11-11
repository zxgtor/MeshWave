import unittest
import numpy as np
from scipy import sparse
from multires import solve_stages, reduced_basis
from wrap_core import wrap, parse_obj, export_obj, similarity
from surface import FlipGuard
from project import validate_project
from test_features import project_fixture


def dense_fixture(side=49):
    xy=np.array([[x/(side-1),y/(side-1)] for y in range(side) for x in range(side)])
    source=np.column_stack([xy,np.zeros(len(xy))]);target=source.copy()
    target[:,2]=.06*np.sin(np.pi*xy[:,0])*np.sin(np.pi*xy[:,1])+.008*np.sin(6*np.pi*xy[:,0])*np.sin(6*np.pi*xy[:,1])
    faces=[]
    for y in range(side-1):
        for x in range(side-1):
            a=y*side+x;faces.extend([[a,a+1,a+side+1],[a,a+side+1,a+side]])
    faces=np.array(faces)
    ids=[y*side+x for y in [0,side//2,side-1] for x in [0,side//2,side-1]]
    def text(v):return '\n'.join(['v '+' '.join(map(str,p)) for p in v]+['vt '+' '.join(map(str,p)) for p in xy]+['f '+' '.join(f'{i+1}/{i+1}' for i in face) for face in faces])
    return text(source),text(target),[[i,i] for i in ids],target


class MultiResolutionTests(unittest.TestCase):
    def test_hierarchy_reduces_dofs_keeps_constraints_and_iteration_budget(self):
        n=2500;graph=sparse.diags([np.ones(n-1),np.ones(n-1)],[-1,1]).tocsr()
        positions=np.column_stack([np.arange(n),np.zeros((n,2))]);left=np.array([0,500,2499]);excluded=np.array([1200,1201])
        free=np.setdiff1d(np.arange(n),np.r_[left,excluded]);active=np.ones(n,dtype=bool);active[excluded]=False
        stages=solve_stages(graph,free,positions,left,active,20,'multistage')
        self.assertEqual(len(stages),3);self.assertEqual(sum(s['budget'] for s in stages),20)
        dimensions=[s['basis'].shape[1] for s in stages]
        self.assertLess(dimensions[0],dimensions[1]);self.assertLess(dimensions[1],dimensions[2]);self.assertEqual(dimensions[-1],len(free))
        for stage in stages:
            np.testing.assert_allclose(np.asarray(stage['basis'].sum(1)).ravel()[free],1,atol=1e-12)
            self.assertEqual(stage['basis'][np.r_[left,excluded]].nnz,0)
            self.assertAlmostEqual(stage['mass'].sum(),active.sum())
        self.assertLess(len(stages[0]['ids']),active.sum())

    def test_overlaid_disconnected_sheets_never_share_controls(self):
        n=1200;chain=sparse.diags([np.ones(n-1),np.ones(n-1)],[-1,1]).tocsr();graph=sparse.block_diag([chain,chain]).tocsr()
        positions=np.tile(np.column_stack([np.arange(n),np.zeros((n,2))]),(2,1))
        basis,_,_=reduced_basis(graph,np.arange(n*2),positions,200)
        self.assertTrue(set(basis[:n].indices).isdisjoint(set(basis[n:].indices)))

    def test_multistage_precision_pins_exclusions_and_original_uv_topology(self):
        source,target,pairs,_=dense_fixture();mask=2*(3*48+3)
        result=wrap(source,target,pairs,12,4,{'source':[mask],'target':[mask]},60,'multistage')
        v,f,uv,uf=parse_obj(source,True);tv,_,_,_=parse_obj(target,True);p=np.asarray(pairs)
        r,k,a,b=similarity(v[p[:,0]],tv[p[:,1]]);aligned=(v-a)@r*k+b
        output=np.asarray(result['vertices'])
        self.assertEqual(result['stats']['stageCount'],3)
        self.assertEqual(sum(s['requestedIterations'] for s in result['stats']['stages']),12)
        self.assertLess(result['stats']['finalMeanDistance'],result['stats']['initialMeanDistance']*.7)
        np.testing.assert_allclose(output[p[:,0]],tv[p[:,1]],atol=1e-10)
        np.testing.assert_allclose(output[np.unique(f[mask])],aligned[np.unique(f[mask])],atol=1e-10)
        self.assertGreaterEqual(FlipGuard(aligned,f).minimum_ratio(output),.01-1e-10)
        _,of,ouv,ouf=parse_obj(export_obj(source,output),True)
        np.testing.assert_array_equal(of,f);np.testing.assert_array_equal(ouv,uv);np.testing.assert_array_equal(ouf,uf)
        self.assertLess(result['stats']['correspondenceQueries'],len(v)*12)
        self.assertEqual(result['stats']['historyScope'],'stage-sample')

    def test_small_mesh_skips_coarse_levels_and_project_mode_compatibility(self):
        source,target,pairs,_=dense_fixture(9)
        result=wrap(source,target,pairs,5,4,solver_mode='multistage')
        self.assertEqual(result['stats']['stageCount'],1)
        p=project_fixture();del p['settings']['solverMode']
        self.assertEqual(validate_project(p)['settings']['solverMode'],'single')
        p['settings']['solverMode']='multistage'
        self.assertEqual(validate_project(p)['settings']['solverMode'],'multistage')
        p['settings']['solverMode']='bad'
        with self.assertRaises(ValueError):validate_project(p)

    def test_multistage_does_not_bypass_conflicting_hard_points(self):
        v=np.array([[0.,0,0],[1,0,0],[1,1,0],[0,1,0]])
        text='\n'.join(['v '+' '.join(map(str,p)) for p in v]+['f 1 2 3','f 1 3 4'])
        with self.assertRaisesRegex(ValueError,'翻面'):wrap(text,text,[[0,0],[1,2],[2,1],[3,3]],5,solver_mode='multistage')


if __name__=='__main__':unittest.main()
