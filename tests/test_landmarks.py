import unittest
from unittest.mock import patch
import numpy as np
from landmarks import camera_rays, map_landmarks, generate_pairs, FEATURES


def camera(scale=1,shift=np.zeros(3)):
    near,far=.1*scale,10*scale;f=1/np.tan(np.deg2rad(40)/2)
    projection=np.array([[f,0,0,0],[0,f,0,0],[0,0,(far+near)/(near-far),2*far*near/(near-far)],[0,0,-1,0]])
    world=np.eye(4);world[:3,3]=np.array([0,0,3])*scale+shift
    return {'inverseProjection':np.linalg.inv(projection).T.ravel().tolist(),'world':world.T.ravel().tolist()}


def project(vertices,cam):
    inverse=np.array(cam['inverseProjection']).reshape(4,4).T
    world=np.array(cam['world']).reshape(4,4).T
    clip=np.column_stack([vertices,np.ones(len(vertices))])@(np.linalg.inv(inverse)@np.linalg.inv(world)).T
    return clip[:,:2]/clip[:,3:]*[.5,-.5]+[.5,.5]


def grid():
    vertices=np.array([[x/10-1,y/10-1,0.] for y in range(21) for x in range(21)])
    faces=[]
    for y in range(20):
        for x in range(20):
            a=y*21+x;faces.extend([[a,a+1,a+22],[a,a+22,a+21]])
    return vertices,np.array(faces)


def obj(v,f):
    return '\n'.join(['v '+' '.join(map(str,p)) for p in v]+['f '+' '.join(str(i+1) for i in p) for p in f])


class LandmarkTests(unittest.TestCase):
    def test_projection_inverse_and_known_vertex_snap(self):
        v,f=grid();ids=[220,178,262,136,304];cam=camera()
        points=project(v[ids],cam)
        mapped,skipped=map_landmarks(v,f,points,cam)
        self.assertEqual(list(mapped.values()),ids);self.assertFalse(skipped)
        origins,directions,lengths,_=camera_rays(cam,np.array([[.5,.5]]))
        np.testing.assert_allclose(directions,[[0,0,-1]],atol=1e-12)
        np.testing.assert_allclose(origins,[[0,0,2.9]],atol=1e-12)

    def test_mapping_is_scale_and_translation_invariant(self):
        v,f=grid();ids=[220,178,262];shift=np.array([100,200,-300]);scale=1000
        transformed=v*scale+shift;cam=camera(scale,shift)
        mapped,_=map_landmarks(transformed,f,project(transformed[ids],cam),cam)
        self.assertEqual(list(mapped.values()),ids)

    def test_exclusion_does_not_cast_through_to_back_layer(self):
        back,f=grid();front=back+[0,0,.2];v=np.vstack([front,back]);faces=np.vstack([f,f+len(front)])
        xy=project(front[[220]],camera())
        mapped,_=map_landmarks(v,faces,xy,camera());self.assertEqual(mapped[0],220)
        mapped,skipped=map_landmarks(v,faces,xy,camera(),[220])
        self.assertFalse(mapped);self.assertIn('排除',skipped[0])

    def test_duplicate_miss_and_coarse_snap_rejected(self):
        v,f=grid();xy=project(v[[220,220]],camera())
        mapped,skipped=map_landmarks(v,f,xy,camera())
        self.assertEqual(len(mapped),1);self.assertIn('重复',skipped[1])
        mapped,skipped=map_landmarks(v*.2,f,np.array([[.9,.9],[2,.5]]),camera())
        self.assertFalse(mapped);self.assertIn('未命中',skipped[0]);self.assertIn('画面',skipped[1])
        mapped,skipped=map_landmarks(np.array([[-1.,-1,0],[1,-1,0],[0,1,0]]),np.array([[0,1,2]]),np.array([[.5,.5]]),camera())
        self.assertFalse(mapped);self.assertIn('偏差',skipped[0])

    def test_invalid_camera_rejected(self):
        for cam in [{'world':[0]*16,'inverseProjection':[0]*16},{'world':[0]*15,'inverseProjection':[0]*16},None]:
            with self.assertRaises(ValueError):camera_rays(cam,np.array([[.5,.5]]))

    def test_pair_generation_matches_feature_identity_and_preserves_bounds(self):
        v,f=grid();text=obj(v,f);ids=[(3+i//6*6)*21+(2+i%6*3) for i in range(len(FEATURES))]
        detected=np.zeros((478,2));detected[:]=.5
        for feature,index in enumerate(ids):detected[FEATURES[feature][0]]=project(v[[index]],camera())[0]
        body={'source':text,'target':text,'sourceView':{'camera':camera()},'targetView':{'camera':camera()},'excludedFaces':{}}
        with patch('landmarks.detector'),patch('landmarks.image_landmarks',return_value=detected):
            result=generate_pairs(body)
        self.assertEqual(result['pairs'],[[i,i] for i in ids]);self.assertEqual(result['names'],[p[1] for p in FEATURES])
        self.assertFalse(result['skipped'])
        excluded=np.where(np.any(np.isin(f,ids),axis=1))[0].tolist()
        body['excludedFaces']={'source':excluded}
        with patch('landmarks.detector'),patch('landmarks.image_landmarks',return_value=detected):
            with self.assertRaisesRegex(ValueError,'至少 6'):
                generate_pairs(body)


if __name__=='__main__':unittest.main()
