"""Same installed application, isolated acceptance catalog and fixed loopback port.

No fixture responses or inference on open. Exit 30 minutes after the first
accepted test Send; the trusted native per-request/watchdog limits remain intact.
"""
import argparse,json,os,signal,sys,threading,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from workspace import server


def main():
 p=argparse.ArgumentParser();p.add_argument('catalog',type=Path);p.add_argument('--port',type=int,choices=(18793,18794),default=18793);args=p.parse_args()
 if os.geteuid()==0 or args.catalog.resolve()==(Path.home()/'HermesLab').resolve():raise ValueError('separate_unprivileged_acceptance_catalog_required')
 os.umask(0o077);server.PORT=args.port;server.ORIGIN='http://127.0.0.1:'+str(args.port)
 app=server.Application(args.catalog);credential=(server.STATE/'client-cookie').read_text().strip();http=server.BoundedServer(('127.0.0.1',server.PORT),server.handler(app,credential));stop=threading.Event()
 signal.signal(signal.SIGTERM,lambda *_:stop.set());signal.signal(signal.SIGINT,lambda *_:stop.set())
 thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start();deadline=None
 print(json.dumps({'application':'actual installed Hermes','catalog':'isolated acceptance data','origin':server.ORIGIN,'inference_on_open':False}),flush=True)
 try:
  while not stop.wait(.25):
   with app.catalog.lock:first=app.catalog.db.execute('SELECT MIN(created) FROM chat_runs').fetchone()[0]
   # Restarting this harness cannot renew the authorized acceptance window.
   if first and deadline is None:deadline=time.monotonic()+max(0,first+1800-time.time())
   if deadline and time.monotonic()>=deadline:break
 finally:
  with app.chat.lock:ids=list(app.chat.controls)
  for run in ids:app.chat.cancel(run)
  end=time.monotonic()+15
  while app.chat.queue.unfinished_tasks and time.monotonic()<end:stop.wait(.05)
  http.shutdown();http.server_close();thread.join(timeout=3)

if __name__=='__main__':main()
