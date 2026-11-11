import copy
import unittest
import numpy as np
from project import validate_project
from wrap_core import parse_obj, wrap, similarity
from surface import TriangleSurface
from test_core import fixture


def project_fixture():
    a,b,pairs,_=fixture()
    return {'format':'facewrap-lite','version':1,
        'models':{'source':{'name':'template.obj','text':a},'target':{'name':'scan.obj','text':b}},
        'pairs':pairs,'pending':None,'excludedFaces':{'source':[0],'target':[0]},
        'settings':{'iterations':15,'smoothness':4,'normalAngle':60,'solverMode':'single','bake':{'resolution':1024,'padding':8,'distanceRatio':.02},'brush':{'radiusPercent':5,'strength':30},'flow':{'resolution':384,'iterations':2,'strength':50,'distancePercent':3,'views':3}},'result':None}


class FeatureTests(unittest.TestCase):
    def test_excluded_source_stays_at_aligned_pose(self):
        a,b,pairs,_=fixture()
        source,faces=parse_obj(a);target,_=parse_obj(b)
        pair=np.asarray(pairs)
        rotation,scale,origin,destination=similarity(source[pair[:,0]],target[pair[:,1]])
        aligned=(source-origin)@rotation*scale+destination
        result=wrap(a,b,pairs,15,4,{'source':[0],'target':[0]})
        vertices=np.array(result['vertices'])
        np.testing.assert_allclose(vertices[np.unique(faces[0])],aligned[np.unique(faces[0])],atol=1e-10)
        np.testing.assert_allclose(vertices[pair[:,0]],target[pair[:,1]],atol=1e-10)
        self.assertGreater(np.linalg.norm(vertices-aligned),.01)
        self.assertEqual(result['stats']['excludedSourceVertices'],3)
        self.assertEqual(result['stats']['excludedTargetFaces'],1)

    def test_surface_omits_vertices_of_excluded_faces(self):
        vertices=np.array([[0,0,0],[1,0,0],[0,1,0],[0,0,10],[1,0,10],[0,1,10]])
        closest,distance,_=TriangleSurface(vertices,np.array([[0,1,2]])).query(np.array([[.2,.2,10]]))
        self.assertEqual(float(closest[0,2]),0)
        self.assertAlmostEqual(float(distance[0]),10)

    def test_masks_reject_conflicts_and_invalid_faces(self):
        a,b,pairs,_=fixture();_,f=parse_obj(a)
        conflict=int(np.where(np.any(f==pairs[0][0],axis=1))[0][0])
        for mask in [{'source':[conflict]},{'target':[conflict]},{'source':[-1]},
                     {'target':[len(f)]},{'source':[.5]},{'source':[True]},
                     {'target':list(range(len(f)))}]:
            with self.subTest(mask=str(mask)[:70]):
                with self.assertRaises(ValueError):wrap(a,b,pairs,5,4,mask)

    def test_project_roundtrip_includes_result_and_regions(self):
        p=project_fixture()
        p['result']=wrap(p['models']['source']['text'],p['models']['target']['text'],p['pairs'],15,4,p['excludedFaces'])
        validated=validate_project(p)
        for key in ['pairs','excludedFaces','settings','pending']:self.assertEqual(validated[key],p[key])
        self.assertEqual(validated['result']['vertices'],p['result']['vertices'])
        self.assertEqual(validated['models']['source']['text'],p['models']['source']['text'])
        self.assertEqual(validated['models']['target']['text'],p['models']['target']['text'])

    def test_unfinished_project_can_save_pending_point_and_single_model(self):
        p=project_fixture();p['result']=None;p['pending']=2
        self.assertEqual(validate_project(p)['pending'],2)
        p['models']['target']=None;p['pairs']=[];p['excludedFaces']['target']=[]
        self.assertIsNone(validate_project(p)['models']['target'])
        p['models']['target']=p['models']['source'];p['models']['source']=None
        p['pending']=None;p['excludedFaces']['source']=[]
        self.assertIsNone(validate_project(p)['models']['source'])

    def test_malformed_project_rejected(self):
        modifications=[{'version':999},{'pairs':[[0,0],[0,1]]},{'pairs':[[99999,0]]},
            {'pending':0},{'pending':30},{'pending':False},{'excludedFaces':{'source':[-1]}},
            {'settings':{'iterations':51}},{'settings':{'iterations':20,'smoothness':float('nan')}},
            {'result':{'vertices':[[0,0,0]]}},{'models':{'source':None,'target':None}}]
        for modification in modifications:
            p=copy.deepcopy(project_fixture());p.update(modification)
            with self.subTest(modification=str(modification)):
                with self.assertRaises(ValueError):validate_project(p)


if __name__=='__main__':unittest.main()
