import tempfile
import threading
import unittest
import zipfile
import json
from pathlib import Path
from unittest.mock import patch
import numpy as np
from anomalies import scan_quality,fit_quality,classify_frame
from temporal import temporal_settings
from batch_jobs import BatchManager
from wrap_core import parse_obj,export_obj
from test_core import obj
from test_optical_flow import flow_fixture


class AnomalyTests(unittest.TestCase):
    def setUp(self):
        self.b,_,self.faces=flow_fixture(side=25,shift=0);self.base=np.array(self.b['vertices']);self.wave=np.sin(self.base[:,0]*np.pi)*np.sin(self.base[:,1]*np.pi)
        self.good=scan_quality(self.b['source'],[],self.b['pairs']);self.good['topologyHash']='same'
        self.qfit={'distancePercent':0.,'sampleVertices':100}

    def verdict(self,current=None,target=None,prior=None,following=None,scan=None,fit=None,excluded=None,weights=None,threshold=2,neighbors=None):
        current=self.base if current is None else current;target=self.b['source'] if target is None else target;excluded=excluded or {'source':[],'target':[]}
        if scan is None:scan=scan_quality(target,excluded['target'],self.b['pairs']);scan['topologyHash']='same'
        if fit is None:fit=fit_quality(self.b['source'],target,current,self.b['pairs'],excluded,weights)
        neighbors=neighbors if neighbors is not None else [{'name':'prev','scanQuality':self.good,'fitQuality':self.qfit},{'name':'next','scanQuality':self.good,'fitQuality':self.qfit}]
        return classify_frame({'source':self.b['source'],'target':target,'vertices':current,'pairs':self.b['pairs'],'excludedFaces':excluded,'brushWeights':weights,'threshold':threshold,'scanQuality':scan,'fitQuality':fit,'neighbors':neighbors},self.base if prior is None else prior,self.base if following is None else following)

    def test_large_scan_noise_is_detected_even_if_fit_did_not_follow_it(self):
        noisy=self.base.copy();rng=np.random.default_rng(5);inside=(self.base[:,0]>.15)&(self.base[:,0]<.85)&(self.base[:,1]>.15)&(self.base[:,1]<.85);noisy[inside,2]+=rng.normal(0,.12,inside.sum())
        result=self.verdict(target=obj(noisy,self.faces));self.assertEqual(result['status'],'rejected');self.assertIn('scan_noise',result['stats']['reasons'])

    def test_coherent_fast_peak_is_not_rejected_for_high_speed_alone(self):
        peak=self.base.copy();peak[:,0]+=.08*self.wave
        result=self.verdict(current=peak,target=obj(peak,self.faces));self.assertEqual(result['status'],'clear');self.assertEqual(result['stats']['reasons'],[])

    def test_broad_surface_jump_is_detected(self):
        jumped=self.base.copy();jumped[:,2]+=.15*self.wave
        result=self.verdict(current=jumped);self.assertIn('surface_jump',result['stats']['reasons']);self.assertEqual(result['status'],'rejected')

    def test_incoherent_tangential_jump_and_neighbor_contamination(self):
        jumped=self.base.copy();ids=np.arange(len(jumped));jumped[:,0]+=.015*(-1.)**ids*self.wave
        result=self.verdict(current=jumped,threshold=.5);self.assertIn('incoherent_jump',result['stats']['reasons'])
        adjacent=self.verdict(following=jumped,threshold=.5);self.assertNotEqual(adjacent['status'],'rejected')

    def test_excluded_noise_does_not_trigger_anomaly_and_input_is_never_changed(self):
        center=312;excluded=np.flatnonzero(np.any(self.faces==center,axis=1)).tolist();noisy=self.base.copy();noisy[center,2]=.3
        quality=scan_quality(obj(noisy,self.faces),excluded,self.b['pairs']);self.assertLess(quality['roughnessPercent'],1e-8)
        original=noisy.copy();result=self.verdict(current=noisy,target=obj(noisy,self.faces),excluded={'source':excluded,'target':excluded});self.assertNotEqual(result['status'],'rejected');np.testing.assert_array_equal(noisy,original)

    def test_context_topology_and_settings_are_not_reported_as_certain_normality(self):
        scan={'roughnessPercent':50.,'sampleVertices':100,'topologyHash':'different'}
        body={'source':self.b['source'],'target':self.b['source'],'vertices':self.base,'pairs':self.b['pairs'],'excludedFaces':{},'threshold':2,'scanQuality':scan,'fitQuality':self.qfit,'neighbors':[{'name':'other','scanQuality':self.good,'fitQuality':self.qfit}]}
        result=classify_frame(body);self.assertEqual(result['status'],'limited');self.assertEqual(result['stats']['reasons'],[])
        for value in [{'detectAnomalies':1},{'anomalyPercent':0},{'anomalyPercent':float('nan')},{'anomalyPercent':21}]:
            with self.assertRaises(ValueError):temporal_settings(value)


class AnomalyBatchTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.manager=BatchManager(self.root,threading.BoundedSemaphore(1));self.b,_,self.faces=flow_fixture(side=25,shift=0);self.base=np.array(self.b['vertices']);self.wave=np.sin(self.base[:,0]*np.pi)*np.sin(self.base[:,1]*np.pi)
        self.body={'source':{'name':'template.obj','text':self.b['source']},'referenceTarget':self.b['target'],'pairs':self.b['pairs'],'settings':{'iterations':5,'solverMode':'multistage'},'temporal':{'mode':'bidirectional','strength':60,'distancePercent':5,'adaptive':True,'speedPercent':1,'detectAnomalies':True,'anomalyPercent':2},'bake':{'resolution':256,'padding':0,'distanceRatio':.02}}

    def tearDown(self):
        for thread in self.manager.threads.values():thread.join(30)
        self.temp.cleanup()

    def wait(self,job):
        self.manager.threads[job['id']].join(30);self.assertFalse(self.manager.threads[job['id']].is_alive());return self.manager.status(job['id'])

    def add_sequence(self,body):
        job=self.manager.create(body)
        for i in range(1,8):
            target=self.base.copy()
            if i==3:target[:,0]+=.08*self.wave
            if i==4:
                rng=np.random.default_rng(4);active=(target[:,0]>.15)&(target[:,0]<.85)&(target[:,1]>.15)&(target[:,1]<.85);target[active,2]+=rng.normal(0,.12,active.sum())
            text=export_obj(self.b['source'],target)+f'\n#frame{i}';self.manager.add({'jobId':job['id'],'name':f'frame{i}.obj','text':text,'texture':self.b['targetTexture']})
        return job

    def solve(self,source,target,*args):
        i=int(target.rsplit('#frame',1)[1]);vertices=parse_obj(target)[0]
        if i==4:vertices=self.base.copy()
        if i==6:vertices=self.base.copy();vertices[:,2]+=.15*self.wave
        return {'vertices':vertices.tolist(),'stats':{}}

    def test_noise_and_fit_jump_are_quarantined_before_adaptive_and_baking(self):
        job=self.add_sequence(self.body)
        with patch('batch_jobs.wrap',side_effect=self.solve):self.manager.start(job['id']);result=self.wait(job)
        self.assertEqual(result['counts']['failed'],2);self.assertEqual(result['counts']['succeeded'],5)
        for index,reason in [(3,'scan_noise'),(5,'surface_jump')]:
            item=result['items'][index];self.assertEqual(item['anomalyStatus'],'rejected');self.assertIn(reason,item['anomalyStats']['reasons']);self.assertNotIn('temporalStats',item);self.assertEqual(item['bakeStatus'],'skipped')
        self.assertNotEqual(result['items'][2]['anomalyStatus'],'rejected')
        for index in [2,4,6]:self.assertEqual(result['items'][index]['temporalStatus'],'seed')
        with zipfile.ZipFile(self.manager.download_path(job['id'])) as z:
            for item in result['items']:self.assertIn(item['resultFile'],z.namelist())
            self.assertIn('anomaly_status',z.read('report.csv').decode('utf-8-sig'));self.assertTrue(json.loads(z.read('settings.json'))['temporal']['detectAnomalies'])

    def test_causal_detection_uses_collected_context_and_resets_after_rejected_frame(self):
        job=self.add_sequence({**self.body,'bake':None,'temporal':{**self.body['temporal'],'mode':'causal'}})
        with patch('batch_jobs.wrap',side_effect=self.solve):self.manager.start(job['id']);result=self.wait(job)
        self.assertEqual(result['counts']['failed'],2)
        for index in [4,6]:self.assertEqual(result['items'][index]['temporalStatus'],'seed');self.assertIsNone(result['items'][index]['previousFrame'])
        for item in result['items']:self.assertIsNone(item.get('nextFrame'))

    def test_detector_failure_is_not_reported_as_clear_and_preserves_geometry(self):
        job=self.manager.create(self.body)
        for i in range(3):self.manager.add({'jobId':job['id'],'name':f'frame{i}.obj','text':self.b['source'],'texture':self.b['targetTexture']})
        with patch('batch_jobs.fit_quality',side_effect=ValueError('quality test error')):self.manager.start(job['id']);result=self.wait(job)
        self.assertEqual(result['counts']['failed'],3)
        for item in result['items']:self.assertEqual(item['anomalyStatus'],'failed');self.assertTrue(item['resultFile'])

    def test_interrupted_detection_has_explicit_state_and_portable_raw_geometry(self):
        job=self.manager.create(self.body);self.manager.add({'jobId':job['id'],'name':'frame.obj','text':self.b['source'],'texture':self.b['targetTexture']});stored=self.manager.jobs[job['id']];stored['status']='running';relative='results/raw.obj';(self.root/job['id']/relative).write_text(self.b['source'],encoding='utf-8',newline='')
        stored['items'][0].update(status='prepared',stage='anomaly',anomalyStatus='pending',temporalStatus='pending',resultFile=relative);self.manager._save(stored)
        stored['items'].append({'id':'0002','name':'failed.obj','status':'failed','error':'original solve error','resultFile':None,'anomalyStatus':'pending'});self.manager._save(stored)
        fresh=BatchManager(self.root,threading.BoundedSemaphore(1));result=fresh.status(job['id']);self.assertEqual(result['items'][0]['anomalyStatus'],'interrupted');self.assertEqual(result['items'][1]['anomalyStatus'],'interrupted');self.assertEqual(result['items'][1]['error'],'original solve error');self.assertTrue(result['archiveReady'])

    def test_cancel_during_detection_preserves_unprocessed_geometry_without_clear_verdict(self):
        job=self.manager.create(self.body)
        for i in range(3):self.manager.add({'jobId':job['id'],'name':f'frame{i}.obj','text':self.b['source'],'texture':self.b['targetTexture']})
        entered=threading.Event();release=threading.Event()
        def slow(*args):entered.set();release.wait(10);return fit_quality(*args)
        with patch('batch_jobs.fit_quality',side_effect=slow):
            self.manager.start(job['id']);self.assertTrue(entered.wait(10));self.manager.cancel(job['id']);release.set();result=self.wait(job)
        self.assertEqual(result['status'],'cancelled');self.assertEqual(result['counts']['skipped'],3)
        for item in result['items']:self.assertEqual(item['anomalyStatus'],'skipped');self.assertTrue(item['resultFile'])
