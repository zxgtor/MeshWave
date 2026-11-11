import base64
import hashlib
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
from batch_jobs import BatchManager
from optical_flow import refine_texture
from texture import bake_texture, png_texture, read_texture
from wrap_core import parse_obj, wrap, export_obj
from test_optical_flow import flow_fixture


class BatchFlowTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.solver=threading.BoundedSemaphore(1);self.manager=BatchManager(self.root,self.solver)
        self.fixture,self.truth,self.faces=flow_fixture(side=17)
        b=self.fixture
        self.body={'source':{'name':'neutral.obj','text':b['source']},'referenceTarget':b['target'],'pairs':b['pairs'],'settings':{'iterations':5,'solverMode':'multistage'},'bake':{'resolution':256,'padding':0,'distanceRatio':.02},'flow':{'settings':b['settings'],'cameraWorld':b['cameraWorld'],'sourceTexture':b['sourceTexture'],'brushWeights':None}}

    def tearDown(self):
        for thread in self.manager.threads.values():thread.join(30)
        self.temp.cleanup()

    def add(self,job,name='frame.obj',fixture=None,**kwargs):
        b=fixture or self.fixture
        return self.manager.add({'jobId':job['id'],'name':name,'text':b['target'],'texture':b['targetTexture'],**kwargs})

    def wait(self,job):
        self.manager.threads[job['id']].join(30);self.assertFalse(self.manager.threads[job['id']].is_alive());return self.manager.status(job['id'])

    def test_real_sequence_refines_each_expression_then_bakes_final_geometry(self):
        other,truth2,_=flow_fixture(side=17,shift=-.035)
        job=self.manager.create(self.body);self.add(job,'frame1.obj');self.add(job,'frame2.obj',other);self.manager.start(job['id']);result=self.wait(job)
        self.assertEqual(result['status'],'completed');self.assertEqual(result['counts']['succeeded'],2)
        with zipfile.ZipFile(self.manager.download_path(job['id'])) as archive:
            for item,b,truth in zip(result['items'],[self.fixture,other],[self.truth,truth2]):
                self.assertEqual(item['flowStatus'],'succeeded');self.assertEqual(item['bakeStatus'],'succeeded');stats=item['flowStats'];self.assertLess(stats['afterPhotoError'],stats['beforePhotoError'])
                before=wrap(b['source'],b['target'],b['pairs'],5,4,normal_angle=60,solver_mode='multistage')['vertices']
                vertices,faces,uv,uf=parse_obj(archive.read(item['resultFile']).decode(),True)
                self.assertLess(np.linalg.norm(vertices-truth,axis=1).mean(),np.linalg.norm(np.array(before)-truth,axis=1).mean())
                pins=[p[0] for p in b['pairs']];np.testing.assert_array_equal(vertices[pins],np.asarray(before)[pins])
                _,sf,suv,suf=parse_obj(b['source'],True);np.testing.assert_array_equal(faces,sf);np.testing.assert_array_equal(uv,suv);np.testing.assert_array_equal(uf,suf)
                expected=bake_texture(b['source'],b['target'],vertices,b['targetTexture'],256,0)
                actual=Image.open(io.BytesIO(archive.read(item['resultFile'].rsplit('/',1)[0]+'/texture.png')))
                np.testing.assert_array_equal(np.asarray(actual),np.asarray(read_texture(expected['texture'])))
            config=json.loads(archive.read('settings.json'));self.assertNotIn('dataUrl',config['flow']['sourceTexture']);self.assertEqual(config['flow']['cameraWorld'],self.fixture['cameraWorld'])
            self.assertIn('flow_status',archive.read('report.csv').decode('utf-8-sig'))
        raw=base64.b64decode(self.fixture['sourceTexture']['dataUrl'].split(',')[1]);self.assertEqual((self.root/job['id']/'reference.texture').read_bytes(),raw)
        self.assertEqual(config['flow']['sourceTexture']['sha256'],hashlib.sha256(raw).hexdigest())

    def test_flat_missing_and_no_improvement_frames_fail_without_fake_baking_then_continue(self):
        job=self.manager.create(self.body)
        flat=png_texture(Image.new('RGB',(256,256),(150,150,150)),'flat.png')
        self.add(job,'frame1.obj',texture=flat);self.add(job,'frame2.obj',texture=None,textureError='未找到贴图')
        self.add(job,'frame3.obj');self.manager.start(job['id']);result=self.wait(job)
        self.assertEqual(result['counts']['failed'],2);self.assertEqual(result['counts']['succeeded'],1)
        with zipfile.ZipFile(self.manager.download_path(job['id'])) as archive:
            for item in result['items'][:2]:
                self.assertEqual(item['flowStatus'],'failed');self.assertEqual(item['bakeStatus'],'skipped');self.assertIn(item['resultFile'],archive.namelist());self.assertNotIn('flowStats',item)
        # The existing refiner also rejects an exact neutral frame with no verified improvement.
        exact={**self.fixture,'target':self.fixture['source']};job=self.manager.create(self.body);self.add(job,fixture=exact);self.manager.start(job['id']);result=self.wait(job)
        self.assertEqual(result['counts']['failed'],1);self.assertEqual(result['items'][0]['bakeStatus'],'skipped')

    def test_reference_camera_weights_and_required_baking_are_validated_before_job_creation(self):
        for flow in [None,{'cameraWorld':[0]*16},{'brushWeights':[2]*len(self.truth)},{'sourceTexture':None},{'settings':{'resolution':1000}}]:
            body={**self.body,'flow':{**self.body['flow'],**(flow or {})}}
            if flow is None:body['bake']=None
            with self.assertRaises(ValueError):self.manager.create(body)
        job=self.manager.create(self.body);raw=base64.b64decode(self.fixture['sourceTexture']['dataUrl'].split(',')[1]);self.assertEqual(job['inputBytes'],len(raw))

    def test_cancel_in_flow_finishes_current_refinement_and_baking_and_skips_next_frame(self):
        job=self.manager.create(self.body);self.add(job,'frame1.obj');self.add(job,'frame2.obj');entered=threading.Event();release=threading.Event()
        def slow(body):entered.set();release.wait(10);return refine_texture(body)
        with patch('batch_jobs.refine_texture',side_effect=slow):
            self.manager.start(job['id']);self.assertTrue(entered.wait(10));self.assertEqual(self.manager.status(job['id'])['items'][0]['stage'],'flow');self.manager.cancel(job['id']);release.set();result=self.wait(job)
        self.assertEqual(result['status'],'cancelled');self.assertEqual(result['counts']['succeeded'],1);self.assertEqual(result['counts']['skipped'],1);self.assertEqual(result['items'][0]['bakeStatus'],'succeeded');self.assertTrue(result['archiveReady'])
        self.assertTrue(self.solver.acquire(False));self.solver.release()

    def test_bake_failure_preserves_refined_geometry_and_flow_stats(self):
        job=self.manager.create(self.body);self.add(job)
        with patch('batch_jobs.bake_texture',side_effect=ValueError('bake test failure')):self.manager.start(job['id']);result=self.wait(job)
        item=result['items'][0];self.assertEqual(item['status'],'failed');self.assertEqual(item['flowStatus'],'succeeded');self.assertEqual(item['bakeStatus'],'failed')
        vertices,_=parse_obj((self.root/job['id']/item['resultFile']).read_text())
        self.assertLess(np.linalg.norm(vertices-self.truth,axis=1).mean(),np.linalg.norm(np.asarray(self.fixture['vertices'])-self.truth,axis=1).mean())

    def test_flow_preserves_soft_protection_exclusions_and_hard_points_from_snapshot(self):
        weights=np.ones(len(self.truth));weights[np.asarray(self.fixture['vertices'])[:,0]<.2]=0
        body={**self.body,'excludedSourceFaces':[10],'excludedTargetFaces':[15],'flow':{**self.body['flow'],'brushWeights':weights.tolist()}}
        job=self.manager.create(body);self.add(job);self.manager.start(job['id']);result=self.wait(job);item=result['items'][0];self.assertEqual(item['status'],'succeeded')
        before=wrap(self.fixture['source'],self.fixture['target'],self.fixture['pairs'],5,4,{'source':[10],'target':[15]},60,'multistage')['vertices']
        with zipfile.ZipFile(self.manager.download_path(job['id'])) as archive:after,_=parse_obj(archive.read(item['resultFile']).decode())
        locked=np.unique(np.r_[np.flatnonzero(weights==0),[p[0] for p in self.fixture['pairs']],self.faces[10]])
        exported_before,_=parse_obj(export_obj(self.fixture['source'],before))
        np.testing.assert_array_equal(after[locked],exported_before[locked])

    def test_restart_in_flow_marks_interrupted_and_preserves_geometry(self):
        job=self.manager.create(self.body);self.add(job);stored=self.manager.jobs[job['id']];stored['status']='running';relative='results/frame.obj'
        (self.root/job['id']/relative).write_text(self.fixture['source'],encoding='utf-8',newline='')
        stored['items'][0].update(status='running',stage='flow',flowStatus='running',bakeStatus='pending',resultFile=relative);self.manager._save(stored)
        fresh=BatchManager(self.root,threading.BoundedSemaphore(1));result=fresh.status(job['id']);item=result['items'][0]
        self.assertEqual(result['status'],'interrupted');self.assertEqual(item['flowStatus'],'interrupted');self.assertEqual(item['bakeStatus'],'skipped');self.assertNotIn('stage',item)
        with zipfile.ZipFile(fresh.download_path(job['id'])) as archive:self.assertIn(relative,archive.namelist())
