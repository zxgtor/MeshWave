// Pure geometry kernel: no DOM, WebGL, network, or changes to topology/UVs.
const cross=(a,b)=>[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];
const dot=(a,b)=>a[0]*b[0]+a[1]*b[1]+a[2]*b[2];
const sub=(a,b)=>[a[0]-b[0],a[1]-b[1],a[2]-b[2]];
const length=a=>Math.hypot(...a);
const normalize=a=>{const n=length(a);return n>1e-30?a.map(x=>x/n):[0,0,0];};
class Heap {
  constructor(){this.items=[];}
  push(value){const a=this.items;let i=a.length;a.push(value);while(i){const p=(i-1)>>1;if(a[p][0]<=value[0])break;a[i]=a[p];i=p;}a[i]=value;}
  pop(){const a=this.items,top=a[0],last=a.pop();if(a.length){let i=0;while(i*2+1<a.length){let j=i*2+1;if(j+1<a.length&&a[j+1][0]<a[j][0])j++;if(a[j][0]>=last[0])break;a[i]=a[j];i=j;}a[i]=last;}return top;}
}
export class BrushMesh {
  constructor(vertices,faces,reference,locked=[],unit=1,weights=null,unfitted=[]){
    this.positions=Float64Array.from(vertices.flat());this.faces=faces.map(f=>[...f]);this.unit=unit;
    this.unfitted=new Set(unfitted);this.locked=new Set(locked);this.n=vertices.length;
    if(weights&&(weights.length!==this.n||Array.from(weights).some(x=>!Number.isFinite(x)||x<0||x>1)))throw Error('笔刷权重必须与模板顶点一一对应，范围为 0–1。');
    this.weights=weights?Float64Array.from(weights):new Float64Array(this.n).fill(1);
    this.corners=Array.from({length:this.n},()=>[]);const neighbors=Array.from({length:this.n},()=>new Set());
    faces.forEach((f,i)=>{for(let j=0;j<3;j++){const id=f[j];this.corners[id].push(i*3+j);neighbors[id].add(f[(j+1)%3]);neighbors[id].add(f[(j+2)%3]);}});
    this.neighbors=neighbors.map(s=>Int32Array.from(s));
    this.referenceNormals=new Float64Array(faces.length*3);this.referenceArea=new Float64Array(faces.length);
    this.faceCross=new Float64Array(faces.length*3);this.normalSums=new Float64Array(this.n*3);
    for(let i=0;i<faces.length;i++){
      const f=faces[i],a=sub(reference[f[1]],reference[f[0]]).map(x=>x/unit),b=sub(reference[f[2]],reference[f[0]]).map(x=>x/unit),c=cross(a,b),size=length(c);
      if(size<=1e-14)throw Error('模板包含零面积面，无法启用笔刷。');
      this.referenceArea[i]=size;this.referenceNormals.set(c.map(x=>x/size),i*3);this.updateFace(i);
    }
    if(this.minimumRatio()<.01-1e-9)throw Error('当前结果不满足防翻面约束，请重新贴合。');
    this.distances=new Float64Array(this.n);this.distances.fill(Infinity);this.touched=[];
  }
  vertex(id){return Array.from(this.positions.subarray(id*3,id*3+3));}
  normal(id){return normalize(Array.from(this.normalSums.subarray(id*3,id*3+3)));}
  vector(face){const f=this.faces[face];return cross(sub(this.vertex(f[1]),this.vertex(f[0])).map(x=>x/this.unit),sub(this.vertex(f[2]),this.vertex(f[0])).map(x=>x/this.unit));}
  updateFace(face){
    const old=this.faceCross.subarray(face*3,face*3+3),next=this.vector(face);
    for(const id of this.faces[face])for(let j=0;j<3;j++)this.normalSums[id*3+j]+=next[j]-old[j];
    this.faceCross.set(next,face*3);
  }
  incident(ids){const faces=new Set();for(const id of ids)for(const corner of this.corners[id])faces.add(Math.floor(corner/3));return faces;}
  refresh(ids){const normals=new Set();for(const f of this.incident(ids)){this.updateFace(f);for(const id of this.faces[f])normals.add(id);}return [...normals];}
  minimumRatio(){let minimum=Infinity;for(let f=0;f<this.faces.length;f++)minimum=Math.min(minimum,dot(this.vector(f),this.referenceNormals.subarray(f*3,f*3+3))/this.referenceArea[f]);return minimum;}
  neighborhood(face,center,radius,viewDirection=null){
    for(const id of this.touched)this.distances[id]=Infinity;this.touched=[];
    const heap=new Heap(),result=[];
    const sign=viewDirection?(dot(this.faceCross.subarray(face*3,face*3+3),viewDirection)>=0?1:-1):1;
    const allowed=id=>!this.locked.has(id)&&(!viewDirection||dot(this.normal(id),viewDirection)*sign>.05);
    const add=(id,d)=>{if(d>radius||d>=this.distances[id]||!allowed(id))return;if(this.distances[id]===Infinity)this.touched.push(id);this.distances[id]=d;heap.push([d,id]);};
    for(const id of this.faces[face])add(id,length(sub(this.vertex(id),center)));
    while(heap.items.length){const [distance,id]=heap.pop();if(distance!==this.distances[id])continue;result.push([id,distance]);const position=this.vertex(id);for(const next of this.neighbors[id])add(next,distance+length(sub(this.vertex(next),position)));}
    return result;
  }
  safeScale(deltas){
    const coefficients=[];
    for(const face of this.incident(deltas.keys())){
      const f=this.faces[face],p=f.map(id=>this.vertex(id)),d=f.map(id=>(deltas.get(id)||[0,0,0]).map(x=>x/this.unit));
      const e1=sub(p[1],p[0]).map(x=>x/this.unit),e2=sub(p[2],p[0]).map(x=>x/this.unit),d1=sub(d[1],d[0]),d2=sub(d[2],d[0]),normal=this.referenceNormals.subarray(face*3,face*3+3),area=this.referenceArea[face];
      const c=dot(cross(e1,e2),normal)/area,a=dot(cross(d1,d2),normal)/area;
      const u=cross(d1,e2),v=cross(e1,d2),b=dot(u.map((x,j)=>x+v[j]),normal)/area;
      coefficients.push([a,b,c]);
    }
    let scale=1;
    for(let attempt=0;attempt<22;attempt++,scale*=.5){
      const valid=coefficients.every(([a,b,c])=>{let value=Math.min(c,a*scale*scale+b*scale+c);if(a>1e-30){const t=Math.max(0,Math.min(scale,-b/(2*a)));value=Math.min(value,a*t*t+b*t+c);}return value>=.01;});
      if(valid)return scale;
    }return 0;
  }
  paintWeights({face,center,radius,strength,tool,target=0,viewDirection=null}){
    if(!['weight-paint','weight-smooth'].includes(tool)||!Number.isFinite(target)||target<0||target>1||!Number.isFinite(radius)||radius<=0||!Number.isFinite(strength)||strength<=0||strength>1)throw Error('权重绘制参数无效。');
    const ids=[],before=[],after=[];
    for(const [id,distance] of this.neighborhood(face,center,radius,viewDirection)){
      const value=this.weights[id],goal=tool==='weight-smooth'?Array.from(this.neighbors[id]).reduce((s,i)=>s+this.weights[i],0)/this.neighbors[id].length:target;
      let next=value+(goal-value)*strength*(1-(distance/radius)**2)**2;
      if(next<1e-8)next=0;else if(next>1-1e-8)next=1;
      if(next!==value){ids.push(id);before.push(value);after.push(next);}
    }
    this.restoreWeights(ids,after);return {kind:'weights',ids,before};
  }
  restoreWeights(ids,values){for(let i=0;i<ids.length;i++)this.weights[ids[i]]=values[i];return {kind:'weights',ids:Array.from(ids)};}
  stamp({face,center,radius,strength,tool,viewDirection=null,surface=null,normalAngle=60}){
    if(!['pull','push','smooth','project','smooth-project'].includes(tool)||!Number.isFinite(radius)||radius<=0||!Number.isFinite(strength)||strength<=0||strength>1)throw Error('笔刷参数无效。');
    const projecting=tool==='project'||tool==='smooth-project';
    if(projecting&&(!surface||!Number.isFinite(normalAngle)||normalAngle<10||normalAngle>89))throw Error('投射目标或法线夹角无效。');
    const deltas=new Map();let missed=0;
    for(const [id,distance] of this.neighborhood(face,center,radius,viewDirection)){
      if(this.weights[id]===0)continue;
      const falloff=(1-(distance/radius)**2)**2;let delta;
      if(tool==='smooth'||tool==='smooth-project'){
        const average=[0,0,0];for(const next of this.neighbors[id]){const p=this.vertex(next);for(let j=0;j<3;j++)average[j]+=p[j];}
        delta=sub(average.map(x=>x/this.neighbors[id].length),this.vertex(id)).map(x=>x*.3*(tool==='smooth-project'?1:strength*falloff));
      }else delta=this.normal(id).map(x=>x*radius*.035*strength*falloff*(tool==='pull'?1:-1));
      if(projecting&&this.unfitted.has(id)){
        if(tool==='project')continue;
        delta=delta.map(x=>x*strength*falloff);
      }else if(projecting){
        const p=this.vertex(id),normal=this.normal(id),cosine=Math.cos(normalAngle*Math.PI/180);
        // Reject an out-of-range starting vertex before relaxing it toward another sheet.
        const anchor=surface.query(p,normal,radius,cosine);
        if(!anchor){missed++;continue;}
        const q=tool==='project'?anchor:surface.query(p.map((x,j)=>x+delta[j]),normal,radius,cosine);
        if(!q||length(sub(q,p))>radius){missed++;continue;}
        delta=sub(q,p).map(x=>x*strength*falloff);
      }
      const size=length(delta),cap=radius*.04*strength;if(size>cap)delta=delta.map(x=>x*cap/size);
      delta=delta.map(x=>x*this.weights[id]);
      if(length(delta)>this.unit*1e-12)deltas.set(id,delta);
    }
    if(!deltas.size)return {ids:[],normals:[],before:[],scale:1,maxMovement:0,missed};
    const scale=this.safeScale(deltas);if(scale<1e-6)return {ids:[],normals:[],before:[],scale:0,maxMovement:0};
    const ids=[...deltas.keys()],before=ids.map(id=>this.vertex(id));let maxMovement=0;
    for(const [id,delta] of deltas){maxMovement=Math.max(maxMovement,length(delta)*scale);for(let j=0;j<3;j++)this.positions[id*3+j]+=delta[j]*scale;}
    return {ids,normals:this.refresh(ids),before,scale,maxMovement,missed};
  }
  restore(ids,values){for(let i=0;i<ids.length;i++)this.positions.set(values.subarray?values.subarray(i*3,i*3+3):values[i],ids[i]*3);return {ids:Array.from(ids),normals:this.refresh(ids),maxMovement:0};}
}

