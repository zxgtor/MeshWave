import test from 'node:test';
import assert from 'node:assert/strict';
import {pointPosition,pointFromHit,pointKey,pointSupport,samePoint} from '../web/surface-points.mjs';
const v=[[0,0,0],[1,0,0],[1,1,0],[0,1,0]],f=[[0,1,2],[0,2,3]];
test('picking and deformed markers use the exact triangle interior',()=>{
 const p=pointFromHit(v,f,0,[.7,.4,0]);
 assert.equal(p.face,0);pointPosition(v,f,p).forEach((x,i)=>assert.ok(Math.abs(x-[.7,.4,0][i])<1e-12));
 const bent=v.map((p,i)=>[...p.slice(0,2),i]);
 assert.ok(Math.abs(pointPosition(bent,f,p)[2]-1.1)<1e-12);
 assert.deepEqual(pointSupport(f,p),[0,1,2]);
});
test('shared-edge aliases and vertex aliases compare equal without changing topology',()=>{
 assert.ok(samePoint(f,{face:0,bary:[.5,0,.5]},{face:1,bary:[.5,.5,0]}));
 assert.equal(pointKey(f,0),pointKey(f,{face:0,bary:[1,0,0]}));
 assert.notEqual(pointKey(f,{face:0,bary:[.2,.3,.5]}),pointKey(f,{face:0,bary:[.3,.2,.5]}));
});
