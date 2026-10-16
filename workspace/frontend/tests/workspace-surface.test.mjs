// Deterministic geometry/focus contracts; real top-layer and native Tab checks remain required.
import { test } from "node:test";
import assert from "node:assert/strict";
import { build } from "esbuild";
const built = await build({ entryPoints: ["src/lib/workspace-surface.ts"], bundle: true,
  write: false, platform: "node", format: "esm" });
const { containModalTab, workspaceSurface, releaseSurface } = await import("data:text/javascript;base64," + Buffer.from(built.outputFiles[0].text).toString("base64"));

function modalTabFixture() {
  const owner = {activeElement:null,defaultView:{getComputedStyle:item=>({visibility:item.hidden?"hidden":"visible"})}};
  const control = (name, disabled=false, hidden=false) => ({name,tabIndex:0,hidden,
    matches:()=>disabled,closest:()=>null,getClientRects:()=>[{}],focus(){owner.activeElement=this;}});
  const first=control("first"),middle=control("middle"),last=control("last");
  const dialog={open:true,ownerDocument:owner,matches:()=>true,
    querySelectorAll:()=>[first,control("disabled",true),middle,control("hidden",false,true),last]};
  const press=(target,shiftKey=false,key="Tab")=>{owner.activeElement=target;let prevented=false;
    containModalTab(dialog,{key,shiftKey,preventDefault(){prevented=true;}});return prevented;};
  return {owner,dialog,first,middle,last,press};
}
test("modal boundary Tab wraps in both directions past disabled and hidden controls",()=>{
  const f=modalTabFixture();assert.equal(f.press(f.last),true);assert.equal(f.owner.activeElement,f.first);
  assert.equal(f.press(f.first,true),true);assert.equal(f.owner.activeElement,f.last);
});
test("interior Tab and unrelated keys preserve the browser's native behavior",()=>{
  const f=modalTabFixture();assert.equal(f.press(f.middle),false);assert.equal(f.press(f.middle,true),false);
  assert.equal(f.press(f.last,false,"Escape"),false);
});
test("nonmodal sheets and closed dialogs never trap document navigation",()=>{
  const f=modalTabFixture();f.dialog.matches=()=>false;assert.equal(f.press(f.last),false);
  f.dialog.matches=()=>true;f.dialog.open=false;assert.equal(f.press(f.last),false);
});
test("desktop sheets stay below the toolbar and above the actual composer", () => {
  const s = workspaceSurface({left:0, top:0, width:1280, height:800}, 74, 680);
  assert.equal(s.mode, "sheet"); assert.equal(s.top,82); assert.equal(s.top+s.height,672);
  assert.equal(s.left+s.width,1272);
});
test("390px uses an explicit focused full-height modal alternative", () => {
  const s = workspaceSurface({left:0, top:0, width:390, height:844},62, 640);
  assert.deepEqual(s,{mode:"modal",left:8,top:8,width:374,height:828});
});
test("a short workspace does not squeeze a sheet over the composer", () => {
  const s = workspaceSurface({left:0, top:0, width:1280, height:400},74,220);
  assert.equal(s.mode,"modal"); assert.equal(s.height,384);
});
test("large attachment/error composers trigger the same modal alternative", () => {
  assert.equal(workspaceSurface({left:0,top:0,width:1000,height:800},74,300).mode,"modal");
});
test("visual viewport offsets and keyboard height constrain fallback bounds", () => {
  const v={left:140,top:180,width:500,height:350};const s=workspaceSurface(v,240,440);
  assert.equal(s.mode,"modal");assert.equal(s.left,148);assert.equal(s.top,188);
  assert.equal(s.left+s.width,632);assert.equal(s.top+s.height,522);
});
function focusFixture() {
  const events=[];const owner={body:{},activeElement:null,other:null,
    querySelector(){return this.other;},getElementById(id){return this[id]??null;}};
  const element=(name,visible=true)=>({name,isConnected:true,getClientRects:()=>visible?[{}]:[],closest:()=>null,
    focus(){owner.activeElement=this;events.push("focus:"+name);}});
  const trigger=element("trigger"), inside=element("inside"),outside=element("outside");
  const dialog={open:true,inert:false,contains:node=>node===inside,
    close(){events.push("close");this.open=false;owner.activeElement=trigger;}};
  owner.activeElement=inside;
  return {events,owner,element,trigger,inside,outside,dialog};
}
test("modal release closes the native top layer and makes retained controls inert", () => {
  const f=focusFixture();releaseSurface(f.dialog,f.trigger,true,f.owner);
  assert.equal(f.dialog.open,false);assert.equal(f.dialog.inert,true);assert.equal(f.owner.activeElement,f.trigger);
  assert.equal(f.events[0],"close");
});
test("outside-click dismissal preserves a control that already acquired focus", () => {
  const f=focusFixture();f.owner.activeElement=f.outside;releaseSurface(f.dialog,f.trigger,false,f.owner);
  assert.equal(f.owner.activeElement,f.outside);
});
test("an opening replacement dialog prevents explicit restoration over its input", () => {
  const f=focusFixture();f.owner.other={};f.owner.activeElement=f.outside;
  releaseSurface(f.dialog,f.trigger,true,f.owner);assert.equal(f.owner.activeElement,f.outside);
});
test("a deleted invoker uses a surviving visible control", () => {
  const f=focusFixture();f.trigger.isConnected=false;f.owner["new-session"]=f.element("new");
  releaseSurface(f.dialog,f.trigger,true,f.owner);assert.equal(f.owner.activeElement,f.owner["new-session"]);
});
test("a hidden mobile rail fallback yields to the visible prompt", () => {
  const f=focusFixture();f.trigger.isConnected=false;f.owner["new-session"]=f.element("new",false);f.owner.prompt=f.element("prompt");
  releaseSurface(f.dialog,f.trigger,true,f.owner);assert.equal(f.owner.activeElement,f.owner.prompt);
});
