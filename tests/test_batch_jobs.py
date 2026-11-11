import json
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
import numpy as np
from batch_jobs import BatchManager,BatchBusy,constraints_manifest,topology_hash
from wrap_core import parse_obj,wrap
from test_core import fixture,obj
from test_texture import plane,quadrants
from PIL import Image
import io


class BatchTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.solver=threading.BoundedSemaphore(1);self.manager=BatchManager(self.root,self.solver)
        self.a,self.b,self.pairs,_=fixture()
        self.body={'source':{'name':'template.obj','text':self.a},'referenceTarget':self.b,'pairs':self.pairs,'settings':{'iterations':5,'solverMode':'multistage'},'mode':'sequence'}

    def tearDown(self):
        for thread in self.manager.threads.values():thread.join(10)
        self.temp.cleanup()

    def start_and_wait(self,job):
        self.manager.start(job['id']);self.manager.threads[job['id']].join(10)
        self.assertFalse(self.manager.threads[job['id']].is_alive());return self.manager.status(job['id'])

    def test_sequence_is_sorted_continues_after_errors_and_exports_exact_template_topology(self):
        job=self.manager.create(self.body)
        for name,text in [('scan10.obj',self.b),('scan2.obj','not an OBJ'),('scan1.obj',self.b)]:self.manager.add({'jobId':job['id'],'name':name,'text':text})
        result=self.start_and_wait(job);self.assertEqual(result['status'],'completed_with_errors');self.assertEqual(result['counts']['succeeded'],2);self.assertEqual([i['name'] for i in result['items']],['scan1.obj','scan2.obj','scan10.obj'])
        with zipfile.ZipFile(self.manager.download_path(job['id'])) as archive:
            self.assertIn('report.csv',archive.namelist());self.assertIn('settings.json',archive.namelist());files=[n for n in archive.namelist() if n.endswith('.obj')];self.assertEqual(len(files),2)
            target,_=parse_obj(self.b);_,original_faces=parse_obj(self.a)
            for name in files:
                v,f=parse_obj(archive.read(name).decode());np.testing.assert_array_equal(f,original_faces)
                np.testing.assert_allclose(v[[p[0] for p in self.pairs]],target[[p[1] for p in self.pairs]],atol=1e-9)
            report=json.loads(archive.read('report.json'));self.assertEqual(report['status'],'completed_with_errors')

    def texture_body(self):
        return {**self.body,'source':{'name':'template.obj','text':plane(True)},'referenceTarget':plane(),'pairs':[[i,i] for i in range(4)],'bake':{'resolution':256,'padding':0,'distanceRatio':.02}}

    def test_batch_bakes_distinct_images_into_template_uv_and_exports_portable_assets(self):
        job=self.manager.create(self.texture_body())
        from texture import png_texture
        images=[quadrants(),png_texture(Image.new('RGBA',(16,16),(23,67,123,128)),'other.png')]
        for i,image in enumerate(images):self.manager.add({'jobId':job['id'],'name':f'scan{i}.obj','text':plane(),'texture':image})
        result=self.start_and_wait(job);self.assertEqual(result['status'],'completed');self.assertEqual(result['counts']['succeeded'],2)
        with zipfile.ZipFile(self.manager.download_path(job['id'])) as archive:
            for i,item in enumerate(result['items']):
                self.assertEqual(item['bakeStats']['coverage'],1);folder=str(Path(item['resultFile']).parent).replace('\\','/')
                self.assertEqual(len(item['resultFiles']),4)
                self.assertIn('mtllib model.mtl',archive.read(item['resultFile']).decode());self.assertIn('map_Kd texture.png',archive.read(folder+'/model.mtl').decode())
                v,f,uv,uf=parse_obj(archive.read(item['resultFile']).decode(),with_uv=True);a,b,c,d=parse_obj(plane(True),with_uv=True)
                np.testing.assert_array_equal(f,b);np.testing.assert_array_equal(uv,c);np.testing.assert_array_equal(uf,d);np.testing.assert_allclose(v,a,atol=1e-9)
                pixels=np.asarray(Image.open(io.BytesIO(archive.read(folder+'/texture.png'))));opacity=np.asarray(Image.open(io.BytesIO(archive.read(folder+'/opacity.png'))))
                np.testing.assert_array_equal(pixels[64,64],[0,255,0,255] if i==0 else [23,67,123,128]);np.testing.assert_array_equal(opacity,pixels[:,:,3])
            self.assertEqual(sum(len(archive.read(n)) for n in archive.namelist() if n.startswith('results/')),result['outputBytes'])
        restored=BatchManager(self.root,threading.BoundedSemaphore(1));self.assertEqual(restored.status(job['id'])['items'],result['items'])

    def test_bake_failures_preserve_geometry_and_continue_without_reusing_another_scan_texture(self):
        job=self.manager.create(self.texture_body())
        for name,texture,error in [('missing.obj',None,'未找到贴图'),('broken.obj',{'name':'bad.png','dataUrl':'data:image/png;base64,AAAA'},None),('good.obj',quadrants(),None)]:
            self.manager.add({'jobId':job['id'],'name':name,'text':plane(),'texture':texture,'textureError':error})
        result=self.start_and_wait(job);self.assertEqual(result['counts']['failed'],2);self.assertEqual(result['counts']['succeeded'],1)
        with zipfile.ZipFile(self.manager.download_path(job['id'])) as archive:
            for item in result['items']:
                self.assertIn(item['resultFile'],archive.namelist())
                if item['status']=='failed':self.assertEqual(item['bakeStatus'],'failed');self.assertIn('几何已保留',item['error'])

    def test_batch_bake_validates_settings_uv_input_and_output_budgets(self):
        for value in [{'resolution':999},{'padding':99},{'distanceRatio':float('nan')}]:
            with self.assertRaises(ValueError):self.manager.create({**self.texture_body(),'bake':value})
        with self.assertRaises(ValueError):self.manager.create({**self.body,'bake':{}})
        job=self.manager.create(self.texture_body());image=quadrants()
        with patch('batch_jobs.MAX_BYTES',len(plane().encode())+1):
            with self.assertRaisesRegex(ValueError,'256 MB'):self.manager.add({'jobId':job['id'],'name':'oversize.obj','text':plane(),'texture':image})
        self.manager.add({'jobId':job['id'],'name':'a.obj','text':plane(),'texture':image});self.manager.add({'jobId':job['id'],'name':'b.obj','text':plane(),'texture':image})
        with patch('batch_jobs.MAX_BYTES',len(plane().encode())+200):result=self.start_and_wait(job)
        self.assertEqual(result['status'],'limited');self.assertEqual(result['counts']['failed'],1);self.assertEqual(result['counts']['skipped'],1);self.assertTrue(result['items'][0]['resultFile'])

    def test_cancel_during_bake_finishes_texture_and_keeps_portable_partial_export(self):
        from texture import bake_texture
        job=self.manager.create(self.texture_body())
        for name in ['frame1.obj','frame2.obj']:self.manager.add({'jobId':job['id'],'name':name,'text':plane(),'texture':quadrants()})
        entered=threading.Event();release=threading.Event()
        def slow(*args,**kwargs):entered.set();release.wait(5);return bake_texture(*args,**kwargs)
        with patch('batch_jobs.bake_texture',side_effect=slow):
            self.manager.start(job['id']);self.assertTrue(entered.wait(5));self.assertEqual(self.manager.status(job['id'])['items'][0]['stage'],'baking');self.manager.cancel(job['id']);release.set();self.manager.threads[job['id']].join(10)
        result=self.manager.status(job['id']);self.assertEqual(result['status'],'cancelled');self.assertEqual(result['counts']['succeeded'],1);self.assertEqual(result['counts']['skipped'],1)
        with zipfile.ZipFile(self.manager.download_path(job['id'])) as archive:self.assertEqual(len([n for n in archive.namelist() if n.startswith('results/')]),4)
        self.assertTrue(self.solver.acquire(False));self.solver.release()

    def test_restart_during_bake_preserves_confirmed_geometry_and_clears_active_stage(self):
        job=self.manager.create(self.texture_body());self.manager.add({'jobId':job['id'],'name':'frame.obj','text':plane(),'texture':quadrants()})
        stored=self.manager.jobs[job['id']];stored['status']='running';relative='results/0001_frame_wrapped.obj'
        (self.root/job['id']/relative).write_text(plane(True),encoding='utf-8',newline='')
        stored['items'][0].update(status='running',stage='baking',bakeStatus='running',resultFile=relative);self.manager._save(stored)
        restored=BatchManager(self.root,threading.BoundedSemaphore(1));result=restored.status(job['id'])
        self.assertEqual(result['status'],'interrupted');self.assertEqual(result['items'][0]['bakeStatus'],'interrupted');self.assertNotIn('stage',result['items'][0])
        with zipfile.ZipFile(restored.download_path(job['id'])) as archive:self.assertEqual(archive.read(relative).decode(),plane(True))

    def test_topology_mismatch_is_not_allowed_to_reuse_target_indices(self):
        job=self.manager.create(self.body);v,f=parse_obj(self.b);f=f[::-1]
        self.manager.add({'jobId':job['id'],'name':'different.obj','text':obj(v,f)})
        result=self.start_and_wait(job);self.assertEqual(result['counts']['failed'],1);self.assertIn('拓扑',result['items'][0]['error'])

    def test_independent_targets_use_their_own_pairs_and_template_signature(self):
        manifest=constraints_manifest({'source':self.a,'target':self.b,'name':'different.obj','pairs':self.pairs})
        v,f=parse_obj(self.b);extra=np.vstack([v,[99,99,99]]);body={**self.body,'mode':'independent','constraints':manifest}
        job=self.manager.create(body);self.manager.add({'jobId':job['id'],'name':'different.obj','text':obj(extra,f[::-1])});self.manager.add({'jobId':job['id'],'name':'missing.obj','text':self.b})
        result=self.start_and_wait(job);self.assertEqual(result['counts']['succeeded'],1);self.assertEqual(result['counts']['failed'],1);self.assertIn('JSON',result['items'][1]['error'])
        manifest['templateTopologyHash']='wrong'
        with self.assertRaises(ValueError):self.manager.create(body)

    def test_cancel_finishes_current_item_and_preserves_partial_archive(self):
        job=self.manager.create(self.body)
        for name in ['frame1.obj','frame2.obj']:self.manager.add({'jobId':job['id'],'name':name,'text':self.b})
        entered=threading.Event();release=threading.Event()
        def slow(*args,**kwargs):entered.set();release.wait(5);return wrap(*args,**kwargs)
        with patch('batch_jobs.wrap',side_effect=slow):
            self.manager.start(job['id']);self.assertTrue(entered.wait(5));cancelled=self.manager.cancel(job['id']);self.assertEqual(cancelled['status'],'cancelling');release.set();self.manager.threads[job['id']].join(10)
        result=self.manager.status(job['id']);self.assertEqual(result['status'],'cancelled');self.assertEqual(result['counts']['succeeded'],1);self.assertEqual(result['counts']['skipped'],1);self.assertTrue(result['archiveReady'])
        self.assertTrue(self.solver.acquire(False));self.solver.release()

    def test_server_restart_marks_unfinished_job_interrupted(self):
        job=self.manager.create(self.body);self.manager.add({'jobId':job['id'],'name':'scan.obj','text':self.b})
        saved=self.manager.jobs[job['id']];saved['status']='running';saved['items'][0]['status']='running';self.manager._save(saved)
        fresh=BatchManager(self.root,threading.BoundedSemaphore(1));result=fresh.status(job['id']);self.assertEqual(result['status'],'interrupted');self.assertEqual(result['counts']['skipped'],1);self.assertTrue(result['archiveReady'])

    def test_lock_conflicts_invalid_names_duplicates_and_upload_failures(self):
        job=self.manager.create(self.body)
        with self.assertRaises(ValueError):self.manager.add({'jobId':job['id'],'name':'../escape.obj','text':self.b})
        self.manager.add({'jobId':job['id'],'name':'SCAN.obj','uploadError':'too large'})
        with self.assertRaises(ValueError):self.manager.add({'jobId':job['id'],'name':'scan.obj','text':self.b})
        self.solver.acquire()
        with self.assertRaises(BatchBusy):self.manager.start(job['id'])
        self.solver.release();result=self.start_and_wait(job);self.assertEqual(result['counts']['failed'],1)
        with self.assertRaises(ValueError):self.manager.status('../escape')

    def test_cancel_draft_and_restored_finished_report(self):
        job=self.manager.create(self.body);self.manager.add({'jobId':job['id'],'name':'scan.obj','text':self.b});result=self.manager.cancel(job['id']);self.assertEqual(result['status'],'cancelled');self.assertTrue(result['archiveReady'])
        fresh=BatchManager(self.root,threading.BoundedSemaphore(1));self.assertEqual(fresh.status(job['id'])['counts'],result['counts'])

    def test_predeclared_queue_reports_unuploaded_items_when_cancelled(self):
        job=self.manager.create({**self.body,'names':['frame1.obj','frame2.obj','frame3.obj']})
        self.manager.add({'jobId':job['id'],'name':'frame1.obj','text':self.b})
        with self.assertRaises(ValueError):self.manager.start(job['id'])
        result=self.manager.cancel(job['id']);self.assertEqual(result['counts']['skipped'],3);self.assertEqual(len(result['items']),3)

    def test_output_limit_preserves_report_and_skips_remaining_items(self):
        job=self.manager.create(self.body)
        for name in ['one.obj','two.obj']:self.manager.add({'jobId':job['id'],'name':name,'text':self.b})
        with patch('batch_jobs.MAX_BYTES',1):result=self.start_and_wait(job)
        self.assertEqual(result['status'],'limited');self.assertEqual(result['counts']['failed'],1);self.assertEqual(result['counts']['skipped'],1);self.assertTrue(result['archiveReady'])

    def test_failed_start_does_not_leave_solver_locked(self):
        job=self.manager.create(self.body);self.manager.add({'jobId':job['id'],'name':'scan.obj','text':self.b})
        with patch.object(self.manager,'_save',side_effect=OSError('disk full')):
            with self.assertRaises(OSError):self.manager.start(job['id'])
        self.assertTrue(self.solver.acquire(False));self.solver.release()
