import test from 'node:test';
import assert from 'node:assert/strict';
import {summarizeQuality,qualityColor,buildQualityGraph,qualityRegion} from '../web/fit-quality.mjs';

test('quality statistics exclude nulls, keep normal issues separate, and use strict threshold exceedance',()=>{
  const report={distances:[0,1,2,null],normalAngles:[0,70,null,null],normalAngle:60};
  const s=summarizeQuality(report,1);
  assert.equal(s.count,3);assert.equal(s.above,1);assert.equal(s.mean,1);
  assert.equal(s.rms,Math.sqrt(5/3));assert.equal(s.median,1);assert.equal(s.p95,1.9);
  assert.equal(s.max,2);assert.equal(s.worst,2);assert.equal(s.normalMismatch,1);assert.equal(s.normalUnknown,1);
  assert.equal(summarizeQuality(report,1,[0,3]).count,1);
  assert.deepEqual(summarizeQuality(report,1,[3]),{count:0,worst:null});
});
test('local selection follows edges, cannot cross disconnected sheets or excluded bridges',()=>{
  const v=[[0,0,0],[1,0,0],[0,1,0],[0,0,.001],[1,0,.001],[0,1,.001],[2,0,0]];
  const f=[[0,1,2],[3,4,5],[1,2,6]];
  let graph=buildQualityGraph(v,f,v.map(()=>0));
  assert.deepEqual(qualityRegion(graph,0,.5),[0]);
  assert.deepEqual(new Set(qualityRegion(graph,0,3)),new Set([0,1,2,6]));
  graph=buildQualityGraph(v,f,[0,null,null,0,0,0,0]);
  assert.deepEqual(qualityRegion(graph,0,10),[0]);
});
test('heat colors clamp to a fixed threshold, distinguish omitted vertices and optional normal issues',()=>{
  assert.deepEqual(qualityColor(0,1,0,60),[.04,.25,.85]);
  assert.deepEqual(qualityColor(1,1,0,60),qualityColor(100,1,0,60));
  assert.deepEqual(qualityColor(null,1,180,60,true),[.24,.26,.29]);
  assert.deepEqual(qualityColor(0,1,180,60,true),[.65,.12,.85]);
  assert.notDeepEqual(qualityColor(0,1,180,60),qualityColor(0,1,180,60,true));
});
