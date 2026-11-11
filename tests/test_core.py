import unittest
import numpy as np
from wrap_core import parse_obj, export_obj, wrap


def obj(v, f):
    return '\n'.join(['v ' + ' '.join(map(str, p)) for p in v] +
                     ['f ' + ' '.join(str(i + 1) for i in p) for p in f])


def fixture():
    v, f = [], []
    cols, rows = 18, 16
    for i in range(rows):
        t = np.pi * (i + .3) / (rows - .4)
        for j in range(cols):
            p = 2 * np.pi * j / cols
            v.append([np.sin(t)*np.cos(p), 1.2*np.cos(t), .8*np.sin(t)*np.sin(p)])
    for i in range(rows-1):
        for j in range(cols):
            a, b = i*cols+j, i*cols+(j+1)%cols
            f.extend([[a,b,a+cols],[b,b+cols,a+cols]])
    source=np.array(v)
    target=source.copy()
    target[:,0]*=1.15 + .08*source[:,1]
    target[:,2]+= .12*np.exp(-source[:,1]**2*3)
    target+=np.array([.5,-.2,.1])
    ids=[30,65,99,140,190,230]
    return obj(source,f),obj(target,f),[[i,i] for i in ids],target


class CoreTests(unittest.TestCase):
    def test_nonrigid_fit_improves_and_pins_are_exact(self):
        a,b,pairs,target=fixture()
        result=wrap(a,b,pairs,15,4)
        v=np.array(result['vertices'])
        self.assertTrue(np.isfinite(v).all())
        self.assertEqual(v.shape,target.shape)
        self.assertLess(result['stats']['finalMeanDistance'],result['stats']['initialMeanDistance']*.7)
        np.testing.assert_allclose(v[np.array(pairs)[:,0]],target[np.array(pairs)[:,1]],atol=1e-10)

    def test_similarity_pose_recovery(self):
        a,_,pairs,_=fixture()
        v,f=parse_obj(a)
        angle=.6
        rotation=np.array([[np.cos(angle),0,np.sin(angle)],[0,1,0],[-np.sin(angle),0,np.cos(angle)]])
        target=v@rotation*2+np.array([3,4,5])
        result=wrap(a,obj(target,f),pairs,5,4)
        np.testing.assert_allclose(result['vertices'],target,atol=1e-8)

    def test_export_preserves_polygon_uv_and_negative_indices(self):
        original='v 0 0 0\nv 1 0 0\nv 1 1 0\nv 0 1 0\nvt 0 0\nvn 0 0 1\ng face\nf -4/1/1 -3/1/1 -2/1/1 -1/1/1\n'
        v,f=parse_obj(original)
        output=export_obj(original,v+1)
        self.assertIn('vt 0 0',output)
        self.assertIn('g face',output)
        self.assertIn('f -4/1 -3/1 -2/1 -1/1',output)
        self.assertNotIn('vn ',output)
        actual,faces=parse_obj(output)
        np.testing.assert_array_equal(f,faces)
        np.testing.assert_allclose(actual,v+1)

    def test_bad_models_rejected(self):
        for text in ['v nan 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3','v 0 0 0\nv 1 0 0\nv 0 1 0\nf 0 2 3','v 0 0 0','v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 9']:
            with self.assertRaises(ValueError):parse_obj(text)

    def test_bad_landmarks_rejected(self):
        a,b,pairs,_=fixture()
        for p in [pairs[:2],[[0,0],[0,1],[2,2]],[[99999,0],[1,1],[2,2]],[[.5,1],[2,2],[3,3]]]:
            with self.assertRaises(ValueError):wrap(a,b,p,5)

    def test_collinear_landmarks_rejected(self):
        a='v 0 0 0\nv 1 0 0\nv 2 0 0\nv 0 1 0\nf 1 2 4\nf 2 3 4'
        with self.assertRaises(ValueError):wrap(a,a,[[0,0],[1,1],[2,2]],5)


if __name__=='__main__':unittest.main()
