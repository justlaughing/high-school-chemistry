"""Build the entire bank; keep original content and emit only changed packages."""
from pathlib import Path
from collections import defaultdict
from html.parser import HTMLParser
from urllib.parse import urlsplit,unquote
import argparse,hashlib,json,mimetypes,os,re,time

HERE=Path(__file__).resolve().parent
def lp(p):return Path('\\\\?\\'+str(p)) if os.name=='nt' and not str(p).startswith('\\\\?\\') else p
BANK=lp(HERE.parent/'试卷分类题库');DEFAULT_OUT=lp(HERE.parent/'题库阅读版');WEB=HERE/'web'
def sha(b):return hashlib.sha256(b).hexdigest()
def js(v):return json.dumps(v,ensure_ascii=False,separators=(',',':'))
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def atomic(p,data):
    p.parent.mkdir(parents=True,exist_ok=True);temp=p.with_name(p.name+'.writing');temp.write_bytes(data);os.replace(temp,p)
class Images(HTMLParser):
    def __init__(self):super().__init__();self.refs=[]
    def handle_starttag(self,t,attrs):
        a=dict(attrs)
        if t=='img' and a.get('src'):self.refs.append(a['src'])
def classify():
    docs=[];seen=set()
    for p in sorted((BANK/'批次记录').glob('*/分类数据.json')):
        d=read(p)
        for r in d['records']:
            key=d['batch']+':'+r['id']
            if key in seen:raise ValueError('重复题号：'+key)
            seen.add(key)
            if not isinstance(r['related'],list) or not isinstance(r['subquestions'],list):raise ValueError('分类结构无效：'+key)
        docs.append(d)
    if not docs:raise ValueError('没有有效批次，保留上次题库')
    return docs
def fingerprint(out,docs,source_assets):
    h=hashlib.sha256()
    h.update(js(docs).encode())
    for p in sorted(WEB.glob('*')):
        if p.is_file():h.update(p.name.encode());h.update(p.read_bytes())
    h.update(Path(__file__).read_bytes())
    for pattern in ['questions/*.json','asset-index.json','styles.json','manifest.json']:
        for p in sorted(out.glob(pattern)):h.update(p.name.encode());h.update(p.read_bytes())
    for p in sorted((out/'assets').glob('*.pack')):
        s=p.stat();h.update(f'{p.name}:{s.st_size}:{s.st_mtime_ns}'.encode())
    for d in docs:
        for r in d['records']:
            p=Path(os.path.normpath(BANK/r['relative_path']))
            if p.is_file():s=p.stat();h.update(f'{p}:{s.st_size}:{s.st_mtime_ns}'.encode())
    for value in source_assets:
        p=Path(value)
        if p.is_file():s=p.stat();h.update(f'{p}:{s.st_size}:{s.st_mtime_ns}'.encode())
    return h.hexdigest()

