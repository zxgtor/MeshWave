import unittest
import numpy as np
import tempfile
import threading
import time
from pathlib import Path
from scipy import sparse
from point_constraints import validate_pairs,positions,solve_affine
from wrap_core import wrap,parse_obj
from brush_support import prepare_brush
from curves import generate_curve_pairs
from project import validate_project
from temporal import smooth_frame
from frame_repair import repair_frame
from batch_jobs import BatchManager,constraints_manifest
from point_constraints import pair_support


def obj(v,f):return '\n'.join(['v '+' '.join(map(str,p)) for p in v]+['f '+' '.join(str(i+1) for i in face) for face in f])
def handle(face,bary):return {'face':face,'bary':bary}
def grid(size=6):
    v=np.array([[x/(size-1),y/(size-1),0] for y in range(size) for x in range(size)],float)
    f=np.array([[y*size+x,y*size+x+1,(y+1)*size+x+1] if k==0 else [y*size+x,(y+1)*size+x+1,(y+1)*size+x] for y in range(size-1) for x in range(size-1) for k in range(2)])
    target=v.copy();target[:,2]=.02*np.sin(v[:,0]*3)*np.cos(v[:,1]*2)
    ids=[0,len(f)//3,len(f)-1];pairs=[[handle(i,[.2,.3,.5]),handle(i,[.2,.3,.5])] for i in ids]
    return v,f,target,pairs


class SurfaceConstraintTests(unittest.TestCase):
    def test_exact_interior_constraints_in_both_solvers(self):
        for mode,size in [('single',6),('multistage',25)]:
            v,f,target,pairs=grid(size);r=wrap(obj(v,f),obj(target,f),pairs,5,4,solver_mode=mode)
            actual=positions(np.asarray(r['vertices']),f,[p[0] for p in pairs]);expected=positions(target,f,[p[1] for p in pairs])
            np.testing.assert_allclose(actual,expected,atol=1e-8)
            self.assertLess(r['stats']['landmarkMaxError'],1e-8)
            body={'source':obj(v,f),'target':obj(target,f),'pairs':pairs,'vertices':r['vertices']}
            reference=prepare_brush(body);self.assertGreater(len(reference['locked']),len(pairs))
            body['vertices'][0][2]+=.1
            with self.assertRaises(ValueError):prepare_brush(body)

    def test_affine_redundancy_and_conflicts(self):
        c=sparse.csr_matrix([[1,0],[0,1],[.5,.5]])
        goal=np.array([[0,0,0],[2,0,0],[1,0,0]],float)
        np.testing.assert_allclose(solve_affine(sparse.eye(2),np.zeros((2,3)),c,goal),goal[:2])
        goal[-1,2]=1
        with self.assertRaisesRegex(ValueError,'冲突'):solve_affine(sparse.eye(2),np.zeros((2,3)),c,goal)

    def test_edge_alias_duplicates_and_invalid_handles(self):
        v=np.array([[0,0,0],[1,0,0],[1,1,0],[0,1,0]],float);f=np.array([[0,1,2],[0,2,3]])
        meshes={'source':(v,f),'target':(v,f)}
        pairs=[[handle(0,[.5,0,.5]),0],[handle(1,[.5,.5,0]),1]]
        with self.assertRaises(ValueError):validate_pairs(pairs,meshes)
        for p in [handle(-1,[.2,.3,.5]),handle(0,[-.1,.5,.6]),handle(0,[.1,.1,.1]),handle(0,[float('nan'),0,1])]:
            with self.assertRaises(ValueError):validate_pairs([[p,0]],meshes)

    def curve_body(self,closed=False):
        v=[[0,0,0],[1,0,0],[1,1,0],[0,1,0]];f=[[0,1,2],[0,2,3]]
        controls=[handle(0,[.8,.1,.1]),handle(1,[.2,.4,.4]),handle(0,[.1,.8,.1])]
        return {'source':obj(v,f),'target':obj(v,f),'pairs':[],'curves':[{'name':'lip','type':'spline','count':9,'closed':closed,'source':controls,'target':controls}]}

    def test_cubic_surface_spline_is_not_vertex_or_edge_sampling(self):
        body=self.curve_body();result=generate_curve_pairs(body);v,f=parse_obj(body['source'])
        points=positions(v,f,[p[0] for p in result['pairs']])
        self.assertEqual(len(points),9);self.assertGreater(points[:,1].max(),.5)
        self.assertGreater(min(np.linalg.norm(points[4]-v,axis=1)),.1)
        np.testing.assert_allclose(points[:,2],0,atol=1e-12)
        self.assertGreater(len(result['paths'][0]['source']),60)
        for a,b in result['pairs']:self.assertEqual(a,b)

    def test_closed_spline_has_no_duplicate_end_sample(self):
        body=self.curve_body(True);r=generate_curve_pairs(body)
        self.assertEqual(len(r['pairs']),9)
        self.assertNotEqual(r['pairs'][0],r['pairs'][-1])

    def test_spline_rejects_disconnected_layers_and_excluded_controls(self):
        body=self.curve_body();body['excludedFaces']={'source':[0],'target':[]}
        with self.assertRaises(ValueError):generate_curve_pairs(body)
        v=[[0,0,0],[1,0,0],[0,1,0],[0,0,.01],[1,0,.01],[0,1,.01]];f=[[0,1,2],[3,4,5]]
        body={'source':obj(v,f),'target':obj(v,f),'pairs':[],'curves':[{'name':'bad','type':'spline','source':[handle(0,[.2,.3,.5]),handle(1,[.2,.3,.5])],'target':[]}] ,'pathOnly':True}
        with self.assertRaisesRegex(ValueError,'路径'):generate_curve_pairs(body)

    def test_project_surface_pending_and_splines_roundtrip(self):
        body=self.curve_body();v,f=parse_obj(body['source'])
        project={'format':'facewrap-lite','version':2,'models':{side:{'text':body[side],'name':side+'.obj'} for side in ['source','target']},'pairs':[],'curves':body['curves'],'pending':handle(0,[.3,.3,.4])}
        r=validate_project(project)
        self.assertEqual(r['pending'],project['pending']);self.assertEqual(r['curves'][0]['type'],'spline')
        np.testing.assert_allclose(positions(v,f,[r['pending']]),[[.7,.4,0]])

    def test_revalidation_preserves_encoded_barycentric_floats(self):
        v,f,target,pairs=grid()
        pairs[0][0]['bary']=[.5990909439815733,.25687520972139133,.1440338462970353]
        normalized=validate_pairs(pairs,{'source':(v,f),'target':(target,f)})
        self.assertEqual(normalized,pairs)

    def test_project_rejects_pending_shared_edge_alias(self):
        body=self.curve_body()
        project={'format':'facewrap-lite','version':2,'models':{side:{'text':body[side],'name':side+'.obj'} for side in ['source','target']},'pairs':[[handle(0,[.5,0,.5]),0]],'pending':handle(1,[.5,.5,0])}
        with self.assertRaisesRegex(ValueError,'冲突'):validate_project(project)

    def test_temporal_and_repair_keep_surface_constraints(self):
        v,f,target,pairs=grid(9);source=obj(v,f);scan=obj(target,f)
        current=np.array(wrap(source,scan,pairs,5)['vertices'])
        body={'source':source,'target':scan,'pairs':pairs,'vertices':current.tolist(),'excludedFaces':{},'normalAngle':60}
        before=current.copy();after=current.copy();before[:,2]+=.002*np.sin(v[:,0]*3);after[:,2]-=.001*np.sin(v[:,0]*3)
        smooth=smooth_frame({**body,'settings':{'mode':'bidirectional'}},before,after)
        locked=pair_support(pairs,0,f)
        np.testing.assert_array_equal(np.array(smooth['vertices'])[locked],current[locked])
        repaired=repair_frame({**body,'settings':{'iterations':5,'smoothness':4,'normalAngle':60},'distanceRatio':.02},current,current,.5)
        np.testing.assert_allclose(positions(np.array(repaired['vertices']),f,[p[0] for p in pairs]),positions(target,f,[p[1] for p in pairs]),atol=1e-8)

    def test_batch_roundtrip_uses_surface_pairs_and_version_two_manifest(self):
        v,f,target,pairs=grid(6);source=obj(v,f);scan=obj(target,f)
        manifest=constraints_manifest({'source':source,'target':scan,'pairs':pairs,'name':'scan.obj'})
        self.assertEqual(manifest['version'],2);self.assertEqual(manifest['items'][0]['pairs'],pairs)
        with tempfile.TemporaryDirectory() as temp:
            manager=BatchManager(Path(temp),threading.BoundedSemaphore(1))
            job=manager.create({'source':{'name':'template.obj','text':source},'referenceTarget':scan,'pairs':pairs,'mode':'sequence','names':['scan.obj'],'settings':{'iterations':5}})
            manager.add({'jobId':job['id'],'name':'scan.obj','text':scan});manager.start(job['id'])
            deadline=time.monotonic()+15
            while time.monotonic()<deadline:
                result=manager.status(job['id'])
                if result['status'] in ('completed','completed_with_errors','failed'):break
                time.sleep(.01)
            self.assertEqual(result['status'],'completed',result)
            item=result['items'][0];vertices,_=parse_obj((Path(temp)/job['id']/item['resultFile']).read_text(encoding='utf-8'))
            np.testing.assert_allclose(positions(vertices,f,[p[0] for p in pairs]),positions(target,f,[p[1] for p in pairs]),atol=1e-8)

    def test_optical_flow_preserves_surface_support_vertices(self):
        from test_optical_flow import flow_fixture
        from optical_flow import refine_texture
        body,_,faces=flow_fixture(side=17)
        body['pairs'].append([handle(95,[.2,.3,.5]),handle(95,[.2,.3,.5])])
        body['vertices']=wrap(body['source'],body['target'],body['pairs'],5)['vertices']
        before=np.asarray(body['vertices']);result=refine_texture(body)
        ids=pair_support(body['pairs'],0,faces)
        np.testing.assert_array_equal(np.array(result['vertices'])[ids],before[ids])


if __name__=='__main__':unittest.main()
