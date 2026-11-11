import {setText,translate} from './i18n.mjs';
const terminal=new Set(['completed','failed','cancelled','interrupted']);
const labels={queued:'排队中',running:'运行中',cancelling:'正在取消',completed:'已完成',failed:'失败',cancelled:'已取消',interrupted:'服务已中断'};
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));

export async function taskRequest(path,body){
  const response=await fetch('/api/tasks'+path,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const data=await response.json();if(!response.ok)throw new Error(data.error||`HTTP ${response.status}`);return data;
}

export class TaskUI{
  constructor(callbacks){
    this.callbacks=callbacks;this.selected=null;this.watching=false;this.revision=0;
    this.select=document.getElementById('task-select');this.info=document.getElementById('task-info');
    this.cancel=document.getElementById('task-cancel');this.view=document.getElementById('task-view');
    this.view.onclick=()=>this.open(this.select.value);
    this.cancel.onclick=async()=>{try{const job=await taskRequest('/'+this.selected+'/cancel',{});this.draw(job);}catch(error){callbacks.error(error);}};
    this.select.onchange=()=>{this.view.disabled=!this.select.value||this.watching;};
    this.refresh();this.timer=setInterval(()=>this.refresh(),1200);
    const requested=new URLSearchParams(location.search).get('task');if(requested)this.open(requested);
  }
  draw(job){
    const p=job.progress||{};const text=[job.id.slice(0,8),labels[job.status]||job.status];
    if(p.stage)text.push(p.stage);
    if(p.requestedIterations)text.push(`${p.iteration}/${p.requestedIterations}`);
    if(Number.isFinite(p.meanDistance))text.push(`平均距离 ${p.meanDistance.toPrecision(4)}`);
    if(job.previewAvailable)text.push(job.status==='completed'?'贴合结果':terminal.has(job.status)?'预览未采用':'阶段预览');
    setText(this.info,text.join(' · '));
    document.getElementById('task-progress').value=job.status==='completed'?1:Math.min(.99,(p.iteration||0)/(p.requestedIterations||1));
    this.cancel.disabled=!this.watching||terminal.has(job.status)||job.status==='cancelling';
    this.info.classList.toggle('error',job.status==='failed');
  }
  async refresh(){
    if(this.refreshing)return;this.refreshing=true;
    try{
      const {tasks}=await taskRequest('');const chosen=this.select.value;this.select.replaceChildren();
      const empty=new Option(translate('选择共享任务'), '');this.select.add(empty);
      for(const job of tasks){const option=new Option('',job.id);setText(option,`${job.id.slice(0,8)} · ${labels[job.status]||job.status}`);this.select.add(option);}
      this.select.value=this.watching?this.selected:(chosen||this.selected||'');this.view.disabled=!this.select.value||this.watching;
      document.getElementById('task-connection').hidden=true;
    }catch{document.getElementById('task-connection').hidden=false;}
    finally{this.refreshing=false;}
  }
  async run(body){
    const job=await taskRequest('',body);return this.watch(job.id);
  }
  async watch(id){
    if(this.watching)throw new Error(translate('正在查看其他任务。'));
    this.selected=id;this.watching=true;this.revision=0;this.view.disabled=true;this.select.disabled=true;
    if(![...this.select.options].some(option=>option.value===id))this.select.add(new Option(id.slice(0,8),id));
    this.select.value=id;
    try{
      while(true){
        const job=await taskRequest('/'+id);this.draw(job);
        if(job.previewAvailable&&(job.progress?.previewRevision||0)>this.revision){
          const preview=await taskRequest('/'+id+'/preview');this.callbacks.preview(preview.vertices);this.revision=preview.revision;
        }
        if(terminal.has(job.status)){
          if(job.status==='completed')return await taskRequest('/'+id+'/result');
          throw new Error(job.error||translate(labels[job.status]));
        }
        await pause(500);
      }
    }finally{this.watching=false;this.cancel.disabled=true;this.select.disabled=false;this.refresh();}
  }
  async open(id){
    if(!id||this.watching||!this.callbacks.canOpen())return;
    if(!this.callbacks.confirmOpen())return;
    this.callbacks.busy(true);
    try{
      const job=await taskRequest('/'+id);this.draw(job);
      if(job.status==='failed')throw new Error(job.error||translate('失败'));
      const input=await taskRequest('/'+id+'/input');await this.callbacks.load(input);
      const result=await this.watch(id);this.callbacks.complete(result);
    }catch(error){this.callbacks.rollback();this.callbacks.error(error);}
    finally{this.callbacks.busy(false);}
  }
}
