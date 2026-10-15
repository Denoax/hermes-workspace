"""Deterministic synthetic-case grading. Does not call models or run code."""
import argparse
import json
from pathlib import Path
from starter.json_limits import bounded_json

def strict_equal(actual, expected):
    if type(actual) is not type(expected):
        return False
    if isinstance(expected, dict):
        return set(actual)==set(expected) and all(strict_equal(actual[k],v) for k,v in expected.items())
    if isinstance(expected, list):
        return len(actual)==len(expected) and all(strict_equal(a,b) for a,b in zip(actual,expected))
    return actual==expected

def strict_json(text):
    if type(text) is not str:
        raise ValueError('invalid_answer_size_or_type')
    return bounded_json(text)

def score(case_id,text,answer_keys):
    if case_id not in answer_keys:
        return {'case_id':case_id,'passed':False,'category':'unknown_case'}
    try:
        actual=strict_json(text)
    except (ValueError,TypeError,UnicodeError):
        return {'case_id':case_id,'passed':False,'category':'parse_error'}
    expected=answer_keys[case_id]
    if type(actual) is not dict or set(actual)!=set(expected):
        return {'case_id':case_id,'passed':False,'category':'schema_error'}
    ok=strict_equal(actual,expected)
    return {'case_id':case_id,'passed':ok,'category':'correct' if ok else 'incorrect'}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--answers',type=Path,required=True,help='JSON mapping case IDs to raw model-answer strings')
    parser.add_argument('--key',type=Path,default=Path(__file__).resolve().parents[1]/'bench/answer_keys.json')
    args=parser.parse_args()
    replies=json.loads(args.answers.read_text(encoding='utf-8'))
    keys=json.loads(args.key.read_text(encoding='utf-8'))['answers']
    if type(replies) is not dict or not replies:parser.error('Answers must be a nonempty object')
    results=[score(k,v,keys) for k,v in sorted(replies.items())]
    print(json.dumps({'fixture_grading_only':True,'total':len(results),
                      'passed':sum(r['passed'] for r in results),'results':results},indent=2))
    return 0 if all(r['passed'] for r in results) else 1

if __name__=='__main__':raise SystemExit(main())
