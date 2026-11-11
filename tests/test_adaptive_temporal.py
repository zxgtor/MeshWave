import io
import json
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PIL import Image
from temporal import smooth_frame,temporal_settings
from batch_jobs import BatchManager
from texture import bake_texture,read_texture
from wrap_core import parse_obj,wrap
from test_core import obj
from test_optical_flow import flow_fixture


class AdaptiveTemporalTests(unittest.TestCase):
    def setUp(self):
        self.b,_,self.faces=flow_fixture(side=17,shift=0);self.base=np.array(self.b['vertices']);self.wave=np.sin(self.base[:,0]*np.pi)*np.sin(self.base[:,1]*np.pi)
        self.settings={'mode':'bidirectional','strength':60,'distancePercent':5,'adaptive':True,'speedPercent':1}

    def shape(self,amount):
        v=self.base.copy();v[:,0]+=amount*self.wave;return v

    def test_fast_peak_does_not_cancel_opposite_neighbor_velocities_and_remains_exact(self):
        current=self.shape(.06);neighbor=self.shape(.01);body={**self.b,'vertices':current.tolist(),'settings':self.settings}
        adaptive=smooth_frame(body,neighbor,neighbor);fixed=smooth_frame({**body,'settings':{**self.settings,'adaptive':False}},neighbor,neighbor)
        center=144;self.assertEqual(adaptive['vertices'][center],current[center].tolist());self.assertLess(fixed['vertices'][center][0],current[center,0]-.02)
        self.assertGreater(adaptive['stats']['fastVertices'],10);self.assertGreater(adaptive['stats']['changedVertices'],0);self.assertEqual(adaptive['stats']['effectiveStrengthMin'],0)

    def test_small_jitter_is_still_smoothed_at_high_strength(self):
        raw=np.array([self.shape(.002*(-1)**i) for i in range(17)]);result=[]
        for i,current in enumerate(raw):
            b={**self.b,'vertices':current.tolist(),'settings':self.settings};r=smooth_frame(b,raw[i-1] if i else None,raw[i+1] if i+1<len(raw) else None);result.append(r['vertices'])
            if 0<i<len(raw)-1:self.assertGreater(r['stats']['effectiveStrengthMean'],50)
        jitter=lambda v:np.linalg.norm(np.diff(np.array(v),n=2,axis=0),axis=2).mean()
        self.assertLess(jitter(result),jitter(raw)*.45)
        reverse=[]
        for i,current in enumerate(raw[::-1]):reverse.append(smooth_frame({**self.b,'vertices':current.tolist(),'settings':self.settings},raw[::-1][i-1] if i else None,raw[::-1][i+1] if i+1<len(raw) else None)['vertices'])
        np.testing.assert_allclose(reverse[::-1],result,atol=1e-12)

    def test_hard_points_exclusions_and_soft_protection_remain_exact_in_both_modes(self):
        b,_,faces=flow_fixture(side=17);b['pairs'].append([144,144]);b['excludedFaces']={'source':[10],'target':[15]};b['vertices']=wrap(b['source'],b['target'],b['pairs'],5,4,b['excludedFaces'])['vertices']
        weights=np.ones(len(self.base));weights[self.base[:,0]<.2]=0;locked=np.unique(np.r_[[p[0] for p in b['pairs']],faces[10],np.flatnonzero(weights==0)])
        for mode in ['causal','bidirectional']:
            r=smooth_frame({**b,'settings':{**self.settings,'mode':mode},'brushWeights':weights.tolist()},self.shape(.01),self.shape(.015))
            np.testing.assert_array_equal(np.asarray(r['vertices'])[locked],np.asarray(b['vertices'])[locked])

    def test_pose_and_scale_do_not_trigger_fast_expression_detection(self):
        angle=.4;rotation=np.array([[np.cos(angle),-np.sin(angle),0],[np.sin(angle),np.cos(angle),0],[0,0,1]])
        current=self.base@rotation*1.8+[3,-2,1];body={**self.b,'target':obj(current,self.faces),'vertices':current.tolist(),'settings':self.settings}
        result=smooth_frame(body,self.base,self.base);np.testing.assert_allclose(result['vertices'],current,atol=1e-12);self.assertLess(result['stats']['speedMaxPercent'],1e-10);self.assertEqual(result['stats']['fastVertices'],0)

    def test_causal_speed_uses_raw_history_not_the_filtered_history(self):
        body={**self.b,'settings':{**self.settings,'mode':'causal'},'motionPrevious':self.base.tolist()}
        result=smooth_frame(body,self.shape(.03));self.assertLess(result['stats']['speedMaxPercent'],1e-10);self.assertAlmostEqual(result['stats']['effectiveStrengthMean'],60)
        without=smooth_frame({**body,'motionPrevious':None},self.shape(.03));self.assertGreater(without['stats']['fastVertices'],0)

    def test_validation_and_disabled_adaptive_backward_compatibility(self):
        for value in [{'adaptive':'yes'},{'adaptive':1},{'speedPercent':0},{'speedPercent':float('nan')},{'speedPercent':11}]:
            with self.assertRaises(ValueError):temporal_settings(value)
        body={**self.b,'vertices':self.shape(.01).tolist(),'settings':{'strength':60,'distancePercent':5}}
        a=smooth_frame(body,self.base);b=smooth_frame({**body,'settings':{**body['settings'],'adaptive':False,'speedPercent':.1}},self.base);np.testing.assert_array_equal(a['vertices'],b['vertices'])
        with self.assertRaises(ValueError):smooth_frame({**self.b,'settings':{**self.settings,'mode':'causal'},'motionPrevious':[[0,0,0]]},self.base)


class AdaptiveBatchTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.manager=BatchManager(self.root,threading.BoundedSemaphore(1));self.b,_,_=flow_fixture(side=17)
        b=self.b;self.body={'source':{'name':'template.obj','text':b['source']},'referenceTarget':b['target'],'pairs':b['pairs'],'settings':{'iterations':5,'solverMode':'multistage'},'temporal':{'mode':'bidirectional','strength':60,'distancePercent':5,'adaptive':True,'speedPercent':.3},'bake':{'resolution':256,'padding':0,'distanceRatio':.02},'flow':{'settings':b['settings'],'cameraWorld':b['cameraWorld'],'sourceTexture':b['sourceTexture'],'brushWeights':None}}

    def tearDown(self):
        for thread in self.manager.threads.values():thread.join(30)
        self.temp.cleanup()

    def wait(self,job):
        self.manager.threads[job['id']].join(30);self.assertFalse(self.manager.threads[job['id']].is_alive());return self.manager.status(job['id'])

    def test_real_flow_adaptive_peak_bake_and_persisted_reports(self):
        job=self.manager.create(self.body)
        for i,shift in enumerate([.025,.05,.025],1):
            frame,_,_=flow_fixture(side=17,shift=shift);self.manager.add({'jobId':job['id'],'name':f'frame{i}.obj','text':frame['target'],'texture':frame['targetTexture']})
        self.manager.start(job['id']);result=self.wait(job);self.assertEqual(result['counts']['succeeded'],3);item=result['items'][1];self.assertTrue(item['temporalStats']['adaptive']);self.assertGreater(item['temporalStats']['fastVertices'],0)
        with zipfile.ZipFile(self.manager.download_path(job['id'])) as z:
            v,_=parse_obj(z.read(item['resultFile']).decode());raw=np.load(self.root/job['id']/'inputs'/f'{item["id"]}.temporal.npy');np.testing.assert_allclose(v[144],raw[144],atol=1e-9)
            target=(self.root/job['id']/'inputs'/f'{item["id"]}.obj').read_text(encoding='utf-8');expected=bake_texture(self.b['source'],target,v,self.b['targetTexture'],256,0)
            actual=Image.open(io.BytesIO(z.read(item['resultFile'].rsplit('/',1)[0]+'/texture.png')));np.testing.assert_array_equal(actual,read_texture(expected['texture']))
            self.assertIn('adaptive_strength_mean',z.read('report.csv').decode('utf-8-sig'));self.assertTrue(json.loads(z.read('settings.json'))['temporal']['adaptive'])
        restored=BatchManager(self.root,threading.BoundedSemaphore(1));self.assertEqual(restored.status(job['id'])['items'],result['items'])

    def test_causal_batch_keeps_raw_motion_reference_separate_from_filtered_output(self):
        body={**self.body,'flow':None,'bake':None,'temporal':{**self.body['temporal'],'mode':'causal','speedPercent':10}}
        job=self.manager.create(body);base=np.array(self.b['vertices']);wave=np.sin(base[:,0]*np.pi)*np.sin(base[:,1]*np.pi);raws=[];seen=[]
        for i in range(4):self.manager.add({'jobId':job['id'],'name':f'frame{i}.obj','text':self.b['source']+f'\n#frame{i}'})
        def jitter(source,target,*args):
            i=int(target.rsplit('#frame',1)[1]);v=base.copy();v[:,0]+=.005*(-1)**i*wave;raws.append(v);return {'vertices':v.tolist(),'stats':{}}
        def smooth(body,previous):seen.append(body['motionPrevious']);return smooth_frame(body,previous)
        with patch('batch_jobs.wrap',side_effect=jitter),patch('batch_jobs.smooth_frame',side_effect=smooth):self.manager.start(job['id']);result=self.wait(job)
        self.assertEqual(result['counts']['succeeded'],4);self.assertIsNone(seen[0])
        for i in range(1,4):np.testing.assert_array_equal(seen[i],raws[i-1])