def _build(out=DEFAULT_OUT,force=False,overrides=None,metadata_overrides=None):
    out=lp(out.resolve());began=time.perf_counter();docs=classify();state_path=HERE/'build-state.json'
    oldstate=read(state_path) if state_path.exists() else {}
    if not force and not overrides and not metadata_overrides and oldstate.get('out')==str(out):
        if fingerprint(out,docs,oldstate.get('sourceAssets',[]))==oldstate.get('fingerprint'):
            result={**read(HERE/'build-report.json'),'changed':[],'seconds':round(time.perf_counter()-began,3),'cached':True}
            return result
    previous={}
    for p in sorted((out/'questions').glob('*.json')):previous.update(read(p))
    prior_index=read(out/'asset-index.json') if (out/'asset-index.json').exists() else {}
    styles=read(out/'styles.json') if (out/'styles.json').exists() else {}
    outputs={};assets={};source_assets=set();styles_used=set();bundles=defaultdict(dict);records=[];evidence=[];original_files={};taxonomy=[]
    def put(path,data):outputs[path]=data if isinstance(data,bytes) else data.encode('utf-8')
    for d in docs:
        batch=d['batch'];taxonomy.extend(d['taxonomy'])
        for raw in d['records']:
            r={**raw};key=batch+':'+r['id']
            if metadata_overrides and key in metadata_overrides:r.update(metadata_overrides[key])
            page=Path(os.path.normpath(BANK/r['relative_path']))
            if not page.is_relative_to(BANK):raise ValueError('题目路径超出题库：'+key)
            if page.is_file():
                data=page.read_bytes();html=data.decode('utf-8-sig');original_files[str(page)]=len(data);content_sha=sha(data);bom=data.startswith(b'\xef\xbb\xbf')
                def replace_style(m):
                    value=m.group(0);digest=sha(value.encode());styles[digest]=value;return '<!--chem-style:'+digest+'-->'
                html=re.sub(r'<style\b[^>]*>.*?</style>',replace_style,html,flags=re.I|re.S)
                parser=Images();parser.feed(html);refs={};hashes=[]
                for i,ref in enumerate(dict.fromkeys(parser.refs)):
                    url=urlsplit(ref)
                    if url.scheme=='data':continue
                    if url.scheme or url.netloc:raise ValueError('外部图片：'+key)
                    path=Path(os.path.normpath(page.parent/unquote(url.path)))
                    if not path.is_relative_to(BANK):raise ValueError('图片路径超出题库：'+ref)
                    image=path.read_bytes();digest=sha(image);source_assets.add(str(path));original_files[str(path)]=len(image)
                    assets[digest]={'path':path,'mime':mimetypes.guess_type(str(path))[0] or 'application/octet-stream','length':len(image)}
                    token='chem-asset:'+digest+':'+str(i)+';';refs[token]=ref;hashes.append(digest)
                    html=html.replace('"'+ref+'"','"'+token+'"').replace("'"+ref+"'","'"+token+"'")
                question={'html':html,'assets':sorted(set(hashes)),'refs':refs,'sourceSha256':content_sha,'bom':bom,'legacyPath':r['relative_path']}
            else:
                if key not in previous:raise ValueError('整题正文缺失：'+key+'；请先导入完整题目')
                question={**previous[key]};html=question['html']
                for digest in question['assets']:
                    if digest not in assets:
                        if digest not in prior_index:raise ValueError('已入库图片缺失：'+key)
                        item=prior_index[digest];assets[digest]={**item,'prior':True}
            if overrides and key in overrides:question={**question,'html':question['html'].replace('</body>',overrides[key]+'</body>')};html=question['html']
            for digest in re.findall(r'<!--chem-style:([a-f0-9]{64})-->',html):
                if digest not in styles:raise ValueError('原始样式缺失：'+key)
                styles_used.add(digest)
            restored=re.sub(r'<!--chem-style:([a-f0-9]{64})-->',lambda m:styles[m[1]],html)
            for token,ref in question['refs'].items():restored=restored.replace(token,ref)
            restored_bytes=(b'\xef\xbb\xbf' if question.get('bom') else b'')+restored.encode('utf-8')
            if overrides and key in overrides:question['sourceSha256']=sha(restored_bytes)
            if not overrides and sha(restored_bytes)!=question['sourceSha256']:raise ValueError('原题逐字还原失败：'+key)
            parser=Images();parser.feed(restored)
            pack='questions/'+sha(batch.encode())[:12]+'-'+sha(r['id'].encode())[0]+'.json'
            bundles[pack][key]=question
            fields=['id','number','paper_id','paper_label','title','main','related','subquestions','text','question_type']
            record={k:r.get(k,'') for k in fields}
            tags=list(dict.fromkeys([r['main']]+r['related']+[t for s in r['subquestions'] for t in s['topics']]))
            record.update(batch=batch,key=key,tags=tags,pack=pack,relative_path='reader.html#'+key);records.append(record)
            evidence.append({'key':key,'path':question['legacyPath'],'htmlSha256':question['sourceSha256'],'images':len(parser.refs),'mathml':len(re.findall(r'<math\b',restored)),'tables':len(re.findall(r'<table\b',restored)),'subquestions':len(r['subquestions'])})
        print(json.dumps({'batch':batch,'questionsProcessed':len(records)},ensure_ascii=True),flush=True)
    asset_index={};groups=defaultdict(list)
    for digest in sorted(assets):groups[digest[:2]].append(digest)
    for prefix,digests in sorted(groups.items()):
        chunks=[];offset=0;filename='assets/'+prefix+'.pack'
        for digest in digests:
            item=assets[digest]
            if item.get('prior'):
                with (out/item['pack']).open('rb') as f:f.seek(item['offset']);data=f.read(item['length'])
            else:data=item['path'].read_bytes()
            if sha(data)!=digest:raise ValueError('图片字节不一致：'+digest)
            asset_index[digest]={'pack':filename,'offset':offset,'length':len(data),'mime':item['mime']};chunks.append(data);offset+=len(data)
        put(filename,b''.join(chunks))
    for path,items in sorted(bundles.items()):put(path,js(dict(sorted(items.items()))))
    put('asset-index.json',js(asset_index));put('styles.json',js({k:styles[k] for k in sorted(styles_used)}))
    catalog={'records':records,'taxonomy':list(dict.fromkeys(taxonomy)),'batches':sorted({r['batch'] for r in records}),'updated':'全量分包阅读版'}
    catalog['version']=sha(js(catalog).encode());put('catalog.json',js(catalog));put('题库工具/catalog.js','window.CHEM_BANK='+js(catalog)+';\n');put('题库工具/live.js','window.CHEM_BANK_LIVE=null;\n')
    for name in ['app.css','packed.js','reader.js','reader.html','update.js','说明.html']:put('题库工具/'+name if name=='app.css' else name,(WEB/name).read_bytes())
    app=(WEB/'app-source.js').read_text(encoding='utf-8')
    replacements=[("const questionUrl = record => new URL(encodePath(record.relative_path), document.baseURI).href;","const questionUrl = record => new URL('reader.html#' + encodeURIComponent(record.key), document.baseURI).href;"),("const isLive = location.protocol === 'http:' || location.protocol === 'https:';","const isLive = false;"),('chemistry-bank-workbench-v2','chemistry-packed-reader-v1'),('src="${esc(url)}"','src="about:blank"'),('prepareFrame(); lastResults =',"prepareFrame(); window.ChemPacked.preview(record.key, $('#question-frame')); lastResults ="),("'离线副本 · 分类数据更新：' + catalog.updated + '。双击“更新题库”可同步并进入实时页面。'","catalog.records.length + '道整题 · 原题与分类来源保留'")]
    for before,after in replacements:
        if before not in app:raise ValueError('共享界面接入点已变化，保留上次产物：'+before[:50])
        app=app.replace(before,after)
    for filename in ['分类概况.md','阅读说明.md','题库维护说明.md']:app=app.replace('href="'+filename+'"','href="说明.html"')
    put('题库工具/app.js',app)
    template=(WEB/'page.html').read_text(encoding='utf-8').replace('{{BASE}}','./').replace('{{VIEW}}','library')
    template=template.replace('<script src="题库工具/app.js?v=2">','<script src="packed.js"></script><script src="题库工具/app.js?v=2">').replace('</body>','<script src="update.js"></script></body>')
    put('index.html',template)
    hashes={p:{'bytes':len(data),'sha256':sha(data)} for p,data in sorted(outputs.items())}
    put('manifest.json',js({'schema':2,'files':hashes,'questions':len(records),'assets':len(assets),'contentVersion':catalog['version']}))
    # Validate all input before publishing; publish the manifest last.
    out.mkdir(parents=True,exist_ok=True);changed=[]
    for path in sorted(outputs,key=lambda p:(p=='manifest.json',p)):
        dest=out/path;data=outputs[path]
        if not dest.exists() or dest.read_bytes()!=data:atomic(dest,data);changed.append(path)
    # Unreferenced old packs are retained until an explicit release cleanup; readers never use them.
    stale=[p.relative_to(out).as_posix() for p in out.rglob('*') if p.is_file() and p.relative_to(out).as_posix() not in outputs]
    result={'schema':2,'questions':len(records),'batches':len(docs),'uniqueAssets':len(assets),'questionPacks':len(bundles),'assetPacks':len(groups),'largestAssetPackBytes':max(len(outputs['assets/'+k+'.pack']) for k in groups),'original':{'files':len(original_files),'bytes':sum(original_files.values())},'reading':{'files':len(outputs),'bytes':sum(map(len,outputs.values()))},'changed':changed,'stale':stale,'seconds':round(time.perf_counter()-began,3),'evidence':evidence}
    if not overrides and not metadata_overrides:
        if not result['original']['files'] and (HERE/'build-report.json').exists():result['original']=read(HERE/'build-report.json')['original']
        atomic(HERE/'build-report.json',json.dumps(result,ensure_ascii=False,indent=2).encode())
        atomic(HERE/'content-index.json',js({r['key']:{'pack':r['pack'],'legacyPath':next(e['path'] for e in evidence if e['key']==r['key'])} for r in records}).encode())
        atomic(HERE/'qa'/'sources.json',js({e['key']:e['path'] for e in evidence}).encode());atomic(HERE/'qa'/'evidence.json',js(evidence).encode())
        state={'out':str(out),'sourceAssets':sorted(source_assets),'fingerprint':fingerprint(out,docs,source_assets)};atomic(state_path,js(state).encode())
    return result

