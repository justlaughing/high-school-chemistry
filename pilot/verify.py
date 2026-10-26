"""Check emitted pack hashes and no-op/single-question incremental behavior."""
from pathlib import Path
import hashlib,json,tempfile
from build import build,HERE,read_json,sha

def inventory(root):return {p.relative_to(root).as_posix():(sha(p.read_bytes()),p.stat().st_mtime_ns) for p in root.rglob('*') if p.is_file()}
root=HERE/'reading';initial=inventory(root);baseline=read_json(root/'manifest.json')
for name,item in baseline['files'].items():
    data=(root/name).read_bytes()
    assert len(data)==item['bytes'] and sha(data)==item['sha256'],name
assets=read_json(root/'asset-index.json')
for digest,item in assets.items():
    with (root/item['pack']).open('rb') as f:f.seek(item['offset']);data=f.read(item['length'])
    assert sha(data)==digest,digest
noop=build(root);assert not noop['changed'];assert inventory(root)==initial
key=read_json(HERE/'sample.json')['keys'][0]
try:
    modified=build(root,{key:'<!--incremental-verification-only-->'})
    changed=modified['changed'];assert len([p for p in changed if p.startswith('questions/')])==1
    assert set(changed)-{'manifest.json'}=={p for p in changed if p.startswith('questions/')}
    assert not any(p.startswith('assets/') for p in changed)
finally:restored=build(root)
assert {p:v[0] for p,v in inventory(root).items()}=={p:v[0] for p,v in initial.items()}
result={'verified':True,'verifiedReadingFiles':len(baseline['files'])+1,'verifiedAssetByteHashes':len(assets),'noopRewrittenFiles':len(noop['changed']),'singleQuestionChangedFiles':changed,'restoredAllOutputHashes':True,'contentRoundTripQuestions':noop['questions'],'evidence':noop['evidence']}
(HERE/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in result.items() if k!='evidence'}))
