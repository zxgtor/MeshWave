import unittest
import numpy as np
from mesh_health import diagnose_mesh, repair_mesh
from wrap_core import parse_obj
from test_core import obj


def damaged():
    return '\n'.join(['v 0 0 0','v 1 0 0','v 0 1 0','v 0 -1 0','v 0 0 1','v 3 3 3','v .5 0 0','v nan 0 0',
        'f 1 2 3','f 2 1 4','f 1 2 5','f 3 2 1','f 1 2 7','f 1 2 99','f 1 x 3','f 1 2 8'])


class MeshHealthTests(unittest.TestCase):
    def test_detects_and_highlights_nonmanifold_invalid_and_isolated(self):
        report=diagnose_mesh({'text':damaged()});c=report['counts']
        self.assertEqual(c['nonManifoldEdges'],1);self.assertEqual(c['invalidFaces'],5)
        self.assertEqual(c['isolatedVertices'],2);self.assertEqual(c['invalidVertices'],1);self.assertEqual(c['duplicateFaces'],1)
        self.assertEqual(len(report['highlights']['nonManifoldEdges']),2)
        self.assertEqual(len(report['highlights']['isolatedVertices']),2)
        self.assertTrue(report['details']);self.assertTrue(report['highlights']['invalidSegments'])

    def test_repair_cleans_all_issues_without_deleting_valid_surface_triangles(self):
        before=damaged();result=repair_mesh({'text':before});self.assertFalse(result['report']['hasIssues'])
        v,f=parse_obj(result['text']);self.assertEqual(len(f),3);self.assertTrue(np.isfinite(v).all())
        expected={tuple(sorted(t)) for t in [((0.,0.,0.),(1.,0.,0.),(0.,1.,0.)),((0.,0.,0.),(1.,0.,0.),(0.,-1.,0.)),((0.,0.,0.),(1.,0.,0.),(0.,0.,1.))]}
        self.assertEqual({tuple(sorted(tuple(p) for p in v[t])) for t in f},expected)
        self.assertEqual(before,damaged())

    def test_open_boundaries_are_valid_not_nonmanifold(self):
        text=obj([[0,0,0],[1,0,0],[0,1,0]],[[0,1,2]])
        self.assertFalse(diagnose_mesh({'text':text})['hasIssues'])

    def test_far_isolated_outlier_does_not_make_small_valid_faces_degenerate(self):
        text=obj([[0,0,0],[1e-8,0,0],[0,1e-8,0],[1e12,0,0]],[[0,1,2]])
        before=diagnose_mesh({'text':text});self.assertEqual(before['counts']['invalidFaces'],0);self.assertEqual(before['counts']['isolatedVertices'],1)
        result=repair_mesh({'text':text});self.assertEqual(result['report']['triangleCount'],1);self.assertEqual(result['report']['vertexCount'],3)

    def test_bowtie_vertex_fans_are_split_without_moving_positions(self):
        text=obj([[0,0,0],[1,0,0],[0,1,0],[-1,0,0],[0,-1,0]],[[0,1,2],[0,3,4]])
        self.assertEqual(diagnose_mesh({'text':text})['counts']['nonManifoldVertices'],1)
        result=repair_mesh({'text':text});self.assertFalse(result['report']['hasIssues']);self.assertEqual(len(result['mesh']['vertices']),6)

    def test_winding_repair_preserves_corner_uvs_and_materials(self):
        text='mtllib skin.mtl\nv 0 0 0\nv 1 0 0\nv 0 1 0\nv 0 -1 0\nvt 0 0\nvt 1 0\nvt 0 1\nvt 1 1\nusemtl skin\ng face\nf 1/1 2/2 3/3\nf 1/1 2/2 4/4\n'
        self.assertEqual(diagnose_mesh({'text':text})['counts']['inconsistentEdges'],1)
        result=repair_mesh({'text':text});self.assertFalse(result['report']['hasIssues']);self.assertTrue(result['mesh']['hasUV'])
        self.assertIn('mtllib skin.mtl',result['text']);self.assertIn('usemtl skin',result['text'])
        v,f,uv,uf=parse_obj(result['text'],True)
        for face,texture in zip(f,uf):
            for p,t in zip(v[face],uv[texture]):
                expected={(0,0,0):(0,0),(1,0,0):(1,0),(0,1,0):(0,1),(0,-1,0):(1,1)}[tuple(p)]
                np.testing.assert_array_equal(t,expected)

    def test_negative_indices_and_polygon_triangulation(self):
        text='v 0 0 0\nv 1 0 0\nv 1 1 0\nv 0 1 0\nv 9 9 9\nf -5 -4 -3 -2\n'
        result=repair_mesh({'text':text});self.assertEqual(result['report']['triangleCount'],2);self.assertEqual(len(result['mesh']['vertices']),4)

    def test_invalid_uvs_drop_only_bad_refs_geometry_retained(self):
        text='v 0 0 0\nv 1 0 0\nv 0 1 0\nvt nan 0\nvt 0 0\nf 1/1 2/2 3/99\n'
        self.assertGreater(diagnose_mesh({'text':text})['counts']['invalidUVs'],0)
        result=repair_mesh({'text':text});self.assertEqual(result['report']['triangleCount'],1);self.assertFalse(result['mesh']['hasUV']);self.assertFalse(result['report']['hasIssues'])

    def test_entirely_invalid_mesh_has_diagnosis_but_no_applicable_repair(self):
        text='v 0 0 0\nv 1 0 0\nv 2 0 0\nf 1 2 3\n'
        self.assertTrue(diagnose_mesh({'text':text})['hasIssues'])
        with self.assertRaises(ValueError):repair_mesh({'text':text})

    def test_nonorientable_strip_is_cut_into_orientable_patches(self):
        n=7;v=[];f=[]
        for i in range(n):
            angle=2*np.pi*i/n
            for sign in [-1,1]:
                width=.2*sign;v.append([(1+width*np.cos(angle/2))*np.cos(angle),(1+width*np.cos(angle/2))*np.sin(angle),width*np.sin(angle/2)])
        for i in range(n):
            a,b=2*i,2*i+1;c,d=(2*i+2,2*i+3) if i<n-1 else (1,0)
            f.extend([[a,b,c],[b,d,c]])
        result=repair_mesh({'text':obj(v,f)});self.assertFalse(result['report']['hasIssues']);self.assertEqual(result['report']['triangleCount'],len(f))
