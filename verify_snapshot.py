from pathlib import Path
import hashlib,json,os
root=Path(__file__).resolve().parent
if os.name=='nt' and not str(root).startswith('\\\\?\\'):root=Path('\\\\?\\'+str(root))
manifest=json.loads((root/'backup-manifest.json').read_text(encoding='utf-8'))
for item in manifest['files']:
    path=root/item['path']
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=item['sha256']:
        raise SystemExit('Backup verification failed: '+item['path'])
print(json.dumps({'verified':True,'files':len(manifest['files']),'bytes':sum(x['bytes'] for x in manifest['files'])}))
