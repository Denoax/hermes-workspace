import { test } from "node:test";
import assert from "node:assert/strict";
import { build } from "esbuild";
const built = await build({ entryPoints: ["src/lib/conversation-management.ts"], bundle: true,
  write: false, platform: "node", format: "esm" });
const { saveManagedConversation } = await import("data:text/javascript;base64," + Buffer.from(built.outputFiles[0].text).toString("base64"));
const row={id:"conversation-b",title:"B",project:"folder-old",arm:"normal"};
function api(){const calls=[];return {calls,rename:async(...args)=>calls.push(["rename",...args]),move:async(...args)=>calls.push(["move",...args])};}
test("Save persists the captured row B and leaves its original snapshot immutable", async () => {
  const a=api(), saved=await saveManagedConversation(row,{title:" B renamed ",project:"folder-new"},a);
  assert.deepEqual(a.calls,[["rename","conversation-b","B renamed"],["move","conversation-b","folder-new"]]);
  assert.equal(row.title,"B");assert.equal(row.project,"folder-old");assert.equal(saved.arm,"normal");
});
test("unchanged changes perform no server mutation", async () => {
  const a=api();await saveManagedConversation(row,{title:"B",project:"folder-old"},a);assert.deepEqual(a.calls,[]);
});
test("rename failure stops the subsequent move and propagates the real failure", async () => {
  const a=api();a.rename=async()=>{throw Error("target deleted");};
  await assert.rejects(saveManagedConversation(row,{title:"new",project:"folder-new"},a),/target deleted/);assert.deepEqual(a.calls,[]);
});
test("move failure is not reported as successful atomic save", async () => {
  const a=api();a.move=async()=>{throw Error("folder unavailable");};
  await assert.rejects(saveManagedConversation(row,{title:"new",project:"folder-new"},a),/folder unavailable/);
  assert.deepEqual(a.calls,[["rename","conversation-b","new"]]);
});
test("invalid names fail before crossing the server boundary", async () => {
  for(const title of ["", " ", "x".repeat(81)]){const a=api();await assert.rejects(saveManagedConversation(row,{title,project:null},a));assert.deepEqual(a.calls,[]);}
});
