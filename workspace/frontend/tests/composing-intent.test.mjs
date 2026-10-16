import { test } from "node:test";
import assert from "node:assert/strict";
import { build } from "esbuild";
const built=await build({entryPoints:["src/lib/composing-intent.ts"],bundle:true,write:false,platform:"node",format:"esm"});
const {restoreComposingIntent,saveComposingIntent}=await import("data:text/javascript;base64,"+Buffer.from(built.outputFiles[0].text).toString("base64"));
const KEY="hermes-ui:composing-intent:v1",P="a".repeat(32),Q="b".repeat(32),S="c".repeat(32);
function storage(raw){const data=new Map(raw===undefined?[]:[[KEY,raw]]);return{getItem:k=>data.get(k)??null,setItem:(k,v)=>data.set(k,v),removeItem:k=>data.delete(k),data};}
test("a newly composed project view is restored after hydration from its authoritative scope",()=>{
  const state=storage();saveComposingIntent(state,{project_id:P,session_id:null},true);
  assert.equal(restoreComposingIntent(state,{project_id:P,session_id:null}),true);
});
test("a root conversation intent can reload without claiming a project",()=>{
  const state=storage();saveComposingIntent(state,null,true);assert.equal(restoreComposingIntent(state,null),true);
});
test("an actual selected conversation overrides a stale composing intent",()=>{
  const state=storage(JSON.stringify({version:1,project_id:P}));
  assert.equal(restoreComposingIntent(state,{project_id:P,session_id:S}),false);
});
test("intent from a different project cannot change the saved view",()=>{
  const state=storage(JSON.stringify({version:1,project_id:P}));
  assert.equal(restoreComposingIntent(state,{project_id:Q,session_id:null}),false);
  assert.equal(restoreComposingIntent(state,{project_id:null,session_id:null}),false);
});
test("malformed, future, extra-key and invalid-id records fail closed",()=>{
  for(const raw of ["{", "null", "[]", JSON.stringify({version:2,project_id:P}),
    JSON.stringify({version:1,project_id:P,session_id:S}),JSON.stringify({version:1,project_id:"not-an-id"})])
    assert.equal(restoreComposingIntent(storage(raw),{project_id:P,session_id:null}),false);
});
test("overview and actual conversation selection clear presentation intent",()=>{
  for(const [view,composing] of [[{project_id:P,session_id:null},false],[{project_id:P,session_id:S},true]]){
    const state=storage(JSON.stringify({version:1,project_id:P}));saveComposingIntent(state,view,composing);
    assert.equal(state.getItem(KEY),null);
  }
});
