// Real React SSR checks captions and disabled states; actual native Settings remains separate.
import {test} from "node:test";
import assert from "node:assert/strict";
import {createRequire} from "node:module";
import {build} from "esbuild";
const result=await build({stdin:{contents:'import{createElement}from"react";import{renderToStaticMarkup}from"react-dom/server";import{PermissionSettings,unavailableReason}from"./src/permissions";export{unavailableReason};export const render=policy=>renderToStaticMarkup(createElement(PermissionSettings,{workspace:"Selected project P",controller:{policy,updating:false,update:()=>{},revoke:()=>{},refreshPolicy:()=>{}}}));',resolveDir:process.cwd(),loader:"tsx"},bundle:true,write:false,platform:"node",format:"cjs",alias:{"@":process.cwd()+"/src"}});
const module={exports:{}};
new Function("require","module","exports",result.outputFiles[0].text)(createRequire(import.meta.url),module,module.exports);
const {render,unavailableReason}=module.exports;
const base={session_id:null,project_id:null,version:0,mode:"chat_only",capabilities:{read:false,write:false,guest:false,search:false,microphone:false},pending:[],grants:[],available:{read:{available:false,reason:"Select a project workspace."},write:{available:false,reason:"Select a project workspace."},guest:{available:false,reason:"Select a project workspace and open a qualified native Lab window."},search:{available:true,reason:"Wikipedia only"},microphone:{available:true,reason:"App and browser permissions required"}}};
test("a selected project overview accurately explains its missing conversation while preserving disabled controls",()=>{
  const html=render(base);assert.ok(html.includes("Selected project P"));
  assert.ok(html.includes("A conversation linked to a project workspace is required."));
  assert.ok(html.includes("and a qualified native Lab window are required."));
  assert.ok(!html.includes("Select a project workspace."));
  const checkboxes=html.match(/<input\b[^>]*type="checkbox"[^>]*>/g)??[];
  assert.equal(checkboxes.length,5);assert.equal(checkboxes.filter(tag=>tag.includes('disabled=""')).length,3);
});
test("real conversation context and other server denials retain their authoritative explanations",()=>{
  assert.equal(unavailableReason({...base,session_id:"a".repeat(32)},"read"),"Select a project workspace.");
  const changed={...base,available:{...base.available,guest:{available:false,reason:"Guest execution unavailable: VM_watchdog_qualified. No host shell fallback."}}};
  assert.equal(unavailableReason(changed,"guest"),changed.available.guest.reason);
});
