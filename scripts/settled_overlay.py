"""Proposed observational rest-state capture guard; no animation mutation.

The reported frames are browser rAF samples, not presented-frame/GPU evidence.
The caller must fail a capture on status=timeout/error rather than claim a
settled still. Use before screenshot only, never during continuous recording.
"""
import json


def settled_overlay(browser, *, expected_title=None, timeout_ms=3000):
    if not 100 <= timeout_ms <= 5000:
        raise ValueError('settled_overlay_timeout_out_of_range')
    source = r'''({expectedTitle, timeoutMs}) => new Promise(resolve => {
      const started = performance.now();
      let frame = 0, finished = false, stable = 0, previous = [], observations = [];
      const describe = node => {
        const style = getComputedStyle(node), rect = node.getBoundingClientRect();
        const matrix = new DOMMatrixReadOnly(style.transform === 'none' ? undefined : style.transform);
        const identity = Math.abs(matrix.a-1)<=.002 && Math.abs(matrix.d-1)<=.002 &&
          Math.abs(matrix.b)<=.002 && Math.abs(matrix.c)<=.002 &&
          Math.abs(matrix.e)<=.25 && Math.abs(matrix.f)<=.25 && matrix.is2D;
        return {node, title:node.querySelector('h2')?.textContent ?? '', opacity:Number(style.opacity),
          transform:style.transform, identity, background:style.backgroundColor, backdrop_filter:style.backdropFilter,
          visible:style.display!=='none' && style.visibility==='visible' && style.pointerEvents!=='none',
          rect:{x:rect.x,y:rect.y,width:rect.width,height:rect.height}};
      };
      const publicRows = rows => rows.map(({node,...row})=>row);
      const finish = (status, detail) => {
        if(finished) return; finished=true; cancelAnimationFrame(frame);clearTimeout(deadline);
        resolve({status, detail, elapsed_ms:performance.now()-started, stable_raf_samples:stable,
          tolerance:{opacity_min:.995, matrix_scale:.002, translation_css_px:.25, rect_drift_css_px:.25, consecutive_samples:4},
          observations});
      };
      const deadline = setTimeout(()=>finish('timeout','overlay_not_settled_before_deadline'),timeoutMs);
      const sample = () => {
        try {
          const nodes=[...document.querySelectorAll('dialog[open]:not([aria-hidden="true"]),.effort-popover,.action-menu')];
          const rows=nodes.map(describe);
          if(!rows.length && !expectedTitle) {finish('no_overlay','no_open_overlay_to_settle');return;}
          const titleMatches=!expectedTitle || rows.some(row=>row.title===expectedTitle);
          const ready=rows.length>0 && titleMatches && rows.every(row=>row.visible && row.opacity>=.995 &&
            row.identity && row.rect.width>0 && row.rect.height>0);
          const same=rows.length===previous.length && rows.every((row,index)=>row.node===previous[index].node &&
            ['x','y','width','height'].every(key=>Math.abs(row.rect[key]-previous[index].rect[key])<=.25));
          stable=ready && same ? stable+1 : 0;
          observations.push({ms:performance.now()-started, stable, rows:publicRows(rows)});
          if(observations.length>48)observations.shift();
          previous=rows;
          if(stable>=4){finish('settled','computed_opacity_transform_and_geometry_stable');return;}
          frame=requestAnimationFrame(sample);
        } catch(error) {finish('error',error.name);}
      };
      frame=requestAnimationFrame(sample);
    })'''
    return browser.evaluate('(' + source + ')(' + json.dumps({'expectedTitle': expected_title, 'timeoutMs': timeout_ms}) + ')')
