"""Actual guest Hermes tools against an owned fixture backend; zero model calls."""
import hashlib
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import secrets
import threading
from lab.relay import validate_request
from lab.workspace_contract import guest_result
from jobs import relay_path

PROGRAM='import json,sys\nv=json.load(sys.stdin)\nprint(json.dumps([min(100,max(0,x)) for x in v]))\n'


def probe(control,run):
    token=control.store.token(run);events=[];step=[0];lock=threading.Lock()
    calls=[('lab_read_file',{'path':'program.py'}),('lab_write_file',{'path':'program.py','text':PROGRAM}),
           ('lab_run',{'language':'python','stdin':'[-10,0,5,101]'})]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def setup(self):super().setup();self.connection.settimeout(3)
        def reply(self,status,value):
            raw=json.dumps(value).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
        def authorized(self):
            return secrets.compare_digest(self.headers.get('Authorization',''),'Bearer '+token) and not control.store.mutate(run,control.store.active)
        def do_GET(self):
            if not self.authorized():self.reply(403,{'error':'lease_denied'});return
            if self.path!='/v1/models':self.reply(404,{'error':'fixture_route_denied'});return
            self.reply(200,{'object':'list','data':[{'id':'mani-lab-qwen','object':'model'}]})
        def do_POST(self):
            if not self.authorized() or self.path!='/v1/chat/completions':self.reply(403,{'error':'fixture_route_or_lease_denied'});return
            try:
                lengths=self.headers.get_all('Content-Length',[])
                if len(lengths)!=1 or not lengths[0].isdigit() or not 0<int(lengths[0])<=32768 or self.headers.get('Transfer-Encoding'):raise ValueError('fixture_body_limit')
                request=validate_request(self.rfile.read(int(lengths[0])),'mani-lab-qwen','candidate')
                with lock:
                    index=step[0];step[0]+=1
                    if index>=4:raise ValueError('fixture_call_budget')
                events.append({'request_fields':sorted(request),'roles':[m['role'] for m in request['messages']],
                    'tool_result_names':[m.get('name') for m in request['messages'] if m['role']=='tool'],
                    'max_tokens':request['max_tokens'],'profile':'owned_protocol_fixture_not_model'})
                if index<3:
                    name,arguments=calls[index]
                    message={'role':'assistant','content':None,'tool_calls':[{'id':'owned_fixture_'+str(index),'type':'function','function':{'name':name,'arguments':json.dumps(arguments)}}]}
                    finish='tool_calls'
                else:message={'role':'assistant','content':'Owned protocol fixture complete.'};finish='stop'
                self.reply(200,{'id':'owned-protocol-fixture','object':'chat.completion','created':0,'model':'mani-lab-qwen',
                    'choices':[{'index':0,'message':message,'finish_reason':finish}],'usage':{'prompt_tokens':0,'completion_tokens':0,'total_tokens':0}})
            except (OSError,ValueError,RuntimeError) as error:
                events.append({'denial':str(error)[:100],'fixture_not_model':True});self.reply(409,{'error':'owned_protocol_denial'})
    class Fixture:
        def server(self):return ThreadingHTTPServer(('127.0.0.1',0),Handler)
    text='import json,sys\nprint(json.dumps(json.load(sys.stdin)))\n'
    files=[{'path':'program.py','text':text,'bytes':len(text.encode()),'sha256':hashlib.sha256(text.encode()).hexdigest()}]
    control.store.mutate(run,lambda m:m.update(qualification_fixture_active=True))
    try:
        with relay_path(control,run,'worker_a',Fixture()):
            result=control.ssh(run,'worker_a','workspace',{'prompt':'Complete this owned protocol fixture with the advertised scoped tools.','model':'mani-lab-qwen','relay_token':token,'files':files,'authority':'candidate'})
    finally:control.store.mutate(run,lambda m:m.update(qualification_fixture_active=False))
    guest_result(result,'candidate')
    names=[event['tool'] for event in result['tool_events']]
    executed=next((event['result'] for event in result['tool_events'] if event['tool']=='lab_run'),{})
    passed=names==[name for name,_ in calls] and executed.get('exit')==0 and executed.get('candidate_uid')==1001 and json.loads(executed.get('stdout','null'))==[0,0,5,100]
    return {'evidence_kind':'actual_pinned_guest_Hermes_protocol_with_scripted_fixture_backend_not_model',
        'passed':passed,'real_model_calls':0,'GPU_window_opened':False,'wire_events':events,'guest_result':result}
