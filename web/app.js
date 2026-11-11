import {setText,appendText,setLabel,translate,getSourceText,preserveName,initializeLanguage} from './i18n.mjs';
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { CSS2DRenderer, CSS2DObject } from 'three/addons/renderers/CSS2DRenderer.js';
import { BrushMesh, StrokeHistory } from './brush.mjs';
import { TargetSurface } from './target-surface.mjs';
import { MeshReview } from './mesh-review.mjs';
import { BatchUI } from './batch-ui.mjs';
import { QualityUI } from './quality-ui.mjs';
import {pointPosition,pointSupport,samePoint,pointLabel,pointFromHit,pairKey} from './surface-points.mjs';

initializeLanguage();
const $ = id => document.getElementById(id);
const state = { source: null, target: null, pairs: [], pending: null, result: null, busy: false,
  edit: null, excludedFaces: {source:new Set(),target:new Set()}, regionUndo: [], dirty:false,
  autoSuggestion:null, autoMessage:'尚未自动检测',brushWeights:null,curves:[],curvePairs:[],curvePaths:null,curveSuggestion:null,curveIndex:0,flowSuggestion:null,flowUi:null };
const views = {};
const brush={context:null,surface:null,history:new StrokeHistory(),stroke:null,pointer:null,lastTime:0,cursor:null};
const health={viewer:null,text:null,name:'',side:'source',report:null,repair:null,after:false,fromCurrent:false,undo:null};
let batchUI=null,qualityUI=null;
function status(text, error = false) { setText($('status'),text); $('status').classList.toggle('error', error); }
function changed() {discardFlowPreview();state.dirty=true;health.undo=null;state.curvePairs=currentCurvePairs();state.curveSuggestion=null;if(state.autoSuggestion){state.autoSuggestion=null;state.autoMessage='编辑状态已变化，旧检测建议已清除。';}}
function download(text, name, type='application/json') {
  const url=URL.createObjectURL(new Blob([text],{type})),a=document.createElement('a');
  a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
async function api(path, body) {
  const response = await fetch(`/api/${path}`, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || `请求失败 ${response.status}`);
  return data;
}
function geometry(vertices, faces, uvs=null, uvFaces=null) {
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(vertices.flat(), 3));
  g.setIndex(faces.flat()); g.computeVertexNormals();
  if(uvs?.length&&uvFaces?.length&&uvFaces.every(f=>f.every(i=>i>=0))){
    const expanded=g.toNonIndexed();g.dispose();expanded.setAttribute('uv',new THREE.Float32BufferAttribute(uvFaces.flatMap(f=>f.flatMap(i=>uvs[i])),2));expanded.computeBoundingSphere();return expanded;
  }
  g.computeBoundingSphere(); return g;
}
function setupView(side, color) {
  const el = $(`${side}-view`), scene = new THREE.Scene(); scene.background = new THREE.Color(0x151619);
  const renderer = new THREE.WebGLRenderer({antialias:true}); renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  el.appendChild(renderer.domElement);
  const labels = new CSS2DRenderer(); Object.assign(labels.domElement.style, {position:'absolute',top:'0',pointerEvents:'none'}); el.appendChild(labels.domElement);
  const camera = new THREE.PerspectiveCamera(40, 1, .01, 100000);
  const controls = new OrbitControls(camera, renderer.domElement); controls.enableDamping = true;
  scene.add(new THREE.HemisphereLight(0xc9dcf3, 0x3c3430, 2.4));
  const key = new THREE.DirectionalLight(0xffffff, 3); key.position.set(3, 5, 7); scene.add(key);
  const fill = new THREE.DirectionalLight(0xabc8ed, 1.8); fill.position.set(-5, 1, -3); scene.add(fill);
  const group = new THREE.Group(); scene.add(group);
  const v = {el, scene, renderer, labels, camera, controls, group, mesh:null, overlay:null, markers:[], color, side};
  const resize = () => {const w=Math.max(1,el.clientWidth),h=Math.max(1,el.clientHeight);renderer.setSize(w,h,false);labels.setSize(w,h);camera.aspect=w/h;camera.updateProjectionMatrix();};
  new ResizeObserver(resize).observe(el); resize();
  let down;
  renderer.domElement.addEventListener('pointerdown', e => {if(side==='source'&&brushActive())return;down=[e.clientX,e.clientY]; if(e.shiftKey) controls.enabled=false;});
  renderer.domElement.addEventListener('pointerup', e => {
    controls.enabled=true;
    if(state.flowSuggestion)return;
    if(side==='source'&&brushActive())return;
    if (!e.shiftKey || !down || Math.hypot(e.clientX-down[0],e.clientY-down[1])>5 || state.busy || !v.mesh) return;
    const rect=renderer.domElement.getBoundingClientRect();
    const ray=new THREE.Raycaster(); ray.setFromCamera(new THREE.Vector2((e.clientX-rect.left)/rect.width*2-1,-(e.clientY-rect.top)/rect.height*2+1),camera);
    const hit=ray.intersectObject(v.mesh)[0]; if(!hit) return;
    if(!['points','curves'].includes($('tool').value)&&!(side==='source'&&qualityUI?.inspecting)){selectRegion(side,hit.faceIndex);return;}
    const vertices=side==='source'&&state.result?state.result.vertices:state[side].vertices;
    const candidates=state[side].faces[hit.faceIndex];
    const id=candidates.reduce((a,b)=>new THREE.Vector3().fromArray(vertices[a]).distanceToSquared(hit.point)<new THREE.Vector3().fromArray(vertices[b]).distanceToSquared(hit.point)?a:b);
    if(side==='source'&&qualityUI?.inspecting){qualityUI.select(id);return;}
    const spline=$('tool').value==='curves'&&state.curves[state.curveIndex]?.type==='spline';
    const point=spline||$('tool').value!=='curves'&&$('point-mode').value==='surface'?pointFromHit(vertices,state[side].faces,hit.faceIndex,v.mesh.worldToLocal(hit.point.clone()).toArray()):id;
    if($('tool').value==='curves')pickCurve(side,point);else pick(side,point);
  });
  renderer.domElement.addEventListener('pointercancel',()=>{controls.enabled=true;down=null;});
  if(side==='source')installBrush(v);
  return v;
}
function disposeMesh(mesh) { if(!mesh) return; mesh.removeFromParent();mesh.geometry.dispose();mesh.material.map?.dispose();mesh.material.dispose(); }
function setMesh(side, vertices) {
  if(side==='source'&&state.flowSuggestion)vertices=state.flowSuggestion.vertices;
  const v=views[side], data=state[side];
  qualityUI?.sync(side,vertices||data.vertices);
  if(side==='source'&&$('show-weights').checked)qualityUI?.hide();
  const qualityDisplay=side==='source'&&qualityUI?.enabled&&!state.flowSuggestion;
  disposeMesh(v.mesh);
  const textureData=side==='source'&&state.result?.texture&&!state.flowSuggestion?state.result.texture:data.texture;
  let map=null;
  const weightDisplay=side==='source'&&$('show-weights').checked&&state.brushWeights&&!state.flowSuggestion;
  if(!qualityDisplay&&!weightDisplay&&$('show-textures').checked&&data.hasUV&&textureData){map=new THREE.TextureLoader().load(textureData.dataUrl);map.colorSpace=THREE.SRGBColorSpace;map.wrapS=map.wrapT=THREE.RepeatWrapping;map.magFilter=THREE.LinearFilter;map.generateMipmaps=false;map.minFilter=THREE.LinearFilter;}
  const options={color:map||weightDisplay||qualityDisplay?0xffffff:v.color,map,side:THREE.DoubleSide,wireframe:$('wire').checked,transparent:Boolean(map),alphaTest:map ? .001 : 0};
  const material=qualityDisplay||map&&$('unlit-textures').checked?new THREE.MeshBasicMaterial(options):new THREE.MeshStandardMaterial({...options,roughness:.72,metalness:map?0:.08});
  v.mesh=new THREE.Mesh(geometry(vertices || data.vertices,data.faces,data.uvs,data.uvFaces),material);
  v.group.add(v.mesh); v.el.querySelector('.placeholder').hidden=true;
  refreshExclusions(side);
  if(weightDisplay)updateWeightColors();
  if(qualityDisplay)qualityUI.apply(v.mesh);
}
function updateWeightColors(ids=null){
  const mesh=views.source?.mesh;if(!mesh||!state.brushWeights||!$('show-weights').checked||state.flowSuggestion)return;
  const g=mesh.geometry;let color=g.attributes.color;
  if(!color){color=new THREE.Float32BufferAttribute(new Float32Array(g.attributes.position.count*3),3);g.setAttribute('color',color);ids=null;}
  const locked=brush.context?.locked||new Set([...blockedVertices('source'),...state.pairs.flatMap(p=>pointSupport(state.source.faces,p[0]))]);
  const paint=(id,index)=>{const w=state.brushWeights[id];color.setXYZ(index,...(locked.has(id)?[.7,.035,.09]:[.07+.88*w,.32+.34*w,.95-.73*w]));};
  if(g.index){for(const id of ids||state.brushWeights.keys())paint(id,id);}
  else if(ids&&brush.context){for(const id of ids)for(const corner of brush.context.corners[id])paint(id,corner);}
  else state.source.faces.forEach((f,i)=>f.forEach((id,j)=>paint(id,i*3+j)));
  color.needsUpdate=true;if(!mesh.material.vertexColors){mesh.material.vertexColors=true;mesh.material.needsUpdate=true;}
}
function blockedVertices(side) {
  const vertices=new Set();
  if(state[side])for(const face of state.excludedFaces[side])for(const id of state[side].faces[face])vertices.add(id);
  return vertices;
}
function refreshExclusions(side) {
  const v=views[side];disposeMesh(v.exclusions);v.exclusions=null;
  if(!state[side]||!state.excludedFaces[side].size||side==='source'&&qualityUI?.enabled)return;
  const vertices=side==='source'&&state.result?state.result.vertices:state[side].vertices;
  const faces=[...state.excludedFaces[side]].map(i=>state[side].faces[i]);
  const mesh=new THREE.Mesh(geometry(vertices,faces),new THREE.MeshBasicMaterial({color:0xf0655b,transparent:true,opacity:.75,side:THREE.DoubleSide,depthWrite:false,polygonOffset:true,polygonOffsetFactor:-2,polygonOffsetUnits:-2}));
  v.group.add(mesh);v.exclusions=mesh;
}
function regionPatch(side,index) {
  const data=state[side];
  if(!data.incident){data.incident=Array.from({length:data.vertices.length},()=>[]);data.faces.forEach((f,i)=>f.forEach(id=>data.incident[id].push(i)));}
  const selected=new Set([index]);let frontier=[index];
  for(let ring=0;ring<Number($('region-size').value);ring++){
    const next=[];for(const face of frontier)for(const id of data.faces[face])for(const neighbor of data.incident[id])if(!selected.has(neighbor)){selected.add(neighbor);next.push(neighbor);}frontier=next;
  }return selected;
}
function selectRegion(side,index) {
  if(state.result){status('请先恢复原始模板，再修改排除区域。',true);return;}
  const patch=regionPatch(side,index),exclude=$('tool').value==='exclude',current=state.excludedFaces[side];
  if(exclude){
    const protectedIds=new Set(state.pairs.flatMap(p=>pointSupport(data.faces,p[side==='source'?0:1])));
    for(const curve of state.curves)for(const point of curve[side])for(const id of pointSupport(data.faces,point))protectedIds.add(id);
    if(side==='source'&&state.pending!==null)pointSupport(state.source.faces,state.pending).forEach(id=>protectedIds.add(id));
    if([...patch].some(i=>state[side].faces[i].some(id=>protectedIds.has(id)))){status('区域包含对应点或曲线节点，请缩小范围或先调整节点。',true);return;}
    if(side==='target'&&new Set([...current,...patch]).size===state.target.faces.length){status('不能排除全部目标面。',true);return;}
  }
  const changedFaces=[...patch].filter(i=>current.has(i)!==exclude);
  if(!changedFaces.length){status('该区域无需更改。');return;}
  state.regionUndo.push({side,faces:changedFaces,exclude});
  for(const i of changedFaces)if(exclude)current.add(i);else current.delete(i);
  state.curvePaths=null;changed();refreshExclusions(side);status(`已${exclude?'排除':'恢复'}${side==='source'?'模板':'目标'} ${changedFaces.length} 个三角面。`);update();
}
function fit(side) {
  const v=views[side]; if(!v.mesh)return;
  const box=new THREE.Box3().setFromObject(v.mesh),sphere=box.getBoundingSphere(new THREE.Sphere());
  const r=Math.max(sphere.radius,.0001),aspect=v.camera.aspect,size=box.getSize(new THREE.Vector3());
  const tangent=Math.tan(THREE.MathUtils.degToRad(20));
  const distance=(Math.max(size.y/(2*tangent),size.x/(2*tangent*aspect))+size.z/2)*1.18;
  v.controls.target.copy(sphere.center);v.camera.position.copy(sphere.center).add(new THREE.Vector3(0,0,distance));
  v.camera.near=r/1000;v.camera.far=distance+r*100;v.camera.updateProjectionMatrix();v.controls.update();
}
function clearResult() {
  qualityUI?.clear();
  discardFlowPreview();
  setText($('flow-info'),'完成几何贴合并加载两侧贴图后，可进行纹理细化。');
  resetBrush();
  const hadResult=Boolean(state.result);
  state.result=null;$('metrics').hidden=true;$('stage-results').hidden=true;$('result-badge').hidden=true;$('overlay').checked=false;disposeMesh(views.source.overlay);views.source.overlay=null;
  if(state.source&&hadResult){setMesh('source');fit('source');}
}
function update() {
  const ready=state.source&&state.target, count=state.pairs.length;
  $('health-current').disabled=state.busy||!state[$('health-side').value];$('health-file').disabled=state.busy;$('health-side').disabled=state.busy;$('health-undo').disabled=state.busy||!health.undo;
  $('brush-tool').disabled=state.busy||!state.result;
  $('brush-radius').disabled=state.busy;$('brush-strength').disabled=state.busy;
  for(const id of ['weight-target','show-weights','weight-protect-all','weight-edit-all'])$(id).disabled=state.busy||!state.result;
  $('brush-undo').disabled=state.busy||!brush.context||!brush.history.undo.length;
  $('brush-redo').disabled=state.busy||!brush.context||!brush.history.redo.length;
  setText($('result-badge'),state.flowSuggestion?'纹理预览':state.result?.textureRefined?'纹理细化':state.result?.manualEdits?'手动修正':'贴合结果');
  $('auto-landmarks').disabled=state.busy||!ready||Boolean(state.result)||state.pending!==null||state.edit!==null;
  $('auto-apply').disabled=state.busy||!state.autoSuggestion;$('auto-cancel').disabled=$('auto-apply').disabled;
  $('auto-review').hidden=!state.autoSuggestion;
  setText($('auto-info'),state.autoSuggestion?`检测到 ${state.autoSuggestion.pairs.length} 对建议点，视图中以 A 编号显示。采用前请检查；原点对尚未替换。`:state.autoMessage);
  const suggested=$('auto-points');suggested.replaceChildren();
  if(state.autoSuggestion){
    state.autoSuggestion.names.forEach((name,i)=>{const li=document.createElement('li');setText(li,`A${i+1} · ${name}`);suggested.append(li);});
    setText($('auto-skipped'),state.autoSuggestion.skipped.length?'已跳过：'+state.autoSuggestion.skipped.map(p=>`${p.name}（${p.reason}）`).join('、'):'所有候选均已映射。检测建议可能有误，请检查眼角、鼻翼和嘴角。');
  }
  setText($('pair-count'),`${count} 对`);
  $('run').disabled=state.busy||!ready||count<3||state.pending!==null||state.edit!==null||Boolean(state.autoSuggestion)||Boolean(state.curveSuggestion);
  $('export').disabled=state.busy||!state.result;$('reset').disabled=state.busy||!state.result;
  $('undo').disabled=state.busy||(!count&&state.pending===null);$('clear').disabled=$('undo').disabled;
  $('overlay').disabled=state.busy||!ready;
  for(const id of ['source','target','demo','iterations','smoothness','normal-angle','solver-mode','open-project','project-file','tool','point-mode','region-size','cancel-edit'])$(id).disabled=state.busy;
  for(const id of ['bake-resolution','bake-padding','bake-distance','show-textures','unlit-textures'])$(id).disabled=state.busy;
  for(const side of ['source','target']){
    $(`${side}-texture`).disabled=state.busy||!state[side]?.hasUV;
    $(`remove-${side}-texture`).disabled=state.busy||!state[side]?.texture;
    setText($(`${side}-texture-name`),state[side]?.texture?`${state[side].texture.name} · ${state[side].texture.width} × ${state[side].texture.height}`:state[side]&&!state[side].hasUV?'模型缺少完整 UV':'选择 PNG / JPEG',Boolean(state[side]?.texture));
  }
  $('bake').disabled=state.busy||!state.result||!state.source?.hasUV||!state.target?.hasUV||!state.target?.texture;
  $('export-texture').disabled=state.busy||!state.result?.texture;$('export-textured-model').disabled=$('export-texture').disabled;
  $('texture-preview').hidden=!state.result?.texture;
  if(state.result?.texture){if($('texture-preview').getAttribute('src')!==state.result.texture.dataUrl)$('texture-preview').src=state.result.texture.dataUrl;
    const stats=state.result.textureStats;setText($('bake-info'),stats?`有效 UV 像素覆盖率 ${(stats.coverage*100).toFixed(1)}% · ${stats.unmatchedPixels.toLocaleString()} 像素未匹配 · ${stats.degenerateUVFaces} 个零面积 UV 面`:`已恢复贴图 · ${state.result.texture.width} × ${state.result.texture.height}`);
  }else{$('texture-preview').removeAttribute('src');setText($('bake-info'),'尚未烘焙');}
  $('save-project').disabled=state.busy||(!state.source&&!state.target);
  setText($('project-state'),!state.source&&!state.target?'未建立工程':state.dirty?'有未保存更改':'已保存');
  $('cancel-edit').hidden=state.edit===null;
  setText($('region-count'),`模板 ${state.excludedFaces.source.size} 面 · 目标 ${state.excludedFaces.target.size} 面`);
  $('undo-region').disabled=state.busy||!state.regionUndo.length;
  $('clear-regions').disabled=state.busy||(!state.excludedFaces.source.size&&!state.excludedFaces.target.size);
  setText($('phase'),brush.stroke?'正在笔刷修正':state.busy?'正在处理':state.result?.textureRefined?'纹理细化结果':state.result?.manualEdits?'手动修正结果':state.result?'贴合完成':state.edit?'重选对应点':$('tool').value==='curves'?'绘制成对曲线':$('tool').value!=='points'?'编辑排除区域':ready?'选择对应点':'准备模型');
  setText($('instruction'),state.busy?'正在处理，请稍候…':state.result?'左侧显示结果，可叠加目标检查，或导出 OBJ':state.pending!==null?'下一步：Shift + 点击右侧目标的相同部位':ready?'Shift + 点击左侧模板，开始选择下一对对应点':'导入两个模型，或载入演示体验完整流程');
  if(!state.busy&&!state.result&&state.edit)setText($('instruction'),`Shift + 点击${state.edit.side==='source'?'左侧模板':'右侧目标'}，替换第 ${state.edit.index+1} 对中的点`);
  else if(!state.busy&&!state.result&&$('tool').value==='curves')setText($('instruction'),'Shift + 点击两侧表面添加曲线节点；两侧起点与绘制方向需对应，生成预览后采用');
  else if(!state.busy&&!state.result&&$('tool').value!=='points')setText($('instruction'),`Shift + 点击任一模型${$('tool').value==='exclude'?'排除':'恢复'}区域，红色为已排除面`);
  if(brushActive()&&!state.busy)setText($('instruction'),'在左侧按住左键修正；Alt + 左键旋转，右键平移；Ctrl+Z 撤销，Ctrl+Y 重做');
  document.body.classList.toggle('busy',state.busy);
  const list=$('pairs');list.replaceChildren();
  if(!count&&state.pending===null){const li=document.createElement('li');li.className='empty';setText(li,'尚未选择对应点');list.append(li);}
  state.pairs.forEach((p,i)=>{
    const li=document.createElement('li'),number=document.createElement('span');setText(number,String(i+1).padStart(2,'0'));li.append(number);
    for(const [column,side,label] of [[0,'source','模板'],[1,'target','目标']]){
      const button=document.createElement('button');setText(button,`${label} ${pointLabel(p[column])}`);setLabel(button,'aria-label',`重选第 ${i+1} 对${label}点`);button.disabled=state.busy;
      button.classList.toggle('editing',state.edit?.index===i&&state.edit.side===side);button.onclick=()=>beginEdit(i,side);li.append(button);
    }
    const remove=document.createElement('button');setText(remove,'删');setLabel(remove,'aria-label',`删除第 ${i+1} 对`);remove.disabled=state.busy;remove.onclick=()=>{clearResult();state.pairs.splice(i,1);state.edit=null;changed();status(`已删除第 ${i+1} 对。`);update();};li.append(remove);list.append(li);
  });
  if(state.pending!==null){const li=document.createElement('li');setText(li,`${count+1}　模板 ${pointLabel(state.pending)} → 等待目标`);list.append(li);}
  renderMarkers();
  updateCurveControls();renderCurves();
  updateFlowControls();
  batchUI?.update(state.busy);
  qualityUI?.update();
  if(batchUI?.active){setText($('phase'),'批处理进行中');setText($('instruction'),'使用固定模板与参数依次求解；当前工作区保留，进度见批处理列表。');}
  if(state.source&&state.brushWeights&&$('show-weights').checked)updateWeightColors();
}
function renderMarkers() {
  for(const side of ['source','target']){
    const v=views[side];for(const m of v.markers){m.removeFromParent();m.element.remove();}v.markers=[];
    if(!state[side])continue;
    const suggestion=state.autoSuggestion;
    const points=(suggestion?suggestion.pairs:state.pairs).map(p=>p[side==='source'?0:1]);
    if(!suggestion&&side==='source'&&state.pending!==null)points.push(state.pending);
    const vertices=side==='source'&&state.result?state.result.vertices:state[side].vertices;
    points.forEach((id,i)=>{const div=document.createElement('div');div.className='marker';div.classList.toggle('suggested',Boolean(suggestion));div.classList.toggle('editing',state.edit?.index===i&&state.edit.side===side);setText(div,suggestion?`A${i+1}`:i+1);if(suggestion)setLabel(div,'title',suggestion.names[i]);const marker=new CSS2DObject(div);marker.position.fromArray(pointPosition(vertices,state[side].faces,id));v.group.add(marker);v.markers.push(marker);});
  }
}
function pick(side,id) {
  if(state.result){status('请先恢复原始模板，再修改对应点。',true);return;}
  if(!state.source||!state.target){status('请先导入两个模型。',true);return;}
  if(pointSupport(state[side].faces,id).some(i=>blockedVertices(side).has(i))){status('此点在排除区域内，请先恢复该区域。',true);return;}
  if(state.edit){
    if(side!==state.edit.side){status('请在正在重选的一侧点击。',true);return;}
    const column=side==='source'?0:1;
    if(state.pairs.some((p,i)=>i!==state.edit.index&&samePoint(state[side].faces,p[column],id))){status('此点已被其他点对使用。',true);return;}
    state.pairs[state.edit.index][column]=id;state.edit=null;changed();status('已更新对应点。');update();return;
  }
  if(side==='source'){
    if(state.pairs.some(p=>samePoint(state.source.faces,p[0],id))){status('此模板点已被选用。',true);return;}
    state.pending=id;status(`已选模板点 ${pointLabel(id)}，请在右侧选择对应点。`);
  }else{
    if(state.pending===null){status('请先在左侧选择模板点。',true);return;}
    if(state.pairs.some(p=>samePoint(state.target.faces,p[1],id))){status('此目标点已被选用。',true);return;}
    if(state.pairs.length>=100){status('最多支持 100 对对应点。',true);return;}
    state.pairs.push([state.pending,id]);state.pending=null;status(`已添加第 ${state.pairs.length} 对对应点。`);
  }changed();update();
}
function beginEdit(index,side) {
  clearResult();state.edit={index,side};state.pending=null;$('tool').value='points';changed();status(`请 Shift + 点击${side==='source'?'模板':'目标'}的新位置；只修改所选点对的一侧。`);update();
}
function captureFace(side, renderer){
  const view=views[side];view.controls.update();view.camera.updateMatrixWorld(true);
  const camera=view.camera.clone();camera.aspect=1;camera.updateProjectionMatrix();camera.updateMatrixWorld(true);
  const scene=new THREE.Scene();scene.background=new THREE.Color(0x32363c);
  scene.add(new THREE.HemisphereLight(0xffffff,0x52535b,1.3));
  const distance=camera.position.distanceTo(view.controls.target);
  const right=new THREE.Vector3().setFromMatrixColumn(camera.matrixWorld,0),up=new THREE.Vector3().setFromMatrixColumn(camera.matrixWorld,1);
  const key=new THREE.DirectionalLight(0xffffff,2);key.position.copy(camera.position).addScaledVector(right,distance*.3).addScaledVector(up,distance*.3);key.target.position.copy(view.controls.target);scene.add(key,key.target);
  const material=new THREE.MeshStandardMaterial({color:0xc6b9ad,roughness:.85,metalness:0,side:THREE.DoubleSide});
  scene.add(new THREE.Mesh(view.mesh.geometry,material));
  try{renderer.render(scene,camera);return {image:{name:side+'.png',dataUrl:renderer.domElement.toDataURL('image/png')},camera:{inverseProjection:camera.projectionMatrixInverse.toArray(),world:camera.matrixWorld.toArray()}};}
  finally{material.dispose();scene.clear();}
}
$('auto-landmarks').onclick=async()=>{
  state.autoSuggestion=null;state.autoMessage='正在从正面灰模渲染检测并映射表面点…';state.busy=true;update();status('正在自动检测人脸对应点…');
  let renderer;
  try{
    renderer=new THREE.WebGLRenderer({antialias:true,preserveDrawingBuffer:true});renderer.setSize(640,640);renderer.outputColorSpace=THREE.SRGBColorSpace;
    const sourceView=captureFace('source',renderer),targetView=captureFace('target',renderer);
    const result=await api('landmarks',{source:state.source.text,target:state.target.text,sourceView,targetView,excludedFaces:serializedExclusions()});
    state.autoSuggestion=result;status(`已生成 ${result.pairs.length} 对建议点，请检查 A 编号后点击“采用建议”。`);
  }catch(error){state.autoMessage='检测未完成；原点对保留。';status(error.message,true);}
  finally{renderer?.dispose();renderer?.forceContextLoss();state.busy=false;update();}
};
$('auto-apply').onclick=()=>{
  const suggestion=state.autoSuggestion;clearResult();state.pairs=suggestion.pairs.map(p=>[...p]);state.curvePairs=[];state.pending=null;state.edit=null;state.autoSuggestion=null;
  state.autoMessage=`已采用 ${state.pairs.length} 对自动点，可在下方列表逐点重选或删除。`;
  changed();status('已采用自动对应点，请检查后开始贴合。');update();
};
$('auto-cancel').onclick=()=>{state.autoSuggestion=null;state.autoMessage='已取消检测建议，原点对未改变。';status(state.autoMessage);update();};
function currentCurvePairs(){return state.curvePairs.filter(p=>state.pairs.some(q=>pairKey(p)===pairKey(q)));}
function curveBasePairs(){const keys=new Set(currentCurvePairs().map(pairKey));return state.pairs.filter(p=>!keys.has(pairKey(p)));}
function curveRequest(pathOnly,curves=state.curves){for(const curve of curves)preserveName(`“${curve.name}”`);return {source:state.source.text,target:state.target.text,curves,pairs:curveBasePairs(),excludedFaces:serializedExclusions(),pathOnly};}
function updateCurveControls(){
  const blocked=state.busy||!state.source||!state.target||Boolean(state.result)||state.pending!==null||state.edit!==null||Boolean(state.autoSuggestion);
  $('curve-new').disabled=blocked||state.curves.length>=12;
  const select=$('curve-select');select.replaceChildren(...state.curves.map((c,i)=>new Option(`${i+1} · ${c.name}`,String(i))));
  state.curveIndex=Math.max(0,Math.min(state.curveIndex,state.curves.length-1));select.value=String(state.curveIndex);
  const curve=state.curves[state.curveIndex];
  setText($('curve-kind'),curve&&curve.type!=='spline'?'旧版网格折线':'三次表面样条');
  for(const id of ['curve-select','curve-name','curve-count','curve-closed','curve-undo-source','curve-undo-target','curve-reverse','curve-delete','curve-generate'])$(id).disabled=blocked||!curve;
  $('curve-generate').disabled=blocked||(!curve&&!currentCurvePairs().length);
  $('curve-apply').disabled=blocked||!state.curveSuggestion;$('curve-cancel').disabled=state.busy||!state.curveSuggestion;
  if(!state.busy){$('curve-name').value=curve?.name||'';$('curve-count').value=curve?.count||8;$('curve-closed').checked=curve?.closed||false;}
  if(curve){$('curve-undo-source').disabled||=!curve.source.length;$('curve-undo-target').disabled||=!curve.target.length;}
}
function renderCurves(){
  for(const side of ['source','target']){
    const view=views[side];if(!view)continue;
    for(const line of view.curveLines||[])disposeMesh(line);view.curveLines=[];
    for(const mark of view.curveMarks||[]){mark.removeFromParent();mark.element.remove();}view.curveMarks=[];
    if(!state[side]||state.result||$('tool').value!=='curves')continue;
    const vertices=state[side].vertices,curve=state.curves[state.curveIndex];
    const label=(id,text,color)=>{const el=document.createElement('span');el.className='marker';setText(el,text);el.style.background=color;const mark=new CSS2DObject(el);mark.renderOrder=text.startsWith('S')?10:20;mark.position.fromArray(pointPosition(vertices,state[side].faces,id));view.group.add(mark);view.curveMarks.push(mark);};
    if(curve){
      const path=state.curvePaths?.[state.curveIndex]?.[side];
      if(path?.length>1){const g=new THREE.BufferGeometry().setFromPoints(path.map(id=>new THREE.Vector3().fromArray(pointPosition(vertices,state[side].faces,id)))),line=new THREE.Line(g,new THREE.LineBasicMaterial({color:0x9dc0e6,depthTest:false,transparent:true,opacity:.9}));line.renderOrder=5;view.group.add(line);view.curveLines.push(line);}
      curve[side].forEach((id,i)=>label(id,`${i===0?'起':i+1}`,'#9dc0e6'));
    }
    state.curveSuggestion?.pairs.forEach((p,i)=>label(p[side==='source'?0:1],`S${i+1}`,'#a8c6ff'));
  }
}
async function editCurves(mutate){
  if(state.busy||state.result||!state.source||!state.target||state.pending!==null||state.edit!==null||state.autoSuggestion){status('请先完成点对编辑或检测预览，并恢复原始模板后再绘制曲线。',true);return;}
  const curves=structuredClone(state.curves);mutate(curves);const curveIndex=state.curveIndex;state.busy=true;update();
  try{const data=await api('curve-pairs',curveRequest(true,curves));state.curves=curves;state.curveIndex=curveIndex;state.curvePaths=data.paths;changed();setText($('curve-info'),'曲线路径已更新。两侧按相同方向绘制后，生成对应点预览。');}
  catch(error){status(error.message,true);}finally{state.busy=false;update();}
}
function pickCurve(side,id){
  if(!state.curves[state.curveIndex]){status('请先点击“新增成对曲线”。',true);return;}
  editCurves(curves=>curves[state.curveIndex][side].push(id));
}
$('curve-new').onclick=()=>editCurves(curves=>{curves.push({name:`${translate('曲线')} ${curves.length+1}`,type:'spline',source:[],target:[],count:8,closed:false});state.curveIndex=curves.length-1;$('tool').value='curves';});
$('curve-select').onchange=()=>{state.curveIndex=Number($('curve-select').value);$('tool').value='curves';update();};
$('curve-name').onchange=()=>{const name=$('curve-name').value;editCurves(curves=>{curves[state.curveIndex].name=name;});};
$('curve-count').onchange=()=>{const count=Number($('curve-count').value);editCurves(curves=>{curves[state.curveIndex].count=count;});};
$('curve-closed').onchange=()=>{const closed=$('curve-closed').checked;editCurves(curves=>{curves[state.curveIndex].closed=closed;});};
for(const side of ['source','target'])$(`curve-undo-${side}`).onclick=()=>editCurves(curves=>curves[state.curveIndex][side].pop());
$('curve-reverse').onclick=()=>editCurves(curves=>{const c=curves[state.curveIndex];c.target=c.closed?[c.target[0],...c.target.slice(1).reverse()].filter(x=>x!==undefined):c.target.slice().reverse();});
$('curve-delete').onclick=()=>editCurves(curves=>curves.splice(state.curveIndex,1));
$('curve-generate').onclick=async()=>{
  state.busy=true;update();
  try{const data=await api('curve-pairs',curveRequest(false));state.curvePaths=data.paths;state.curveSuggestion={...data,basePairs:curveBasePairs()};setText($('curve-info'),`预览 ${data.pairs.length} 对新采样点（S 编号）。采用后替换此前未手动修改的曲线点，保留普通点对；两侧“起”节点必须对应。`);status('曲线点已生成，请检查采样方向与位置。');}
  catch(error){state.curveSuggestion=null;setText($('curve-info'),error.message);status(error.message,true);}finally{state.busy=false;update();}
};
$('curve-apply').onclick=()=>{const data=state.curveSuggestion;if(!data)return;clearResult();state.pairs=[...data.basePairs,...data.pairs];state.curvePairs=data.pairs;changed();setText($('curve-info'),`已采用 ${data.pairs.length} 对曲线点，共 ${state.pairs.length} 对。曲线点可在普通列表中编辑，编辑后按普通点处理。`);status('曲线对应点已采用，可开始贴合。');update();};
$('curve-cancel').onclick=()=>{state.curveSuggestion=null;setText($('curve-info'),'已取消预览，现有点对未改变。');update();};
async function load(side,text,name){
  if(new TextEncoder().encode(text).length>18*1024*1024)throw new Error('单文件上限为 18 MB。');
  const data=await api('mesh',{text});
  if(side==='source'&&data.vertices.length>100000)throw new Error('模板上限为 100,000 顶点，请先简化模型。');
  clearResult();state[side]={...data,text,name};if(side==='source')state.brushWeights=null;state.curves=[];state.curvePairs=[];state.curvePaths=null;state.curveIndex=0;state.pairs=[];state.pending=null;state.edit=null;state.excludedFaces[side]=new Set();state.regionUndo=[];changed();
  setText($(`${side}-name`),name,true);setText($(`${side}-info`),`${data.vertices.length.toLocaleString()} 顶点 · ${data.faces.length.toLocaleString()} 三角面 · ${data.hasUV?'UV 就绪':'无完整 UV'}`);
  setMesh(side);fit(side);update();
}
for(const side of ['source','target'])$(side).addEventListener('change',async e=>{
  const file=e.target.files[0];if(!file)return;state.busy=true;update();status(`正在读取 ${file.name}…`);
  try{if(file.size>18*1024*1024)throw new Error('单文件上限为 18 MB。');await load(side,await file.text(),file.name);status('模型已载入。');}catch(error){status(error.message,true);}finally{state.busy=false;e.target.value='';update();}
});
$('undo').onclick=()=>{clearResult();if(state.pending!==null)state.pending=null;else state.pairs.pop();state.edit=null;changed();status('已撤销。');update();};
$('clear').onclick=()=>{clearResult();state.pairs=[];state.pending=null;state.edit=null;changed();status('已清空对应点。');update();};
$('reset').onclick=()=>{clearResult();changed();status('已恢复原始模板，保留对应点与排除区域。');update();};
$('cancel-edit').onclick=()=>{state.edit=null;status('已取消重选，原点对未改变。');update();};
$('tool').onchange=()=>{state.edit=null;update();};
$('undo-region').onclick=()=>{
  const action=state.regionUndo.at(-1),set=state.excludedFaces[action.side];
  if(!action.exclude){
    const protectedIds=new Set(state.pairs.flatMap(p=>pointSupport(state[action.side].faces,p[action.side==='source'?0:1])));if(action.side==='source'&&state.pending!==null)pointSupport(state.source.faces,state.pending).forEach(id=>protectedIds.add(id));
    for(const curve of state.curves)for(const point of curve[action.side])for(const id of pointSupport(state[action.side].faces,point))protectedIds.add(id);
    if(action.faces.some(i=>state[action.side].faces[i].some(id=>protectedIds.has(id)))){status('撤销会排除现有对应点或曲线节点，请先调整节点。',true);return;}
    if(action.side==='target'&&new Set([...set,...action.faces]).size===state.target.faces.length){status('撤销会排除全部目标面，无法执行。',true);return;}
  }
  clearResult();state.regionUndo.pop();
  for(const i of action.faces)if(action.exclude)set.delete(i);else set.add(i);
  state.curvePaths=null;changed();refreshExclusions(action.side);status('已撤销上一次区域操作。');update();
};
$('clear-regions').onclick=()=>{
  clearResult();state.excludedFaces={source:new Set(),target:new Set()};state.regionUndo=[];state.curvePaths=null;changed();
  refreshExclusions('source');refreshExclusions('target');status('已清空两侧排除区域。');update();
};
for(const id of ['iterations','smoothness','normal-angle','solver-mode'])$(id).onchange=()=>{clearResult();changed();update();};
$('wire').onchange=()=>{for(const v of Object.values(views))if(v.mesh)v.mesh.material.wireframe=$('wire').checked;};
$('fit').onclick=()=>{fit('source');fit('target');};
$('overlay').onchange=()=>{
  disposeMesh(views.source.overlay);views.source.overlay=null;
  if($('overlay').checked&&state.target){const mesh=new THREE.Mesh(geometry(state.target.vertices,state.target.faces),new THREE.MeshBasicMaterial({color:0x7d8796,transparent:true,opacity:.2,wireframe:true,depthWrite:false}));views.source.group.add(mesh);views.source.overlay=mesh;}
};
$('run').onclick=async()=>{
  clearResult();changed();
  state.busy=true;update();status($('solver-mode').value==='multistage'?'正在从粗到细求解，较大模型可能需要数分钟…':'正在单阶段求解，较大模型可能需要数分钟…');
  try{
    state.result=await api('wrap',{source:state.source.text,target:state.target.text,pairs:state.pairs,iterations:Number($('iterations').value),smoothness:Number($('smoothness').value),normalAngle:Number($('normal-angle').value),solverMode:$('solver-mode').value,excludedFaces:serializedExclusions()});changed();
    setMesh('source',state.result.vertices);fit('source');$('result-badge').hidden=false;
    const s=state.result.stats;const metrics=$('metrics');metrics.hidden=false;metrics.replaceChildren();
    for(const text of [`平均三角面距离　${s.initialMeanDistance.toPrecision(4)} → ${s.finalMeanDistance.toPrecision(4)}`,`对应点最大误差　${s.landmarkMaxError.toExponential(2)}`,`法线过滤 ${s.normalFilteredNearestVertices} 个最近匹配 · 防翻面限步 ${s.flipLimitedSteps} 次`,`${s.iterations}/${s.requestedIterations} 次迭代 · 顶点数与拓扑保留`]){const el=document.createElement('strong');setText(el,text);metrics.append(el);}
    showStages(s);
    status(s.stoppedByFlipGuard?'防翻面保护已提前停止迭代，保留最后安全结果；请检查对应点和局部形变。':'贴合完成。请旋转视图、叠加目标检查结果。');
  }catch(error){status(error.message,true);}finally{state.busy=false;update();}
};
function showStages(stats){
  const container=$('stage-results');container.replaceChildren();container.hidden=!stats.stages?.length;if(container.hidden)return;
  const table=document.createElement('table'),caption=document.createElement('caption');setText(caption,`${stats.solverMode==='multistage'?'多阶段':'单阶段'} · 总耗时 ${stats.totalSeconds.toFixed(2)} 秒 · 匹配查询 ${stats.correspondenceQueries.toLocaleString()} 点次`);table.append(caption);
  const header=document.createElement('tr');for(const text of ['阶段','控制点','匹配点','迭代','完整网格误差','耗时']){const th=document.createElement('th');setText(th,text);header.append(th);}table.append(header);
  for(const stage of stats.stages){const row=document.createElement('tr');for(const text of [stage.name+(stage.blockedByFlipGuard?'（保护限步）':''),stage.controlVertices.toLocaleString(),stage.sampleVertices.toLocaleString(),`${stage.iterations}/${stage.requestedIterations}`,`${stage.initialMeanDistance.toPrecision(3)} → ${stage.finalMeanDistance.toPrecision(3)}`,`${stage.seconds.toFixed(2)} 秒`]){const td=document.createElement('td');setText(td,text);row.append(td);}table.append(row);}container.append(table);
}
$('export').onclick=async()=>{
  state.busy=true;update();
  try{const data=await api('export',{source:state.source.text,vertices:state.result.vertices});download(data.text,state.source.name.replace(/\.obj$/i,'')+'_wrapped.obj','text/plain');status('已导出 OBJ，保留原始面和 UV。');}catch(error){status(error.message,true);}finally{state.busy=false;update();}
};
function serializedExclusions(){return {source:[...state.excludedFaces.source],target:[...state.excludedFaces.target]};}
function brushActive(){return Boolean(state.result&&brush.context&&!state.flowSuggestion&&!qualityUI?.inspecting&&$('brush-tool').value!=='navigate');}
function weightTool(){return ['weight-paint','weight-smooth'].includes($('brush-tool').value);}
function brushSettings(){const radiusPercent=Number($('brush-radius').value),strength=Number($('brush-strength').value);if(!Number.isFinite(radiusPercent)||radiusPercent<.2||radiusPercent>20||!Number.isFinite(strength)||strength<1||strength>100)throw Error('笔刷半径为 0.2%–20%，强度为 1–100。');return {radiusPercent,strength};}
function resetBrush(){
  if(brush.stroke)finishBrush(true);
  brush.context=null;brush.surface=null;brush.history=new StrokeHistory();brush.pointer=null;$('brush-tool').value='navigate';
  if(brush.cursor)brush.cursor.hidden=true;setText($('brush-info'),'完成贴合后，选择笔刷并在左侧拖动。');
}
function installBrush(view){
  const canvas=view.renderer.domElement,cursor=document.createElement('div');cursor.className='brush-cursor';cursor.hidden=true;view.el.append(cursor);brush.cursor=cursor;
  canvas.tabIndex=0;
  const pointer=e=>({x:e.clientX,y:e.clientY});
  canvas.addEventListener('pointerdown',e=>{
    if(!brushActive()||state.busy||e.button!==0||e.altKey)return;
    e.preventDefault();e.stopImmediatePropagation();
    try{brushSettings();}catch(error){status(error.message,true);return;}
    canvas.focus({preventScroll:true});const damping=view.controls.enableDamping;view.controls.enableDamping=false;view.controls.update();view.controls.enabled=false;brush.pointer=pointer(e);
    brush.stroke={pointerId:e.pointerId,kind:weightTool()?'weights':'geometry',before:new Map(),limited:0,lastClient:null,
      metadata:{dirty:state.dirty,damping,texture:state.result.texture,textureStats:state.result.textureStats,stats:state.result.stats,manualEdits:state.result.manualEdits,textureRefined:state.result.textureRefined,flowStats:state.result.flowStats,flowInfo:getSourceText($('flow-info')),
        metrics:$('metrics').cloneNode(true),stages:$('stage-results').cloneNode(true)}};
    canvas.setPointerCapture(e.pointerId);state.busy=true;update();
  },true);
  canvas.addEventListener('pointermove',e=>{
    if(!brushActive())return;brush.pointer=e.altKey?null:pointer(e);
    if(brush.stroke){e.preventDefault();e.stopImmediatePropagation();}
  },true);
  canvas.addEventListener('pointerup',e=>{
    if(!brush.stroke||brush.stroke.pointerId!==e.pointerId)return;
    e.preventDefault();e.stopImmediatePropagation();brush.pointer=pointer(e);
    try{const last=brush.stroke.lastClient;if(!last||Math.hypot(last.x-e.clientX,last.y-e.clientY)>2)stampBrush();finishBrush(false);}
    catch(error){finishBrush(true);status(error.message,true);}
  },true);
  canvas.addEventListener('pointercancel',e=>{if(brush.stroke?.pointerId===e.pointerId){e.stopImmediatePropagation();finishBrush(true);}},true);
  canvas.addEventListener('lostpointercapture',()=>{if(brush.stroke)finishBrush(true);});
  canvas.addEventListener('pointerleave',()=>{if(!brush.stroke){brush.pointer=null;cursor.hidden=true;}});
}
function brushHit(){
  if(!brush.pointer||!views.source.mesh)return null;
  const view=views.source,rect=view.renderer.domElement.getBoundingClientRect(),ray=new THREE.Raycaster();
  if(brush.pointer.x<rect.left||brush.pointer.x>rect.right||brush.pointer.y<rect.top||brush.pointer.y>rect.bottom)return null;
  view.camera.updateMatrixWorld(true);view.mesh.updateMatrixWorld(true);ray.setFromCamera(new THREE.Vector2((brush.pointer.x-rect.left)/rect.width*2-1,-(brush.pointer.y-rect.top)/rect.height*2+1),view.camera);
  return ray.intersectObject(view.mesh)[0]||null;
}
function syncBrushGeometry(change){
  const context=brush.context,view=views.source,g=view.mesh.geometry,position=g.attributes.position,normal=g.attributes.normal;
  for(const id of change.ids){const p=context.vertex(id);state.result.vertices[id]=p;if(g.index)position.setXYZ(id,...p);else for(const corner of context.corners[id])position.setXYZ(corner,...p);}
  for(const id of change.normals){const n=context.normal(id);if(g.index)normal.setXYZ(id,...n);else for(const corner of context.corners[id])normal.setXYZ(corner,...n);}
  position.needsUpdate=true;normal.needsUpdate=true;
  if(g.boundingSphere)g.boundingSphere.radius+=change.maxMovement||0;
  qualityUI?.clear(true,true);
}
function invalidateBrushOutputs(){
  if(state.result.textureRefined||state.result.flowStats)setText($('flow-info'),'几何已手动修改，先前纹理细化统计已失效。');
  const hadTexture=Boolean(state.result.texture);delete state.result.texture;delete state.result.textureStats;delete state.result.stats;delete state.result.textureRefined;delete state.result.flowStats;state.result.manualEdits=true;
  $('metrics').hidden=false;setText($('metrics'),'几何已手动修正，原求解误差与阶段统计已失效。');$('stage-results').hidden=true;
  if(hadTexture)setMesh('source',state.result.vertices);
  changed();
}
function stampBrush(){
  if(!brush.stroke||!brush.pointer)return;
  const hit=brushHit();brush.stroke.lastClient={...brush.pointer};if(!hit)return;
  const settings=brushSettings(),viewDirection=views.source.camera.position.clone().sub(hit.point).normalize().toArray();
  if(brush.stroke.kind==='weights'){
    const change=brush.context.paintWeights({face:hit.faceIndex,center:hit.point.toArray(),radius:brush.context.unit*settings.radiusPercent/100,strength:settings.strength/100,tool:$('brush-tool').value,target:Number($('weight-target').value)/100,viewDirection});
    change.ids.forEach((id,i)=>{if(!brush.stroke.before.has(id))brush.stroke.before.set(id,change.before[i]);});
    if(change.ids.length){changed();updateWeightColors(change.ids);}
    setText($('brush-info'),`本笔已修改 ${brush.stroke.before.size} 个顶点权重；几何保持不变。`);return;
  }
  const change=brush.context.stamp({face:hit.faceIndex,center:hit.point.toArray(),radius:brush.context.unit*settings.radiusPercent/100,strength:settings.strength/100,tool:$('brush-tool').value,viewDirection,surface:brush.surface,normalAngle:Number($('normal-angle').value)});
  if(change.scale<1)brush.stroke.limited++;
  brush.stroke.missed=(brush.stroke.missed||0)+(change.missed||0);
  if(!change.ids.length){setText($('brush-info'),change.scale===0?'防翻面保护阻止了该步，请减小强度。':change.missed?'未找到距离及法线合格的目标表面，可增大半径或检查法线方向。':'范围内没有变化：可能已贴面，或没有可移动顶点。');return;}
  change.ids.forEach((id,i)=>{if(!brush.stroke.before.has(id))brush.stroke.before.set(id,change.before[i]);});
  syncBrushGeometry(change);invalidateBrushOutputs();
  setText($('brush-info'),`本笔已修改 ${brush.stroke.before.size} 个顶点${brush.stroke.limited?' · 防翻面已限步':''}${change.missed?` · ${change.missed} 个顶点无合格投射`:''}`);
}
function finishBrush(cancel){
  const stroke=brush.stroke;if(!stroke)return;brush.stroke=null;
  try{
    if(stroke.kind==='weights'){
      if(cancel){const ids=[...stroke.before.keys()];brush.context.restoreWeights(ids,ids.map(id=>stroke.before.get(id)));state.dirty=stroke.metadata.dirty;updateWeightColors(ids);setText($('brush-info'),'已取消当前权重笔画。');}
      else{const recorded=brush.history.record(brush.context,stroke.before,'weights');setText($('brush-info'),recorded?`已绘制 ${stroke.before.size} 个顶点权重；可撤销 ${brush.history.undo.length} 笔。`:'本笔未改变权重。');}
    }else if(cancel){
      const ids=[...stroke.before.keys()],change=brush.context.restore(ids,ids.map(id=>stroke.before.get(id)));syncBrushGeometry(change);
      for(const key of ['texture','textureStats','stats','manualEdits','textureRefined','flowStats']){if(stroke.metadata[key]===undefined)delete state.result[key];else state.result[key]=stroke.metadata[key];}
      state.dirty=stroke.metadata.dirty;
      setText($('flow-info'),stroke.metadata.flowInfo);
      for(const [id,node] of [['metrics',stroke.metadata.metrics],['stage-results',stroke.metadata.stages]]){$(id).hidden=node.hidden;$(id).replaceChildren(...node.childNodes);}
      setMesh('source',state.result.vertices);setText($('brush-info'),'已取消当前笔画，恢复笔画前状态。');
    }else{
      const recorded=brush.history.record(brush.context,stroke.before);
      setText($('brush-info'),recorded?`已完成一笔，修改 ${stroke.before.size} 个顶点；可撤销 ${brush.history.undo.length} 笔。`:stroke.missed?'本笔未改变几何：未找到距离及法线合格的目标表面。':'本笔未改变几何。');
    }
    views.source.mesh.geometry.computeBoundingSphere();
  }finally{
    views.source.controls.enabled=true;views.source.controls.enableDamping=stroke.metadata.damping;state.busy=false;
    const canvas=views.source.renderer.domElement;if(canvas.hasPointerCapture(stroke.pointerId))canvas.releasePointerCapture(stroke.pointerId);
    status(cancel?'已取消当前笔画。':stroke.kind==='weights'?'权重绘制完成，几何和烘焙贴图保持不变。':'笔刷操作完成；几何变化后请重新烘焙贴图。');update();
  }
}
function processBrushFrame(time){
  if(!brushActive()){if(brush.cursor)brush.cursor.hidden=true;return;}
  if((state.busy&&!brush.stroke)||time-brush.lastTime<40)return;brush.lastTime=time;
  let hit;try{hit=brushHit();}catch{return;}
  if(!hit){brush.cursor.hidden=true;return;}
  try{
    const radius=brush.context.unit*brushSettings().radiusPercent/100,view=views.source,rect=view.renderer.domElement.getBoundingClientRect();
    const size=Math.max(3,radius*rect.height/(Math.tan(THREE.MathUtils.degToRad(view.camera.fov/2))*view.camera.position.distanceTo(hit.point)));
    brush.cursor.hidden=false;Object.assign(brush.cursor.style,{left:`${brush.pointer.x-rect.left}px`,top:`${brush.pointer.y-rect.top}px`,width:`${size}px`,height:`${size}px`});
    if(brush.stroke)stampBrush();
  }catch(error){if(brush.stroke)finishBrush(true);status(error.message,true);}
}
$('brush-tool').onchange=async()=>{
  if($('brush-tool').value!=='navigate')$('quality-local').checked=false;
  brush.pointer=null;if(brush.cursor)brush.cursor.hidden=true;
  if($('brush-tool').value==='navigate'){update();return;}
  if(!state.result){$('brush-tool').value='navigate';return;}
  if(!brush.context){
    state.busy=true;update();status('正在准备笔刷约束…');
    try{const data=await api('brush-reference',{source:state.source.text,target:state.target.text,pairs:state.pairs,vertices:state.result.vertices,excludedFaces:serializedExclusions()});brush.context=new BrushMesh(state.result.vertices,state.source.faces,data.reference,data.locked,data.unit,state.brushWeights);state.brushWeights=brush.context.weights;setText($('brush-info'),'笔刷就绪：在左侧按住左键修正。');status('笔刷就绪。');}
    catch(error){$('brush-tool').value='navigate';status(error.message,true);}
    finally{state.busy=false;update();}
  }else update();
  if(brush.context&&(weightTool()||$('show-weights').checked)){if(weightTool())$('show-weights').checked=true;setMesh('source',state.result.vertices);}
  if(brush.context&&['project','smooth-project'].includes($('brush-tool').value)&&!brush.surface){
    try{brush.surface=new TargetSurface(state.target.vertices,state.target.faces,[...state.excludedFaces.target],brush.context.unit);status('投射笔刷就绪，投射距离上限为当前笔刷半径。');}
    catch(error){$('brush-tool').value='navigate';status(error.message,true);update();}
  }
};
for(const id of ['brush-radius','brush-strength'])$(id).onchange=()=>{changed();};
$('show-weights').onchange=()=>{if(state.source)setMesh('source',state.result?.vertices);};
for(const [id,value] of [['weight-protect-all',0],['weight-edit-all',1]])$(id).onclick=async()=>{
  if(state.busy||!state.result)return;
  if(!brush.context){$('brush-tool').value='weight-paint';await $('brush-tool').onchange();}
  if(!brush.context)return;
  const before=new Map();for(let i=0;i<brush.context.n;i++)if(!brush.context.locked.has(i)&&brush.context.weights[i]!==value){before.set(i,brush.context.weights[i]);brush.context.weights[i]=value;}
  if(brush.history.record(brush.context,before,'weights'))changed();
  $('show-weights').checked=true;setMesh('source',state.result.vertices);setText($('brush-info'),`已设置 ${before.size} 个顶点权重为 ${value*100}%；硬锁定不变。`);update();
};
function historyBrush(direction){
  if(state.busy||!brush.context||!state.result||state.flowSuggestion)return;
  const change=brush.history.apply(brush.context,direction);if(!change)return;
  if(change.kind==='weights'){changed();updateWeightColors(change.ids);}
  else{syncBrushGeometry(change);invalidateBrushOutputs();views.source.mesh.geometry.computeBoundingSphere();}
  setText($('brush-info'),`可撤销 ${brush.history.undo.length} 笔 · 可重做 ${brush.history.redo.length} 笔`);status(change.kind==='weights'?'已恢复权重，几何和烘焙贴图保持不变。':direction==='undo'?'已撤销一笔，贴图仍需重新烘焙。':'已重做一笔。');update();
}
$('brush-undo').onclick=()=>historyBrush('undo');$('brush-redo').onclick=()=>historyBrush('redo');
window.addEventListener('keydown',e=>{
  if(e.key==='Escape'&&brush.stroke){e.preventDefault();finishBrush(true);return;}
  if(e.target instanceof Element&&e.target.closest('input,textarea,select,[contenteditable=true]'))return;
  if(!e.ctrlKey&&!e.metaKey)return;
  if(e.key.toLowerCase()==='z'&&brush.context){e.preventDefault();historyBrush(e.shiftKey?'redo':'undo');}
  else if(e.key.toLowerCase()==='y'&&brush.context){e.preventDefault();historyBrush('redo');}
});
window.addEventListener('blur',()=>{if(brush.stroke)finishBrush(true);});
function bakeSettings(){return {resolution:Number($('bake-resolution').value),padding:Number($('bake-padding').value),distanceRatio:Number($('bake-distance').value)/100};}
function clearBakedTexture(){
  if(state.result){delete state.result.texture;delete state.result.textureStats;}
  if(state.source)setMesh('source',state.result?.vertices);
}
function invalidateFlowTextureStats(){if(state.result?.textureRefined){delete state.result.flowStats;setText($('flow-info'),'输入贴图已变化，先前纹理统计失效；细化几何保留。');}}
for(const side of ['source','target']){
  $(`${side}-texture`).onchange=async e=>{
    const file=e.target.files[0];if(!file)return;
    state.busy=true;update();status('正在读取贴图…');
    try{
      if(!state[side]?.hasUV)throw new Error('模型需要完整 UV 才能显示贴图。');
      if(file.size>8*1024*1024)throw new Error('输入贴图上限为 8 MB。');
      const dataUrl=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=()=>reject(new Error('无法读取图片。'));reader.readAsDataURL(file);});
      const texture=await api('texture',{name:file.name,dataUrl});
      state[side].texture=texture;invalidateFlowTextureStats();clearBakedTexture();setMesh(side,side==='source'?state.result?.vertices:undefined);changed();status('贴图已载入；之前的烘焙结果已清除，模型贴合结果保留。');
    }catch(error){status(error.message,true);}finally{state.busy=false;e.target.value='';update();}
  };
  $(`remove-${side}-texture`).onclick=()=>{delete state[side].texture;invalidateFlowTextureStats();clearBakedTexture();setMesh(side,side==='source'?state.result?.vertices:undefined);changed();status('已移除贴图并清除旧烘焙结果。');update();};
}
for(const id of ['show-textures','unlit-textures'])$(id).onchange=()=>{for(const side of ['source','target'])if(state[side])setMesh(side,side==='source'?state.result?.vertices:undefined);};
for(const id of ['bake-resolution','bake-padding','bake-distance'])$(id).onchange=()=>{clearBakedTexture();changed();update();};
$('bake').onclick=async()=>{
  clearBakedTexture();changed();state.busy=true;update();status('正在烘焙纹理，高分辨率可能需要数分钟…');
  try{
    const settings=bakeSettings();
    const result=await api('bake',{source:state.source.text,target:state.target.text,vertices:state.result.vertices,targetTexture:state.target.texture,...settings,normalAngle:Number($('normal-angle').value),excludedFaces:serializedExclusions()});
    state.result.texture=result.texture;state.result.textureStats=result.stats;$('show-textures').checked=true;setMesh('source',state.result.vertices);changed();
    status(`纹理烘焙完成，覆盖率 ${(result.stats.coverage*100).toFixed(1)}%；未匹配区域为透明。`);
  }catch(error){status(error.message,true);}finally{state.busy=false;update();}
};
$('export-texture').onclick=async()=>{
  try{const blob=await(await fetch(state.result.texture.dataUrl)).blob();download(blob,state.source.name.replace(/\.obj$/i,'')+'_baked.png','image/png');status('已导出模板 UV 贴图 PNG。');}catch(error){status(error.message,true);}
};
$('export-textured-model').onclick=async()=>{
  state.busy=true;update();
  try{
    const response=await fetch('/api/texture-export',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({source:state.source.text,vertices:state.result.vertices,texture:state.result.texture})});
    if(!response.ok)throw new Error((await response.json()).error||'导出失败。');
    download(await response.blob(),state.source.name.replace(/\.obj$/i,'')+'_textured.zip','application/zip');status('已导出 OBJ、MTL、颜色贴图和透明度贴图，解压后一起使用。');
  }catch(error){status(error.message,true);}finally{state.busy=false;update();}
};
function projectData(){
  return {format:'facewrap-lite',version:state.pairs.some(p=>p.some(x=>!Number.isInteger(x)))||state.pending!==null&&!Number.isInteger(state.pending)||state.curves.some(c=>c.type==='spline')?2:1,curves:state.curves,curvePairs:currentCurvePairs(),brushWeights:state.brushWeights?Array.from(state.brushWeights):null,models:Object.fromEntries(['source','target'].map(side=>[side,state[side]?{name:state[side].name,text:state[side].text,texture:state[side].texture}:null])),
    pairs:state.pairs,pending:state.pending,excludedFaces:serializedExclusions(),settings:{iterations:Number($('iterations').value),smoothness:Number($('smoothness').value),normalAngle:Number($('normal-angle').value),solverMode:$('solver-mode').value,bake:bakeSettings(),brush:brushSettings(),flow:flowSettings()},result:state.result?{vertices:state.result.vertices,texture:state.result.texture,manualEdits:Boolean(state.result.manualEdits),textureRefined:Boolean(state.result.textureRefined)}:null};
}
$('save-project').onclick=async()=>{
  state.busy=true;update();
  try{const project=projectData();const text=JSON.stringify(project);if(new TextEncoder().encode(text).length>96*1024*1024)throw new Error('工程超过 96 MB，无法保存。');await api('project',project);download(text,(state.source?.name||state.target.name).replace(/\.obj$/i,'')+'.facewrap.json');state.dirty=false;status('工程已下载，包含模型、贴图、点对、排除区域、参数和当前结果。');}catch(error){status(error.message,true);}finally{state.busy=false;update();}
};
$('open-project').onclick=()=>$('project-file').click();
$('project-file').onchange=async e=>{
  const file=e.target.files[0];if(!file)return;
  if(state.dirty&&!confirm(translate('打开工程将替换当前未保存的工作，是否继续？'))){e.target.value='';return;}
  state.busy=true;update();status('正在检查工程文件…');
  try{
    if(file.size>96*1024*1024)throw new Error('工程文件上限为 96 MB。');
    let input;try{input=JSON.parse(await file.text());}catch{throw new Error('工程文件不是有效的 JSON。');}
    const project=await api('project',input);health.undo=null;
    clearResult();state.autoSuggestion=null;state.autoMessage='尚未自动检测';state.source=project.models.source;state.target=project.models.target;state.brushWeights=project.brushWeights?Float64Array.from(project.brushWeights):null;state.pairs=project.pairs;state.pending=project.pending;state.edit=null;state.regionUndo=[];
    state.excludedFaces={source:new Set(project.excludedFaces.source),target:new Set(project.excludedFaces.target)};state.result=project.result;
    state.curves=project.curves;state.curvePairs=project.curvePairs;state.curveIndex=0;state.curvePaths=null;
    if(state.curves.length){try{state.curvePaths=(await api('curve-pairs',curveRequest(true))).paths;}catch(error){setText($('curve-info'),`曲线已恢复，路径需检查：${error.message}`);}}
    $('iterations').value=project.settings.iterations;
    $('normal-angle').value=project.settings.normalAngle;
    $('solver-mode').value=project.settings.solverMode;
    $('brush-radius').value=project.settings.brush.radiusPercent;$('brush-strength').value=project.settings.brush.strength;
    for(const [key,id] of Object.entries(flowInputs))$(id).value=project.settings.flow[key];
    setText($('flow-info'),state.result?.textureRefined?'已恢复纹理细化结果；重新计算可查看本次统计。':'尚未进行纹理细化。');
    $('bake-resolution').value=project.settings.bake.resolution;$('bake-padding').value=project.settings.bake.padding;$('bake-distance').value=project.settings.bake.distanceRatio*100;
    const smooth=String(project.settings.smoothness);if(![...$('smoothness').options].some(o=>o.value===smooth))$('smoothness').add(new Option(`自定义 ${smooth}`,smooth));$('smoothness').value=smooth;
    $('tool').value='points';
    for(const side of ['source','target']){
      if(state[side]){const m=state[side];setText($(`${side}-name`),m.name,true);setText($(`${side}-info`),`${m.vertices.length.toLocaleString()} 顶点 · ${m.faces.length.toLocaleString()} 三角面 · ${m.hasUV?'UV 就绪':'无完整 UV'}`);setMesh(side,side==='source'?state.result?.vertices:undefined);fit(side);}
      else{disposeMesh(views[side].mesh);views[side].mesh=null;refreshExclusions(side);views[side].el.querySelector('.placeholder').hidden=false;setText($(`${side}-name`),'选择 OBJ 文件');setText($(`${side}-info`),side==='source'?'保留此模型的拓扑和 UV':'模板将贴合此模型的表面');}
    }
    $('result-badge').hidden=!state.result;
    if(state.result){$('metrics').hidden=false;setText($('metrics'),state.result.textureRefined?'已恢复纹理细化结果；本次未重算纹理统计，可继续检查、烘焙或导出。':state.result.manualEdits?'已恢复手动修正结果；原求解统计已失效，可继续修正或导出。':'已恢复保存的结果；尚未按当前质量约束重新验证，重新计算后显示误差和保护指标。');}
    state.dirty=false;status(`已打开工程：${file.name}`);
  }catch(error){status(`打开失败：${error.message}；当前工程未替换。`,true);}finally{state.busy=false;e.target.value='';update();}
};
window.addEventListener('beforeunload',e=>{if(state.dirty){e.preventDefault();e.returnValue='';}});
const flowInputs={resolution:'flow-resolution',views:'flow-views',iterations:'flow-iterations',strength:'flow-strength',distancePercent:'flow-distance'};
function flowSettings(){
  const s=Object.fromEntries(Object.entries(flowInputs).map(([key,id])=>[key,Number($(id).value)]));
  if(![256,384,512].includes(s.resolution)||![1,3].includes(s.views)||!Number.isInteger(s.iterations)||s.iterations<1||s.iterations>5||!Number.isFinite(s.strength)||s.strength<1||s.strength>100||!Number.isFinite(s.distancePercent)||s.distancePercent<.1||s.distancePercent>10)throw Error('纹理细化参数超出允许范围。');
  return s;
}
function updateFlowControls(){
  const pending=Boolean(state.flowSuggestion),ready=state.result&&state.source?.hasUV&&state.target?.hasUV&&state.source?.texture&&state.target?.texture;
  $('flow-run').disabled=state.busy||pending||!ready;$('flow-apply').disabled=state.busy||!pending;$('flow-cancel').disabled=state.busy||!pending;
  for(const id of Object.values(flowInputs))$(id).disabled=state.busy||pending;
  if(pending){
    for(const id of ['run','reset','export','export-texture','export-textured-model','bake','brush-tool','brush-radius','brush-strength','brush-undo','brush-redo','weight-target','show-weights','weight-protect-all','weight-edit-all','source','target','demo','iterations','smoothness','normal-angle','solver-mode','open-project','project-file','source-texture','target-texture','remove-source-texture','remove-target-texture','health-current','health-file','health-undo','undo','clear','undo-region','clear-regions','tool','point-mode','region-size','cancel-edit'])$(id).disabled=true;
    for(const button of $('pairs').querySelectorAll('button'))button.disabled=true;
    setText($('phase'),'纹理细化预览');setText($('instruction'),'左侧显示候选几何；采用后才替换结果，取消保留原结果。此时保存工程仍保存原结果。');
  }
}
function discardFlowPreview(){
  if(!state.flowSuggestion)return;
  state.flowSuggestion=null;
  if(state.flowUi&&state.result){$('metrics').hidden=state.flowUi.metrics;$('stage-results').hidden=state.flowUi.stages;}
  state.flowUi=null;if(state.source)setMesh('source',state.result?.vertices);
}
function flowSummary(s){return `纹理灰度残差 ${s.beforePhotoError.toFixed(2)} → ${s.afterPhotoError.toFixed(2)} · ${s.matchedVertices} 个匹配顶点 · ${s.views} 视图 · ${s.iterations} 次迭代 · ${s.seconds.toFixed(2)} 秒${s.flipLimitedSteps?' · 防翻面已限步':''}`;}
for(const id of Object.values(flowInputs))$(id).onchange=()=>{changed();};
$('flow-run').onclick=async()=>{
  state.busy=true;update();status('正在渲染纹理并计算双向光流…');
  try{
    const settings=flowSettings();views.source.controls.update();views.source.camera.updateMatrixWorld(true);
    const data=await api('flow-refine',{source:state.source.text,target:state.target.text,vertices:state.result.vertices,pairs:state.pairs,excludedFaces:serializedExclusions(),brushWeights:state.brushWeights?Array.from(state.brushWeights):null,sourceTexture:state.source.texture,targetTexture:state.target.texture,cameraWorld:views.source.camera.matrixWorld.toArray(),normalAngle:Number($('normal-angle').value),settings});
    state.flowUi={metrics:$('metrics').hidden,stages:$('stage-results').hidden};state.flowSuggestion=data;$('metrics').hidden=true;$('stage-results').hidden=true;
    setMesh('source',data.vertices);setText($('flow-info'),'预览：'+flowSummary(data.stats)+'。请旋转检查后采用；原结果尚未替换。');status('纹理细化预览已生成。');
  }catch(error){setText($('flow-info'),error.message);status(error.message,true);}finally{state.busy=false;update();}
};
$('flow-cancel').onclick=()=>{discardFlowPreview();setText($('flow-info'),'已取消纹理细化预览，原结果和贴图保持不变。');status('已取消纹理细化预览。');update();};
$('flow-apply').onclick=()=>{
  const data=state.flowSuggestion;if(!data)return;state.flowSuggestion=null;state.flowUi=null;resetBrush();
  state.result={vertices:data.vertices,manualEdits:Boolean(state.result.manualEdits),textureRefined:true,flowStats:data.stats};changed();setMesh('source',data.vertices);
  $('metrics').hidden=false;setText($('metrics'),'已采用纹理细化；原几何求解统计与烘焙贴图已失效。');$('stage-results').hidden=true;setText($('flow-info'),flowSummary(data.stats)+'。已采用，请重新烘焙贴图。');status('已采用纹理细化，保留拓扑、UV、硬点和软权重。');update();
};
function healthButtons(){
  $('health-close').disabled=state.busy;$('health-preview').disabled=state.busy||!health.report?.hasIssues||Boolean(health.repair);
  for(const id of ['health-original','health-download','health-apply'])$(id).disabled=state.busy||!health.repair;
}
function showHealthReport(after=false){
  health.after=after;const report=after?health.repair.report:health.report;if(!report)return;
  $('health-viewport').hidden=false;
  const labels={nonManifoldEdges:'非流形边',nonManifoldVertices:'非流形顶点',invalidFaces:'无效/重复原始面',duplicateFaces:'其中重复三角面',isolatedVertices:'孤立点',invalidVertices:'无效顶点',inconsistentEdges:'绕序冲突边',invalidUVs:'无效 UV / 引用'};
  const list=$('health-counts');list.replaceChildren();
  for(const [key,label] of Object.entries(labels)){const el=document.createElement('div');setText(el,`${label}：${after?`${health.report.counts[key]} → `:''}${report.counts[key]}`);list.append(el);}
  setText($('health-status'),`${after?'修复预览':'原始诊断'} · ${report.vertexCount.toLocaleString()} 顶点 · ${report.triangleCount.toLocaleString()} 个有效三角面${report.hasIssues?' · 检测到问题':' · 所列问题为 0'}。${after?'当前工程尚未替换。':''}`);
  const details=$('health-details');details.replaceChildren();for(const item of report.details){const li=document.createElement('li');setText(li,`原文件第 ${item.line} 行：${item.reason}`);details.append(li);}
  if(report.detailsOmitted){const li=document.createElement('li');setText(li,`另有 ${report.detailsOmitted} 条记录未列出。`);details.append(li);}
  health.viewer||=new MeshReview($('health-viewport'));health.viewer.show(report);
  setText($('health-original'),after?'查看原始':'查看修复后');healthButtons();
}
async function inspectHealth(text,name,fromCurrent){
  health.text=text;health.name=name;health.side=$('health-side').value;health.fromCurrent=fromCurrent;health.report=null;health.repair=null;health.after=false;
  setText($('health-title'),`${health.side==='source'?'模板':'目标'}诊断 · ${name}`);setText($('health-status'),'正在检查网格…');$('health-counts').replaceChildren();$('health-details').replaceChildren();$('health-viewport').hidden=true;
  setText($('health-impact'),`应用修复将替换${health.side==='source'?'模板':'目标'}，清空点对、曲线、排除区和贴合结果${health.side==='source'?'，并重置模板软权重':''}。可撤销一次；开始其他编辑后撤销失效。原文件不会被覆盖。`);
  $('health-dialog').showModal();state.busy=true;healthButtons();update();
  try{health.report=await api('mesh-diagnose',{text});showHealthReport();}
  catch(error){setText($('health-status'),error.message);}
  finally{state.busy=false;healthButtons();update();}
}
$('health-side').onchange=()=>update();
$('health-current').onclick=()=>{const m=state[$('health-side').value];if(m)inspectHealth(m.text,m.name,true);};
$('health-file').onclick=()=>$('health-upload').click();
$('health-upload').onchange=async e=>{const file=e.target.files[0];if(!file)return;try{if(file.size>18*1024*1024)throw Error('诊断 OBJ 文件上限为 18 MB。');await inspectHealth(await file.text(),file.name,false);}catch(error){status(error.message,true);}finally{e.target.value='';}};
$('health-dialog').addEventListener('cancel',e=>{if(state.busy)e.preventDefault();});
$('health-close').onclick=()=>$('health-dialog').close();
$('health-preview').onclick=async()=>{
  state.busy=true;healthButtons();update();setText($('health-status'),'正在生成修复预览…');
  try{health.repair=await api('mesh-repair',{text:health.text,side:health.side});showHealthReport(true);
    if(!health.repair.mesh.hasUV)appendText($('health-impact'),' 修复后没有完整 UV，不保留该侧贴图。');
  }catch(error){setText($('health-status'),`无法生成修复结果：${error.message}`);}finally{state.busy=false;healthButtons();update();}
};
$('health-original').onclick=()=>showHealthReport(!health.after);
$('health-download').onclick=()=>download(health.repair.text,health.name.replace(/\.obj$/i,'')+'_repaired.obj','text/plain');
const repairStateKeys=['source','target','pairs','pending','result','edit','excludedFaces','regionUndo','dirty','autoSuggestion','autoMessage','brushWeights','curves','curvePairs','curvePaths','curveIndex'];
function rebuildModelsAfterRepair(){
  for(const side of ['source','target']){
    const m=state[side];
    if(m){setText($(`${side}-name`),m.name,true);setText($(`${side}-info`),`${m.vertices.length.toLocaleString()} 顶点 · ${m.faces.length.toLocaleString()} 三角面 · ${m.hasUV?'UV 就绪':'无完整 UV'}`);setMesh(side,side==='source'?state.result?.vertices:undefined);fit(side);}
    else{disposeMesh(views[side].mesh);views[side].mesh=null;refreshExclusions(side);views[side].el.querySelector('.placeholder').hidden=false;setText($(`${side}-name`),'选择 OBJ 文件');setText($(`${side}-info`),side==='source'?'保留此模型的拓扑和 UV':'模板将贴合此模型的表面');}
  }
  $('result-badge').hidden=!state.result;if(state.result){$('metrics').hidden=false;setText($('metrics'),'已恢复修复前结果；重新计算可刷新误差统计。');}
  if(state.result?.textureRefined)setText($('flow-info'),state.result.flowStats?flowSummary(state.result.flowStats):'已恢复纹理细化结果；统计未重算。');
  update();
}
$('health-apply').onclick=()=>{
  if(!health.repair||state.busy)return;
  const snapshot=structuredClone(Object.fromEntries(repairStateKeys.map(key=>[key,state[key]]))),side=health.side,old=state[side];
  clearResult();state[side]={...health.repair.mesh,text:health.repair.text,name:health.name.replace(/\.obj$/i,'')+'_repaired.obj'};
  if(health.fromCurrent&&old?.texture&&state[side].hasUV)state[side].texture=old.texture;
  if(side==='source')state.brushWeights=null;
  state.pairs=[];state.pending=null;state.edit=null;state.curves=[];state.curvePairs=[];state.curvePaths=null;state.curveIndex=0;state.autoSuggestion=null;state.autoMessage='网格已修复，请重新检测或选择对应点。';
  state.excludedFaces={source:new Set(),target:new Set()};state.regionUndo=[];changed();health.undo=snapshot;
  setText($('curve-info'),'网格已修复，请重新建立曲线。');$('health-dialog').close();rebuildModelsAfterRepair();status('已应用修复；点对等约束已清空，可撤销上次修复。');
};
$('health-undo').onclick=()=>{const snapshot=health.undo;if(!snapshot||state.busy)return;clearResult();Object.assign(state,snapshot);changed();setText($('curve-info'),'已恢复修复前曲线与点对。');rebuildModelsAfterRepair();status('已恢复修复前工程；笔刷撤销历史未恢复。');};
function demoMesh(target=false){
  const vertices=[],faces=[],rows=28,cols=40;
  // A closed, asymmetric head-like surface with identical topology in both demo models.
  for(let i=0;i<=rows;i++)for(let j=0;j<cols;j++){
    const theta=Math.PI*(i+.15)/(rows+.3),phi=2*Math.PI*j/cols;
    let x=Math.sin(theta)*Math.cos(phi)*.8,y=Math.cos(theta)*1.2,z=Math.sin(theta)*Math.sin(phi)*.72;
    z+=.28*Math.exp(-((x/.22)**2+(y/.32)**2))*Math.max(0,Math.sin(phi));
    if(target){x*=1.13+.07*y;y=y*1.08+.08*x*x;z=z*1.07+.09*Math.exp(-(((y-.3)/.3)**2));x+=.2;y+=.1;}
    vertices.push([x,y,z]);
  }
  const top=vertices.push(target?[.2,1.396,.000001]:[0,1.2,0])-1;
  const bottom=vertices.push(target?[.2,-1.196,.000001]:[0,-1.2,0])-1;
  for(let i=0;i<rows;i++)for(let j=0;j<cols;j++){const a=i*cols+j,b=i*cols+(j+1)%cols,c=a+cols,d=b+cols;faces.push([a,b,c],[b,d,c]);}
  for(let j=0;j<cols;j++){faces.push([top,(j+1)%cols,j]);faces.push([bottom,rows*cols+j,rows*cols+(j+1)%cols]);}
  const uv=[];
  for(const face of faces){
    const corners=face.map(id=>id<top?[id%cols/cols,1-(Math.floor(id/cols)+.15)/(rows+.3)]:null);
    const known=corners.filter(Boolean);
    if(Math.max(...known.map(p=>p[0]))-Math.min(...known.map(p=>p[0]))>.5)for(const p of known)if(p[0]<.5)p[0]+=1;
    corners.forEach((p,i)=>uv.push(p||[known.reduce((s,p)=>s+p[0],0)/known.length,face[i]===top?1:0]));
  }
  return {text:vertices.map(p=>'v '+p.join(' ')).concat(uv.map(p=>'vt '+p.join(' ')),faces.map((f,i)=>'f '+f.map((id,j)=>`${id+1}/${i*3+j+1}`).join(' '))).join('\n'),ids:[4*cols+10,9*cols+5,9*cols+15,14*cols+10,20*cols+7,20*cols+13,14*cols+30]};
}
function demoTexture(){
  const canvas=document.createElement('canvas');canvas.width=canvas.height=512;const ctx=canvas.getContext('2d');
  for(let y=0;y<16;y++)for(let x=0;x<16;x++){ctx.fillStyle=(x+y)%2?'#548991':'#ecd4ad';ctx.fillRect(x*32,y*32,32,32);}
  return {name:'demo_checker.png',dataUrl:canvas.toDataURL('image/png')};
}
$('demo').onclick=async()=>{
  if((state.source||state.target)&&!confirm(translate('载入演示会替换当前模型和对应点，是否继续？')))return;
  state.busy=true;update();status('正在载入演示…');
  try{const a=demoMesh(),b=demoMesh(true);await load('source',a.text,'demo_template.obj');await load('target',b.text,'demo_target.obj');state.target.texture=await api('texture',demoTexture());setMesh('target');state.pairs=a.ids.map(i=>[i,i]);status('演示已载入，包含 UV、扫描棋盘贴图和 7 对点；贴合后可烘焙纹理。');}catch(error){status(error.message,true);}finally{state.busy=false;update();}
};
try{views.source=setupView('source',0xa8afb9);views.target=setupView('target',0x7d8796);
  qualityUI=new QualityUI({api,
    readiness:()=>({source:state.source,target:state.target,result:state.result,busy:state.busy,preview:Boolean(state.flowSuggestion),exclusions:serializedExclusions(),normalAngle:Number($('normal-angle').value)}),
    setBusy:value=>{state.busy=value;update();},
    paint:()=>{if(state.source)setMesh('source',state.result?.vertices);},
    enterInspection:()=>{$('brush-tool').value='navigate';brush.pointer=null;if(brush.cursor)brush.cursor.hidden=true;},
    focus:id=>{const view=views.source,point=new THREE.Vector3().fromArray(state.result.vertices[id]),offset=point.clone().sub(view.controls.target);view.camera.position.add(offset);view.controls.target.copy(point);view.controls.update();}
  });
  batchUI=new BatchUI({api,download,
    readiness:()=>({busy:state.busy,source:Boolean(state.source),target:Boolean(state.target),result:Boolean(state.result),flowReady:Boolean(state.source?.hasUV&&state.source?.texture),paired:state.pairs.length>=3,blocked:Boolean(state.flowSuggestion||state.autoSuggestion||state.curveSuggestion||state.pending!==null||state.edit!==null)}),
    setBusy:value=>{if(state.busy!==value){state.busy=value;update();}},
    getConstraints:()=>api('batch-constraints',{source:state.source.text,target:state.target.text,name:state.target.name,pairs:state.pairs,excludedFaces:serializedExclusions()}),
    getSnapshot:async (useCurrent,bake,flow,temporal)=>{
      const source={name:state.source.name,text:state.source.text};
      if(useCurrent){const exported=await api('export',{source:state.source.text,vertices:state.result.vertices});source.text=exported.text;source.name=source.name.replace(/\.obj$/i,'')+'_current.obj';}
      let flowSnapshot=null;
      if(flow){if(!state.source.hasUV||!state.source.texture)throw Error('批量光流需要模板完整 UV 和原始参考贴图。');views.source.controls.update();views.source.camera.updateMatrixWorld(true);flowSnapshot={settings:flowSettings(),cameraWorld:views.source.camera.matrixWorld.toArray(),brushWeights:state.brushWeights?Array.from(state.brushWeights):null,sourceTexture:{...state.source.texture}};}
      return {source,temporal:temporal?{...temporal,brushWeights:state.brushWeights?Array.from(state.brushWeights):null}:null,flow:flowSnapshot,bake:bake?bakeSettings():null,useCurrentResult:useCurrent,referenceTarget:state.target?.text,pairs:state.pairs.map(p=>[...p]),excludedSourceFaces:[...state.excludedFaces.source],excludedTargetFaces:[...state.excludedFaces.target],settings:{iterations:Number($('iterations').value),smoothness:Number($('smoothness').value),normalAngle:Number($('normal-angle').value),solverMode:$('solver-mode').value}};
    }});update();batchUI.resume();
  function animate(time=performance.now()){requestAnimationFrame(animate);processBrushFrame(time);for(const v of Object.values(views)){v.controls.update();v.renderer.render(v.scene,v.camera);v.labels.render(v.scene,v.camera);}if($('health-dialog').open)health.viewer?.render();}animate();
}catch(error){status(`三维视图初始化失败：${error.message}`,true);}

