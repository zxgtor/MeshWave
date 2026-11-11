import {setText,appendText,setLabel,preserveName} from './i18n.mjs';
// A batch owns its input snapshot; this controller never replaces the working meshes.
const $=id=>document.getElementById(id);
const terminal=new Set(['completed','completed_with_errors','cancelled','interrupted','failed','limited']);
const labels={draft:'等待上传完成',running:'顺序求解中',cancelling:'等待当前项完成后停止',packaging:'正在打包',completed:'全部完成',completed_with_errors:'完成，部分失败',cancelled:'已取消',interrupted:'服务中断',failed:'任务失败',limited:'达到输出上限',awaiting_upload:'待上传',pending:'等待',prepared:'待序列处理',succeeded:'成功',skipped:'跳过'};
export class BatchUI {
  constructor(callbacks){
    Object.assign(this,callbacks);this.files=[];this.constraints=null;this.report=null;this.active=false;this.uploading=false;this.cancelRequested=false;this.stage='';this.downloading=false;this.polling=false;this.retries=0;this.error='';
    this.id=this.remember('facewrap-batch-job');
    $('batch-files').onchange=e=>this.chooseFiles(e);
    this.textures=[];
    $('batch-textures').onchange=e=>{const files=[...e.target.files];if(files.length>100){this.error='一次最多选择 100 张贴图。';e.target.value='';this.render();return;}this.textures=files;setText($('batch-texture-info'),`已选择 ${files.length} 张贴图，按扫描主名匹配。`);this.error='';this.update(false);};
    $('batch-bake').onchange=()=>this.update(false);
    $('batch-flow').onchange=()=>{if($('batch-flow').checked)$('batch-bake').checked=true;this.update(false);};
    $('batch-temporal').onchange=()=>this.update(false);
    $('temporal-adaptive').onchange=()=>this.update(false);
    $('temporal-anomalies').onchange=()=>this.update(false);
    $('temporal-repair').onchange=()=>{if($('temporal-repair').checked){$('temporal-anomalies').checked=true;$('batch-bake').checked=true;}this.update(false);};
    $('batch-constraints').onchange=e=>this.chooseConstraints(e);
    $('batch-mode').onchange=()=>this.update(false);
    $('batch-start').onclick=()=>this.start();$('batch-cancel').onclick=()=>this.cancel();$('batch-download').onclick=()=>this.downloadZip();$('batch-refresh').onclick=()=>this.resume();
    $('batch-clear').onclick=async()=>{if(this.report?.status==='draft'){try{await this.api('batch-cancel',{jobId:this.id});}catch(error){this.error=error.message;this.render();return;}}this.files=[];this.textures=[];$('batch-textures').value='';setText($('batch-texture-info'),'未选择贴图。');this.constraints=null;this.selectionChanged=false;this.report=null;this.id=null;this.remember('facewrap-batch-job','');this.remember('facewrap-batch-auto','');$('batch-files').value='';$('batch-constraints').value='';setText($('batch-constraint-info'),'约束按扫描文件名匹配，并核对模板拓扑。');this.error='';this.update(false);};
    $('batch-export-constraints').onclick=async()=>{try{const data=await this.getConstraints();this.download(JSON.stringify(data,null,2),'batch-constraints.json');setText($('batch-constraint-info'),`已导出 ${data.items[0].name} 的点对与目标排除区。`);}catch(error){this.error=error.message;this.render();}};
  }
  remember(key,value){try{if(value===undefined)return localStorage.getItem(key);if(value)localStorage.setItem(key,value);else localStorage.removeItem(key);}catch{}return null;}
  lockWorkspace(){if(!this.ownsBusy){this.ownsBusy=true;this.setBusy(true);}}
  unlockWorkspace(){if(this.ownsBusy){this.ownsBusy=false;this.setBusy(false);}}
  chooseFiles(e){
    const files=Array.from(e.target.files||[]);const seen=new Set();
    if(files.length>50||files.some(f=>!f.name.toLowerCase().endsWith('.obj')||seen.has(f.name.toLowerCase())||!seen.add(f.name.toLowerCase()))){this.error='每批最多 50 个 OBJ，文件名不能重复。';this.render();e.target.value='';return;}
    files.sort((a,b)=>a.name.localeCompare(b.name,'zh-CN',{numeric:true,sensitivity:'base'}));this.files=files;this.selectionChanged=true;this.error='';this.update(false);
  }
  async chooseConstraints(e){
    this.loadingConstraints=true;this.update(false);
    try{
      let merged=null;const names=new Set();
      for(const file of Array.from(e.target.files||[])){
        if(file.size>1024*1024)throw Error('每个约束 JSON 上限 1 MB。');const value=JSON.parse(await file.text());
        if(value.format!=='facewrap-batch-constraints'||value.version!==1||typeof value.templateTopologyHash!=='string'||!Array.isArray(value.items)||!value.items.length)throw Error('不是有效的批处理约束 JSON。');
        if(merged&&merged.templateTopologyHash!==value.templateTopologyHash)throw Error('约束文件来自不同模板，不能合并。');
        merged||={format:value.format,version:1,templateTopologyHash:value.templateTopologyHash,items:[]};
        for(const item of value.items){if(typeof item.name!=='string'||names.has(item.name.toLowerCase()))throw Error('约束中存在无效或重复文件名。');names.add(item.name.toLowerCase());merged.items.push(item);}
      }
      if(!merged||merged.items.length>50)throw Error('约束 JSON 合计需要 1–50 项。');this.constraints=merged;this.error='';setText($('batch-constraint-info'),`已加载 ${merged.items.length} 项独立扫描约束。`);
    }catch(error){this.error=`约束加载失败：${error.message}；原约束保留。`;}
    this.loadingConstraints=false;e.target.value='';this.update(false);
  }
  update(busy){
    const r=this.readiness(),external=busy||r.busy,locked=external||this.active||r.blocked||this.loadingConstraints||this.downloading;
    for(const id of ['batch-files','batch-constraints','batch-mode','batch-clear','batch-auto-download','batch-bake','batch-textures','batch-flow','batch-temporal'])$(id).disabled=locked;
    for(const id of ['temporal-strength','temporal-distance','temporal-mode','temporal-adaptive','temporal-anomalies','temporal-repair'])$(id).disabled=locked||!$('batch-temporal').checked;
    $('temporal-speed').disabled=locked||!$('batch-temporal').checked||!$('temporal-adaptive').checked;
    $('anomaly-threshold').disabled=locked||!$('batch-temporal').checked||!$('temporal-anomalies').checked;
    const repair=$('batch-temporal').checked&&$('temporal-repair').checked;$('repair-max-gap').disabled=locked||!$('batch-temporal').checked||!repair;if(repair){$('temporal-anomalies').checked=true;$('temporal-anomalies').disabled=true;}
    const flow=$('batch-flow').checked;if(flow||repair){$('batch-bake').checked=true;$('batch-bake').disabled=true;}
    $('batch-use-result').disabled=locked||!r.result;if(!r.result)$('batch-use-result').checked=false;
    const independent=$('batch-mode').value==='independent';
    $('batch-start').disabled=locked||!r.source||!this.files.length||(flow&&!r.flowReady)||(independent?!this.constraints:!r.target||!r.paired);
    setText($('batch-flow-info'),`${flow&&!r.flowReady?'请先在第 06 节给模板加载原始参考贴图并确保完整 UV。':'使用第 06 节模板原始参考贴图。'}请先将左侧模型转到正面；共用第 08 节光流参数、当前左侧相机朝向和软权重。几何与光流独立求解；勾选时序后再跨帧平滑。`);
    $('batch-export-constraints').disabled=locked||!r.source||!r.target||!r.paired;
    $('batch-cancel').disabled=(external&&!this.ownsBusy)||!(this.active||this.report?.status==='draft')||this.report?.status==='packaging'||this.cancelRequested;
    $('batch-download').disabled=this.downloading||!this.report?.archiveReady;
    $('batch-refresh').disabled=(external&&!this.ownsBusy)||!this.id||this.uploading||this.polling;
    setText($('batch-selection'),`已选择 ${this.files.length} 个扫描；${independent?'每项使用其独立约束':'复用当前已采用点对及排除区'}。`);
    this.render();
  }
  render(){
    const report=this.report;let info='选择扫描并启动；结果自动打包为 ZIP。';
    if(this.active&&this.stage==='preparing')info='正在固定模板与参数快照…';
    else if(this.uploading)info=`正在上传：${report?.items.filter(i=>i.status!=='awaiting_upload').length||0} / ${this.files.length}。`;
    else if(report){const c=report.counts;info=`${labels[report.status]||report.status} · 成功 ${c.succeeded} · 失败 ${c.failed} · 跳过 ${c.skipped} · 等待 ${c.pending}${c.prepared?' · 待序列处理 '+c.prepared:''}${c.running?' · 当前项计算中':''}`;}
    if(this.selectionChanged&&!this.active)info=`新队列待启动 · ${this.files.length} 项${report?.archiveReady?'；上次结果仍可下载。':'。'}`;
    if(report?.error)info+=' '+report.error;
    if(this.error)info+=' '+this.error;setText($('batch-info'),info);
    setText($('batch-output'),report?.outputPath?`结果目录：${preserveName(report.outputPath)}`:'');
    const list=$('batch-items');list.replaceChildren();
    const items=!this.selectionChanged&&report?.items.length?report.items:this.files.map(f=>({name:f.name,status:'pending'}));
    for(const item of items){const li=document.createElement('li'),name=document.createElement('span'),state=document.createElement('b');setText(name,item.name,true);setLabel(name,'title',item.name,true);setText(state,item.stage==='repair'?'异常修复中':item.stage==='anomaly'?'异常检测中':item.stage==='temporal'?'时序平滑中':item.stage==='flow'?'光流细化中':item.stage==='baking'?'正在烘焙':labels[item.status]||item.status);li.append(name,state);if(item.repairStatus){const detail=document.createElement('small');setText(detail,({running:'正在插值和受约束重新贴合',succeeded:'异常几何修复成功',failed:'修复失败，继续隔离',unavailable:'无可用修复区间',skipped:'修复已取消',interrupted:'修复已中断'})[item.repairStatus]||item.repairStatus);if(item.repairStats)appendText(detail,` · ${item.repairStats.beforeFrame} → ${item.repairStats.afterFrame} · 插值 ${(item.repairStats.fraction*100).toFixed(0)}%`);if(item.repairError){detail.classList.add('batch-error');appendText(detail,' · '+item.repairError);}li.append(detail);}if(item.anomalyStatus){const detail=document.createElement('small');setText(detail,({pending:'待异常检测',rejected:'可疑异常 · 已隔离',repaired:'几何已修复 · 原扫描异常保留',clear:'未发现异常信号',limited:'上下文不足 · 已检查可用信号',failed:'异常检测失败',interrupted:'异常检测中断',skipped:'未完成异常检测'})[item.anomalyStatus]||item.anomalyStatus);if(item.anomalyStats){const a=item.anomalyStats;appendText(detail,` · 扫描粗糙度 ${a.scanRoughnessPercent?.toFixed(2)??'—'}% · 离面误差 ${a.fitDistancePercent?.toFixed(2)??'—'}%`);}li.append(detail);}if(item.flowStats){const detail=document.createElement('small');setText(detail,`光流残差 ${item.flowStats.beforePhotoError.toFixed(2)} → ${item.flowStats.afterPhotoError.toFixed(2)} · ${item.flowStats.matchedVertices} 个匹配顶点`);li.append(detail);}if(item.temporalStats){const detail=document.createElement('small');setText(detail,item.temporalStats.seed?(item.temporalStats.mode==='bidirectional'?'双向片段边界 · 保留本帧几何':'时序历史起点 · 保留本帧几何'):`时序平滑 · ${item.temporalStats.changedVertices} 个顶点 · 最大修正 ${item.temporalStats.maxCorrection.toPrecision(3)} · 前帧 ${item.previousFrame}${item.nextFrame?' · 后帧 '+item.nextFrame:''}`);li.append(detail);if(item.temporalStats.adaptive&&!item.temporalStats.seed){const adaptive=document.createElement('small');setText(adaptive,`自适应强度 ${item.temporalStats.effectiveStrengthMean.toFixed(1)}%（均值） · 速度 ${item.temporalStats.speedMaxPercent.toFixed(2)}%/帧（最大） · 快速保护 ${item.temporalStats.fastVertices} 顶点`);li.append(adaptive);}}if(item.bakeStats){const detail=document.createElement('small');setText(detail,`已烘焙 ${item.bakeStats.resolution}² · 覆盖 ${(item.bakeStats.coverage*100).toFixed(1)}% · 未匹配 ${item.bakeStats.unmatchedPixels} 像素`);li.append(detail);}if(item.error){const detail=document.createElement('small');detail.className='batch-error';setText(detail,item.error);li.append(detail);}list.append(li);}
  }
  async start(){
    if(this.active)return;
    this.active=true;this.uploading=true;this.cancelRequested=false;this.stage='preparing';this.error='';this.lockWorkspace();this.update(true);
    try{
      const files=[...this.files],textures=[...this.textures],flow=$('batch-flow').checked,bake=flow||$('batch-bake').checked,independent=$('batch-mode').value==='independent',automatic=$('batch-auto-download').checked;
      const temporal=$('batch-temporal').checked?{repairAnomalies:$('temporal-repair').checked,repairMaxGap:Number($('repair-max-gap').value),detectAnomalies:$('temporal-anomalies').checked,anomalyPercent:Number($('anomaly-threshold').value),adaptive:$('temporal-adaptive').checked,speedPercent:Number($('temporal-speed').value),mode:$('temporal-mode').value,strength:Number($('temporal-strength').value),distancePercent:Number($('temporal-distance').value)}:null;
      const snapshot=await this.getSnapshot($('batch-use-result').checked,bake,flow,temporal);
      if(independent&&!files.some(f=>this.constraints?.items.some(i=>i.name.toLowerCase()===f.name.toLowerCase())))throw Error('独立约束 JSON 没有与所选文件名匹配的项目。');
      if(this.report?.status==='draft')await this.api('batch-cancel',{jobId:this.id});
      const created=await this.api('batch-create',{...snapshot,names:files.map(f=>f.name),mode:independent?'independent':'sequence',constraints:this.constraints});this.id=created.id;this.report=created;this.selectionChanged=false;this.remember('facewrap-batch-job',this.id);this.remember('facewrap-batch-auto',automatic?this.id:'');this.stage='uploading';this.update(true);
      for(const file of files){
        if(this.cancelRequested)break;
        let text,uploadError;if(file.size>18*1024*1024)uploadError='单文件超过 18 MB 上限。';else{try{text=await file.text();}catch(error){uploadError=error.message;}}
        let texture,textureError;
        if(bake&&!uploadError){
          const stem=name=>name.replace(/\.[^.]+$/,'').toLowerCase(),matches=textures.filter(image=>stem(image.name)===stem(file.name));
          if(matches.length!==1)textureError=matches.length?'扫描匹配到多张同主名贴图，请只保留一张。':'未找到同主名 PNG/JPEG 贴图。';
          else try{const image=matches[0];if(!/\.(png|jpe?g)$/i.test(image.name)||image.size>8*1024*1024)throw Error('扫描贴图仅支持 PNG/JPEG，单张上限 8 MB。');const dataUrl=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=()=>reject(Error('无法读取扫描贴图。'));reader.readAsDataURL(image);});texture={name:image.name,dataUrl:dataUrl.replace(/^data:[^;]*;/,/\.png$/i.test(image.name)?'data:image/png;':'data:image/jpeg;')};}catch(error){textureError=error.message;}
        }
        try{this.report=await this.api('batch-add',{jobId:this.id,name:file.name,text,uploadError,texture,textureError});}
        catch(error){if(this.cancelRequested)break;this.report=await this.api('batch-add',{jobId:this.id,name:file.name,uploadError:error.message});}
        this.render();
      }
      this.uploading=false;
      if(this.cancelRequested){this.report=await this.api('batch-cancel',{jobId:this.id});this.active=false;this.unlockWorkspace();this.update(false);return;}
      this.report=await this.api('batch-start',{jobId:this.id});this.stage='running';this.poll();
    }catch(error){
      this.error=error.message;this.uploading=false;this.active=false;this.unlockWorkspace();this.update(false);
    }
  }
  async poll(){
    if(this.polling||!this.id)return;clearTimeout(this.timer);this.polling=true;
    try{
      const id=this.id,report=await this.api('batch-status',{jobId:this.id});
      if(id!==this.id)return;
      if(this.report?.cancelRequested&&!report.cancelRequested){this.timer=setTimeout(()=>this.poll(),300);return;}
      this.report=report;this.retries=0;this.error='';
      if(terminal.has(this.report.status)){
        this.active=false;this.cancelRequested=false;this.unlockWorkspace();this.update(false);
        await this.autoDownload();
      }else if(this.report.status==='draft'){
        this.active=false;this.uploading=false;this.unlockWorkspace();this.error='上传尚未完成。请取消该草稿后重新选择扫描。';this.update(false);
      }else{this.active=true;this.lockWorkspace();this.render();this.timer=setTimeout(()=>this.poll(),750);}
    }catch(error){
      this.error=`任务查询失败：${error.message}`;this.render();this.retries++;
      if(this.retries<10&&this.active)this.timer=setTimeout(()=>this.poll(),2000);
      else{this.active=false;this.unlockWorkspace();this.update(false);}
    }finally{this.polling=false;$('batch-refresh').disabled=(!this.ownsBusy&&this.readiness().busy)||!this.id||this.uploading;}
  }
  async resume(){
    if(!this.id||this.uploading||this.polling)return;this.active=true;this.lockWorkspace();await this.poll();
  }
  async cancel(){
    this.cancelRequested=true;this.error='取消已请求：当前求解项会先完成。';this.render();$('batch-cancel').disabled=true;
    if(this.stage==='preparing'&&this.active)return;
    try{if(this.id)this.report=await this.api('batch-cancel',{jobId:this.id});if(!this.uploading)this.poll();}
    catch(error){this.error=error.message;this.render();this.cancelRequested=false;$('batch-cancel').disabled=false;}
  }
  async downloadZip(){
    if(!this.id||this.downloading||!this.report?.archiveReady)return;this.downloading=true;this.update(false);
    const id=this.id;
    try{const response=await fetch(`/api/batch-download?jobId=${encodeURIComponent(id)}`);if(!response.ok)throw Error((await response.json()).error||'下载失败。');this.download(await response.blob(),`facewrap_batch_${id.slice(0,8)}.zip`,'application/zip');}
    catch(error){this.error=`ZIP 下载未完成：${error.message}；可重试下载。`;this.render();}
    finally{this.downloading=false;this.update(false);}
  }
  async autoDownload(id=this.id){
    if(id!==this.id||this.remember('facewrap-batch-auto')!==id)return;
    if(this.downloading){clearTimeout(this.autoTimer);this.autoTimer=setTimeout(()=>this.autoDownload(id),500);return;}
    this.remember('facewrap-batch-auto','');if(this.report.startedAt)await this.downloadZip();
  }
}

