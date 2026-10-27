"""Loopback reader and classified-data watcher. Only reading output is served."""
from pathlib import Path
from http.server import ThreadingHTTPServer,SimpleHTTPRequestHandler
from functools import partial
from urllib.parse import urlsplit,unquote,parse_qs
from urllib.request import urlopen
import argparse,json,os,re,threading,time,webbrowser,hashlib,traceback,sys,zipfile
from build import build,lp,sha
HERE=Path(__file__).resolve().parent;ROOT=lp(HERE.parent/'题库阅读版');BANK=lp(HERE.parent/'试卷分类题库')
STATE=HERE/'运行状态.json';stop=threading.Event();last_error='';last_build=''
BASELINE_ARCHIVE=None
if sys.stdout is None:sys.stdout=open(HERE/'运行日志.log','a',encoding='utf-8');sys.stderr=sys.stdout
class Handler(SimpleHTTPRequestHandler):
    qa=False;ranges=True
    def log_message(self,*args):pass
    def translate_path(self,path):
        if self.qa:
            name=unquote(urlsplit(path).path)
            for prefix,base in [('/__baseline__/',BANK),('/__qa__/',lp(HERE/'qa'))]:
                if name.startswith(prefix):return str(base/name[len(prefix):])
        return os.path.normpath(super().translate_path(path))
    def do_POST(self):
        if not self.qa or self.path!='/__qa__/result':self.send_error(405);return
        count=int(self.headers.get('Content-Length','0'))
        if not 0<count<6000000:self.send_error(413);return
        result=json.loads(self.rfile.read(count));name='browser-qa.json' if self.ranges else 'browser-qa-no-range.json';(HERE/name).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');self.send_response(200);self.end_headers();self.wfile.write(b'OK')
    def do_GET(self):
        parsed=urlsplit(self.path)
        if parsed.path=='/api/health':
            data=json.dumps({'product':'chemistry-packed-reader-v2','root':str(ROOT),'pid':os.getpid(),'error':last_error,'updated':last_build},ensure_ascii=False).encode();self.send_response(200);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(data)));self.send_header('Access-Control-Allow-Origin','null');self.end_headers();self.wfile.write(data);return
        path=Path(self.translate_path(self.path));allowed=[ROOT]
        if self.qa:allowed.extend([BANK,lp(HERE/'qa')])
        if not any(path.resolve().is_relative_to(base.resolve()) for base in allowed):self.send_error(403);return
        if self.qa and parsed.path.startswith('/__baseline__/') and not path.is_file() and BASELINE_ARCHIVE:
            try:
                name='02_设定层/试卷分类题库/'+path.resolve().relative_to(BANK.resolve()).as_posix();data=BASELINE_ARCHIVE.read(name)
                self.send_response(200);self.send_header('Content-Type',self.guess_type(str(path)));self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data);return
            except KeyError:self.send_error(404);return
        if path.suffix=='.pack' and path.is_file() and self.ranges and self.headers.get('Range'):
            match=re.fullmatch(r'bytes=(\d+)-(\d+)',self.headers['Range'])
            if not match:self.send_error(416);return
            start,end=map(int,match.groups());size=path.stat().st_size
            if start>end or end>=size:self.send_error(416);return
            self.send_response(206);self.send_header('Content-Type','application/octet-stream');self.send_header('Content-Length',str(end-start+1));self.send_header('Content-Range',f'bytes {start}-{end}/{size}');self.send_header('Accept-Ranges','bytes');self.end_headers()
            try:
                with path.open('rb') as f:f.seek(start);self.wfile.write(f.read(end-start+1))
            except (BrokenPipeError,ConnectionResetError):pass
            return
        super().do_GET()
    def end_headers(self):self.send_header('Cache-Control','no-cache');super().end_headers()

def source_stamp():return [(str(p),p.stat().st_mtime_ns,p.stat().st_size) for p in sorted((BANK/'批次记录').glob('*/分类数据.json'))]
def watch():
    global last_error,last_build
    previous=source_stamp()
    while not stop.wait(2):
        try:
            current=source_stamp()
            if current==previous:continue
            time.sleep(.5)
            if source_stamp()!=current:continue
            result=build();last_build=time.strftime('%Y-%m-%d %H:%M:%S');last_error='';previous=current
            print(json.dumps({'updated':True,'questions':result['questions'],'rewritten':len(result['changed'])}),flush=True)
        except Exception as error:
            last_error=str(error);print('Update retained prior complete bank: '+str(error),flush=True);stop.wait(4)

def existing(port):
    try:
        with urlopen(f'http://127.0.0.1:{port}/api/health',timeout=1) as response:data=json.load(response)
        return data.get('product')=='chemistry-packed-reader-v2' and Path(data['root'])==ROOT
    except Exception:return False

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=8765);p.add_argument('--no-open',action='store_true');p.add_argument('--qa',action='store_true');p.add_argument('--no-range',action='store_true');p.add_argument('--no-watch',action='store_true');p.add_argument('--skip-build',action='store_true');args=p.parse_args()
    if existing(args.port):
        if not args.skip_build:build()
        if not args.no_open:webbrowser.open(f'http://127.0.0.1:{args.port}/')
        print('Existing reader reused');raise SystemExit(0)
    if not args.skip_build:build()
    Handler.qa=args.qa;Handler.ranges=not args.no_range
    if args.qa:
        archive=Path(r'D:\高中化学_本地备份\题库重构前-20261027.zip')
        if archive.is_file():BASELINE_ARCHIVE=zipfile.ZipFile(archive)
    server=ThreadingHTTPServer(('127.0.0.1',args.port),partial(Handler,directory=str(ROOT)));url=f'http://127.0.0.1:{args.port}/'
    STATE.write_text(json.dumps({'root':str(ROOT),'pid':os.getpid(),'port':args.port,'url':url},ensure_ascii=False,indent=2),encoding='utf-8')
    if not args.no_watch:threading.Thread(target=watch,daemon=True).start()
    print(json.dumps({'url':url,'root':str(ROOT)},ensure_ascii=True),flush=True)
    if not args.no_open:webbrowser.open(url)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:
        stop.set();server.server_close()
        if BASELINE_ARCHIVE:BASELINE_ARCHIVE.close()
