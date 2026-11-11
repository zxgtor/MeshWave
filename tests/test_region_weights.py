import unittest
import tempfile
import threading
import json
import numpy as np
from pathlib import Path
from wrap_core import wrap,parse_obj,similarity,exclusion_masks
from brush_support import prepare_brush
from project import validate_project
from batch_jobs import BatchManager
from multires import solve_stages
from scipy import sparse
from test_core import fixture,obj
from test_surface_constraints import grid

class RegionWeightTests(unittest.TestCase):
    def reference(self,a,b,p):
        v,f=parse_obj(a);t,_=parse_obj(b);ids=np.array(p)
        r,k,x,y=similarity(v[ids[:,0]],t[ids[:,1]])
        return (v-x)@r*k+y

    def test_fixed_and_follow_regions(self):
        a,b,p,_=fixture();v,f=parse_obj(a);ids=f[0];ref=self.reference(a,b,p)
        fixed=wrap(a,b,p,10,4,{'source':[0],'target':[]})
        follow=wrap(a,b,p,10,4,{'source':[0],'target':[],'sourceMode':'follow'})
        np.testing.assert_allclose(np.array(fixed['vertices'])[ids],ref[ids],atol=1e-10)
        self.assertGreater(np.linalg.norm(np.array(follow['vertices'])[ids]-ref[ids]),1e-4)
        np.testing.assert_allclose(np.array(follow['vertices'])[np.array(p)[:,0]],np.array(parse_obj(b)[0])[np.array(p)[:,1]],atol=1e-9)
        body={'source':a,'target':b,'pairs':p,'vertices':follow['vertices'],'excludedFaces':{'source':[0],'sourceMode':'follow'}}
        self.assertFalse(set(ids)&set(prepare_brush(body)['locked']))
        self.assertEqual(follow['stats']['followingSourceVertices'],3)

    def test_zero_weights_preserve_alignment_hard_points_take_priority(self):
        a,b,p,_=fixture();v,f=parse_obj(a);ref=self.reference(a,b,p)
        weights=[1.]*len(v);weights[0]=0;weights[p[0][0]]=0
        out=wrap(a,b,p,8,4,brush_weights=weights)
        np.testing.assert_allclose(out['vertices'][0],ref[0],atol=1e-10)
        np.testing.assert_allclose(np.array(out['vertices'])[np.array(p)[:,0]],parse_obj(b)[0][np.array(p)[:,1]],atol=1e-10)
        self.assertTrue(out['stats']['weightedGeometry'])

    def test_fractional_weights_reduce_surface_attraction(self):
        # Boundary landmarks fix alignment; a smooth central bump provides a
        # known non-rigid signal independent of pose.
        v,f,_,_=grid(9);t=v.copy();t[:,2]=.05*np.sin(np.pi*v[:,0])*np.sin(np.pi*v[:,1]);p=[[0,0],[8,8],[72,72],[80,80]]
        outputs=[]
        for w in [0,.05,1]:
            result=wrap(obj(v,f),obj(t,f),p,5,12,brush_weights=[w]*len(v))
            outputs.append(np.array(result['vertices'])[40,2])
        self.assertAlmostEqual(outputs[0],0,places=10)
        self.assertGreater(outputs[1],outputs[0]+1e-5)
        self.assertGreater(outputs[2],outputs[1]+1e-4)

    def test_barycentric_constraints_override_protected_supports_multistage(self):
        from point_constraints import positions,pair_support
        v,f,t,p=grid(25);weights=np.ones(len(v));weights[pair_support(p,0,f)]=0;weights[350]=0
        result=wrap(obj(v,f),obj(t,f),p,5,4,solver_mode='multistage',brush_weights=weights.tolist())
        np.testing.assert_allclose(positions(np.array(result['vertices']),f,[pair[0] for pair in p]),positions(t,f,[pair[1] for pair in p]),atol=1e-9)
        self.assertGreater(result['stats']['stageCount'],1)

    def test_coarse_samples_omit_follow_region_and_weight_mass(self):
        v,f,t,p=grid(25);n=len(v);edges=np.vstack([f[:,[0,1]],f[:,[1,2]],f[:,[2,0]]]);edges=np.vstack([edges,edges[:,::-1]])
        graph=sparse.coo_matrix((np.ones(len(edges)),(edges[:,0],edges[:,1])),shape=(n,n)).tocsr()
        weights=np.full(n,.25);weights[100:350]=0
        stages=solve_stages(graph,np.arange(n),v,np.array([0,24,600]),weights>0,5,'multistage',weights)
        for stage in stages:
            self.assertTrue(np.all(weights[stage['ids']]>0))
        self.assertAlmostEqual(stages[0]['mass'].sum(),weights.sum()+weights[[0,24,600]].sum())

    def test_project_legacy_defaults_and_v3_roundtrip(self):
        a,b,p,_=fixture();base={'format':'facewrap-lite','version':1,'models':{side:{'name':side+'.obj','text':text} for side,text in [('source',a),('target',b)]},'pairs':p}
        self.assertEqual(validate_project(base)['excludedFaces'].get('sourceMode','fixed'),'fixed')
        base.update(version=3,excludedFaces={'source':[0],'sourceMode':'follow'},brushWeights=[.5]*len(parse_obj(a)[0]))
        out=validate_project(base);self.assertEqual(out['excludedFaces']['sourceMode'],'follow');self.assertEqual(out['brushWeights'],base['brushWeights'])
        for bad in ['bad',None,{},True]:
            base['excludedFaces']['sourceMode']=bad
            with self.assertRaises(ValueError):validate_project(base)

    def test_follow_temporal_and_repair_do_not_reproject_to_scan(self):
        from test_optical_flow import flow_fixture
        from temporal import smooth_frame
        from frame_repair import repair_frame
        body,_,faces=flow_fixture(side=17,shift=0);v=np.array(body['vertices'])
        selected=270;ids=faces[selected];wave=np.sin(v[:,0]*np.pi)*np.sin(v[:,1]*np.pi)
        neighbor=v.copy();neighbor[:,2]+=.006*wave
        body.update(excludedFaces={'source':[selected],'sourceMode':'follow'},normalAngle=60,settings={'strength':60,'distancePercent':5})
        smoothed=smooth_frame(body,neighbor)
        self.assertGreater(np.array(smoothed['vertices'])[ids,2].mean(),.0001)
        fixed=smooth_frame({**body,'excludedFaces':{'source':[selected],'sourceMode':'fixed'}},neighbor)
        np.testing.assert_array_equal(np.array(fixed['vertices'])[ids],v[ids])
        repaired=repair_frame({**body,'settings':{'iterations':5,'smoothness':4,'normalAngle':60},'distanceRatio':.02},neighbor,neighbor,.5)
        self.assertGreater(np.array(repaired['vertices'])[ids,2].mean(),.001)
        np.testing.assert_array_equal(np.array(repaired['vertices'])[np.array(body['pairs'])[:,0]],v[np.array(body['pairs'])[:,0]])

    def test_invalid_weights_and_mode_rejected(self):
        a,b,p,_=fixture();n=len(parse_obj(a)[0])
        for weights in [[],[True]*n,[float('nan')]*n,[-.1]*n,[1.1]*n]:
            with self.assertRaises(ValueError):wrap(a,b,p,5,brush_weights=weights)
        with self.assertRaises(ValueError):wrap(a,b,p,5,excluded_faces={'sourceMode':'bad'})

    def test_batch_uses_persisted_geometry_weights_and_follow_mode(self):
        a,b,p,_=fixture();n=len(parse_obj(a)[0]);weights=[1.]*n;weights[10]=0
        with tempfile.TemporaryDirectory() as tmp:
            manager=BatchManager(Path(tmp),threading.Semaphore(1));job=manager.create({'mode':'sequence','source':{'name':'template.obj','text':a},'referenceTarget':b,'pairs':p,'excludedSourceFaces':[0],'sourceRegionMode':'follow','brushWeights':weights,'settings':{'iterations':5,'smoothness':4,'normalAngle':60,'solverMode':'single'},'names':['scan.obj']})
            manager.add({'jobId':job['id'],'name':'scan.obj','text':b})
            manager._run(job['id'])
            result=manager.status(job['id']);self.assertEqual(result['items'][0]['status'],'succeeded',result)
            config=json.loads((Path(tmp)/job['id']/'config.json').read_text())
            self.assertEqual(config['sourceRegionMode'],'follow');self.assertEqual(config['brushWeights'],weights)
            path=Path(tmp)/job['id']/result['items'][0]['resultFile'];vertices,_=parse_obj(path.read_text())
            np.testing.assert_allclose(vertices[10],self.reference(a,b,p)[10],atol=1e-8)

if __name__=='__main__':unittest.main()
