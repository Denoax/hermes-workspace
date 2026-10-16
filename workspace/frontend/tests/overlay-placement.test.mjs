// Placement/keyboard utility tests. They do not certify browser focus or motion.
import { test } from "node:test";
import assert from "node:assert/strict";
import { build } from "esbuild";
const built = await build({ entryPoints: ["src/lib/overlay-placement.ts"], bundle: true,
  write: false, platform: "node", format: "esm" });
const { placeOverlay, menuIndex } = await import("data:text/javascript;base64," + Buffer.from(built.outputFiles[0].text).toString("base64"));
const view = { left: 0, top: 0, width: 1280, height: 800 };
const rect = (left, top, width=32, height=32) => ({ left, top, width, height, right: left+width, bottom: top+height });
const size = { width: 232, height: 200 };
test("composer menu opens above its real trigger while space permits", () => {
  const p = placeOverlay(rect(300,730), size, view, "top-start");
  assert.equal(p.placement,"top-start"); assert.equal(p.left,300); assert.equal(p.top,524);
});
test("a row near the top opens below rather than outside the viewport", () => {
  const p = placeOverlay(rect(210,20), size, view, "top-end");
  assert.equal(p.placement,"bottom-end"); assert.ok(p.top >= 52);
});
test("a bottom row flips upwards without changing the trigger geometry", () => {
  const anchor = rect(210,740), before=structuredClone(anchor);
  const p = placeOverlay(anchor,size,view,"bottom-end");
  assert.equal(p.placement,"top-end"); assert.deepEqual(anchor,before);
});
test("right-edge overflow shifts the surface inside the viewport", () => {
  const p = placeOverlay(rect(1240,200),size,view,"bottom-start");
  assert.ok(p.left+size.width<=1272); assert.ok(p.left>=8);
});
test("left-edge end alignment is constrained without negative coordinates", () => {
  assert.equal(placeOverlay(rect(12,200),size,view,"bottom-end").left,8);
});
test("narrow viewport constrains the source surface width", () => {
  const p = placeOverlay(rect(150,500),{width:330,height:220},{left:0,top:0,width:320,height:600},"top-end");
  assert.equal(p.maxWidth,304); assert.ok(p.left>=8);
});
test("visual viewport offset is included during zoom and keyboard displacement", () => {
  const viewport={left:100,top:160,width:390,height:420};
  const p=placeOverlay(rect(450,500),size,viewport,"bottom-start");
  assert.ok(p.left>=108 && p.left+size.width<=482); assert.ok(p.top>=168);
});
test("oversized menu receives a scrollable available height instead of leaving screen", () => {
  const p=placeOverlay(rect(300,300),{width:232,height:1000},view,"bottom-end");
  assert.ok(p.maxHeight>0 && p.maxHeight<1000);
  assert.ok(p.top+p.maxHeight<=792);
});
test("origin follows the trigger after horizontal collision adjustment", () => {
  const p=placeOverlay(rect(12,300),size,view,"top-end");
  const x=parseFloat(p.transformOrigin);
  assert.ok(x>=0 && x<=size.width); assert.ok(x<50);
});
test("generated in-viewport cases keep the rendered surface inside all four edges", () => {
  for(let i=0;i<1000;i++){
    const width=320+(i*37)%1280,height=420+(i*61)%700;
    const viewport={left:10,top:20,width,height};
    const anchor=rect(10+(i*11)%(width-32),20+(i*13)%(height-32));
    const surface={width:170+(i*5)%300,height:80+(i*3)%700};
    const p=placeOverlay(anchor,surface,viewport,i%2?"top-end":"bottom-start");
    assert.ok(p.left>=18);assert.ok(p.left+Math.min(surface.width,p.maxWidth)<=width+2+1e-8);
    assert.ok(p.top>=28);assert.ok(p.top+Math.min(surface.height,p.maxHeight)<=height+12+1e-8);
  }
});
test("arrow navigation wraps across enabled actions", () => {
  assert.equal(menuIndex("ArrowDown",2,3),0); assert.equal(menuIndex("ArrowUp",0,3),2);
});
test("first arrow opens the expected first or last action", () => {
  assert.equal(menuIndex("ArrowDown",-1,3),0); assert.equal(menuIndex("ArrowUp",-1,3),2);
});
test("Home and End reach boundary actions, an empty list has no target", () => {
  assert.equal(menuIndex("Home",2,3),0); assert.equal(menuIndex("End",0,3),2);assert.equal(menuIndex("Home",0,0),-1);
});
