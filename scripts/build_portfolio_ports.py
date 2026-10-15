"""Rebuild exact owned pure TS ports with an explicitly supplied existing esbuild.
No package install/network step. Runtime ships the resulting dependency-free MJS.
"""
import argparse,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def build(esbuild):
 ui=ROOT/'workspace/ui'
 subprocess.run([str(esbuild),*[str(ui/'owned'/name) for name in ['glassOptics.ts','sliderFlight.ts','paintPane.ts']], '--outdir='+str(ui),'--out-extension:.js=.mjs','--format=esm'],check=True)
 path=ui/'paintPane.mjs';text=path.read_text()
 changes={
 '[hidden],[data-glass-copy],.pane-close':'[hidden],[data-glass-copy],.sr-only,.pane-glass,.pane-flight-layer',
 's.visibility !== "hidden" &&':'s.visibility !== "hidden" && s.opacity !== "0" &&',
 '"button,a,input,img"':'"button,a,input,img,.sidebar,.toolbar,.composer,.message,.gooey-segment"',
 'svg,[data-glass-copy],.pane-close':'svg,[data-glass-copy],.sr-only',
 'const visible = (e) => {':'const visible = (e) => {\n    if (e.closest("dialog") && e.closest("dialog") !== node) return false;',
 }
 for before,after in changes.items():
  if before not in text:raise ValueError('owned_paint_source_or_compiler_drift')
  text=text.replace(before,after)
 text="import {svgFill,paintValues} from './paint-support.mjs';\n"+text
 text=text.replace('ctx.fillStyle = s.fill;', 'ctx.fillStyle = svgFill(element,svg,ctx,s.fill);')
 text=text.replace('const walker = document.createTreeWalker', 'paintValues(node,ctx,origin,visible);\n  const walker = document.createTreeWalker')
 path.write_text(text)

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--esbuild',type=Path,required=True);args=parser.parse_args();build(args.esbuild)
