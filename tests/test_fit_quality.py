import copy
import unittest
import numpy as np
from fit_quality import inspect_fit


def obj(vertices, faces):
    return '\n'.join(['v '+' '.join(map(str, p)) for p in vertices] +
                     ['f '+' '.join(str(i+1) for i in f) for f in faces])


class FitQualityTests(unittest.TestCase):
    def body(self):
        vertices=[[.25,.25,1],[.5,.25,1],[.25,.5,1]]
        return {'source':obj(vertices,[[0,1,2]]),
                'target':obj([[0,0,0],[2,0,0],[0,2,0]],[[0,1,2]]),
                'vertices':vertices,'normalAngle':60}

    def test_distance_to_triangle_interior_and_read_only(self):
        body=self.body();before=copy.deepcopy(body);r=inspect_fit(body)
        np.testing.assert_allclose(r['distances'],[1,1,1],atol=1e-12)
        np.testing.assert_allclose(r['normalAngles'],[0,0,0],atol=1e-6)
        self.assertEqual(body,before)

    def test_target_exclusions_and_degenerate_faces(self):
        body=self.body()
        body['target']=obj([[0,0,0],[2,0,0],[0,2,0],[0,0,-2],[2,0,-2],[0,2,-2]],[[0,1,2],[3,4,5],[0,0,0]])
        body['excludedFaces']={'source':[],'target':[0]}
        r=inspect_fit(body)
        np.testing.assert_allclose(r['distances'],[3,3,3])
        np.testing.assert_allclose(r['normalAngles'],[0,0,0],atol=1e-6)
        self.assertEqual(r['excludedTargetFaces'],1)
        self.assertEqual(r['ignoredDegenerateTargetFaces'],1)

    def test_source_exclusions_include_boundary_and_skip_unused_vertices(self):
        body=self.body();body['vertices']=[[.1,.1,1],[.6,.1,1],[.6,.6,1],[.1,.6,1],[9,9,9]]
        body['source']=obj(body['vertices'],[[0,1,2],[0,2,3]])
        body['excludedFaces']={'source':[0],'target':[]}
        r=inspect_fit(body)
        self.assertEqual(r['distances'],[None,None,None,1.,None])
        self.assertEqual(r['excludedVertices'],4)

    def test_reversed_normals_do_not_hide_distance_and_collapsed_normals_unknown(self):
        body=self.body();body['target']=obj([[0,0,0],[2,0,0],[0,2,0]],[[0,2,1]])
        r=inspect_fit(body)
        np.testing.assert_allclose(r['distances'],[1,1,1])
        np.testing.assert_allclose(r['normalAngles'],[180,180,180])
        body['vertices']=[[.1,.1,1]]*3
        self.assertEqual(inspect_fit(body)['normalAngles'],[None,None,None])

    def test_scale_translation_and_all_excluded(self):
        body=self.body();scale=1000;offset=np.array([1e7,-2e7,3e7])
        v=np.asarray(body['vertices'])*scale+offset
        body['source']=obj(v,[[0,1,2]]);body['vertices']=v.tolist()
        body['target']=obj(np.asarray([[0,0,0],[2,0,0],[0,2,0]])*scale+offset,[[0,1,2]])
        np.testing.assert_allclose(inspect_fit(body)['distances'],[1000]*3,atol=1e-6)
        body['excludedFaces']={'source':[0],'target':[]}
        self.assertEqual(inspect_fit(body)['distances'],[None]*3)

    def test_invalid_result_and_settings_rejected(self):
        for value in [[],[[0,0,0]],[[float('nan'),0,0]]*3]:
            body=self.body();body['vertices']=value
            with self.assertRaises(ValueError):inspect_fit(body)
        body=self.body();body['normalAngle']=float('nan')
        with self.assertRaises(ValueError):inspect_fit(body)
        body=self.body();body['excludedFaces']={'source':[],'target':[0]}
        with self.assertRaises(ValueError):inspect_fit(body)


if __name__=='__main__':unittest.main()
