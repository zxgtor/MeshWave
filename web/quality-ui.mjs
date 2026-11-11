import * as THREE from 'three';
import {setText} from './i18n.mjs';
import {summarizeQuality,qualityColor,buildQualityGraph,qualityRegion} from './fit-quality.mjs';
const $=id=>document.getElementById(id);

export class QualityUI{
  constructor(callbacks){
    Object.assign(this,callbacks);this.data=null;this.thresholdPercent=.2;this.radiusPercent=5;this.region=null;this.seed=null;
    $('quality-compute').onclick=()=>this.compute();
    $('show-quality').onchange=()=>{if(this.enabled)$('show-weights').checked=false;else $('quality-local').checked=false;this.paint();this.update();};
    $('quality-normals').onchange=()=>this.paint();
    $('quality-local').onchange=()=>{if(this.inspecting)this.enterInspection();this.update();};
    $('quality-threshold').onchange=()=>this.parameter('thresholdPercent','quality-threshold',.001,10);
    $('quality-radius').onchange=()=>this.parameter('radiusPercent','quality-radius',.1,20);
    $('quality-clear-local').onclick=()=>{this.seed=null;this.region=null;this.render();this.paint();};
    $('quality-worst').onclick=()=>{
      if(!this.data)return;const stats=summarizeQuality(this.data,this.threshold);
      if(stats.worst===null)return;
      $('show-quality').checked=true;$('show-weights').checked=false;$('quality-local').checked=true;
      this.enterInspection();this.select(stats.worst);this.focus(stats.worst);this.update();
    };
    this.update();
  }
  get enabled(){return Boolean(this.data&&$('show-quality').checked);}
  get inspecting(){return this.enabled&&$('quality-local').checked;}
  get threshold(){return this.data.unit*this.thresholdPercent/100;}
  parameter(key,id,min,max){
    const value=Number($(id).value);
    if(!Number.isFinite(value)||value<min||value>max){$(id).value=this[key];setText($('quality-info'),'质量检查参数超出范围。');return;}
    this[key]=value;
    if(this.data){if(this.seed!==null)this.select(this.seed);else{this.render();this.paint();}}
  }
  hide(){
    $('show-quality').checked=false;$('quality-local').checked=false;this.update();
  }
  clear(stale=false,repaint=false){
    const wasVisible=this.enabled;this.data=null;this.graph=null;this.region=null;this.seed=null;this.vertices=null;
    $('show-quality').checked=false;$('quality-local').checked=false;
    $('quality-global').hidden=true;$('quality-local-summary').hidden=true;$('quality-legend').hidden=true;
    setText($('quality-info'),stale?'几何已变化，请重新计算质量检查。':'完成贴合后，计算误差并检查局部区域。');
    this.update();if(wasVisible&&repaint)this.paint();
  }
  sync(side,vertices){
    if(!this.data)return;
    const r=this.readiness();
    if(r.source!==this.source||r.target!==this.target||r.result?.vertices!==this.vertices||side==='source'&&vertices!==this.vertices||r.preview)this.clear(true);
  }
  update(){
    const r=this.readiness(),blocked=r.busy||this.computing||r.preview;
    $('quality-compute').disabled=blocked||!r.result||!r.source||!r.target;
    for(const id of ['show-quality','quality-normals','quality-threshold','quality-radius'])$(id).disabled=blocked||!this.data;
    $('quality-local').disabled=blocked||!this.enabled;
    $('quality-worst').disabled=blocked||!this.data||!this.data.distances.some(d=>d!==null);
    $('quality-clear-local').disabled=blocked||this.seed===null;
    $('quality-legend').hidden=!this.enabled;
  }
  async compute(){
    const r=this.readiness();if(r.busy||r.preview||!r.result)return;
    this.computing=true;this.setBusy(true);setText($('quality-info'),'正在计算完整表面误差…');
    try{
      const data=await this.api('fit-quality',{source:r.source.text,target:r.target.text,vertices:r.result.vertices,excludedFaces:r.exclusions,normalAngle:r.normalAngle});
      this.data=data;this.vertices=r.result.vertices;this.source=r.source;this.target=r.target;this.graph=null;this.region=null;this.seed=null;
      $('show-quality').checked=true;$('show-weights').checked=false;
      setText($('quality-info'),`检查完成 · 跳过 ${data.excludedVertices} 个模板顶点 · 排除 ${data.excludedTargetFaces} 个目标面 · 忽略 ${data.ignoredDegenerateTargetFaces} 个退化目标面`);
      this.render();this.paint();
    }catch(error){this.clear(false,true);setText($('quality-info'),error.message);}
    finally{this.computing=false;this.setBusy(false);this.update();}
  }
  describe(stats){
    if(!stats.count)return '没有可统计的顶点。';
    const n=value=>value.toPrecision(4);
    return `${stats.count} 个顶点 · 超阈值 ${stats.above} (${(stats.above/stats.count*100).toFixed(1)}%)\n平均 ${n(stats.mean)} · RMS ${n(stats.rms)}\n中位数 ${n(stats.median)} · P95 ${n(stats.p95)} · 最大 ${n(stats.max)}\n法线异常 ${stats.normalMismatch} · 法线未知 ${stats.normalUnknown}`;
  }
  render(){
    if(!this.data)return;
    $('quality-global').hidden=false;
    setText($('quality-global'),`全局质量\n${this.describe(summarizeQuality(this.data,this.threshold))}`);
    $('quality-local-summary').hidden=this.seed===null;
    if(this.seed!==null)setText($('quality-local-summary'),`局部质量 · 中心顶点 #${this.seed+1}\n表面半径 ${this.radiusPercent}% (${(this.radiusPercent*this.data.unit/100).toPrecision(4)})\n${this.describe(summarizeQuality(this.data,this.threshold,this.region))}`);
    setText($('quality-legend-label'),`表面误差 · 0 → ${this.threshold.toPrecision(4)} (${this.thresholdPercent}%)`);
    setText($('quality-legend-note'),$('quality-normals').checked?'灰色不计入统计 · 紫色法线异常':'灰色不计入统计 · 红色达到阈值');
  }
  select(id){
    if(!this.data||this.data.distances[id]===null){setText($('quality-info'),'此处为排除区或未使用顶点，不参与统计。');return;}
    this.graph??=buildQualityGraph(this.vertices,this.source.faces,this.data.distances);
    this.seed=id;this.region=qualityRegion(this.graph,id,this.radiusPercent*this.data.unit/100);
    this.render();this.paint();this.update();
  }
  apply(mesh){
    if(!this.enabled)return;
    const g=mesh.geometry,colors=new THREE.Float32BufferAttribute(new Float32Array(g.attributes.position.count*3),3),region=this.region?new Set(this.region):null;
    const put=(id,index)=>{
      let color=qualityColor(this.data.distances[id],this.threshold,this.data.normalAngles[id],this.data.normalAngle,$('quality-normals').checked);
      if(region&&!region.has(id)&&this.data.distances[id]!==null)color=color.map(x=>x*.25);
      colors.setXYZ(index,...color);
    };
    if(g.index)this.data.distances.forEach((_,id)=>put(id,id));
    else this.source.faces.forEach((face,i)=>face.forEach((id,j)=>put(id,i*3+j)));
    g.setAttribute('color',colors);mesh.material.vertexColors=true;mesh.material.needsUpdate=true;
    this.render();this.update();
  }
}
