import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {navConnection,springStep,navGapTarget} from '../workspace/ui/portfolio-nav.mjs';
import {openingCell,sampleCell,retargetCell,arrivedFront} from '../workspace/ui/flight-kernel.mjs';
import {soundChoice,soundEligible} from '../workspace/ui/interface-audio.mjs';

test('ported seam matches the pinned original geometry',()=>{
  const source=fs.readFileSync(new URL('./fixtures/navConnection.ts',import.meta.url),'utf8').replace(/:\s*number/g,'').replace('export function','function');
  const context=vm.createContext({});vm.runInContext(source+';this.reference=navConnection;',context);
  for(const gap of [-1,-.5,0,.2,1,2,4,10,20]){
    const original=context.reference(gap,40,12,20), actual=navConnection(gap,40,12,20);
    assert.equal(actual.path,original.path);assert.equal(actual.corner,original.corner);assert.equal(actual.coverage,original.coverage);
  }
});
test('spring reverses without resetting position or velocity',()=>{
  let state={value:-1,velocity:0};for(let i=0;i<8;i++)state=springStep(state.value,state.velocity,20,1/60);
  const reversal=springStep(state.value,state.velocity,-1,0);
  assert.ok(Math.abs(reversal.value-state.value)<1e-10);assert.ok(Math.abs(reversal.velocity-state.velocity)<1e-10);
  for(let i=0;i<180;i++)state=springStep(state.value,state.velocity,-1,1/60);
  assert.ok(Math.abs(state.value+1)<1e-8);assert.ok(Math.abs(state.velocity)<1e-8);
});
test('emission cohorts are born over time and share exact settled coverage',()=>{
  const source={left:100,width:100,bottom:44},target={left:20,top:60,width:40,height:40};
  const cells=[];for(let y=0;y<40;y+=4)for(let x=0;x<40;x+=4)cells.push(openingCell(cells.length,x,y,4,4,source,target));
  const early=cells.map(c=>sampleCell(c,.04));assert.ok(early.some(p=>p.born));assert.ok(early.some(p=>!p.born));assert.equal(arrivedFront(cells,early,40),0);
  const settled=cells.map(c=>sampleCell(c,1));assert.equal(arrivedFront(cells,settled,40),40);assert.ok(settled.every(p=>p.arrived&&p.a===1));
});
test('reversal preserves sampled position velocity alpha and birth eligibility',()=>{
 const c=openingCell(7,4,4,4,4,{left:100,width:100,bottom:44},{left:20,top:60,width:40,height:40});
 for(const t of [.04,.16,.35,.9]){const p=sampleCell(c,t),reverse=retargetCell(c,p,t,{x:120,y:44},false),q=sampleCell(reverse,t);for(const key of ['x','y','vx','vy','a'])assert.ok(Math.abs(p[key]-q[key])<1e-8,`${key} at ${t}`);assert.equal(q.born,p.born);if(!p.born)assert.equal(sampleCell(reverse,t+.2).a,0);}
});
test('synthetic and disabled activations never play sound',()=>{
  const button={disabled:false,getAttribute:()=>null};
  assert.equal(soundEligible({isTrusted:false},button),false);assert.equal(soundEligible({isTrusted:true},{...button,disabled:true}),false);
  assert.equal(soundEligible({isTrusted:true},button),true);assert.equal(soundChoice('close-dialog'),'soft-close');assert.equal(soundChoice('files'),'soft-press');
});

test('retargeting an already opaque tile keeps it opaque through resize',()=>{
 const cell=openingCell(1,4,4,4,4,{left:100,width:80,bottom:44},{left:20,top:60,width:40,height:40});
 const pose=sampleCell(cell,.2);assert.equal(pose.a,1);
 const retargeted=retargetCell(cell,pose,.2,{x:200,y:100},true);
 for(const time of [.2,.3,.5,.64])assert.equal(sampleCell(retargeted,time).a,1);
});

test('Settings opens both adjacent seams in the four-action source bar',()=>{assert.deepEqual([0,1,2,3].map(i=>navGapTarget(i,2)),[0,-1,20,20]);assert.deepEqual([0,1,2,3].map(i=>navGapTarget(i,-1)),[0,-1,-1,-1]);});