export class StrokeHistory {
  constructor(limit=20,bytes=32*1024*1024){this.limit=limit;this.byteLimit=bytes;this.undo=[];this.redo=[];}
  record(context,before,kind='geometry'){
    const weights=kind==='weights';
    const ids=[...before.keys()].filter(id=>weights?before.get(id)!==context.weights[id]:before.get(id).some((x,j)=>x!==context.positions[id*3+j]));
    if(!ids.length)return false;
    const entry={kind,ids:Int32Array.from(ids),before:Float64Array.from(ids.flatMap(id=>before.get(id))),after:Float64Array.from(ids.flatMap(id=>weights?context.weights[id]:context.vertex(id)))};
    this.redo=[];this.undo.push(entry);
    const size=e=>e.ids.byteLength+e.before.byteLength+e.after.byteLength;
    while(this.undo.length>this.limit||(this.undo.length>1&&this.undo.reduce((s,e)=>s+size(e),0)>this.byteLimit))this.undo.shift();
    return true;
  }
  apply(context,direction){const from=direction==='undo'?this.undo:this.redo,to=direction==='undo'?this.redo:this.undo;if(!from.length)return null;const entry=from.pop();const values=entry[direction==='undo'?'before':'after'];const update=entry.kind==='weights'?context.restoreWeights(entry.ids,values):context.restore(entry.ids,values);to.push(entry);return update;}
}
