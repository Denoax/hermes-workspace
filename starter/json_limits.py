"""Explicit wire-size/depth/duplicate-key limits for untrusted JSON text."""
import json

def bounded_json(raw, max_bytes=65536, max_depth=16):
    if type(raw) is str:
        raw=raw.encode('utf-8',errors='strict')
    if type(raw) is not bytes or len(raw)>max_bytes:
        raise ValueError('invalid_json_size_or_type')
    text=raw.decode('utf-8',errors='strict')
    depth=0;quoted=False;escaped=False
    for character in text:
        if quoted:
            if escaped:escaped=False
            elif character=='\\':escaped=True
            elif character=='"':quoted=False
        elif character=='"':quoted=True
        elif character in '[{':
            depth+=1
            if depth>max_depth:raise ValueError('excessive_json_nesting')
        elif character in ']}':
            depth-=1
            if depth<0:raise ValueError('invalid_json_nesting')
    def unique(pairs):
        result={}
        for key,value in pairs:
            if key in result:raise ValueError('duplicate_json_key')
            result[key]=value
        return result
    def reject_constant(value):raise ValueError('nonfinite_json')
    try:return json.loads(text,object_pairs_hook=unique,parse_constant=reject_constant)
    except RecursionError as exc:raise ValueError('excessive_json_nesting') from exc
