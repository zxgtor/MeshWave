import unittest
from unittest.mock import patch
import numpy as np
from temporal import smooth_frame,temporal_settings
from surface import FlipGuard,TriangleSurface
from wrap_core import parse_obj,wrap
from test_core import obj
from test_optical_flow import flow_fixture


class TemporalTests(unittest.TestCase):
    def setUp(self):
        self.body,_,self.faces=flow_fixture(side=17,shift=0)
        self.base=np.asarray(self.body['vertices']);self.body.update(settings={'strength':60,'distancePercent':5},normalAngle=60)
        self.wave=np.sin(self.base[:,0]*np.pi)*np.sin(self.base[:,1]*np.pi)

    def test_causal_smoothing_reduces_known_tangential_jitter_with_exact_pins(self):
        raw=[];filtered=[];previous=None
        for i in range(12):
            current=self.base.copy();current[:,0]+=.015*(-1)**i*self.wave
            body={**self.body,'vertices':current.tolist()};result=smooth_frame(body,previous);previous=np.array(result['vertices']);raw.append(current);filtered.append(previous)
            np.testing.assert_array_equal(previous[[p[0] for p in body['pairs']]],current[[p[0] for p in body['pairs']]])
        jitter=lambda v:np.linalg.norm(np.diff(np.array(v),n=2,axis=0),axis=2).mean()
        self.assertLess(jitter(filtered),jitter(raw)*.5);self.assertFalse(result['stats']['seed']);self.assertGreater(result['stats']['changedVertices'],10)

    def test_pose_and_scale_changes_are_not_delayed(self):
        angle=.45;r=np.array([[np.cos(angle),-np.sin(angle),0],[np.sin(angle),np.cos(angle),0],[0,0,1]])
        current=self.base@r*1.7+[3,-4,2]
        body={**self.body,'vertices':current.tolist(),'target':obj(current,self.faces)}
        result=smooth_frame(body,self.base);np.testing.assert_allclose(result['vertices'],current,atol=1e-12);self.assertEqual(result['stats']['changedVertices'],0)

    def test_current_frame_pins_excluded_region_and_zero_weights_are_preserved(self):
        b,_,f=flow_fixture(side=17);b['pairs'].append([144,144]);b['excludedFaces']={'source':[10],'target':[15]}
        b['vertices']=wrap(b['source'],b['target'],b['pairs'],5,4,b['excludedFaces'])['vertices'];weights=np.ones(len(self.base));weights[self.base[:,0]<.3]=0
        b.update(brushWeights=weights.tolist(),settings={'strength':60,'distancePercent':5})
        result=smooth_frame(b,self.base);after=np.array(result['vertices']);before=np.array(b['vertices']);locked=np.unique(np.r_[[p[0] for p in b['pairs']],f[10],np.flatnonzero(weights==0)])
        np.testing.assert_array_equal(after[locked],before[locked]);self.assertGreater(result['stats']['changedVertices'],0)
        with patch('temporal.TriangleSurface',wraps=TriangleSurface) as surface:smooth_frame(b,self.base)
        np.testing.assert_array_equal(surface.call_args.args[1],np.delete(f,[15],axis=0))

    def test_distance_cap_and_continuous_flip_guard_bound_extreme_history(self):
        previous=self.base.copy();previous[:,0]+=.3*self.wave
        result=smooth_frame({**self.body,'settings':{'strength':90,'distancePercent':.5}},previous);after=np.array(result['vertices'])
        self.assertLessEqual(np.linalg.norm(after-self.base,axis=1).max(),np.sqrt(2)*.005+1e-12)
        self.assertGreaterEqual(FlipGuard(self.base,self.faces).minimum_ratio(after),.01-1e-9)

    def test_target_normal_filter_rejects_backfacing_matches(self):
        previous=self.base.copy();previous[:,0]+=.015*self.wave
        result=smooth_frame({**self.body,'target':obj(self.base,self.faces[:,::-1])},previous)
        np.testing.assert_array_equal(result['vertices'],self.base);self.assertEqual(result['stats']['matchedVertices'],0)

    def test_seed_and_validation(self):
        result=smooth_frame(self.body);self.assertTrue(result['stats']['seed']);np.testing.assert_array_equal(result['vertices'],self.base)
        for value in [None,{'strength':0},{'strength':True},{'distancePercent':float('nan')},{'distancePercent':6}]:
            with self.assertRaises(ValueError):temporal_settings(value)
        with self.assertRaises(ValueError):smooth_frame(self.body,[[0,0,0]])
        with self.assertRaises(ValueError):smooth_frame({**self.body,'brushWeights':[-1]*len(self.base)},self.base)
        result=smooth_frame({**self.body,'brushWeights':[0]*len(self.base)},self.base+[.01,0,0]);np.testing.assert_array_equal(result['vertices'],self.base)
