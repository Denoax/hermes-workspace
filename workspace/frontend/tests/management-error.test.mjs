// Real React SSR checks the accessible markup/scope contract, not native visibility.
import {test} from "node:test";
import assert from "node:assert/strict";
import {createRequire} from "node:module";
import {build} from "esbuild";
const result=await build({stdin:{contents:'import{createElement}from"react";import{renderToStaticMarkup}from"react-dom/server";import{ManagementError,managementFailureMessage}from"./src/ManagementError";export{managementFailureMessage};export const render=(failure,epoch)=>renderToStaticMarkup(createElement(ManagementError,{failure,epoch}));',resolveDir:process.cwd(),loader:"tsx"},bundle:true,write:false,platform:"node",format:"cjs"});
const module={exports:{}};
new Function("require","module","exports",result.outputFiles[0].text)(createRequire(import.meta.url),module,module.exports);
const {render,managementFailureMessage}=module.exports;
test("a deleted target gives a readable actionable error in its own alert",()=>{
  const message=managementFailureMessage(Error("unknown_session"));
  const html=render({epoch:4,message},4);
  assert.match(html,/role="alert"/);assert.match(html,/no longer available/);assert.match(html,/Close this dialog/);
});
test("a late error from an older dialog does not appear in the new target",()=>{
  assert.equal(render({epoch:4,message:"Earlier failure"},5),"");assert.equal(render(null,5),"");
});
test("unrecognized failures retain their useful cause as escaped text",()=>{
  const message=managementFailureMessage(Error('<img src=x onerror=alert(1)>'));
  const html=render({epoch:1,message},1);assert.match(html,/Could not save changes:/);
  assert.ok(!html.includes('<img'));assert.ok(html.includes('&lt;img'));
});
