"""Build only the pinned pilot sample. Original question bank is read-only input."""
from pathlib import Path
from collections import defaultdict
from urllib.parse import urlsplit,unquote
from html.parser import HTMLParser
import argparse,hashlib,json,mimetypes,os,re,time

HERE=Path(__file__).resolve().parent
REPO=HERE.parent
BANK=REPO/'02_设定层'/'试卷分类题库'
if os.name=='nt':BANK=Path('\\\\?\\'+str(BANK))
def sha(data):return hashlib.sha256(data).hexdigest()
def js(value):return json.dumps(value,ensure_ascii=False,separators=(',',':'))
def read_json(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def tags(r):return list(dict.fromkeys([r['main']]+r['related']+[t for s in r['subquestions'] for t in s['topics']]))
class Resources(HTMLParser):
    def __init__(self):super().__init__();self.refs=[]
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag=='img' and a.get('src'):self.refs.append(a['src'])

def pin_sample():
    if (HERE/'sample.json').exists():return
    selected=[]
    for path in sorted((BANK/'批次记录').glob('*/分类数据.json')):
        doc=read_json(path);records=doc['records'];chosen=[]
        # Include each main module, then rich image/formula examples and a stable spread.
        modules=sorted({r['main'].split('/')[0] for r in records})
        for module in modules:
            options=[r for r in records if r['main'].split('/')[0]==module]
            chosen.append(max(options,key=lambda r:r.get('images',0)+r.get('maths',0)+len(r['subquestions'])*10))
        for r in sorted(records,key=lambda r:-(r.get('images',0)+r.get('maths',0)+len(r['subquestions'])*10)):
            if len(chosen)>=10:break
            if r not in chosen:chosen.append(r)
        for r in sorted(records,key=lambda r:sha((doc['batch']+':'+r['id']).encode())):
            if len(chosen)>=20:break
            if r not in chosen:chosen.append(r)
        selected.extend(doc['batch']+':'+r['id'] for r in chosen)
    (HERE/'sample.json').write_text(js({'keys':sorted(selected),'baseline':'bb6463c7bc9393d71739299722fe8f91b477f53d'}),encoding='utf-8')

def build(out,overrides=None):
    start=time.perf_counter();pin_sample();wanted=set(read_json(HERE/'sample.json')['keys'])
    outputs={};assets={};styles={};bundles=defaultdict(dict);records=[];original_files={};evidence=[];taxonomy=[]
    def put(path,data):outputs[path]=data if isinstance(data,bytes) else data.encode('utf-8')
    for source in sorted((BANK/'批次记录').glob('*/分类数据.json')):
        doc=read_json(source);batch=doc['batch'];taxonomy.extend(doc['taxonomy'])
        for r in doc['records']:
            key=batch+':'+r['id']
            if key not in wanted:continue
            page=BANK/r['relative_path'];raw=page.read_bytes();html=raw.decode('utf-8-sig');original_files[str(page)]=len(raw)
            original_html=html
            if overrides and key in overrides:html=html.replace('</body>',overrides[key]+'</body>')
            style_replacements={}
            def style_replace(m):
                value=m.group(0);digest=sha(value.encode());styles[digest]=value;token='<!--chem-style:'+digest+'-->';style_replacements[token]=value;return token
            html=re.sub(r'<style\b[^>]*>.*?</style>',style_replace,html,flags=re.I|re.S)
            parser=Resources();parser.feed(html);replacements={};asset_hashes=[]
            for ref_index,ref in enumerate(dict.fromkeys(parser.refs)):
                url=urlsplit(ref)
                if url.scheme=='data':continue
                if url.scheme or url.netloc:raise ValueError('External image in '+key)
                path=Path(os.path.normpath(page.parent/unquote(url.path)))
                if not path.is_relative_to(BANK):raise ValueError('Asset outside bank '+ref)
                data=path.read_bytes();digest=sha(data);original_files[str(path)]=len(data)
                assets[digest]={'data':data,'mime':mimetypes.guess_type(str(path))[0] or 'application/octet-stream'}
                token='chem-asset:'+digest+':'+str(ref_index)+';';replacements[token]=ref;asset_hashes.append(digest)
                html=html.replace('"'+ref+'"','"'+token+'"').replace("'"+ref+"'","'"+token+"'")
            # Stable partition depends only on batch and immutable question id.
            bucket=sha(batch.encode())[:12]+'-'+sha(r['id'].encode())[0]
            pack='questions/'+bucket+'.json'
            bundles[pack][key]={'html':html,'assets':sorted(set(asset_hashes)),'sourceSha256':sha(raw)}
            restored=html
            for token,value in style_replacements.items():restored=restored.replace(token,value)
            for token,value in replacements.items():restored=restored.replace(token,value)
            expected=original_html if not overrides or key not in overrides else original_html.replace('</body>',overrides[key]+'</body>')
            if restored!=expected:raise ValueError('Content round-trip mismatch '+key)
            keep=['id','number','paper_id','paper_label','title','main','related','subquestions','text','question_type']
            record={k:r.get(k,'') for k in keep};record.update(batch=batch,key=key,tags=tags(r),pack=pack,relative_path='reader.html#'+key)
            records.append(record)
            evidence.append({'key':key,'path':r['relative_path'],'htmlSha256':sha(raw),'images':len(parser.refs),'uniqueImages':len(set(asset_hashes)),'mathml':len(re.findall(r'<math\b',original_html)),'tables':len(re.findall(r'<table\b',original_html)),'subquestions':len(r['subquestions'])})
    if len(records)!=len(wanted):raise ValueError('Sample question missing')
    asset_index={};asset_buckets=defaultdict(list)
    for digest in sorted(assets):asset_buckets[digest[0]].append(digest)
    for bucket,digests in sorted(asset_buckets.items()):
        chunks=[];offset=0;filename='assets/'+bucket+'.pack'
        for digest in digests:
            item=assets[digest];data=item['data'];asset_index[digest]={'pack':filename,'offset':offset,'length':len(data),'mime':item['mime']};chunks.append(data);offset+=len(data)
        put(filename,b''.join(chunks))
    for path,items in bundles.items():put(path,js(dict(sorted(items.items()))))
    put('asset-index.json',js(asset_index));put('styles.json',js(styles))
    catalog={'records':records,'taxonomy':list(dict.fromkeys(taxonomy)),'batches':sorted({r['batch'] for r in records}),'updated':'180题试验 · 基线2026-10-27'}
    catalog['version']=sha(js(catalog).encode())
    put('题库工具/catalog.js','window.CHEM_BANK='+js(catalog)+';\n')
    put('题库工具/live.js','window.CHEM_BANK_LIVE=null;\n')
    put('题库工具/app.css',(BANK/'题库工具'/'app.css').read_bytes())
    app=(BANK/'题库工具'/'app.js').read_text(encoding='utf-8')
    app=app.replace("const questionUrl = record => new URL(encodePath(record.relative_path), document.baseURI).href;","const questionUrl = record => new URL('reader.html#' + encodeURIComponent(record.key), document.baseURI).href;")
    app=app.replace("const isLive = location.protocol === 'http:' || location.protocol === 'https:';","const isLive = false;")
    app=app.replace("chemistry-bank-workbench-v2","chemistry-packed-pilot-v1")
    app=app.replace('src="${esc(url)}"','src="about:blank"')
    app=app.replace('prepareFrame(); lastResults =','prepareFrame(); window.ChemPacked.preview(record.key, $(\'#question-frame\')); lastResults =')
    app=app.replace("'离线副本 · 分类数据更新：' + catalog.updated + '。双击“更新题库”可同步并进入实时页面。'","'180题试验版 · 共享阅读器 · 正式题库仍保留原入口。'")
    app=app.replace('href="分类概况.md"','href="说明.html"').replace('href="阅读说明.md"','href="说明.html"').replace('href="题库维护说明.md"','href="说明.html"')
    put('题库工具/app.js',app)
    template=(BANK/'题库工具'/'page.html').read_text(encoding='utf-8').replace('{{BASE}}','./').replace('{{VIEW}}','library')
    template=template.replace('高中化学 · 知识点题库','高中化学 · 180题试验版').replace('知识点 / 题目 / 关联','180题试验版 / 9个批次')
    template=template.replace('<script src="题库工具/app.js?v=2">','<script src="packed.js"></script><script src="题库工具/app.js?v=2">')
    put('index.html',template)
    for filename in ['packed.js','reader.html','reader.js','说明.html']:put(filename,(HERE/'web'/filename).read_bytes())
    hashes={path:{'bytes':len(data),'sha256':sha(data)} for path,data in sorted(outputs.items())}
    put('manifest.json',js({'schema':1,'files':hashes,'questions':len(records),'assets':len(assets)}))
    changed=[];out.mkdir(parents=True,exist_ok=True)
    for path,data in sorted(outputs.items()):
        dest=out/path;dest.parent.mkdir(parents=True,exist_ok=True)
        if not dest.exists() or dest.read_bytes()!=data:dest.write_bytes(data);changed.append(path)
    unexpected=sorted(p.relative_to(out).as_posix() for p in out.rglob('*') if p.is_file() and p.relative_to(out).as_posix() not in outputs)
    if unexpected:raise ValueError('Stale outputs require explicit review: '+str(unexpected))
    result={'questions':len(records),'batches':len(catalog['batches']),'uniqueAssets':len(assets),'questionPacks':len(bundles),'assetPacks':len(asset_buckets),'original':{'files':len(original_files),'bytes':sum(original_files.values())},'reading':{'files':len(outputs),'bytes':sum(len(v) for v in outputs.values())},'changed':changed,'seconds':round(time.perf_counter()-start,3),'evidence':evidence}
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,default=HERE/'reading');args=parser.parse_args()
    result=build(args.out)
    (HERE/'build-report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    (HERE/'qa'/'sources.json').write_text(js({r['key']:r['path'] for r in result['evidence']}),encoding='utf-8')
    (HERE/'qa'/'evidence.json').write_text(js(result['evidence']),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='evidence'},ensure_ascii=True))
