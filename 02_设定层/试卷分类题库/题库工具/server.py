"""Local chemistry catalog: watch classified batches and serve live read-only pages."""
from pathlib import Path
from collections import OrderedDict
from datetime import datetime, timezone, timedelta
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import quote, urlsplit, parse_qs
import argparse, hashlib, json, os, threading, time, traceback, webbrowser
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / '题库工具' / '运行状态.json'
DATA_JS = ROOT / '题库工具' / 'catalog.js'
UI_VERSION = 2
CN_TIME = timezone(timedelta(hours=8))

def atomic_write(path, text):
    temp = path.with_name(path.name + '.writing')
    temp.write_text(text, encoding='utf-8')
    os.replace(temp, path)

def source_files():
    return sorted((ROOT / '批次记录').glob('*/分类数据.json'))

def fingerprint():
    return tuple((str(p), p.stat().st_mtime_ns, p.stat().st_size) for p in source_files())

def read_catalog():
    records, taxonomy, batches = [], [], []
    seen = set()
    files = source_files()
    for source in files:
        doc = json.loads(source.read_text(encoding='utf-8-sig'))
        batch = str(doc.get('batch', source.parent.name))
        if batch in batches:
            raise ValueError('批次编号重复：' + batch)
        batches.append(batch)
        taxonomy.extend(doc['taxonomy'])
        for raw in doc['records']:
            r = {k: raw[k] for k in ['id', 'number', 'paper_id', 'paper_label', 'title', 'main', 'related', 'subquestions']}
            key = batch + ':' + str(r['id'])
            if key in seen:
                raise ValueError('题目编号重复：' + key)
            seen.add(key)
            target = (ROOT / raw['relative_path']).resolve()
            if not target.is_relative_to(ROOT) or not target.is_file():
                raise ValueError('题目阅读文件缺失或超出题库目录：' + key)
            r.update(batch=batch, key=key, relative_path=target.relative_to(ROOT).as_posix(), text=raw.get('text', ''), question_type=raw.get('question_type', ''))
            r['tags'] = list(dict.fromkeys([r['main']] + r['related'] + [t for s in r['subquestions'] for t in s['topics']]))
            taxonomy.extend(r['tags'])
            records.append(r)
    # Include ancestors of any newly introduced knowledge point.
    paths = []
    for path in dict.fromkeys(taxonomy):
        if not isinstance(path, str) or not path or any(x in ['', '.', '..'] for x in path.split('/')):
            raise ValueError('知识点路径格式无效：' + str(path))
        parts = path.split('/')
        for depth in range(1, len(parts) + 1):
            ancestor = '/'.join(parts[:depth])
            if ancestor not in paths:
                paths.append(ancestor)
    updated = datetime.fromtimestamp(max((p.stat().st_mtime for p in files), default=time.time()), CN_TIME).strftime('%Y-%m-%d %H:%M:%S')
    data = {'records': records, 'taxonomy': paths, 'batches': batches, 'updated': updated}
    version = hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    return {**data, 'version': version}

def matches(record, path):
    return any(t == path or t.startswith(path + '/') for t in record['tags'])

def snapshot(data):
    from create_pages import build
    build(ROOT)
    atomic_write(DATA_JS, 'window.CHEM_BANK=' + json.dumps(data, ensure_ascii=False).replace('<', '\\u003c') + ';\n')
    records, paths = data['records'], data['taxonomy']
    modules = [p for p in paths if '/' not in p]
    children = {p: [] for p in paths}
    for p in paths:
        if '/' in p:
            children[p.rsplit('/', 1)[0]].append(p)
    related = {p: sum(matches(r, p) for r in records) for p in paths}
    primary = {p: sum(r['main'] == p or r['main'].startswith(p + '/') for r in records) for p in paths}
    papers = OrderedDict()
    for r in records:
        papers.setdefault((r['batch'], r['paper_id']), []).append(r)
    md = ['# 试卷分类题库 · 分类概况', '', '数据更新：' + data['updated'] + '（北京时间）。监测服务运行期间，本文件随分类数据变化自动同步。', '',
          f'当前{len(papers)}套试卷、{len(records)}道整题、{len(modules)}个主模块，{sum(bool(v) for v in related.values())}/{len(paths)}个分类节点已有题目。', '',
          '[打开动态分类概况](分类概况.html) · [打开阅读入口](阅读入口.html)', '',
          '自动监测入口是题库根目录的“打开题库.cmd”。直接打开HTML可阅读最近一次同步的离线副本。原始试卷新增后仍需先提取和分类，概况监测的是批次记录中的分类数据。', '',
          '## 模块概况', '', '|模块|主类别整题|全部相关整题|', '|---|---:|---:|']
    for m in modules:
        md.append(f'|{m}|{primary[m]}|{related[m]}|')
    md.extend(['', '相关题包含下级类别及小问命中，不同类别可引用同一题，不能将各类相关题数相加作为总题数。', '',
               '## 试卷来源', '', '|批次|试卷编号|试卷|题数|', '|---|---|---|---:|'])
    for (batch, pid), rs in papers.items():
        md.append(f'|{batch}|{pid}|{rs[0]["paper_label"]}|{len(rs)}|')
    md.extend(['', '## 分类结构与题目', '', '题目按直接标注的知识点列出；下级题目在下级类别查看。', ''])
    def node(path):
        md.extend(['#' * min(6, path.count('/') + 3) + ' ' + path.split('/')[-1], '', f'类别路径：`{path}`；主类别{primary[path]}题，相关{related[path]}题。', ''])
        direct = [r for r in records if path in r['tags']]
        for r in direct:
            badges = []
            if r['main'] == path:
                badges.append('主类别')
            if path in r['related']:
                badges.append('相关知识点')
            locators = [s['locator'] for s in r['subquestions'] if path in s['topics']]
            if locators:
                badges.append('小问：' + '、'.join(locators))
            label = f'{r["batch"]} · {r["id"]} · {r["paper_label"]}第{r["number"]}题 · {r["title"]}'
            md.append('- [' + label.replace('[', '［').replace(']', '］') + '](' + quote(r['relative_path'], safe='/') + ') — ' + '；'.join(badges))
        if not direct:
            md.append('暂无题目。' if not related[path] else '本节点无直接标注题目，相关题目见下级。')
        md.append('')
        for child in children[path]:
            node(child)
    for module in modules:
        node(module)
    atomic_write(ROOT / '分类概况.md', '\n'.join(md) + '\n')

