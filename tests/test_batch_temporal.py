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
from batch_jobs import BatchManager,constraints_manifest
from temporal import smooth_frame
from optical_flow import refine_texture
from texture import bake_texture,read_texture
from wrap_core import wrap,parse_obj,export_obj
from test_optical_flow import flow_fixture


class BatchTemporalTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.solver=threading.BoundedSemaphore(1);self.manager=BatchManager(self.root,self.solver)
        self.b,_,self.faces=flow_fixture(side=17,shift=0);b=self.b
        self.body={'source':{'name':'template.obj','text':b['source']},'referenceTarget':b['target'],'pairs':b['pairs'],'settings':{'iterations':5,'solverMode':'multistage'},'temporal':{'strength':60,'distancePercent':5}}

    def tearDown(self):
        for thread in self.manager.threads.values():thread.join(30)
        self.temp.cleanup()

    def add(self,job,name,text=None,**kwargs):
        self.manager.add({'jobId':job['id'],'name':name,'text':self.b['target'] if text is None else text,'texture':self.b['targetTexture'],**kwargs})

    def run_job(self,job):
        self.manager.start(job['id']);self.manager.threads[job['id']].join(30);self.assertFalse(self.manager.threads[job['id']].is_alive());return self.manager.status(job['id'])

    def test_smoothed_jitter_batch_preserves_per_frame_constraints_uv_and_bakes_final_vertices(self):
        names=[f'frame{i}.obj' for i in range(5)];manifest=constraints_manifest({'source':self.b['source'],'target':self.b['target'],'name':names[0],'pairs':self.b['pairs']})
        manifest['items']=[{'name':name,'pairs':self.b['pairs']+[[120+i,120+i]],'excludedTargetFaces':[20+i]} for i,name in enumerate(names)]
        weights=np.ones(len(self.b['vertices']));weights[np.asarray(self.b['vertices'])[:,0]<.2]=0
        body={**self.body,'mode':'independent','constraints':manifest,'excludedSourceFaces':[10],'bake':{'resolution':256,'padding':0,'distanceRatio':.02},'temporal':{**self.body['temporal'],'brushWeights':weights.tolist()}}
        job=self.manager.create(body)
        for i in reversed(range(5)):self.add(job,names[i],self.b['target']+f'\n#frame{i}')
        raws=[]
        def jitter(source,target,pairs,*args):
            i=int(target.rsplit('#frame',1)[1]);v=np.array(self.b['vertices']);v[:,0]+=.015*(-1)**i*np.sin(v[:,0]*np.pi)*np.sin(v[:,1]*np.pi)
            locked=np.unique(np.r_[[p[0] for p in pairs],self.faces[10]]);v[locked]=np.asarray(self.b['vertices'])[locked];raws.append(v.copy());return {'vertices':v.tolist(),'stats':{}}
        with patch('batch_jobs.wrap',side_effect=jitter):result=self.run_job(job)
        self.assertEqual(result['counts']['succeeded'],5);outputs=[]
        with zipfile.ZipFile(self.manager.download_path(job['id'])) as z:
            for i,item in enumerate(result['items']):
                v,f,uv,uf=parse_obj(z.read(item['resultFile']).decode(),True);outputs.append(v);_,sf,suv,suf=parse_obj(self.b['source'],True)
                np.testing.assert_array_equal(f,sf);np.testing.assert_array_equal(uv,suv);np.testing.assert_array_equal(uf,suf)
                locked=np.unique(np.r_[[p[0] for p in manifest['items'][i]['pairs']],self.faces[10],np.flatnonzero(weights==0)])
                np.testing.assert_allclose(v[locked],raws[i][locked],atol=1e-9)
                expected=bake_texture(self.b['source'],self.b['target'],v,self.b['targetTexture'],256,0,excluded_faces={'source':[10],'target':[20+i]})
                pixels=Image.open(io.BytesIO(z.read(item['resultFile'].rsplit('/',1)[0]+'/texture.png')));np.testing.assert_array_equal(pixels,read_texture(expected['texture']))
                self.assertEqual(item['temporalStatus'],'seed' if i==0 else 'succeeded');self.assertEqual(item['previousFrame'],names[i-1] if i else None)
            self.assertIn('temporal_status',z.read('report.csv').decode('utf-8-sig'));self.assertEqual(sum(len(z.read(n)) for n in z.namelist() if n.startswith('results/')),result['outputBytes'])
        jitter=lambda v:np.linalg.norm(np.diff(np.array(v),n=2,axis=0),axis=2).mean()
        self.assertLess(jitter(outputs),jitter(raws)*.6)

    def test_real_flow_temporal_bake_pipeline_matches_expected_stage_order(self):
        b,_,_=flow_fixture(side=17);other,_,_=flow_fixture(side=17,shift=.045)
        body={**self.body,'source':{'name':'template.obj','text':b['source']},'referenceTarget':b['target'],'bake':{'resolution':256,'padding':0,'distanceRatio':.02},'flow':{'settings':b['settings'],'cameraWorld':b['cameraWorld'],'sourceTexture':b['sourceTexture'],'brushWeights':None}}
        job=self.manager.create(body)
        for i,frame in enumerate([b,other]):self.add(job,f'frame{i}.obj',frame['target'])
        result=self.run_job(job);self.assertEqual(result['counts']['succeeded'],2);previous=None
        with zipfile.ZipFile(self.manager.download_path(job['id'])) as z:
            for item,frame in zip(result['items'],[b,other]):
                initial=wrap(frame['source'],frame['target'],frame['pairs'],5,4,normal_angle=60,solver_mode='multistage')
                refined=refine_texture({**frame,'vertices':initial['vertices']})
                expected=smooth_frame({**frame,'vertices':refined['vertices'],'settings':body['temporal']},previous);previous=np.asarray(expected['vertices'])
                actual,_=parse_obj(z.read(item['resultFile']).decode());exported,_=parse_obj(export_obj(frame['source'],previous));np.testing.assert_array_equal(actual,exported)
                self.assertEqual(item['flowStatus'],'succeeded');self.assertEqual(item['bakeStatus'],'succeeded')
        self.assertGreater(result['items'][1]['temporalStats']['changedVertices'],0)

    def test_failed_mesh_bake_and_smoothing_break_history_before_next_frame(self):
        job=self.manager.create({**self.body,'bake':{'resolution':256,'padding':0,'distanceRatio':.02}})
        for i in range(1,8):self.add(job,f'frame{i}.obj','bad OBJ' if i==2 else None,**({'texture':None,'textureError':'missing'} if i==4 else {}))
        def smooth(body,previous):
            # Call order is 1,3,4,5,6,7; fail only frame 6.
            smooth.calls+=1
            if smooth.calls==5:raise ValueError('injected temporal failure')
            return smooth_frame(body,previous)
        smooth.calls=0
        with patch('batch_jobs.smooth_frame',side_effect=smooth):result=self.run_job(job)
        self.assertEqual(result['counts']['failed'],3)
        for index in [0,2,4,6]:self.assertEqual(result['items'][index]['temporalStatus'],'seed');self.assertIsNone(result['items'][index]['previousFrame'])
        self.assertEqual(result['items'][5]['temporalStatus'],'failed');self.assertTrue(result['items'][5]['resultFile'])

    def test_cancel_in_temporal_finishes_current_frame_and_keeps_textured_partial_archive(self):
        job=self.manager.create({**self.body,'bake':{'resolution':256,'padding':0,'distanceRatio':.02}});self.add(job,'frame1.obj');self.add(job,'frame2.obj')
        entered=threading.Event();release=threading.Event()
        def slow(body,previous):entered.set();release.wait(10);return smooth_frame(body,previous)
        with patch('batch_jobs.smooth_frame',side_effect=slow):
            self.manager.start(job['id']);self.assertTrue(entered.wait(10));self.assertEqual(self.manager.status(job['id'])['items'][0]['stage'],'temporal');self.manager.cancel(job['id']);release.set();self.manager.threads[job['id']].join(30)
        result=self.manager.status(job['id']);self.assertEqual(result['status'],'cancelled');self.assertEqual(result['counts']['succeeded'],1);self.assertEqual(result['counts']['skipped'],1);self.assertEqual(result['items'][0]['bakeStatus'],'succeeded')
        self.assertTrue(self.solver.acquire(False));self.solver.release()

    def test_restart_in_temporal_keeps_geometry_and_marks_interrupted(self):
        job=self.manager.create(self.body);self.add(job,'frame.obj');stored=self.manager.jobs[job['id']];stored['status']='running';relative='results/frame.obj';(self.root/job['id']/relative).write_text(self.b['source'],encoding='utf-8',newline='')
        stored['items'][0].update(status='running',stage='temporal',temporalStatus='running',resultFile=relative);self.manager._save(stored)
        fresh=BatchManager(self.root,threading.BoundedSemaphore(1));result=fresh.status(job['id']);self.assertEqual(result['items'][0]['temporalStatus'],'interrupted');self.assertNotIn('stage',result['items'][0]);self.assertTrue(result['archiveReady'])

    def test_temporal_configuration_validation(self):
        for value in [False,{'strength':91},{'distancePercent':0},{'brushWeights':[-1]*len(self.b['vertices'])}]:
            with self.assertRaises(ValueError):self.manager.create({**self.body,'temporal':value})
