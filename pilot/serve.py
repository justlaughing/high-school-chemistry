"""Serve only the generated reading directory on loopback; support byte ranges."""
from pathlib import Path
from http.server import ThreadingHTTPServer,SimpleHTTPRequestHandler
from functools import partial
import argparse,re,webbrowser,json,os
from urllib.parse import urlsplit,unquote
ROOT=Path(__file__).resolve().parent/'reading'
if os.name=='nt':ROOT=Path('\\\\?\\'+str(ROOT))
class Handler(SimpleHTTPRequestHandler):
    qa=False
    ranges=True
    def translate_path(self,path):
        if self.qa:
            name=unquote(urlsplit(path).path)
            for prefix,base in [('/__baseline__/',ROOT.parent.parent/'02_设定层'/'试卷分类题库'),('/__qa__/',ROOT.parent/'qa')]:
                if name.startswith(prefix):return str(base/name[len(prefix):])
        return os.path.normpath(super().translate_path(path))
    def log_message(self,*args):pass
    def do_POST(self):
        if not self.qa or self.path!='/__qa__/result':self.send_error(405);return
        size=int(self.headers.get('Content-Length','0'))
        if not 0<size<2000000:self.send_error(413);return
        result=json.loads(self.rfile.read(size));output='browser-qa.json' if self.ranges else 'browser-qa-no-range.json';(ROOT.parent/output).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        self.send_response(200);self.end_headers();self.wfile.write(b'OK')
    def do_GET(self):
        path=Path(self.translate_path(self.path))
        allowed=[ROOT]
        if self.qa:allowed.extend([ROOT.parent/'qa',ROOT.parent.parent/'02_设定层'/'试卷分类题库'])
        if not any(path.resolve().is_relative_to(base.resolve()) for base in allowed):self.send_error(403);return
        if self.ranges and path.suffix=='.pack' and path.is_file() and self.headers.get('Range'):
            match=re.fullmatch(r'bytes=(\d+)-(\d+)',self.headers['Range'])
            if not match:self.send_error(416);return
            start,end=map(int,match.groups());size=path.stat().st_size
            if start>end or end>=size:self.send_error(416);return
            self.send_response(206);self.send_header('Content-Type','application/octet-stream');self.send_header('Content-Length',str(end-start+1));self.send_header('Content-Range',f'bytes {start}-{end}/{size}');self.send_header('Accept-Ranges','bytes');self.end_headers()
            with path.open('rb') as file:file.seek(start);self.wfile.write(file.read(end-start+1))
            return
        super().do_GET()
    def end_headers(self):self.send_header('Cache-Control','no-cache');super().end_headers()
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=8796);p.add_argument('--no-open',action='store_true');p.add_argument('--qa',action='store_true');p.add_argument('--no-range',action='store_true');args=p.parse_args();Handler.qa=args.qa;Handler.ranges=not args.no_range
    server=ThreadingHTTPServer(('127.0.0.1',args.port),partial(Handler,directory=str(ROOT)))
    url=f'http://127.0.0.1:{server.server_port}/';print(json.dumps({'url':url,'root':str(ROOT)}),flush=True)
    if not args.no_open:webbrowser.open(url)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()
