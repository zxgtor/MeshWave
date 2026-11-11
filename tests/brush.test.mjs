import test from 'node:test';
import assert from 'node:assert/strict';
import {BrushMesh,StrokeHistory} from '../web/brush.mjs';
import {TargetSurface} from '../web/target-surface.mjs';

test('weights scale all five geometry tools after the movement cap, with zero protection exact',()=>{
  const {v,f}=grid(21,(x,y)=>.04*Math.exp(-((x-.5)**2+(y-.5)**2)/.004));
  const surface=new TargetSurface(grid().v,f);
  for(const tool of ['pull','push','smooth','project','smooth-project']){
    const contexts=[0,.5,1].map(w=>new BrushMesh(v,f,v,[221],1,v.map(()=>w)));
    const before=Array.from(contexts[0].positions);
    for(const c of contexts)apply(c,tool,{center:[.5,.5,.04],surface});
    assert.deepEqual(Array.from(contexts[0].positions),before);
    const full=contexts[2].vertex(220),half=contexts[1].vertex(220);
    assert.ok(Math.hypot(...full.map((x,j)=>x-v[220][j]))>0);
    for(let j=0;j<3;j++)assert.ok(Math.abs(half[j]-v[220][j]-(full[j]-v[220][j])*.5)<1e-12);
    for(const c of contexts){assert.deepEqual(c.vertex(221),v[221]);assert.ok(c.minimumRatio()>=.01);}
  }
});

test('weight painting has radial falloff, skips locks and disconnected sheets, and never edits geometry',()=>{
  const {v,f}=grid(),n=v.length,vertices=[...v,...v.map(p=>[p[0],p[1],-.001])],faces=[...f,...f.map(t=>t.map(i=>i+n))];
  const c=new BrushMesh(vertices,faces,vertices,[221]),before=Array.from(c.positions);
  const r=c.paintWeights({face:420,center:[.5,.5,0],radius:.2,strength:1,tool:'weight-paint',target:0,viewDirection:[0,0,1]});
  assert.equal(c.weights[220],0);assert.ok(c.weights[219]>0&&c.weights[219]<1);assert.equal(c.weights[221],1);assert.equal(c.weights[0],1);assert.ok(r.ids.every(id=>id<n));assert.ok(Array.from(c.weights.slice(n)).every(w=>w===1));assert.deepEqual(Array.from(c.positions),before);
  c.paintWeights({face:420,center:[.5,.5,0],radius:.2,strength:1,tool:'weight-paint',target:.7});assert.ok(Math.abs(c.weights[220]-.7)<1e-12);
});

test('weight smoothing and mixed geometry/weight history restore exact values',()=>{
  const {v,f}=grid(),c=new BrushMesh(v,f,v,[221]),history=new StrokeHistory(),positions=Array.from(c.positions);c.weights[220]=0;
  const initial=Array.from(c.weights),r=c.paintWeights({face:420,center:[.5,.5,0],radius:.2,strength:.5,tool:'weight-smooth'});
  assert.ok(c.weights[220]>0&&c.weights[220]<1);assert.equal(c.weights[221],1);assert.deepEqual(Array.from(c.positions),positions);
  history.record(c,new Map(r.ids.map((id,i)=>[id,r.before[i]])),'weights');const painted=Array.from(c.weights);
  const g=apply(c);history.record(c,new Map(g.ids.map((id,i)=>[id,g.before[i]])));const edited=Array.from(c.positions);
  history.apply(c,'undo');assert.deepEqual(Array.from(c.positions),positions);assert.deepEqual(Array.from(c.weights),painted);
  history.apply(c,'undo');assert.deepEqual(Array.from(c.weights),initial);
  history.apply(c,'redo');assert.deepEqual(Array.from(c.weights),painted);history.apply(c,'redo');assert.deepEqual(Array.from(c.positions),edited);
});

