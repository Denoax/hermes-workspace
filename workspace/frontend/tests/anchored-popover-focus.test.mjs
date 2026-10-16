// Controlled React/DOM contract fixture. Native browser focus is separately required.
import { test, afterEach } from "node:test";
import assert from "node:assert/strict";
import { build } from "esbuild";
const built=await build({entryPoints:["src/AnchoredPopover.tsx"],bundle:true,write:false,platform:"node",format:"esm",define:{"process.env.NODE_ENV":'"production"'},
  plugins:[{name:"controlled-popover",setup(builder){
    builder.onResolve({filter:/^(react|react-dom|motion\/react)$/},args=>({path:args.path,namespace:"fixture"}));
    builder.onResolve({filter:/lib\/reduced-motion$/},()=>({path:"reduced",namespace:"fixture"}));
    builder.onLoad({filter:/.*/,namespace:"fixture"},args=>({contents:({
      react:"export const useLayoutEffect=(...a)=>globalThis.__popoverHooks.effect(...a),useRef=(...a)=>globalThis.__popoverHooks.ref(...a),useState=(...a)=>globalThis.__popoverHooks.state(...a);",
      "react-dom":"export const createPortal=child=>child;", "motion/react":"export const motion={div:'div'};",
      reduced:"export const useReducedMotion=()=>false;"
    })[args.path]}));
  }}]});
const {AnchoredPopover}=await import("data:text/javascript;base64,"+Buffer.from(built.outputFiles[0].text).toString("base64"));
let restore;
afterEach(()=>restore?.());
function harness(){
  const names=["__popoverHooks","document","window","innerWidth","innerHeight","ResizeObserver","requestAnimationFrame","cancelAnimationFrame","addEventListener","removeEventListener"];
  const previous=names.map(name=>[name,Object.getOwnPropertyDescriptor(globalThis,name)]);
  restore=()=>{for(const[name,value]of previous){if(value)Object.defineProperty(globalThis,name,value);else delete globalThis[name];}};
  const slots=[];let cursor=0,pending=[],tree,closed=0;const listeners=new Map(),focused=[];
  const owner={activeElement:null,modal:null,targets:[],querySelector:()=>owner.modal,querySelectorAll:()=>owner.targets};
  const element=name=>({name,isConnected:true,tabIndex:0,getClientRects:()=>[{}],closest:()=>null,
    getBoundingClientRect:()=>({left:200,top:200,right:232,bottom:232,width:32,height:32}),
    focus(){owner.activeElement=this;focused.push(name);}});
  const previousControl=element("previous"),anchor=element("anchor"),nextControl=element("next"),item=element("item"),negative=element("negative");negative.tabIndex=-1;
  const node={offsetWidth:232,offsetHeight:100,scrollHeight:98,
    contains:value=>value===item,querySelector:()=>item,querySelectorAll:()=>[item]};
  owner.targets=[previousControl,anchor,negative,nextControl];owner.activeElement=anchor;
  globalThis.document=owner;globalThis.window={visualViewport:null};globalThis.innerWidth=1280;globalThis.innerHeight=800;
  globalThis.ResizeObserver=class{observe(){}disconnect(){}};
  globalThis.requestAnimationFrame=()=>1;globalThis.cancelAnimationFrame=()=>{};
  globalThis.addEventListener=(name,callback)=>listeners.set(name,callback);globalThis.removeEventListener=name=>listeners.delete(name);
  globalThis.__popoverHooks={
    ref(value){const i=cursor++;return slots[i]??(slots[i]={current:value});},
    state(value){const i=cursor++;if(!slots[i])slots[i]={value};return[slots[i].value,next=>{slots[i].value=next;}];},
    effect(fn,deps){const i=cursor++,prior=slots[i];if(!prior||deps.some((v,j)=>v!==prior.deps[j])){
      prior?.cleanup?.();slots[i]={deps};pending.push(()=>slots[i].cleanup=fn());}}
  };
  function render(){cursor=0;tree=AnchoredPopover({id:"menu",anchor,close:()=>closed++,className:"action-menu",menu:true,label:"Actions",children:null});
    tree.props.ref.current=node;const jobs=pending;pending=[];jobs.forEach(job=>job());}
  render();render();
  return {owner,anchor,item,previousControl,nextControl,negative,node,focused,listeners,get closed(){return closed;},
    tab(shiftKey=false){const event={key:"Tab",shiftKey,currentTarget:node,defaultPrevented:false,preventDefault(){this.defaultPrevented=true;}};
      tree.props.onKeyDown(event);return event;},
    unmount(){slots.forEach(slot=>slot?.cleanup?.());}};
}
test("Tab exits to the next actual tabbable control exactly once",()=>{
  const h=harness(),event=h.tab();assert.equal(event.defaultPrevented,true);assert.equal(h.owner.activeElement,h.nextControl);
  assert.equal(h.closed,1);assert.equal(h.focused.at(-1),"next");
});
test("Shift-Tab exits to the control before the invoker",()=>{
  const h=harness(),event=h.tab(true);assert.equal(event.defaultPrevented,true);assert.equal(h.owner.activeElement,h.previousControl);
});
test("a document boundary fallback cannot also perform the browser default move",()=>{
  const h=harness();h.owner.targets=[h.anchor];const event=h.tab();
  assert.equal(event.defaultPrevented,true);assert.equal(h.owner.activeElement,h.anchor);assert.equal(h.closed,1);
});
test("unmount leaves a newly clicked outside control's focus intact",()=>{
  const h=harness();h.owner.activeElement=h.nextControl;h.unmount();assert.equal(h.owner.activeElement,h.nextControl);
});
test("menu teardown cannot restore its invoker over an opening dialog",()=>{
  const h=harness();h.owner.modal={open:true};h.owner.activeElement=h.item;const before=h.focused.length;
  h.unmount();assert.equal(h.focused.length,before);
});
