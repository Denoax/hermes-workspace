"""Transfer complete CPU observations without enlarging browser message limits."""
import base64
import hashlib
import json
import re

MAX_BYTES = 32 * 1024 * 1024
CHUNK_BYTES = 12 * 1024


def stop_performance(browser):
    metadata = browser.evaluate('''(async()=>{const raw=globalThis.__hermesPerformanceProbe.stop();const bytes=new TextEncoder().encode(JSON.stringify(raw));globalThis.__hermesPerformanceTransfer=bytes;const hash=await crypto.subtle.digest('SHA-256',bytes);return {bytes:bytes.length,sha256:[...new Uint8Array(hash)].map(v=>v.toString(16).padStart(2,'0')).join('')}})()''')
    if (not isinstance(metadata,dict) or type(metadata.get('bytes')) is not int
            or not 0 < metadata['bytes'] <= MAX_BYTES
            or not isinstance(metadata.get('sha256'),str)
            or not re.fullmatch('[a-f0-9]{64}',metadata['sha256'])):
        raise RuntimeError('bounded_performance_transfer_required')
    parts=[]
    for start in range(0,metadata['bytes'],CHUNK_BYTES):
        end=min(start+CHUNK_BYTES,metadata['bytes'])
        encoded=browser.evaluate('btoa(String.fromCharCode(...globalThis.__hermesPerformanceTransfer.subarray('+str(start)+','+str(end)+')))')
        if not isinstance(encoded,str) or len(encoded)>4*((CHUNK_BYTES+2)//3):
            raise RuntimeError('bounded_performance_chunk_required')
        raw=base64.b64decode(encoded,validate=True)
        if len(raw)!=end-start:
            raise RuntimeError('performance_chunk_length_changed')
        parts.append(raw)
    raw=b''.join(parts)
    if hashlib.sha256(raw).hexdigest()!=metadata['sha256']:
        raise RuntimeError('performance_transfer_hash_changed')
    result=json.loads(raw)
    browser.evaluate('delete globalThis.__hermesPerformanceTransfer')
    return result
