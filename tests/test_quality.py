import unittest
import numpy as np
from surface import TriangleSurface, FlipGuard, closest_triangle_points, face_vectors
from wrap_core import wrap, parse_obj, similarity
from project import validate_project
from test_core import fixture, obj
from test_features import project_fixture


class QualityTests(unittest.TestCase):
    def test_analytic_face_edge_and_vertex_distances(self):
        tri=np.array([[[0.,0,0],[2,0,0],[0,2,0]]])
        surface=TriangleSurface(tri.reshape(-1,3),np.array([[0,1,2]]))
        points=np.array([[.5,.5,3],[1,-2,0],[-1,-1,0],[2,2,0]])
        closest,distance,_=surface.query(points)
        np.testing.assert_allclose(closest,[[.5,.5,0],[1,0,0],[0,0,0],[1,1,0]],atol=1e-12)
        np.testing.assert_allclose(distance,[3,2,np.sqrt(2),np.sqrt(2)],atol=1e-12)

    def test_long_triangle_not_lost_by_centroid_seed(self):
        tri=[[[0,0,0],[1000,0,0],[0,1000,0]]]
        tri.extend([[[1+i*.01,1,1],[1.01+i*.01,1,1],[1+i*.01,1.01,1]] for i in range(40)])
        tri=np.asarray(tri,float)
        surface=TriangleSurface(tri.reshape(-1,3),np.arange(tri.size//3).reshape(-1,3),leaf_size=2)
        closest,distance,face=surface.query(np.array([[.1,.1,.01]]))
        self.assertEqual(face[0],0)
        np.testing.assert_allclose(closest,[[.1,.1,0]],atol=1e-12)
        self.assertAlmostEqual(distance[0],.01)

    def test_bvh_matches_exhaustive_search_with_normal_filter(self):
        rng=np.random.default_rng(71)
        tri=rng.normal(size=(93,3,3));points=rng.normal(size=(39,3))
        surface=TriangleSurface(tri.reshape(-1,3),np.arange(len(tri)*3).reshape(-1,3),leaf_size=3)
        normals=rng.normal(size=points.shape);normals/=np.linalg.norm(normals,axis=1)[:,None]
        q=closest_triangle_points(points[:,None,:],tri[None,:,:,:])
        d2=np.sum((q-points[:,None,:])**2,axis=2)
        for sn in [None,normals]:
            expected=d2.copy()
            if sn is not None:expected[sn@surface.normals.T<.5]=np.inf
            closest,distance,faces=surface.query(points,sn,.5)
            np.testing.assert_allclose(distance,np.sqrt(expected.min(axis=1)),atol=1e-12)
            np.testing.assert_allclose(np.linalg.norm(points-closest,axis=1),distance,atol=1e-12)

    def test_normals_skip_nearer_opposite_surface(self):
        tri=np.array([[[0,0,0],[0,2,0],[2,0,0]],[[0,0,1],[2,0,1],[0,2,1]]],float)
        surface=TriangleSurface(tri.reshape(-1,3),np.array([[0,1,2],[3,4,5]]))
        point=np.array([[.2,.2,.1]])
        self.assertEqual(surface.query(point)[2][0],0)
        q,d,f=surface.query(point,np.array([[0.,0,1]]),.5)
        self.assertEqual(f[0],1);self.assertAlmostEqual(d[0],.9)
        np.testing.assert_allclose(q,[[.2,.2,1]])

    def test_no_eligible_normal_and_degenerate_target(self):
        v=np.array([[0.,0,0],[1,0,0],[0,1,0],[5,5,5]])
        surface=TriangleSurface(v,np.array([[0,1,2],[3,3,3]]))
        self.assertEqual(surface.ignored_degenerate,1)
        _,d,f=surface.query(np.array([[.2,.2,1]]),np.array([[0.,0,-1]]))
        self.assertTrue(np.isinf(d[0]));self.assertEqual(f[0],-1)
        with self.assertRaises(ValueError):TriangleSurface(v,np.array([[3,3,3]]))

    def test_guard_limits_flip_and_continuous_collapse(self):
        base=np.array([[0.,0,0],[1,0,0],[0,1,0]])
        guard=FlipGuard(base,np.array([[0,1,2]]))
        for proposal in [np.array([[0.,0,0],[1,0,0],[0,-1,0]]),np.array([[0.,0,0],[-1,0,0],[0,-1,0]])]:
            alpha=guard.safe_step(base,proposal)
            self.assertGreater(alpha,0);self.assertLess(alpha,.5)
            for t in np.linspace(0,alpha,51):self.assertGreaterEqual(guard.minimum_ratio(base+t*(proposal-base)),.01)
        # The second endpoint is positively oriented, but its path passes through collapse.
        self.assertAlmostEqual(guard.minimum_ratio(proposal),1)

    def test_infeasible_hard_landmarks_rejected(self):
        v=np.array([[0.,0,0],[1,0,0],[1,1,0],[0,1,0]])
        text=obj(v,[[0,1,2],[0,2,3]])
        with self.assertRaisesRegex(ValueError,'翻面'):
            wrap(text,text,[[0,0],[1,2],[2,1],[3,3]],5)

    def test_reversed_target_winding_rejected(self):
        a,b,pairs,_=fixture();v,f=parse_obj(b)
        with self.assertRaisesRegex(ValueError,'朝向'):
            wrap(a,obj(v,f[:,::-1]),pairs,5)

    def test_safe_result_preserves_pins_regions_and_orientation(self):
        a,b,pairs,_=fixture();source,faces=parse_obj(a);target,_=parse_obj(b);pairs=np.asarray(pairs)
        r,k,origin,destination=similarity(source[pairs[:,0]],target[pairs[:,1]])
        aligned=(source-origin)@r*k+destination
        result=wrap(a,b,pairs.tolist(),15,4,{'source':[0],'target':[0]},55)
        vertices=np.array(result['vertices']);guard=FlipGuard(aligned,faces)
        self.assertGreaterEqual(guard.minimum_ratio(vertices),.01-1e-10)
        np.testing.assert_allclose(vertices[pairs[:,0]],target[pairs[:,1]],atol=1e-10)
        np.testing.assert_allclose(vertices[np.unique(faces[0])],aligned[np.unique(faces[0])],atol=1e-10)
        self.assertFalse(result['stats']['sampledSurface'])
        self.assertLess(result['stats']['finalMeanDistance'],result['stats']['initialMeanDistance']*.7)

    def test_project_normal_angle_roundtrip_and_legacy_default(self):
        project=project_fixture();project['settings']['normalAngle']=75
        self.assertEqual(validate_project(project)['settings']['normalAngle'],75)
        del project['settings']['normalAngle']
        self.assertEqual(validate_project(project)['settings']['normalAngle'],60)
        for value in [0,90,False,float('nan')]:
            project['settings']['normalAngle']=value
            with self.assertRaises(ValueError):validate_project(project)


if __name__=='__main__':unittest.main()