def build(out=DEFAULT_OUT,force=False,overrides=None,metadata_overrides=None):
    lock=HERE/'build.lock';deadline=time.monotonic()+90
    while True:
        try:
            fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY);os.write(fd,str(os.getpid()).encode());os.close(fd);break
        except FileExistsError:
            try:
                pid=int(lock.read_text())
                if os.name=='nt':
                    import ctypes
                    from ctypes import wintypes
                    kernel=ctypes.WinDLL('kernel32',use_last_error=True);kernel.OpenProcess.restype=wintypes.HANDLE;handle=kernel.OpenProcess(0x1000,False,pid)
                    if handle:
                        code=wintypes.DWORD();kernel.GetExitCodeProcess.argtypes=[wintypes.HANDLE,ctypes.POINTER(wintypes.DWORD)];kernel.GetExitCodeProcess(handle,ctypes.byref(code));kernel.CloseHandle.argtypes=[wintypes.HANDLE];kernel.CloseHandle(handle);alive=code.value==259
                    else:alive=ctypes.get_last_error()==5
                else:
                    try:os.kill(pid,0);alive=True
                    except ProcessLookupError:alive=False
                if not alive:lock.unlink();continue
            except (ValueError,FileNotFoundError):pass
            if time.monotonic()>deadline:raise RuntimeError('题库正在更新，请稍后再试')
            time.sleep(.2)
    try:return _build(out,force,overrides,metadata_overrides)
    finally:lock.unlink(missing_ok=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--force',action='store_true');args=p.parse_args();r=build(force=args.force)
    print(json.dumps({k:v for k,v in r.items() if k not in ['evidence','changed']},ensure_ascii=True));print(json.dumps({'rewrittenFiles':len(r['changed'])}))