test('invalid vertex weights and paint parameters are rejected',()=>{
  const {v,f}=grid();for(const weights of [[0],v.map(()=>NaN),v.map(()=>1.1)])assert.throws(()=>new BrushMesh(v,f,v,[],1,weights));
  const c=new BrushMesh(v,f,v);for(const target of [-1,NaN,2])assert.throws(()=>c.paintWeights({face:420,center:[.5,.5,0],radius:.2,strength:1,tool:'weight-paint',target}));
});
function grid(side=21,z=()=>0){
  const v=[],f=[];for(let y=0;y<side;y++)for(let x=0;x<side;x++)v.push([x/(side-1),y/(side-1),z(x/(side-1),y/(side-1))]);
  for(let y=0;y<side-1;y++)for(let x=0;x<side-1;x++){const a=y*side+x;f.push([a,a+1,a+side+1],[a,a+side+1,a+side]);}
  return {v,f};
}
function apply(context,tool='pull',extra={}){return context.stamp({face:420,center:[.5,.5,0],radius:.2,strength:1,tool,viewDirection:[0,0,1],...extra});}
test('push/pull are local, preserve locked vertices, and have opposite signs',()=>{
  const {v,f}=grid(),locked=[220,221],a=new BrushMesh(v,f,v,locked,1),b=new BrushMesh(v,f,v,locked,1);
  const pulled=apply(a),pushed=apply(b,'push');assert.ok(pulled.ids.length>4);assert.deepEqual(pulled.ids,pushed.ids);
  for(const id of pulled.ids){assert.ok(a.vertex(id)[2]>0);assert.ok(b.vertex(id)[2]<0);assert.ok(Math.hypot(v[id][0]-.5,v[id][1]-.5)<.2);}
  for(const id of locked)assert.deepEqual(a.vertex(id),v[id]);
  for(let i=0;i<v.length;i++)if(!pulled.ids.includes(i))assert.deepEqual(a.vertex(i),v[i]);
  assert.ok(a.minimumRatio()>=.01);assert.ok(b.minimumRatio()>=.01);
});
test('geodesic brush never touches an overlaid disconnected sheet',()=>{
  const {v,f}=grid(),n=v.length;const vertices=[...v,...v.map(p=>[p[0],p[1],p[2]-.001])],faces=[...f,...f.map(t=>t.map(i=>i+n))];
  const context=new BrushMesh(vertices,faces,vertices,[],1);const result=apply(context);
  assert.ok(result.ids.length);assert.ok(result.ids.every(i=>i<n));for(let i=n;i<vertices.length;i++)assert.deepEqual(context.vertex(i),vertices[i]);
});
test('smooth brush reduces a local bump without touching locked/outside vertices',()=>{
  const {v,f}=grid(21,(x,y)=>.04*Math.exp(-((x-.5)**2+(y-.5)**2)/.004));
  const context=new BrushMesh(v,f,v,[221],1),before=context.vertex(220)[2];
  for(let i=0;i<10;i++)apply(context,'smooth',{center:[.5,.5,.04]});
  assert.ok(context.vertex(220)[2]<before);assert.deepEqual(context.vertex(221),v[221]);assert.deepEqual(context.vertex(0),v[0]);assert.ok(context.minimumRatio()>=.01);
});
test('guard catches endpoint flips and collapse hidden inside a positive endpoint',()=>{
  const v=[[0,0,0],[1,0,0],[0,1,0]],context=new BrushMesh(v,[[0,1,2]],v,[],1);
  for(const deltas of [new Map([[2,[0,-2,0]]]),new Map([[1,[-2,0,0]],[2,[0,-2,0]]])]){const scale=context.safeScale(deltas);assert.ok(scale>0&&scale<.5);}
});
test('stroke history restores exact coordinates, supports redo, and clears redo on new stroke',()=>{
  const {v,f}=grid(),context=new BrushMesh(v,f,v,[],1),history=new StrokeHistory(),beforeAll=Array.from(context.positions),before=new Map();
  for(let i=0;i<3;i++){const result=apply(context);result.ids.forEach((id,j)=>{if(!before.has(id))before.set(id,result.before[j]);});}
  assert.equal(history.record(context,before),true);const edited=Array.from(context.positions);
  history.apply(context,'undo');assert.deepEqual(Array.from(context.positions),beforeAll);
  history.apply(context,'redo');assert.deepEqual(Array.from(context.positions),edited);
  history.apply(context,'undo');const next=apply(context,'push');history.record(context,new Map(next.ids.map((id,i)=>[id,next.before[i]])));assert.equal(history.redo.length,0);
});
test('fully locked brushes and no-op smoothing do not create history',()=>{
  const {v,f}=grid(),context=new BrushMesh(v,f,v,v.map((_,i)=>i),1);assert.equal(apply(context).ids.length,0);
  const history=new StrokeHistory();assert.equal(history.record(context,new Map()),false);
});

test('target query finds triangle interiors and edges, respects distance, winding and exclusions',()=>{
  const v=[[0,0,0],[1,0,0],[0,1,0],[0,0,.02],[1,0,.02],[0,1,.02]],f=[[0,1,2],[3,5,4]];
  const s=new TargetSurface(v,f);
  assert.deepEqual(s.query([.2,.2,.019],[0,0,1],.1,.5),[.2,.2,0]);
  assert.equal(s.query([.2,.2,.019],[0,0,1],.01,.5),null);
  assert.ok(Math.hypot(...s.query([-.01,.2,.01],[0,0,1],.1,.5).map((x,i)=>x-[0,.2,0][i]))<1e-14);
  assert.equal(new TargetSurface(v,f,[0]).query([.2,.2,.019],[0,0,1],.1,.5),null);
  assert.throws(()=>new TargetSurface(v,f,[0,1]));
});

