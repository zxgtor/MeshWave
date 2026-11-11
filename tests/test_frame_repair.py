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
from frame_repair import repair_frame
from batch_jobs import BatchManager
from temporal import temporal_settings
from wrap_core import parse_obj,export_obj,wrap,similarity
from texture import bake_texture,read_texture
from surface import FlipGuard
from test_optical_flow import flow_fixture


class FrameRepairTests(unittest.TestCase):
    def setUp(self):
        self.b,_,self.faces=flow_fixture(side=17,shift=0);self.base=np.array(self.b['vertices']);self.wave=np.sin(self.base[:,0]*np.pi)*np.sin(self.base[:,1]*np.pi)
        self.body={**self.b,'excludedFaces':{},'settings':{'iterations':5,'smoothness':4,'normalAngle':60},'distanceRatio':.02}

    def shape(self,amount):
        v=self.base.copy();v[:,0]+=amount*self.wave;return v

    def test_interpolation_fraction_and_seeded_refit_recover_correspondence(self):
        before,after=self.shape(.01),self.shape(.05);truth=self.shape(.02);bad=self.shape(-.03)
        body={**self.body,'target':export_obj(self.b['target'],truth),'vertices':bad.tolist()};r=repair_frame(body,before,after,.25)
        np.testing.assert_allclose(r['vertices'],truth,atol=1e-10);self.assertEqual(r['stats']['fraction'],.25);self.assertGreater(r['stats']['surfaceMatches'],10)

    def test_noisy_scan_does_not_destroy_interpolated_prior(self):
        noisy=self.base.copy();inside=(self.base[:,0]>.2)&(self.base[:,0]<.8)&(self.base[:,1]>.2)&(self.base[:,1]<.8);noisy[inside,2]+=np.random.default_rng(3).normal(0,.1,inside.sum())
        body={**self.body,'target':export_obj(self.b['target'],noisy),'vertices':noisy.tolist()};r=repair_frame(body,self.base,self.base,.5);v=np.array(r['vertices'])
        self.assertLess(np.linalg.norm(v-self.base,axis=1).mean(),np.linalg.norm(noisy-self.base,axis=1).mean()*.2)
        self.assertLessEqual(r['stats']['maxSeedDeviation'],r['stats']['maxRefitDistance']+1e-12);self.assertGreaterEqual(r['stats']['minimumProjectedAreaRatio'],.01-1e-9)

    def test_current_frame_pins_fixed_region_and_zero_weights_are_preserved(self):
        b,_,f=flow_fixture(side=17);b['pairs'].append([144,144]);masks={'source':[10],'target':[15]};existing=wrap(b['source'],b['target'],b['pairs'],5,4,masks)['vertices'];weights=np.ones(len(existing));weights[self.base[:,0]<.2]=0
        body={**self.body,'source':b['source'],'target':b['target'],'pairs':b['pairs'],'excludedFaces':masks,'vertices':existing,'brushWeights':weights.tolist()};r=repair_frame(body,self.shape(.01),self.shape(.05),.5);v=np.array(r['vertices'])
        pins=[p[0] for p in b['pairs']];target=parse_obj(b['target'])[0];np.testing.assert_array_equal(v[pins],target[[p[1] for p in b['pairs']]])
        np.testing.assert_allclose(v[f[10]],np.array(existing)[f[10]],atol=1e-12);np.testing.assert_allclose(v[weights==0],np.array(existing)[weights==0],atol=1e-12);self.assertGreaterEqual(FlipGuard(self.base,f).minimum_ratio(v),.01-1e-9)

    def test_unsupported_inputs_do_not_produce_fake_repairs(self):
        for t in [0,1,float('nan')]:
            with self.assertRaises(ValueError):repair_frame(self.body,self.base,self.base,t)
        with self.assertRaises(ValueError):repair_frame({**self.body,'brushWeights':[0]*len(self.base)},self.base,self.base,.5)
        with self.assertRaises(ValueError):repair_frame(self.body,[[0,0,0]],self.base,.5)
        for config in [{'repairAnomalies':True},{'detectAnomalies':True,'repairMaxGap':0},{'detectAnomalies':True,'repairAnomalies':1}]:
            with self.assertRaises(ValueError):temporal_settings(config)


class BatchRepairTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.manager=BatchManager(self.root,threading.BoundedSemaphore(1));self.b,_,self.faces=flow_fixture(side=17,shift=0);self.base=np.array(self.b['vertices']);self.wave=np.sin(self.base[:,0]*np.pi)*np.sin(self.base[:,1]*np.pi)
        self.body={'source':{'name':'template.obj','text':self.b['source']},'referenceTarget':self.b['target'],'pairs':self.b['pairs'],'settings':{'iterations':5,'solverMode':'multistage'},'temporal':{'mode':'bidirectional','strength':60,'distancePercent':2,'detectAnomalies':True,'anomalyPercent':2,'repairAnomalies':True,'repairMaxGap':3},'bake':{'resolution':256,'padding':0,'distanceRatio':.02}}

    def tearDown(self):
        for thread in self.manager.threads.values():thread.join(30)
        self.temp.cleanup()

    def create(self,bad=(2,),count=3,body=None):
        job=self.manager.create(body or self.body)
        for i in range(1,count+1):self.manager.add({'jobId':job['id'],'name':f'frame{i}.obj','text':self.b['target']+f'\n#frame{i}','texture':self.b['targetTexture']})
        def solve(source,target,*args):
            i=int(target.rsplit('#frame',1)[1]);v=self.base.copy()
            if i in bad:v[:,2]+=.15*self.wave
            return {'vertices':v.tolist(),'stats':{}}
        return job,solve

    def wait(self,job):
        self.manager.threads[job['id']].join(30);self.assertFalse(self.manager.threads[job['id']].is_alive());return self.manager.status(job['id'])

    def test_repaired_frame_rechecks_and_exports_fresh_texture_preserving_original_cache(self):
        job,solve=self.create()
        with patch('batch_jobs.wrap',side_effect=solve):self.manager.start(job['id']);result=self.wait(job)
        self.assertEqual(result['counts']['succeeded'],3);item=result['items'][1];self.assertEqual(item['anomalyStatus'],'repaired');self.assertEqual(item['temporalStatus'],'repaired');self.assertEqual(item['repairStatus'],'succeeded');self.assertEqual(item['bakeStatus'],'succeeded');self.assertIsNone(item['error'])
        raw=np.load(self.root/job['id']/'inputs'/f'{item["id"]}.temporal.npy');self.assertGreater(raw[:,2].max(),.1);self.assertTrue((self.root/job['id']/item['repairStats']['originalResultFile']).is_file())
        with zipfile.ZipFile(self.manager.download_path(job['id'])) as z:
            v,f,uv,uf=parse_obj(z.read(item['resultFile']).decode(),True);np.testing.assert_allclose(v,self.base,atol=1e-9);_,sf,suv,suf=parse_obj(self.b['source'],True);np.testing.assert_array_equal(f,sf);np.testing.assert_array_equal(uv,suv);np.testing.assert_array_equal(uf,suf)
            expected=bake_texture(self.b['source'],self.b['target'],v,self.b['targetTexture'],256,0);actual=Image.open(io.BytesIO(z.read(item['resultFile'].rsplit('/',1)[0]+'/texture.png')));np.testing.assert_array_equal(actual,read_texture(expected['texture']))
            self.assertEqual(sum(len(z.read(n)) for n in z.namelist() if n.startswith('results/')),result['outputBytes']);self.assertIn('repair_status',z.read('report.csv').decode('utf-8-sig'))

    def test_edge_or_oversized_gap_is_not_extrapolated_and_gaps_use_original_normal_endpoints(self):
        job,solve=self.create(bad=(1,3))
        with patch('batch_jobs.wrap',side_effect=solve):self.manager.start(job['id']);result=self.wait(job)
        self.assertEqual(result['items'][0]['repairStatus'],'unavailable');self.assertEqual(result['items'][2]['repairStatus'],'unavailable')
        for max_gap,expected in [(1,'unavailable'),(3,'succeeded')]:
            body={**self.body,'temporal':{**self.body['temporal'],'repairMaxGap':max_gap}};job,solve=self.create(bad=(2,3),count=5,body=body)
            with patch('batch_jobs.wrap',side_effect=solve):self.manager.start(job['id']);result=self.wait(job)
            for i in (1,2):self.assertEqual(result['items'][i]['repairStatus'],expected)
            if max_gap==3:
                self.assertAlmostEqual(result['items'][1]['repairStats']['fraction'],1/3);self.assertAlmostEqual(result['items'][2]['repairStats']['fraction'],2/3)
                for i in (1,2):self.assertEqual(result['items'][i]['repairStats']['beforeFrame'],'frame1.obj');self.assertEqual(result['items'][i]['repairStats']['afterFrame'],'frame4.obj')

    def test_failed_recheck_keeps_quarantined_geometry(self):
        job,solve=self.create()
        def bad(*args):v=self.base.copy();v[:,2]+=.15*self.wave;return {'vertices':v.tolist(),'stats':{}}
        with patch('batch_jobs.wrap',side_effect=solve),patch('batch_jobs.repair_frame',side_effect=bad):self.manager.start(job['id']);result=self.wait(job)
        item=result['items'][1];self.assertEqual(item['repairStatus'],'failed');self.assertEqual(item['anomalyStatus'],'rejected');self.assertEqual(item['bakeStatus'],'skipped');self.assertNotIn('repairStats',item)
        v,_=parse_obj((self.root/job['id']/item['resultFile']).read_text(encoding='utf-8'));self.assertGreater(v[:,2].max(),.1)

    def test_bake_failure_retains_successfully_rebuilt_geometry(self):
        job,solve=self.create();bake=self.manager._bake_result
        def maybe(*args,**kwargs):
            if args[1].get('repairStatus')=='succeeded':raise ValueError('repair bake test')
            return bake(*args,**kwargs)
        with patch('batch_jobs.wrap',side_effect=solve),patch.object(self.manager,'_bake_result',side_effect=maybe):self.manager.start(job['id']);result=self.wait(job)
        item=result['items'][1];self.assertEqual(item['status'],'failed');self.assertEqual(item['repairStatus'],'succeeded');self.assertEqual(item['bakeStatus'],'failed');v,_=parse_obj((self.root/job['id']/item['resultFile']).read_text(encoding='utf-8'));np.testing.assert_allclose(v,self.base,atol=1e-9)

    def test_cancel_during_repair_finishes_current_repair_and_bake(self):
        job,solve=self.create();entered=threading.Event();release=threading.Event()
        def slow(*args):entered.set();release.wait(10);return repair_frame(*args)
        with patch('batch_jobs.wrap',side_effect=solve),patch('batch_jobs.repair_frame',side_effect=slow):
            self.manager.start(job['id']);self.assertTrue(entered.wait(10));self.manager.cancel(job['id']);release.set();result=self.wait(job)
        self.assertEqual(result['status'],'cancelled');self.assertEqual(result['items'][1]['repairStatus'],'succeeded');self.assertEqual(result['items'][1]['bakeStatus'],'succeeded');self.assertEqual(result['counts']['skipped'],2)

    def test_restart_during_repair_keeps_original_geometry_and_marks_interrupted(self):
        job,_=self.create();stored=self.manager.jobs[job['id']];stored['status']='running';relative='results/original.obj';(self.root/job['id']/relative).write_text(self.b['source'],encoding='utf-8',newline='');stored['items'][1].update(status='running',stage='repair',repairStatus='running',anomalyStatus='rejected',resultFile=relative);self.manager._save(stored)
        fresh=BatchManager(self.root,threading.BoundedSemaphore(1));result=fresh.status(job['id']);self.assertEqual(result['items'][1]['repairStatus'],'interrupted');self.assertNotIn('stage',result['items'][1]);self.assertTrue(result['archiveReady'])

    def test_actual_scan_noise_can_be_rebuilt_and_baked_from_normal_flow_frames(self):
        b,_,_=flow_fixture(side=17,shift=.03);body={**self.body,'source':{'name':'template.obj','text':b['source']},'referenceTarget':b['target'],'flow':{'settings':b['settings'],'cameraWorld':b['cameraWorld'],'sourceTexture':b['sourceTexture'],'brushWeights':None}}
        job=self.manager.create(body)
        for i in range(1,4):
            v,_=parse_obj(b['target'])
            if i==2:
                inside=(v[:,0]>.2)&(v[:,0]<.8)&(v[:,1]>.2)&(v[:,1]<.8);v[inside,2]+=np.random.default_rng(6).normal(0,.12,inside.sum())
            self.manager.add({'jobId':job['id'],'name':f'frame{i}.obj','text':export_obj(b['target'],v),'texture':b['targetTexture']})
        self.manager.start(job['id']);result=self.wait(job);item=result['items'][1];self.assertEqual(item.get('repairStatus'),'succeeded',item);self.assertEqual(item['bakeStatus'],'succeeded');self.assertEqual(result['counts']['succeeded'],3)

    def test_valid_noisy_scan_with_failed_initial_solve_can_rebuild_missing_result(self):
        job=self.manager.create(self.body)
        for i in range(1,4):
            v=self.base.copy()
            if i==2:
                inside=(v[:,0]>.2)&(v[:,0]<.8)&(v[:,1]>.2)&(v[:,1]<.8);v[inside,2]+=np.random.default_rng(6).normal(0,.1,inside.sum())
            self.manager.add({'jobId':job['id'],'name':f'frame{i}.obj','text':export_obj(self.b['target'],v)+f'\n#frame{i}','texture':self.b['targetTexture']})
        def solve(source,target,*args):
            if '#frame2' in target:raise ValueError('initial solve test failure')
            return {'vertices':self.base.tolist(),'stats':{}}
        with patch('batch_jobs.wrap',side_effect=solve):self.manager.start(job['id']);result=self.wait(job)
        item=result['items'][1];self.assertEqual(item['repairStatus'],'succeeded',item);self.assertEqual(item['bakeStatus'],'succeeded');self.assertIsNone(item['repairStats']['originalResultFile']);self.assertFalse((self.root/job['id']/'inputs'/'0002.temporal.npy').exists())
