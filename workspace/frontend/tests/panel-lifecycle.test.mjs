// Hook lifecycle contract; actual native top-layer motion is checked separately.
import { test, afterEach } from "node:test";
import assert from "node:assert/strict";
import { build } from "esbuild";
const built=await build({entryPoints:["src/controls.tsx"],bundle:true,write:false,platform:"node",format:"esm",
  define:{"process.env.NODE_ENV":'"production"'},plugins:[{name:"controlled-panel",setup(builder){
    builder.onResolve({filter:/^(react|react-dom|motion\/react)$/},args=>({path:args.path,namespace:"fixture"}));
    builder.onResolve({filter:/lib\/reduced-motion$/},()=>({path:"reduced",namespace:"fixture"}));
    builder.onLoad({filter:/.*/,namespace:"fixture"},args=>({contents:({
      react:"export const useLayoutEffect=(...a)=>globalThis.__panelHooks.effect(...a),useRef=(...a)=>globalThis.__panelHooks.ref(...a),useState=(...a)=>globalThis.__panelHooks.state(...a);",
      "react-dom":"export const createPortal=child=>child;",
      "motion/react":"export const motion={dialog:'dialog'},useIsPresent=()=>globalThis.__panelPresent;",
      reduced:"export const useReducedMotion=()=>false;"
    })[args.path]}));
  }}]});
const {Panel}=await import("data:text/javascript;base64,"+Buffer.from(built.outputFiles[0].text).toString("base64"));
let restore;
afterEach(()=>restore?.());
function harness(){
  const names=["__panelHooks","__panelPresent","document","window","innerWidth","innerHeight","ResizeObserver","addEventListener","removeEventListener"];
  const previous=names.map(name=>[name,Object.getOwnPropertyDescriptor(globalThis,name)]);
  restore=()=>{for(const[name,value]of previous){if(value)Object.defineProperty(globalThis,name,value);else delete globalThis[name];}};
  const slots=[];let cursor=0,pending=[],tree,closed=0,shows=0;const listeners=new Map();
  const owner={activeElement:null,body:{},querySelector:()=>null,getElementById:()=>trigger};
  const control=name=>({name,isConnected:true,getClientRects:()=>[{}],closest:()=>null,focus(){owner.activeElement=this;}});
  const trigger=control("trigger"),input=control("input");owner.activeElement=trigger;
  const node={open:false,inert:false,dataset:{},style:{},contains:value=>value===input,
    querySelector:()=>input,showModal(){this.open=true;shows++;},show(){this.open=true;shows++;},
    close(){this.open=false;owner.activeElement=trigger;}};
  globalThis.document=owner;globalThis.window={visualViewport:null};globalThis.innerWidth=1280;globalThis.innerHeight=800;
  globalThis.ResizeObserver=class{observe(){}disconnect(){}};
  globalThis.addEventListener=(name,fn)=>listeners.set(name,fn);globalThis.removeEventListener=name=>listeners.delete(name);
  globalThis.__panelHooks={
    ref(value){const i=cursor++;return slots[i]??(slots[i]={current:value});},
    state(value){const i=cursor++;if(!slots[i])slots[i]={value};return[slots[i].value,next=>{slots[i].value=next;}];},
    effect(fn,deps){const i=cursor++,prior=slots[i];if(!prior||deps.some((v,j)=>v!==prior.deps[j])){
      prior?.cleanup?.();slots[i]={deps};pending.push(()=>slots[i].cleanup=fn());}}
  };
  function render(present){globalThis.__panelPresent=present;cursor=0;tree=Panel({title:"Settings",close:()=>closed++,children:null});
    tree.props.ref.current=node;const jobs=pending;pending=[];jobs.forEach(job=>job());}
  render(true);
  return {node,input,trigger,owner,render,get shows(){return shows;},get closed(){return closed;},
    dismiss(){tree.props.onCancel({preventDefault(){}});},
    unmount(){slots.forEach(slot=>slot?.cleanup?.());}};
}
test("Settings reopened during retained exit regains the native top layer and input focus",()=>{
  const h=harness();assert.equal(h.node.open,true);assert.equal(h.shows,1);
  h.dismiss();h.render(false);assert.equal(h.node.open,false);assert.equal(h.node.inert,true);
  h.render(true);assert.equal(h.node.open,true);assert.equal(h.node.inert,false);
  assert.equal(h.owner.activeElement,h.input);assert.equal(h.shows,2);
  h.dismiss();h.render(false);h.render(true);assert.equal(h.node.open,true);assert.equal(h.shows,3);
  assert.equal(h.closed,2);h.unmount();assert.equal(h.node.open,false);
});
