"""Verify every emitted file, image slice and reconstructed original question."""
from pathlib import Path
import argparse,json,re,time
from build import HERE,DEFAULT_OUT,read,sha,build,js,atomic
def inventory(root):return {p.relative_to(root).as_posix():(sha(p.read_bytes()),p.stat().st_mtime_ns) for p in root.rglob('*') if p.is_file()}
def verify(incremental=False):
    start=time.perf_counter();root=DEFAULT_OUT;manifest=read(root/'manifest.json');styles=read(root/'styles.json');assets=read(root/'asset-index.json');questions={}
    for name,expected in manifest['files'].items():
        data=(root/name).read_bytes()
        if len(data)!=expected['bytes'] or sha(data)!=expected['sha256']:raise ValueError('产物校验失败：'+name)
    packs={}
    for digest,info in assets.items():
        if info['pack'] not in packs:packs[info['pack']]=(root/info['pack']).read_bytes()
        data=packs[info['pack']][info['offset']:info['offset']+info['length']]
        if len(data)!=info['length'] or sha(data)!=digest:raise ValueError('图片还原失败：'+digest)
    for p in sorted((root/'questions').glob('*.json')):
        if p.relative_to(root).as_posix() in manifest['files']:questions.update(read(p))
    for key,q in questions.items():
        text=re.sub(r'<!--chem-style:([a-f0-9]{64})-->',lambda m:styles[m[1]],q['html'])
        for token,value in q['refs'].items():text=text.replace(token,value)
        raw=(b'\xef\xbb\xbf' if q.get('bom') else b'')+text.encode()
        if sha(raw)!=q['sourceSha256']:raise ValueError('原题逐字还原失败：'+key)
        if any(h not in assets for h in q['assets']):raise ValueError('图片未收录：'+key)
    result={'verified':True,'files':len(manifest['files'])+1,'questions':len(questions),'imageByteHashes':len(assets),'rawHtmlRoundTrip':len(questions)}
    if incremental:
        before=inventory(root);unchanged=build();assert unchanged['changed']==[];assert inventory(root)==before
        key=sorted(questions)[0]
        record=next(r for r in read(root/'catalog.json')['records'] if r['key']==key)
        rollback={name:(root/name).read_bytes() for name in ['manifest.json',record['pack'],'catalog.json','题库工具/catalog.js']}
        def restore():
            for name,data in rollback.items():atomic(root/name,data)
            build(force=True)
        try:
            changed=build(force=True,overrides={key:'<!--incremental-check-only-->'})['changed'];assert len([p for p in changed if p.startswith('questions/')])==1;assert set(changed)-{'manifest.json'}=={p for p in changed if p.startswith('questions/')}
        finally:restore()
        assert {p:v[0] for p,v in inventory(root).items()}=={p:v[0] for p,v in before.items()}
        result.update(noopRewrittenFiles=0,contentChangeFiles=changed,allHashesRestored=True)
        try:
            meta=build(force=True,metadata_overrides={key:{'title':'临时分类标题核验'}})['changed'];assert not any(p.startswith('assets/') or p.startswith('questions/') for p in meta)
        finally:restore()
        assert {p:v[0] for p,v in inventory(root).items()}=={p:v[0] for p,v in before.items()};result['metadataChangeFiles']=meta
    result['seconds']=round(time.perf_counter()-start,3);(HERE/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');return result
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--incremental',action='store_true');args=p.parse_args();print(json.dumps(verify(args.incremental),ensure_ascii=True))