class Catalog:
    def __init__(self):
        self.lock = threading.RLock()
        self.signature = None
        self.data = None
        self.error = None
        self.refresh()

    def refresh(self):
        with self.lock:
            try:
                before = fingerprint()
                if before == self.signature and self.data is not None and not self.error:
                    return
                data = read_catalog()
                after = fingerprint()
                if before != after:
                    return  # A producer is still writing; retry on the next cycle.
                if self.data is None or data['version'] != self.data['version']:
                    snapshot(data)
                self.data, self.signature, self.error = data, after, None
            except Exception as exc:
                self.error = str(exc)

    def watch(self):
        while True:
            time.sleep(1)
            self.refresh()

    def payload(self):
        self.refresh()
        with self.lock:
            return {**(self.data or {'records': [], 'taxonomy': [], 'batches': [], 'version': ''}), 'monitoring': True, 'error': self.error}

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def end_headers(self):
        self.send_header('Cache-Control', 'no-store')
        super().end_headers()

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == '/api/health':
            return self.send_json({'app': 'chemistry-bank-live', 'root': str(ROOT), 'pid': os.getpid(), 'uiVersion': UI_VERSION})
        if path == '/api/catalog':
            data = self.server.catalog.payload()
            requested = parse_qs(urlsplit(self.path).query).get('version', [''])[0]
            if requested and requested == data['version']:
                data = {k: data.get(k) for k in ['version', 'updated', 'monitoring', 'error']}
                data['unchanged'] = True
            return self.send_json(data)
        super().do_GET()

    def send_json(self, data):
        encoded = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, *args):
        pass

def open_existing():
    try:
        state = json.loads(STATE.read_text(encoding='utf-8'))
        address = 'http://127.0.0.1:' + str(int(state['port'])) + '/'
        with urlopen(address + 'api/health', timeout=2) as response:
            health = json.load(response)
        if health.get('app') == 'chemistry-bank-live' and health.get('root') == str(ROOT) and health.get('uiVersion') == UI_VERSION:
            # Every launch checks current classification files before showing the page.
            with urlopen(address + 'api/catalog', timeout=10) as response:
                json.load(response)
            webbrowser.open(address + quote('阅读入口.html'))
            return True
    except (OSError, ValueError, KeyError):
        pass
    return False

def serve(port, open_browser=False):
    catalog = Catalog()
    if catalog.data is None:
        raise RuntimeError('无法读取分类数据：' + str(catalog.error))
    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    server.catalog = catalog
    actual_port = server.server_address[1]
    atomic_write(STATE, json.dumps({'root': str(ROOT), 'pid': os.getpid(), 'port': actual_port, 'url': f'http://127.0.0.1:{actual_port}/'}, ensure_ascii=False, indent=2))
    atomic_write(ROOT / '题库工具' / 'live.js', 'window.CHEM_BANK_LIVE=' + json.dumps({'url': f'http://127.0.0.1:{actual_port}/', 'uiVersion': UI_VERSION}) + ';\n')
    threading.Thread(target=catalog.watch, daemon=True).start()
    if open_browser:
        threading.Thread(target=lambda: webbrowser.open(f'http://127.0.0.1:{actual_port}/' + quote('阅读入口.html')), daemon=True).start()
    print('Live catalog on 127.0.0.1:' + str(actual_port), flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()
        try:
            if json.loads(STATE.read_text(encoding='utf-8'))['pid'] == os.getpid():
                STATE.unlink()
        except (OSError, ValueError, KeyError):
            pass

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=0)
    parser.add_argument('--snapshot', action='store_true')
    parser.add_argument('--open', action='store_true')
    parser.add_argument('--update', action='store_true', help='Rebuild the classified catalog and shared entry pages before opening.')
    args = parser.parse_args()
    if args.snapshot:
        data = read_catalog()
        snapshot(data)
        print(json.dumps({'questions': len(data['records']), 'batches': len(data['batches']), 'taxonomy': len(data['taxonomy'])}))
    else:
        try:
            if args.update:
                snapshot(read_catalog())
            if not (args.open and open_existing()):
                serve(args.port, open_browser=args.open)
        except Exception:
            (ROOT/'题库工具'/'运行错误.log').write_text(traceback.format_exc(),encoding='utf-8')
            if args.open:
                webbrowser.open((ROOT/'阅读入口.html').as_uri())
            raise