test('projection reduces surface distance with exact locks, undo and redo',()=>{
  const {v,f}=grid(),edited=v.map(p=>[p[0],p[1],.025]),s=new TargetSurface(v,f),ctx=new BrushMesh(edited,f,v,[221],1),h=new StrokeHistory();
  const initial=Array.from(ctx.positions),r=apply(ctx,'project',{center:[.5,.5,.025],surface:s});
  assert.ok(r.ids.length>0);assert.ok(ctx.vertex(220)[2]<.025);assert.deepEqual(ctx.vertex(221),edited[221]);assert.deepEqual(ctx.vertex(0),edited[0]);
  h.record(ctx,new Map(r.ids.map((id,i)=>[id,r.before[i]])));const after=Array.from(ctx.positions);
  h.apply(ctx,'undo');assert.deepEqual(Array.from(ctx.positions),initial);h.apply(ctx,'redo');assert.deepEqual(Array.from(ctx.positions),after);assert.ok(ctx.minimumRatio()>=.01);
});

test('surface smoothing relaxes uneven spacing while preserving a planar target',()=>{
  const {v,f}=grid();v[220][0]+=.02;
  const s=new TargetSurface(grid().v,f),ctx=new BrushMesh(v,f,v,[221],1),initial=ctx.vertex(220)[0];
  for(let i=0;i<6;i++)apply(ctx,'smooth-project',{center:[.52,.5,0],surface:s});
  assert.ok(ctx.vertex(220)[0]<initial);assert.equal(ctx.vertex(220)[2],0);assert.deepEqual(ctx.vertex(221),v[221]);assert.deepEqual(ctx.vertex(0),v[0]);assert.ok(ctx.minimumRatio()>=.01);
});

test('projection never moves vertices toward excluded, reversed or distant surfaces',()=>{
  const {v,f}=grid(),edited=v.map(p=>[p[0],p[1],.025]);
  for(const tool of ['project','smooth-project'])for(const s of [new TargetSurface(v,f.map(t=>[t[0],t[2],t[1]])),new TargetSurface(v.map(p=>[p[0],p[1],-1]),f)]){
    const ctx=new BrushMesh(edited,f,v,[],1),before=Array.from(ctx.positions),r=apply(ctx,tool,{center:[.5,.5,.025],surface:s});
    assert.equal(r.ids.length,0);assert.ok(r.missed>0);assert.deepEqual(Array.from(ctx.positions),before);
  }
  const excluded=new TargetSurface(v,f,f.map((_,i)=>i).filter(i=>i!==0)),ctx=new BrushMesh(edited,f,v,[],1);
  assert.equal(apply(ctx,'project',{center:[.5,.5,.025],surface:excluded}).ids.length,0);
});

test('BVH queries match exhaustive triangle queries across branches and transformed scales',()=>{
  const {v,f}=grid(7,(x,y)=>.03*Math.sin(x*5)*Math.cos(y*3));
  for(const scale of [.001,1000]){
    const points=v.map(p=>p.map(x=>x*scale+123)),s=new TargetSurface(points,f,[],scale);
    for(let i=0;i<12;i++){
      const p=[123+scale*(i+.3)/13,123+scale*.45,123+scale*.1],q=s.query(p,[0,0,1],scale,.5);
      let best=null,d=Infinity;
      for(const triangle of f){const r=new TargetSurface(points,[triangle],[],scale).query(p,[0,0,1],scale,.5);if(r){const next=Math.hypot(...r.map((x,j)=>x-p[j]));if(next<d){d=next;best=r;}}}
      assert.ok(Math.hypot(...q.map((x,j)=>x-best[j]))<scale*1e-9);
    }
  }
});


test('following regions skip projection but retain smooth deformation and undo',()=>{
  const {v,f}=grid(21,(x,y)=>.04*Math.exp(-((x-.5)**2+(y-.5)**2)/.004));
  const surface=new TargetSurface(grid().v,f),follow=[220];
  const c=new BrushMesh(v,f,v,[],1,null,follow);
  const before=c.vertex(220);apply(c,'project',{center:before,surface});
  assert.deepEqual(c.vertex(220),before);
  const history=new StrokeHistory(),all=new Map([...Array(c.n).keys()].map(i=>[i,c.vertex(i)]));
  const changed=apply(c,'smooth-project',{center:before,surface});
  assert.ok(changed.ids.includes(220));assert.ok(c.vertex(220)[2]<before[2]);
  history.record(c,all);history.apply(c,'undo');assert.deepEqual(c.vertex(220),before);
});
