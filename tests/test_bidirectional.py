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
from batch_jobs import BatchManager,BatchOutputLimit
from texture import bake_texture,read_texture
from wrap_core import parse_obj,export_obj,wrap
from test_optical_flow import flow_fixture


class BidirectionalTests(unittest.TestCase):
    def setUp(self):
        self.b,_,self.faces=flow_fixture(side=17,shift=0);self.base=np.asarray(self.b['vertices']);self.wave=np.sin(self.base[:,0]*np.pi)*np.sin(self.base[:,1]*np.pi)
        self.settings={'mode':'bidirectional','strength':60,'distancePercent':5}

    def shape(self,amount):
        v=self.base.copy();v[:,0]+=amount*self.wave;return v

    def filtered(self,frames,mode='bidirectional'):
        out=[];previous=None
        for i,current in enumerate(frames):
            body={**self.b,'vertices':current.tolist(),'settings':{**self.settings,'mode':mode}}
            r=smooth_frame(body,frames[i-1] if i else None,frames[i+1] if i+1<len(frames) else None) if mode=='bidirectional' else smooth_frame(body,previous)
            previous=np.array(r['vertices']);out.append(previous)
        return np.array(out)

    def test_reversal_symmetry_and_high_frequency_jitter_reduction(self):
        raw=np.array([self.shape(.015*(-1)**i) for i in range(17)]);result=self.filtered(raw)
        np.testing.assert_allclose(self.filtered(raw[::-1])[::-1],result,atol=1e-12)
        jitter=lambda v:np.linalg.norm(np.diff(v,n=2,axis=0),axis=2).mean()
        self.assertLess(jitter(result),jitter(raw)*.4)
        np.testing.assert_array_equal(result[[0,-1]],raw[[0,-1]])

    def test_centered_filter_preserves_fast_linear_expression_without_causal_delay(self):
        raw=np.array([self.shape(-.04+.01*i) for i in range(9)])
        bidirectional=self.filtered(raw);causal=self.filtered(raw,'causal')
        np.testing.assert_allclose(bidirectional,raw,atol=1e-12)
        self.assertGreater(np.linalg.norm(causal[4]-raw[4]),.01)

    def test_per_frame_locks_and_validation(self):
        b,_,faces=flow_fixture(side=17);b['pairs'].append([144,144]);b['excludedFaces']={'source':[10],'target':[15]}
        b['vertices']=wrap(b['source'],b['target'],b['pairs'],5,4,b['excludedFaces'])['vertices'];weights=np.ones(len(self.base));weights[self.base[:,0]<.2]=0
        result=smooth_frame({**b,'settings':self.settings,'brushWeights':weights.tolist()},self.shape(-.01),self.shape(.01))
        locked=np.unique(np.r_[[p[0] for p in b['pairs']],faces[10],np.flatnonzero(weights==0)])
        np.testing.assert_array_equal(np.array(result['vertices'])[locked],np.array(b['vertices'])[locked])
        with self.assertRaises(ValueError):temporal_settings({'mode':'unknown'})
        with self.assertRaises(ValueError):smooth_frame({**b,'settings':self.settings},self.base,[[0,0,0]])


class BidirectionalBatchTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.solver=threading.BoundedSemaphore(1);self.manager=BatchManager(self.root,self.solver)
        self.b,_,self.faces=flow_fixture(side=17,shift=0);self.base=np.array(self.b['vertices']);self.wave=np.sin(self.base[:,0]*np.pi)*np.sin(self.base[:,1]*np.pi)
        self.body={'source':{'name':'template.obj','text':self.b['source']},'referenceTarget':self.b['target'],'pairs':self.b['pairs'],'settings':{'iterations':5,'solverMode':'multistage'},'temporal':{'mode':'bidirectional','strength':60,'distancePercent':5},'bake':{'resolution':256,'padding':0,'distanceRatio':.02}}

    def tearDown(self):
        for thread in self.manager.threads.values():thread.join(30)
        self.temp.cleanup()

    def add(self,job,index,**kwargs):self.manager.add({'jobId':job['id'],'name':f'frame{index}.obj','text':self.b['target']+f'\n#frame{index}','texture':self.b['targetTexture'],**kwargs})

    def wait(self,job):
        self.manager.threads[job['id']].join(30);self.assertFalse(self.manager.threads[job['id']].is_alive());return self.manager.status(job['id'])

    def jitter(self,source,target,*args):
        index=int(target.rsplit('#frame',1)[1]);v=self.base.copy();v[:,0]+=.015*(-1)**index*self.wave
        return {'vertices':v.tolist(),'stats':{}}

    def test_immutable_neighbors_two_pass_pipeline_and_final_texture_export(self):
        job=self.manager.create(self.body)
        for i in [5,3,1,4,2]:self.add(job,i)
        with patch('batch_jobs.wrap',side_effect=self.jitter):self.manager.start(job['id']);result=self.wait(job)
        self.assertEqual(result['counts']['succeeded'],5);self.assertEqual(result['counts']['prepared'],0)
        with zipfile.ZipFile(self.manager.download_path(job['id'])) as z:
            for i,item in enumerate(result['items']):
                load=lambda n:np.load(self.root/job['id']/'inputs'/f'{result["items"][n]["id"]}.temporal.npy')
                current=load(i);body={**self.b,'vertices':current.tolist(),'settings':self.body['temporal']};expected=smooth_frame(body,load(i-1) if i else None,load(i+1) if i<4 else None)
                v,f,uv,uf=parse_obj(z.read(item['resultFile']).decode(),True);serialized,_=parse_obj(export_obj(self.b['source'],expected['vertices']));np.testing.assert_array_equal(v,serialized)
                self.assertEqual(item['temporalStatus'],'seed' if i in (0,4) else 'succeeded')
                if i not in (0,4):self.assertEqual(item['previousFrame'],f'frame{i}.obj');self.assertEqual(item['nextFrame'],f'frame{i+2}.obj')
                baked=bake_texture(self.b['source'],self.b['target'],v,self.b['targetTexture'],256,0)
                actual=Image.open(io.BytesIO(z.read(item['resultFile'].rsplit('/',1)[0]+'/texture.png')));np.testing.assert_array_equal(actual,read_texture(baked['texture']))
            self.assertEqual(sum(len(z.read(n)) for n in z.namelist() if n.startswith('results/')),result['outputBytes'])

    def test_failed_input_splits_segments_and_short_segments_preserve_boundaries(self):
        job=self.manager.create(self.body)
        for i in range(1,8):self.add(job,i,**({'texture':None,'textureError':'missing'} if i==4 else {}))
        with patch('batch_jobs.wrap',side_effect=self.jitter):self.manager.start(job['id']);result=self.wait(job)
        self.assertEqual(result['counts']['failed'],1);self.assertEqual(result['counts']['succeeded'],6)
        for i in [0,2,4,6]:self.assertEqual(result['items'][i]['temporalStatus'],'seed')
        for i in [1,5]:self.assertEqual(result['items'][i]['temporalStatus'],'succeeded')

    def test_cancel_during_collection_finishes_collected_prefix(self):
        job=self.manager.create(self.body)
        for i in range(1,5):self.add(job,i)
        entered=threading.Event();release=threading.Event();calls=0
        def slow(*args):
            nonlocal calls
            calls+=1
            if calls==3:entered.set();release.wait(10)
            return self.jitter(*args)
        with patch('batch_jobs.wrap',side_effect=slow):
            self.manager.start(job['id']);self.assertTrue(entered.wait(10));self.manager.cancel(job['id']);release.set();result=self.wait(job)
        self.assertEqual(result['status'],'cancelled');self.assertEqual(result['counts']['succeeded'],3);self.assertEqual(result['counts']['skipped'],1);self.assertEqual(result['items'][1]['temporalStatus'],'succeeded')

    def test_cancel_during_finalization_keeps_raw_geometry_for_remaining_frames(self):
        job=self.manager.create(self.body)
        for i in range(1,5):self.add(job,i)
        entered=threading.Event();release=threading.Event()
        def slow(*args):entered.set();release.wait(10);return smooth_frame(*args)
        with patch('batch_jobs.smooth_frame',side_effect=slow),patch('batch_jobs.wrap',side_effect=self.jitter):
            self.manager.start(job['id']);self.assertTrue(entered.wait(10));self.manager.cancel(job['id']);release.set();result=self.wait(job)
        self.assertEqual(result['counts']['succeeded'],1);self.assertEqual(result['counts']['skipped'],3)
        with zipfile.ZipFile(self.manager.download_path(job['id'])) as z:
            for item in result['items'][1:]:self.assertIn(item['resultFile'],z.namelist());self.assertEqual(item['bakeStatus'],'skipped')
        self.assertTrue(self.solver.acquire(False));self.solver.release()

    def test_restart_recovers_prepared_geometry_without_claiming_smoothing(self):
        job=self.manager.create(self.body);self.add(job,1);stored=self.manager.jobs[job['id']];stored['status']='running';relative='results/raw.obj';(self.root/job['id']/relative).write_text(self.b['source'],encoding='utf-8',newline='')
        stored['items'][0].update(status='prepared',temporalStatus='pending',resultFile=relative);self.manager._save(stored)
        fresh=BatchManager(self.root,threading.BoundedSemaphore(1));result=fresh.status(job['id']);self.assertEqual(result['items'][0]['temporalStatus'],'interrupted');self.assertEqual(result['counts']['skipped'],1);self.assertTrue(result['archiveReady'])

    def test_real_flow_bidirectional_constraints_and_baking(self):
        b,_,faces=flow_fixture(side=17);weights=np.ones(len(self.base));weights[self.base[:,0]<.2]=0
        body={**self.body,'source':{'name':'template.obj','text':b['source']},'referenceTarget':b['target'],'excludedSourceFaces':[10],'excludedTargetFaces':[15],'temporal':{**self.body['temporal'],'brushWeights':weights.tolist()},'flow':{'settings':b['settings'],'cameraWorld':b['cameraWorld'],'sourceTexture':b['sourceTexture'],'brushWeights':weights.tolist()}}
        job=self.manager.create(body)
        for i,shift in enumerate([.03,.045,.035],1):self.add(job,i,text=flow_fixture(side=17,shift=shift)[0]['target'])
        self.manager.start(job['id']);result=self.wait(job);self.assertEqual(result['counts']['succeeded'],3)
        item=result['items'][1];self.assertEqual(item['flowStatus'],'succeeded');self.assertEqual(item['temporalStatus'],'succeeded');self.assertEqual(item['bakeStatus'],'succeeded')
        raw=np.load(self.root/job['id']/'inputs'/f'{item["id"]}.temporal.npy');locked=np.unique(np.r_[[p[0] for p in b['pairs']],faces[10],np.flatnonzero(weights==0)])
        with zipfile.ZipFile(self.manager.download_path(job['id'])) as z:
            v,_=parse_obj(z.read(item['resultFile']).decode());np.testing.assert_allclose(v[locked],raw[locked],atol=1e-9)
            target=(self.root/job['id']/'inputs'/f'{item["id"]}.obj').read_text(encoding='utf-8')
            expected=bake_texture(b['source'],target,v,b['targetTexture'],256,0,excluded_faces={'source':[10],'target':[15]})
            pixels=Image.open(io.BytesIO(z.read(item['resultFile'].rsplit('/',1)[0]+'/texture.png')));np.testing.assert_array_equal(pixels,read_texture(expected['texture']))

    def test_output_limit_in_finalization_keeps_all_confirmed_raw_geometry(self):
        job=self.manager.create(self.body)
        for i in range(1,4):self.add(job,i)
        with patch.object(self.manager,'_bake_result',side_effect=BatchOutputLimit('256 MB')):
            self.manager.start(job['id']);result=self.wait(job)
        self.assertEqual(result['status'],'limited');self.assertEqual(result['counts']['failed'],1);self.assertEqual(result['counts']['skipped'],2)
        with zipfile.ZipFile(self.manager.download_path(job['id'])) as z:
            for item in result['items']:self.assertIn(item['resultFile'],z.namelist())
