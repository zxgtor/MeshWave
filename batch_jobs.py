"""Sequential, disk-backed wrap and optional texture batches with partial export."""
import csv
import base64
import hashlib
import io
import json
import re
import threading
import time
import uuid
import zipfile
from pathlib import Path
import numpy as np
from wrap_core import mesh_data,parse_obj,wrap,export_obj,index_list,exclusion_masks,MAX_SOURCE
from point_constraints import handle_shape,surface_pairs,validate_pairs
from texture import read_texture, bake_texture, texture_bundle
from optical_flow import refine_texture, cameras, cv_module
from flow_settings import flow_settings
from temporal import temporal_settings, smooth_frame
from anomalies import scan_quality,fit_quality,classify_frame
from frame_repair import repair_frame

MAX_ITEMS=50
MAX_BYTES=256*1024*1024
TERMINAL={'completed','completed_with_errors','cancelled','interrupted','failed','limited'}


class BatchBusy(ValueError):pass
class BatchOutputLimit(ValueError):pass


def topology_hash(vertices,faces):
    header=np.array([len(vertices),len(faces)],dtype='<i8').tobytes()
    return hashlib.sha256(header+np.asarray(faces,dtype='<i8').tobytes()).hexdigest()


def filename(value):
    if not isinstance(value,str) or not value or len(value)>255 or '/' in value or '\\' in value or not value.lower().endswith('.obj'):
        raise ValueError('扫描名称必须是不含路径的 OBJ 文件名。')
    return value


def geometry_settings(value):
    if not isinstance(value,dict):raise ValueError('批处理参数无效。')
    result={k:value.get(k,d) for k,d in [('iterations',20),('smoothness',4),('normalAngle',60),('solverMode','multistage')]}
    if type(result['iterations']) is not int or not 5<=result['iterations']<=50:raise ValueError('批处理迭代为 5–50 次。')
    for key,lo,hi in [('smoothness',.1,30),('normalAngle',10,89)]:
        if type(result[key]) not in (int,float) or not np.isfinite(result[key]) or not lo<=result[key]<=hi:raise ValueError('批处理平滑强度或法线夹角无效。')
    if result['solverMode'] not in ('single','multistage'):raise ValueError('批处理求解模式无效。')
    return result


def pairs_valid(pairs,source_count,target_count):
    if not isinstance(pairs,list) or not 3<=len(pairs)<=100 or any(not isinstance(p,list) or len(p)!=2 for p in pairs):raise ValueError('每项需要 3–100 对对应点。')
    for column,limit in [(0,source_count),(1,target_count)]:
        ids=[handle_shape(p[column],limit) for p in pairs]
        keys=[json.dumps(i,sort_keys=True) for i in ids]
        if len(set(keys))!=len(keys):raise ValueError('批处理对应点存在重复索引。')


def constraints_manifest(body):
    source,sf=parse_obj(body['source']);target,tf=parse_obj(body['target']);pairs=validate_pairs(body['pairs'],{'source':(source,sf),'target':(target,tf)},3)
    masks=exclusion_masks(sf,tf,body.get('excludedFaces',{}),pairs)
    return {'format':'facewrap-batch-constraints','version':2 if surface_pairs(pairs) else 1,'templateTopologyHash':topology_hash(source,sf),
            'items':[{'name':filename(body['name']),'pairs':pairs,'excludedTargetFaces':masks['target'][0].tolist()}]}


