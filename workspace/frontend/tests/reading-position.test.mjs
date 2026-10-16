// Controlled hook lifecycle fixture. Native reading/streaming still needs browser verification.
import { test, afterEach } from "node:test";
import assert from "node:assert/strict";
import { build } from "esbuild";
const built=await build({entryPoints:["src/lib/use-reading-position.ts"],bundle:true,write:false,platform:"node",format:"esm",
  plugins:[{name:"controlled-hooks",setup(build){build.onResolve({filter:/^react$/},()=>({path:"react",namespace:"fixture"}));
    build.onLoad({filter:/.*/,namespace:"fixture"},()=>({contents:"export const useLayoutEffect=(...a)=>globalThis.__readingHooks.effect(...a),useRef=(...a)=>globalThis.__readingHooks.ref(...a),useState=(...a)=>globalThis.__readingHooks.state(...a);"}));}}]});
const {useReadingPosition}=await import("data:text/javascript;base64,"+Buffer.from(built.outputFiles[0].text).toString("base64"));
let restore;
afterEach(()=>restore?.());
function harness(){
  const names=["__readingHooks","document","ResizeObserver","requestAnimationFrame","cancelAnimationFrame"];
  const previous=names.map(name=>[name,Object.getOwnPropertyDescriptor(globalThis,name)]);
  restore=()=>{for(const[name,value]of previous){if(value)Object.defineProperty(globalThis,name,value);else delete globalThis[name];}};
  const listeners=new Map(), frames=new Map(), observers=[], slots=[];let frameId=0,cursor=0,pending=[],view;
  const node={scrollHeight:600,clientHeight:200,scrollTop:0,firstElementChild:{},
    addEventListener:(k,f)=>listeners.set("node:"+k,f),removeEventListener:k=>listeners.delete("node:"+k)};
  globalThis.document={hidden:false,addEventListener:(k,f)=>listeners.set(k,f),removeEventListener:k=>listeners.delete(k)};
  globalThis.ResizeObserver=class{constructor(callback){this.callback=callback;observers.push(this);}observe(){}disconnect(){this.disconnected=true;}};
  globalThis.requestAnimationFrame=f=>{frames.set(++frameId,f);return frameId;};
  globalThis.cancelAnimationFrame=id=>frames.delete(id);
  globalThis.__readingHooks={
    ref(value){const i=cursor++;return slots[i]??(slots[i]={current:value});},
    state(value){const i=cursor++;if(!slots[i])slots[i]={value};return[slots[i].value,next=>{slots[i].value=next;}];},
    effect(fn,deps){const i=cursor++,prior=slots[i];if(!prior||deps.some((v,j)=>v!==prior.deps[j])){
      prior?.cleanup?.();slots[i]={deps};pending.push(()=>slots[i].cleanup=fn());}}
  };
  function render(scope="a",conversation=true){cursor=0;view=useReadingPosition(scope,conversation);view.container.current=node;const jobs=pending;pending=[];jobs.forEach(f=>f());return view;}
  function resize(){observers.at(-1).callback();}
  function flush(){const jobs=[...frames.values()];frames.clear();jobs.forEach(f=>f());}
  render();
  return {node,render,resize,flush,frames,observers,listeners,get view(){return view;},scroll(top){node.scrollTop=top;listeners.get("node:scroll")();}};
}
test("opening a conversation starts at its latest content",()=>{const h=harness();assert.equal(h.node.scrollTop,400);});
test("stream growth does not steal a reader's position above the end",()=>{
  const h=harness();h.scroll(30);assert.equal(h.render().atEnd,false);h.node.scrollHeight=1000;h.resize();h.flush();assert.equal(h.node.scrollTop,30);
});
test("a following reader stays at the end as output grows",()=>{const h=harness();h.node.scrollHeight=1000;h.resize();h.flush();assert.equal(h.node.scrollTop,800);});
test("Jump to latest resumes following explicitly",()=>{
  const h=harness();h.scroll(30);h.node.scrollHeight=1000;h.view.jump();assert.equal(h.node.scrollTop,800);assert.equal(h.render().atEnd,true);
});
test("multiple size observations coalesce to one pending frame",()=>{const h=harness();for(let i=0;i<30;i++)h.resize();assert.equal(h.frames.size,1);});
test("hidden documents schedule no scroll work and recover on visibility",()=>{
  const h=harness();document.hidden=true;h.node.scrollHeight=1000;h.resize();assert.equal(h.frames.size,0);
  document.hidden=false;h.listeners.get("visibilitychange")();h.flush();assert.equal(h.node.scrollTop,800);
});
test("hiding cancels an already queued growth frame without moving the reader",()=>{
  const h=harness();h.node.scrollHeight=1000;h.resize();assert.equal(h.frames.size,1);
  document.hidden=true;h.listeners.get("visibilitychange")();assert.equal(h.frames.size,0);
  h.flush();assert.equal(h.node.scrollTop,400);
  document.hidden=false;h.listeners.get("visibilitychange")();h.flush();assert.equal(h.node.scrollTop,800);
});
test("a queued callback that races a hidden document performs no scroll write",()=>{
  const h=harness();h.node.scrollHeight=1000;h.resize();document.hidden=true;
  h.flush();assert.equal(h.node.scrollTop,400);
});
test("overview starts at the top without streaming follow",()=>{
  const h=harness();h.render("folder/overview",false);assert.equal(h.node.scrollTop,0);h.node.scrollHeight=1000;h.resize();h.flush();assert.equal(h.node.scrollTop,0);
});
test("scope change cancels an old pending frame and disconnects its observer",()=>{
  const h=harness();h.resize();const old=h.observers[0];h.render("b");assert.equal(h.frames.size,0);assert.equal(old.disconnected,true);assert.equal(h.observers.length,2);
});