class BatchManager:
    def __init__(self,root,solver):
        self.root=Path(root);self.solver=solver;self.lock=threading.RLock();self.jobs={};self.threads={}

    def _path(self,job_id):
        if not isinstance(job_id,str) or not re.fullmatch('[a-f0-9]{32}',job_id):raise ValueError('批处理任务编号无效。')
        return self.root/job_id

    def _save(self,job):
        path=self._path(job['id']);temporary=path/'job.tmp'
        temporary.write_text(json.dumps(job,ensure_ascii=False,allow_nan=False),encoding='utf-8');temporary.replace(path/'job.json')

    def _get(self,job_id):
        path=self._path(job_id)
        if job_id not in self.jobs:
            if not (path/'job.json').is_file():raise ValueError('任务不存在；请检查本地服务或重新开始。')
            job=json.loads((path/'job.json').read_text(encoding='utf-8'));self.jobs[job_id]=job
            if job['status']=='packaging' and (path/'results.zip').is_file():
                job['status']=job.get('finalStatus','interrupted');self._save(job)
            elif job['status'] in ('running','cancelling','packaging'):
                for item in job['items']:
                    if item['status'] in ('awaiting_upload','pending','running','prepared'):
                        item.update(status='skipped',error='本地服务停止，未完成；请另建批次重试。');item.pop('stage',None)
                        if item.get('bakeStatus')=='running':item['bakeStatus']='interrupted'
                        if item.get('flowStatus')=='running':item['flowStatus']='interrupted';item['bakeStatus']='skipped'
                        if item.get('temporalStatus')=='running':item['temporalStatus']='interrupted';item['bakeStatus']='skipped'
                        if item.get('temporalStatus')=='pending':item['temporalStatus']='interrupted';item['bakeStatus']='skipped'
                    if item.get('anomalyStatus')=='pending':item['anomalyStatus']='interrupted'
                    if item.get('repairStatus')=='running':item['repairStatus']='interrupted';item.pop('stage',None)
                job['status']='interrupted';job['finishedAt']=time.time();self._save(job);self._archive(job)
        return self.jobs[job_id]

    def _public(self,job):
        value=json.loads(json.dumps(job));value['outputPath']=str(self._path(job['id']).resolve())
        value['archiveReady']=(self._path(job['id'])/'results.zip').is_file() and job['status'] in TERMINAL
        value['counts']={status:sum(i['status']==status for i in job['items']) for status in ['awaiting_upload','pending','running','prepared','succeeded','failed','skipped']}
        return value

    def create(self,body):
        source=body.get('source');mode=body.get('mode','sequence')
        names=body.get('names',[])
        if not isinstance(names,list) or len(names)>MAX_ITEMS:raise ValueError('每批最多 50 个扫描。')
        names=[filename(name) for name in names]
        if len({n.casefold() for n in names})!=len(names):raise ValueError('队列文件名重复。')
        if not isinstance(source,dict) or not isinstance(source.get('name'),str) or not isinstance(source.get('text'),str):raise ValueError('缺少批处理模板。')
        if len(source['text'].encode('utf-8'))>18*1024*1024:raise ValueError('模板上限为 18 MB。')
        source_mesh=mesh_data(source['text']);sv=np.asarray(source_mesh['vertices']);sf=np.asarray(source_mesh['faces'])
        if len(sv)>MAX_SOURCE:raise ValueError('模板超过 100,000 顶点。')
        settings=geometry_settings(body.get('settings',{}))
        bake=body.get('bake')
        if bake is not None:
            if not isinstance(bake,dict):raise ValueError('批量烘焙参数无效。')
            resolution,padding,ratio=bake.get('resolution',1024),bake.get('padding',8),bake.get('distanceRatio',.02)
            if type(resolution) is not int or resolution not in (256,512,1024,2048) or type(padding) is not int or not 0<=padding<=16 or type(ratio) not in (int,float) or not np.isfinite(ratio) or not .001<=ratio<=.2:raise ValueError('批量烘焙参数超出范围。')
            from texture import rasterize_uv
            _,_,uv,uf=parse_obj(source['text'],with_uv=True);rasterize_uv(uv,uf,256)
            bake={'resolution':resolution,'padding':padding,'distanceRatio':ratio}
        if settings['solverMode']=='single' and len(sv)>25000:raise ValueError('超过 25,000 顶点请使用多阶段模式。')
        excluded=index_list(body.get('excludedSourceFaces',[]),len(sf),'模板排除面').tolist();signature=topology_hash(sv,sf)
        region_mode=body.get('sourceRegionMode','fixed')
        if region_mode not in ('fixed','follow'):raise ValueError('模板区域模式无效。')
        geometry_weights=body.get('brushWeights')
        if geometry_weights is not None and (not isinstance(geometry_weights,list) or len(geometry_weights)!=len(sv) or any(type(w) not in (int,float) or not np.isfinite(w) or not 0<=w<=1 for w in geometry_weights)):
            raise ValueError('几何软权重必须与模板顶点一一对应，范围为 0–1。')
        config={'mode':mode,'sourceName':source['name'][:255],'sourceVertexCount':len(sv),'sourceHash':hashlib.sha256(source['text'].encode()).hexdigest(),'templateTopologyHash':signature,'settings':settings,'excludedSourceFaces':excluded,'sourceRegionMode':region_mode,'brushWeights':geometry_weights,'useCurrentResult':body.get('useCurrentResult',False),'constraints':{}}
        config['bake']=bake
        temporal=body.get('temporal')
        if temporal is not None:
            ts=temporal_settings(temporal);weights=temporal.get('brushWeights')
            if weights is not None and (not isinstance(weights,list) or len(weights)!=len(sv) or any(type(v) not in (int,float) or not np.isfinite(v) or not 0<=v<=1 for v in weights)):raise ValueError('时序平滑软权重无效。')
            config['temporal']={**ts,'brushWeights':weights}
        flow=body.get('flow');reference_bytes=None
        if flow is not None:
            if not isinstance(flow,dict) or bake is None:raise ValueError('批量光流细化需要开启烘焙，并提供参考贴图及光流参数。')
            fs=flow_settings(flow.get('settings',{}));camera=flow.get('cameraWorld');cameras(sv,sv,camera,fs['views']);cv_module()
            weights=flow.get('brushWeights')
            if weights is not None and (not isinstance(weights,list) or len(weights)!=len(sv) or any(type(v) not in (int,float) or not np.isfinite(v) or not 0<=v<=1 for v in weights)):raise ValueError('批量光流软权重无效。')
            texture=flow.get('sourceTexture');read_texture(texture)
            reference_bytes=base64.b64decode(texture['dataUrl'].split(',',1)[1],validate=True)
            config['flow']={'settings':fs,'cameraWorld':camera,'brushWeights':weights,'sourceTexture':{'name':texture['name'][:255],'header':texture['dataUrl'].split(',',1)[0],'sha256':hashlib.sha256(reference_bytes).hexdigest()}}
        if mode=='sequence':
            target,tf=parse_obj(body['referenceTarget']);pairs=body.get('pairs');pairs_valid(pairs,len(sv),len(target))
            target_excluded=index_list(body.get('excludedTargetFaces',[]),len(tf),'目标排除面').tolist();exclusion_masks(sf,tf,{'source':excluded,'target':target_excluded},pairs)
            config.update(referenceTopologyHash=topology_hash(target,tf),pairs=pairs,excludedTargetFaces=target_excluded)
        elif mode=='independent':
            manifest=body.get('constraints',{})
            if not isinstance(manifest,dict) or manifest.get('format')!='facewrap-batch-constraints' or type(manifest.get('version')) is not int or manifest['version'] not in (1,2) or manifest.get('templateTopologyHash')!=signature:raise ValueError('扫描约束 JSON 与当前模板拓扑不匹配。')
            items=manifest.get('items')
            if not isinstance(items,list) or not 1<=len(items)<=MAX_ITEMS:raise ValueError('扫描约束 JSON 需要 1–50 项。')
            for item in items:
                if not isinstance(item,dict):raise ValueError('扫描约束项格式无效。')
                name=filename(item.get('name'));key=name.casefold()
                if key in config['constraints']:raise ValueError('扫描约束 JSON 存在重复文件名。')
                config['constraints'][key]={'pairs':item.get('pairs'),'excludedTargetFaces':item.get('excludedTargetFaces',[])}
        else:raise ValueError('批处理模式无效。')
        with self.lock:
            if sum(j['status'] not in TERMINAL for j in self.jobs.values())>=4:raise BatchBusy('尚有多个未结束批次，请先取消或完成已有任务。')
            job_id=uuid.uuid4().hex;path=self._path(job_id);(path/'inputs').mkdir(parents=True);(path/'results').mkdir()
            (path/'template.obj').write_text(source['text'],encoding='utf-8',newline='');(path/'config.json').write_text(json.dumps(config,ensure_ascii=False),encoding='utf-8')
            if reference_bytes is not None:(path/'reference.texture').write_bytes(reference_bytes)
            items=[{'id':f'{i+1:04d}','name':name,'status':'awaiting_upload','error':None,'resultFile':None} for i,name in enumerate(names)]
            job={'id':job_id,'status':'draft','createdAt':time.time(),'finishedAt':None,'cancelRequested':False,'inputBytes':len(reference_bytes or b''),'outputBytes':0,'sourceName':config['sourceName'],'mode':mode,'bake':bake,'flow':bool(config.get('flow')),'temporal':{k:v for k,v in config['temporal'].items() if k!='brushWeights'} if config.get('temporal') else None,'predeclared':bool(names),'items':items}
            self.jobs[job_id]=job;self._save(job);return self._public(job)

    def add(self,body):
        with self.lock:
            job=self._get(body['jobId']);name=filename(body.get('name'))
            if job['status']!='draft':raise ValueError('该任务已不能添加扫描。')
            existing=next((i for i in job['items'] if i['name'].casefold()==name.casefold()),None)
            if existing and existing['status']!='awaiting_upload':raise ValueError('队列有重复文件名，请重命名后重新加入。')
            if job.get('predeclared') and not existing:raise ValueError('该扫描不在创建时的队列内。')
            if not existing and len(job['items'])>=MAX_ITEMS:raise ValueError('每批最多 50 个扫描。')
            error=body.get('uploadError');text=body.get('text');size=0
            if error is not None:
                if not isinstance(error,str) or not error:raise ValueError('上传错误信息无效。')
                error=error[:500]
            else:
                if not isinstance(text,str):raise ValueError('扫描文件内容无效。')
                size=len(text.encode('utf-8'))
                if size>18*1024*1024 or job['inputBytes']+size>MAX_BYTES:raise ValueError('单扫描上限 18 MB，每批上传总量上限 256 MB。')
            texture=body.get('texture');texture_error=body.get('textureError');texture_bytes=None
            if job.get('bake') and not error:
                try:
                    if texture_error:raise ValueError(str(texture_error)[:500])
                    read_texture(texture);texture_bytes=base64.b64decode(texture['dataUrl'].split(',',1)[1],validate=True)
                except (ValueError,TypeError) as exc:texture_error=str(exc)[:500]
                if texture_bytes is not None:
                    if job['inputBytes']+size+len(texture_bytes)>MAX_BYTES:raise ValueError('模型与贴图上传总量超过 256 MB，请拆分批次。')
                    size+=len(texture_bytes)
            item_id=existing['id'] if existing else f'{len(job["items"])+1:04d}';item={'id':item_id,'name':name,'status':'failed' if error else 'pending','error':error,'resultFile':None}
            if job.get('bake') and not error:
                item['textureError']=texture_error
                if texture_bytes is not None:
                    (self._path(job['id'])/'inputs'/f'{item_id}.texture').write_bytes(texture_bytes);item['textureName']=texture['name'][:255];item['textureHeader']=texture['dataUrl'].split(',',1)[0]
            if not error:(self._path(job['id'])/'inputs'/f'{item_id}.obj').write_text(text,encoding='utf-8',newline='')
            job['inputBytes']+=size
            if existing:existing.update(item)
            else:job['items'].append(item)
            self._save(job);return self._public(job)

    def start(self,job_id):
        with self.lock:
            job=self._get(job_id)
            if job['status']!='draft' or not job['items']:raise ValueError('任务没有可启动的扫描队列。')
            if any(i['status']=='awaiting_upload' for i in job['items']):raise ValueError('尚有扫描未上传，不能启动。')
            if not self.solver.acquire(blocking=False):raise BatchBusy('已有计算正在进行，请稍后再启动批处理。')
            try:
                job['items'].sort(key=lambda i:[int(s) if re.fullmatch('[0-9]+',s) else s for s in re.split(r'([0-9]+)',i['name'].casefold())]);job['status']='running';job['startedAt']=time.time();self._save(job)
                thread=threading.Thread(target=self._run,args=(job_id,),daemon=True);self.threads[job_id]=thread;thread.start()
            except Exception:self.solver.release();job['status']='failed';raise
            return self._public(job)

    def status(self,job_id):
        with self.lock:return self._public(self._get(job_id))

    def cancel(self,job_id):
        with self.lock:
            job=self._get(job_id)
            if job['status'] in TERMINAL or job['status']=='packaging':return self._public(job)
            if not job['cancelRequested']:job['cancelRequestedAt']=time.time()
            job['cancelRequested']=True
            if job['status']=='draft':
                for item in job['items']:
                    if item['status'] in ('pending','awaiting_upload'):item.update(status='skipped',error='已取消。')
                job['status']='cancelled';job['finishedAt']=time.time();self._save(job);self._archive(job)
            else:job['status']='cancelling';self._save(job)
            return self._public(job)

    def _archive(self,job):
        path=self._path(job['id']);config=json.loads((path/'config.json').read_text(encoding='utf-8'))
        report=self._public(job);report.pop('outputPath',None);report.pop('archiveReady',None)
        if job['status']=='packaging':report['status']=job['finalStatus']
        report.pop('finalStatus',None)
        (path/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        table=io.StringIO();writer=csv.writer(table);writer.writerow(['filename','status','result','seconds','mean_distance','error','bake_status','coverage','unmatched_pixels','flow_status','photo_before','photo_after','flow_matched_vertices','temporal_status','previous_frame','temporal_mean_correction','temporal_max_correction','next_frame','adaptive_strength_mean','adaptive_speed_max_percent','adaptive_fast_vertices','anomaly_status','anomaly_reasons','scan_roughness_percent','fit_distance_percent','repair_status','repair_before','repair_after','repair_fraction','repair_error'])
        for item in job['items']:
            def safe(v):
                s=str(v or '');return "'"+s if s.startswith(('=','+','-','@','\t','\r')) else s
            writer.writerow([safe(item['name']),item['status'],item.get('resultFile') or '',item.get('seconds',''),item.get('stats',{}).get('finalMeanDistance',''),safe(item.get('error')),item.get('bakeStatus',''),item.get('bakeStats',{}).get('coverage',''),item.get('bakeStats',{}).get('unmatchedPixels',''),item.get('flowStatus',''),item.get('flowStats',{}).get('beforePhotoError',''),item.get('flowStats',{}).get('afterPhotoError',''),item.get('flowStats',{}).get('matchedVertices',''),item.get('temporalStatus',''),safe(item.get('previousFrame')),item.get('temporalStats',{}).get('meanCorrection',''),item.get('temporalStats',{}).get('maxCorrection',''),safe(item.get('nextFrame')),item.get('temporalStats',{}).get('effectiveStrengthMean',''),item.get('temporalStats',{}).get('speedMaxPercent',''),item.get('temporalStats',{}).get('fastVertices',''),item.get('anomalyStatus',''),';'.join(item.get('anomalyStats',{}).get('reasons',[])),item.get('anomalyStats',{}).get('scanRoughnessPercent',''),item.get('anomalyStats',{}).get('fitDistancePercent',''),item.get('repairStatus',''),safe(item.get('repairStats',{}).get('beforeFrame')),safe(item.get('repairStats',{}).get('afterFrame')),item.get('repairStats',{}).get('fraction',''),safe(item.get('repairError'))])
        (path/'report.csv').write_text(table.getvalue(),encoding='utf-8-sig')
        with zipfile.ZipFile(path/'results.tmp',mode='w',compression=zipfile.ZIP_DEFLATED) as archive:
            archive.write(path/'report.json','report.json');archive.write(path/'report.csv','report.csv');archive.writestr('settings.json',json.dumps(config,ensure_ascii=False,indent=2))
            archive.writestr('README.txt','Mesh Wave batch\nTextured items have their own folder with model.obj, model.mtl, texture.png and opacity.png. Keep these files together.\nGeometry-only / failed baking items preserve original template material references; use original template materials.\nTransparent pixels indicate unmatched or excluded UV regions. See report.json / report.csv for optical flow, temporal smoothing, bake coverage, failures and skipped scans.\n')
            for item in job['items']:
                for relative in item.get('resultFiles',([item['resultFile']] if item.get('resultFile') else [])):archive.write(path/relative,relative)
        (path/'results.tmp').replace(path/'results.zip')

    def download_path(self,job_id):
        with self.lock:
            job=self._get(job_id);path=self._path(job_id)/'results.zip'
            if job['status'] not in TERMINAL or not path.is_file():raise BatchBusy('批处理尚未完成打包。')
            return path

    def _bake_result(self,job,item,source,target,vertices,constraints,relative,size,config,texture=None):
        path=self._path(job['id']);bake=config['bake'];excluded_source=config['excludedSourceFaces'];settings=config['settings']
        if texture is None:texture={'name':item.get('textureName','scan.png'),'dataUrl':item['textureHeader']+','+base64.b64encode((path/'inputs'/f'{item["id"]}.texture').read_bytes()).decode()}
        baked=bake_texture(source,target,vertices,texture,**{'resolution':bake['resolution'],'padding':bake['padding'],'distance_ratio':bake['distanceRatio'],'normal_angle':settings['normalAngle'],'excluded_faces':{'source':excluded_source,'sourceMode':config.get('sourceRegionMode','fixed'),'target':constraints['excludedTargetFaces']}})
        bundle=texture_bundle(source,vertices,baked['texture'])
        folder=relative[:-4];assets={}
        with zipfile.ZipFile(io.BytesIO(bundle)) as package:
            for name in ('model.obj','model.mtl','texture.png','opacity.png'):assets[f'{folder}/{name}']=package.read(name)
        asset_size=sum(map(len,assets.values()))
        if job['outputBytes']-size+asset_size>MAX_BYTES:raise BatchOutputLimit('带贴图输出超过 256 MB 上限，请拆分批次。')
        for name,data in assets.items():
            (path/name).parent.mkdir(parents=True,exist_ok=True);(path/name).write_bytes(data)
        with self.lock:
            item.update(status='succeeded',bakeStatus='succeeded',bakeStats=baked['stats'],resultFile=f'{folder}/model.obj',resultFiles=list(assets));job['outputBytes']+=asset_size-size
        (path/relative).unlink()

    def _finish_bidirectional(self,job,config,source,limited):
        path=self._path(job['id']);ts=config['temporal'];stopped_by_limit=False
        with self.lock:
            initial_cancel=job.get('cancelRequestedAt');job['phase']='anomaly' if ts.get('detectAnomalies') else 'bidirectional';self._save(job)
        if ts.get('detectAnomalies'):self._screen_anomalies(job,config,source,initial_cancel)
        if ts.get('repairAnomalies'):stopped_by_limit=self._repair_anomalies(job,config,source,initial_cancel)
        bidirectional=ts['mode']=='bidirectional';previous_filtered=None;previous_raw=None
        for index,item in enumerate(job['items']):
            if item['status']!='prepared':continue
            with self.lock:
                if job.get('cancelRequestedAt')!=initial_cancel or stopped_by_limit:
                    item.update(status='skipped',temporalStatus='skipped',bakeStatus='skipped',error='已停止；保留未平滑、未烘焙的几何。');item['anomalyStatus']='skipped' if item.get('anomalyStatus')=='pending' else item.get('anomalyStatus');self._save(job);continue
                item.update(status='running',stage='temporal',temporalStatus='running');self._save(job)
            started=time.perf_counter();phase='temporal'
            try:
                target=(path/'inputs'/f'{item["id"]}.obj').read_text(encoding='utf-8')
                constraints={'pairs':config['pairs'],'excludedTargetFaces':config['excludedTargetFaces']} if config['mode']=='sequence' else config['constraints'][item['name'].casefold()]
                prior=job['items'][index-1] if index else None;following=job['items'][index+1] if index+1<len(job['items']) else None
                prior=prior if prior and prior['status']=='succeeded' and prior.get('repairStatus')!='succeeded' else None
                following=following if following and following['status']=='prepared' else None
                if prior is None:previous_filtered=None;previous_raw=None
                load=lambda entry:np.load(path/'inputs'/f'{entry["id"]}.temporal.npy',allow_pickle=False) if entry else None
                current=load(item)
                smoothed=smooth_frame({'source':source,'target':target,'vertices':current.tolist(),'pairs':constraints['pairs'],'excludedFaces':{'source':config['excludedSourceFaces'],'sourceMode':config.get('sourceRegionMode','fixed'),'target':constraints['excludedTargetFaces']},'normalAngle':config['settings']['normalAngle'],'settings':ts,'brushWeights':ts['brushWeights'],'motionPrevious':previous_raw.tolist() if previous_raw is not None else None},load(prior) if bidirectional else previous_filtered,load(following) if bidirectional else None)
                relative=item['resultFile'];size=(path/relative).stat().st_size;text=export_obj(source,smoothed['vertices']);new_size=len(text.encode('utf-8'))
                if job['outputBytes']-size+new_size>MAX_BYTES:raise BatchOutputLimit('双向平滑输出超过 256 MB 上限。')
                temporary=path/(relative+'.tmp');temporary.write_text(text,encoding='utf-8',newline='');temporary.replace(path/relative)
                with self.lock:
                    job['outputBytes']+=new_size-size;size=new_size
                    seed=smoothed['stats']['seed'];item.update(status='succeeded',temporalStatus='seed' if seed else 'succeeded',temporalStats=smoothed['stats'],previousFrame=prior['name'] if prior and not seed else None,nextFrame=following['name'] if following and not seed and bidirectional else None);self._save(job)
                if config.get('bake'):
                    phase='baking'
                    with self.lock:item.update(status='running',stage='baking',bakeStatus='running');self._save(job)
                    self._bake_result(job,item,source,target,smoothed['vertices'],constraints,relative,size,config)
                previous_filtered=np.asarray(smoothed['vertices']);previous_raw=current
            except Exception as exc:
                with self.lock:
                    stopped_by_limit=stopped_by_limit or isinstance(exc,BatchOutputLimit)
                    item.update(status='failed',error=('烘焙失败' if phase=='baking' else '双向平滑失败')+'（几何已保留）：'+str(exc)[:900])
                    if phase=='baking':item['bakeStatus']='failed'
                    else:item.update(temporalStatus='failed',bakeStatus='skipped')
            finally:
                with self.lock:item.pop('stage',None);item['seconds']=item.get('seconds',0)+time.perf_counter()-started;self._save(job)
        return limited or stopped_by_limit

    def _repair_anomalies(self,job,config,source,cancel_marker):
        path=self._path(job['id']);ts=config['temporal'];threshold=ts['anomalyPercent']
        # Freeze normal endpoints. Repaired frames are never used to synthesize another frame.
        eligible={i for i,item in enumerate(job['items']) if item['status']=='prepared' and item.get('anomalyStatus') in ('clear','limited') and item.get('fitQuality',{}).get('distancePercent') is not None and item['fitQuality']['distancePercent']<=threshold and item.get('scanQuality',{}).get('roughnessPercent') is not None}
        candidates={i for i,item in enumerate(job['items']) if item.get('anomalyStatus')=='rejected'}
        load=lambda entry:np.load(path/'inputs'/f'{entry["id"]}.temporal.npy',allow_pickle=False)
        for index in sorted(candidates):
            item=job['items'][index]
            if job.get('cancelRequestedAt')!=cancel_marker:
                with self.lock:item.update(repairStatus='skipped',repairError='已取消修复。');self._save(job)
                continue
            left=index-1;right=index+1
            while left in candidates:left-=1
            while right in candidates:right+=1
            if left not in eligible or right not in eligible or right-left-1>ts['repairMaxGap']:
                with self.lock:item.update(repairStatus='unavailable',repairError='缺少前后可用正常帧，或连续异常超过修复上限。');self._save(job)
                continue
            started=time.perf_counter();phase='repair';original_error=item.get('error');original_file=item.get('resultFile')
            try:
                with self.lock:item.update(status='running',stage='repair',repairStatus='running');self._save(job)
                before,after=job['items'][left],job['items'][right];bv,av=load(before),load(after)
                c={'pairs':config['pairs'],'excludedTargetFaces':config['excludedTargetFaces']} if config['mode']=='sequence' else config['constraints'][item['name'].casefold()]
                target=(path/'inputs'/f'{item["id"]}.obj').read_text(encoding='utf-8');old_cache=path/'inputs'/f'{item["id"]}.temporal.npy'
                body={'source':source,'target':target,'vertices':load(item).tolist() if old_cache.is_file() else parse_obj((path/original_file).read_text(encoding='utf-8'))[0].tolist() if original_file else None,'pairs':c['pairs'],'excludedFaces':{'source':config['excludedSourceFaces'],'sourceMode':config.get('sourceRegionMode','fixed'),'target':c['excludedTargetFaces']},'brushWeights':ts['brushWeights'],'settings':config['settings'],'distanceRatio':ts['distancePercent']/100}
                repaired=repair_frame(body,bv,av,(index-left)/(right-left))
                quality=fit_quality(source,target,repaired['vertices'],c['pairs'],body['excludedFaces'],ts['brushWeights'])
                full_scan_quality=quality
                filtered_noise='scan_noise' in item.get('anomalyStats',{}).get('reasons',[]) and repaired['stats'].get('autoExcludedTargetFaces',0)>0
                if filtered_noise:quality={'distancePercent':repaired['stats']['trustedFitDistancePercent'],'sampleVertices':repaired['stats']['trustedVertexCount']}
                evidence=[{'name':n['name'],'scanQuality':n.get('scanQuality',{}),'fitQuality':n.get('fitQuality',{})} for n in [before,after]]
                check=classify_frame({**body,'vertices':repaired['vertices'],'threshold':threshold,'scanQuality':item.get('scanQuality',{}),'fitQuality':quality,'neighbors':evidence},bv,av)
                remaining=[reason for reason in check['stats']['reasons'] if reason!='scan_noise']
                if quality['distancePercent'] is None or quality['distancePercent']>threshold or remaining:raise ValueError('重新贴合后仍有几何异常，未采用修复：'+','.join(remaining or ['离面误差超过阈值']))
                text=export_obj(source,repaired['vertices']);size=len(text.encode('utf-8'));old_size=(path/original_file).stat().st_size if original_file else 0
                if job['outputBytes']-old_size+size>MAX_BYTES:raise BatchOutputLimit('修复输出超过 256 MB 上限。')
                stem=re.sub(r'[^\w.-]+','_',Path(item['name']).stem,flags=re.UNICODE).strip('._')[:100] or 'scan';relative=f'results/{index+1:04d}_{stem}_repaired.obj'
                temporary=path/(relative+'.tmp');temporary.write_text(text,encoding='utf-8',newline='');temporary.replace(path/relative)
                stats={**repaired['stats'],'beforeFrame':before['name'],'afterFrame':after['name'],'gapFrames':right-left-1,'fitQuality':quality,'fullScanFitQuality':full_scan_quality,'qualityScope':'trusted-scan-and-temporal-prior' if filtered_noise else 'full-scan','excludedTargetFaces':repaired.get('excludedTargetFaces',c['excludedTargetFaces']),'geometryCheck':check['stats'],'originalResultFile':original_file,'normalEndpointStatus':[before['anomalyStatus'],after['anomalyStatus']]}
                with self.lock:
                    job['outputBytes']+=size-old_size;item.update(status='running' if config.get('bake') else 'succeeded',stage='baking' if config.get('bake') else None,repairStatus='succeeded',repairStats=stats,repairOriginalError=original_error,error=None,anomalyStatus='repaired',temporalStatus='repaired',resultFile=relative,pairs=c['pairs'],bakeStatus='disabled' if not config.get('bake') else 'pending');self._save(job)
                if config.get('bake'):
                    phase='baking'
                    with self.lock:item.update(status='running',stage='baking',bakeStatus='running');self._save(job)
                    if item.get('textureError'):raise ValueError(item['textureError'])
                    self._bake_result(job,item,source,target,repaired['vertices'],{**c,'excludedTargetFaces':stats['excludedTargetFaces']},relative,size,config)
            except Exception as exc:
                with self.lock:
                    item.update(status='failed')
                    if phase=='baking':item.update(bakeStatus='failed',error='几何已修复，重新烘焙失败：'+str(exc)[:800])
                    else:item.update(repairStatus='failed',repairError=str(exc)[:800],error=original_error)
                if isinstance(exc,BatchOutputLimit):return True
            finally:
                with self.lock:item.pop('stage',None);item['seconds']=item.get('seconds',0)+time.perf_counter()-started;self._save(job)
        return False

    def _screen_anomalies(self,job,config,source,cancel_marker):
        path=self._path(job['id']);ts=config['temporal'];ready={i['id'] for i in job['items'] if i['status']=='prepared'}
        def constraints(item):return {'pairs':config['pairs'],'excludedTargetFaces':config['excludedTargetFaces']} if config['mode']=='sequence' else config['constraints'][item['name'].casefold()]
        def load(item):return np.load(path/'inputs'/f'{item["id"]}.temporal.npy',allow_pickle=False) if item and item['id'] in ready else None
        for item in job['items']:
            if item['id'] not in ready:continue
            if job.get('cancelRequestedAt')!=cancel_marker:return
            try:
                with self.lock:item.update(stage='anomaly',anomalyStatus='pending');self._save(job)
                c=constraints(item);target=(path/'inputs'/f'{item["id"]}.obj').read_text(encoding='utf-8')
                quality=fit_quality(source,target,load(item),c['pairs'],{'source':config['excludedSourceFaces'],'sourceMode':config.get('sourceRegionMode','fixed'),'target':c['excludedTargetFaces']},ts['brushWeights'])
                with self.lock:item['fitQuality']=quality
            except Exception as exc:
                with self.lock:item.update(status='failed',anomalyStatus='failed',temporalStatus='skipped',bakeStatus='skipped',error='异常检测失败（几何已保留）：'+str(exc)[:800])
                ready.discard(item['id'])
            finally:
                with self.lock:item.pop('stage',None);self._save(job)
        # Freeze evidence before classifying, so rejecting one frame cannot change another verdict.
        evidence=[{'name':i['name'],'scanQuality':i.get('scanQuality',{}),'fitQuality':i.get('fitQuality',{})} for i in job['items']]
        labels={'scan_noise':'扫描表面噪声突增','surface_jump':'贴合偏离目标表面','incoherent_jump':'不连贯的局部贴合跳变'}
        for index,item in enumerate(job['items']):
            if not item.get('scanQuality') or item.get('anomalyStatus')=='failed':continue
            if job.get('cancelRequestedAt')!=cancel_marker:return
            try:
                with self.lock:item['stage']='anomaly';self._save(job)
                c=constraints(item);target=(path/'inputs'/f'{item["id"]}.obj').read_text(encoding='utf-8')
                prior=job['items'][index-1] if index else None;following=job['items'][index+1] if index+1<len(job['items']) else None;current=load(item)
                verdict=classify_frame({'source':source,'target':target,'vertices':current,'pairs':c['pairs'],'excludedFaces':{'source':config['excludedSourceFaces'],'sourceMode':config.get('sourceRegionMode','fixed'),'target':c['excludedTargetFaces']},'brushWeights':ts['brushWeights'],'threshold':ts['anomalyPercent'],'scanQuality':item.get('scanQuality',{}),'fitQuality':item.get('fitQuality',{}),'neighbors':[evidence[n] for n in [index-1,index+1] if 0<=n<len(evidence)]},load(prior),load(following))
                with self.lock:
                    item.update(anomalyStatus=verdict['status'],anomalyStats=verdict['stats'])
                    if verdict['status']=='rejected':item.update(status='failed',temporalStatus='skipped',bakeStatus='skipped',error='可疑异常帧，已隔离（保留已有几何和约束，未平滑/烘焙）：'+'；'.join(labels[r] for r in verdict['stats']['reasons'])+('。原错误：'+item['error'] if item.get('error') else ''))
            except Exception as exc:
                with self.lock:item.update(status='failed',anomalyStatus='failed',temporalStatus='skipped',bakeStatus='skipped',error='异常检测失败（几何已保留）：'+str(exc)[:800])
            finally:
                with self.lock:item.pop('stage',None);self._save(job)

    def _run(self,job_id):
        path=self._path(job_id)
        try:
            config=json.loads((path/'config.json').read_text(encoding='utf-8'));source=(path/'template.obj').read_text(encoding='utf-8')
            flow=config.get('flow');reference_texture=None
            if flow:reference_texture={'name':flow['sourceTexture']['name'],'dataUrl':flow['sourceTexture']['header']+','+base64.b64encode((path/'reference.texture').read_bytes()).decode()}
            job=self.jobs[job_id];limited=False;previous=None;previous_name=None;previous_motion=None
            bidirectional=config.get('temporal',{}).get('mode')=='bidirectional' or config.get('temporal',{}).get('detectAnomalies',False)
            for rank,item in enumerate(job['items'],1):
                with self.lock:
                    if item['status']!='pending':previous=None;previous_motion=None;continue
                    if job['cancelRequested'] or limited:item.update(status='skipped',error='已取消。' if job['cancelRequested'] else '输出达到 256 MB 上限，请拆分批次。');self._save(job);continue
                    item.update(status='running',startedAt=time.time());self._save(job)
                started=time.perf_counter();temporal_candidate=None;motion_candidate=None
                try:
                    target=(path/'inputs'/f'{item["id"]}.obj').read_text(encoding='utf-8');tv,tf=parse_obj(target)
                    if config['mode']=='sequence':
                        if topology_hash(tv,tf)!=config['referenceTopologyHash']:raise ValueError('目标拓扑或顶点数量与参考目标不一致，不能复用旧目标索引。')
                        constraints={'pairs':config['pairs'],'excludedTargetFaces':config['excludedTargetFaces']}
                    else:
                        constraints=config['constraints'].get(item['name'].casefold())
                        if constraints is None:raise ValueError('没有该扫描的独立对应点 JSON。')
                    pairs_valid(constraints.get('pairs'),config['sourceVertexCount'],len(tv))
                    if config.get('temporal',{}).get('detectAnomalies'):
                        quality=scan_quality(target,constraints['excludedTargetFaces'],constraints['pairs']);quality['topologyHash']=topology_hash(tv,tf)
                        with self.lock:item.update(scanQuality=quality,anomalyStatus='pending');self._save(job)
                    settings=config['settings'];result=wrap(source,target,constraints['pairs'],settings['iterations'],settings['smoothness'],{'source':config['excludedSourceFaces'],'sourceMode':config.get('sourceRegionMode','fixed'),'target':constraints['excludedTargetFaces']},settings['normalAngle'],settings['solverMode'],config.get('brushWeights'))
                    text=export_obj(source,result['vertices']);size=len(text.encode('utf-8'))
                    if job['outputBytes']+size>MAX_BYTES:limited=True;raise ValueError('批量输出超过 256 MB 上限，请拆分批次。')
                    stem=re.sub(r'[^\w.-]+','_',Path(item['name']).stem,flags=re.UNICODE).strip('._')[:100] or 'scan';relative=f'results/{rank:04d}_{stem}_wrapped.obj'
                    (path/relative).write_text(text,encoding='utf-8',newline='')
                    with self.lock:item.update(status='succeeded',resultFile=relative,stats=result['stats'],pairs=constraints['pairs']);job['outputBytes']+=size
                    texture=None
                    if flow:
                        with self.lock:item.update(status='running',stage='flow',flowStatus='running',bakeStatus='pending');self._save(job)
                        try:
                            if item.get('textureError'):raise ValueError(item['textureError'])
                            texture={'name':item.get('textureName','scan.png'),'dataUrl':item['textureHeader']+','+base64.b64encode((path/'inputs'/f'{item["id"]}.texture').read_bytes()).decode()}
                            refined=refine_texture({'source':source,'target':target,'vertices':result['vertices'],'pairs':constraints['pairs'],'excludedFaces':{'source':config['excludedSourceFaces'],'sourceMode':config.get('sourceRegionMode','fixed'),'target':constraints['excludedTargetFaces']},'brushWeights':flow['brushWeights'],'sourceTexture':reference_texture,'targetTexture':texture,'cameraWorld':flow['cameraWorld'],'normalAngle':settings['normalAngle'],'settings':flow['settings']})
                            refined_text=export_obj(source,refined['vertices']);refined_size=len(refined_text.encode('utf-8'))
                            if job['outputBytes']-size+refined_size>MAX_BYTES:limited=True;raise ValueError('光流细化输出超过 256 MB 上限，请拆分批次。')
                            temporary=path/(relative+'.tmp');temporary.write_text(refined_text,encoding='utf-8',newline='');temporary.replace(path/relative)
                            result['vertices']=refined['vertices']
                            with self.lock:
                                job['outputBytes']+=refined_size-size;size=refined_size;item.update(flowStatus='succeeded',flowStats=refined['stats'])
                        except Exception as exc:
                            with self.lock:item.update(status='failed',flowStatus='failed',bakeStatus='skipped',error='光流细化失败（几何已保留，未烘焙）：'+str(exc)[:850])
                            continue
                        finally:
                            with self.lock:item.pop('stage',None)
                    if bidirectional:
                        if config.get('bake') and item.get('textureError'):
                            with self.lock:item.update(status='failed',bakeStatus='failed',error='烘焙输入无效（几何已保留）：'+item['textureError'])
                            continue
                        np.save(path/'inputs'/f'{item["id"]}.temporal.npy',np.asarray(result['vertices'],dtype=float),allow_pickle=False)
                        with self.lock:item.update(status='prepared',temporalStatus='pending',bakeStatus='pending' if config.get('bake') else 'disabled');self._save(job)
                        continue
                    if config.get('temporal'):
                        with self.lock:item.update(status='running',stage='temporal',temporalStatus='running');self._save(job)
                        try:
                            ts=config['temporal'];motion_candidate=np.asarray(result['vertices'],dtype=float)
                            smoothed=smooth_frame({'source':source,'target':target,'vertices':result['vertices'],'pairs':constraints['pairs'],'excludedFaces':{'source':config['excludedSourceFaces'],'sourceMode':config.get('sourceRegionMode','fixed'),'target':constraints['excludedTargetFaces']},'normalAngle':settings['normalAngle'],'settings':ts,'brushWeights':ts['brushWeights'],'motionPrevious':previous_motion.tolist() if previous_motion is not None and ts.get('adaptive') else None},previous)
                            smooth_text=export_obj(source,smoothed['vertices']);smooth_size=len(smooth_text.encode('utf-8'))
                            if job['outputBytes']-size+smooth_size>MAX_BYTES:limited=True;raise ValueError('时序平滑输出超过 256 MB 上限，请拆分批次。')
                            temporary=path/(relative+'.tmp');temporary.write_text(smooth_text,encoding='utf-8',newline='');temporary.replace(path/relative)
                            result['vertices']=smoothed['vertices'];temporal_candidate=np.asarray(smoothed['vertices'])
                            with self.lock:
                                job['outputBytes']+=smooth_size-size;size=smooth_size;item.update(status='succeeded',temporalStatus='seed' if smoothed['stats']['seed'] else 'succeeded',temporalStats=smoothed['stats'],previousFrame=previous_name if previous is not None else None)
                        except Exception as exc:
                            with self.lock:item.update(status='failed',temporalStatus='failed',bakeStatus='skipped' if config.get('bake') else 'disabled',error='时序平滑失败（几何已保留）：'+str(exc)[:900])
                            continue
                        finally:
                            with self.lock:item.pop('stage',None)
                    if config.get('bake'):
                        with self.lock:item.update(status='running',stage='baking',bakeStatus='running');self._save(job)
                        try:
                            if item.get('textureError'):raise ValueError(item['textureError'])
                            self._bake_result(job,item,source,target,result['vertices'],constraints,relative,size,config,texture)
                        except Exception as exc:
                            with self.lock:
                                limited=limited or isinstance(exc,BatchOutputLimit);item.update(status='failed',bakeStatus='failed',error='烘焙失败（几何已保留）：'+str(exc)[:900])
                        finally:
                            with self.lock:item.pop('stage',None)
                except Exception as exc:
                    with self.lock:item.update(status='failed',error=str(exc)[:1000])
                finally:
                    with self.lock:
                        if config.get('temporal'):previous=temporal_candidate if item['status']=='succeeded' else None;previous_motion=motion_candidate if item['status']=='succeeded' else None;previous_name=item['name']
                        item['seconds']=time.perf_counter()-started;self._save(job)
            if bidirectional:limited=self._finish_bidirectional(job,config,source,limited)
            with self.lock:
                job['finalStatus']='cancelled' if job['cancelRequested'] else 'limited' if limited else 'completed_with_errors' if any(i['status']=='failed' for i in job['items']) else 'completed'
                job['status']='packaging';job['finishedAt']=time.time();self._save(job)
            self._archive(job)
            with self.lock:job['status']=job.pop('finalStatus');self._save(job)
        except Exception as exc:
            with self.lock:
                job=self.jobs[job_id];job['status']='failed';job['error']=str(exc)[:1000];job['finishedAt']=time.time()
                for item in job['items']:
                    if item['status'] in ('pending','running','prepared'):
                        item.update(status='skipped',error='任务异常停止。');item.pop('stage',None)
                        if item.get('bakeStatus')=='running':item['bakeStatus']='interrupted'
                        if item.get('flowStatus')=='running':item['flowStatus']='interrupted';item['bakeStatus']='skipped'
                        if item.get('temporalStatus')=='running':item['temporalStatus']='interrupted';item['bakeStatus']='skipped'
                        if item.get('temporalStatus')=='pending':item['temporalStatus']='interrupted';item['bakeStatus']='skipped'
                    if item.get('anomalyStatus')=='pending':item['anomalyStatus']='interrupted'
                    if item.get('repairStatus')=='running':item['repairStatus']='interrupted';item.pop('stage',None)
                try:self._save(job);self._archive(job)
                except Exception:pass
        finally:self.solver.release()
