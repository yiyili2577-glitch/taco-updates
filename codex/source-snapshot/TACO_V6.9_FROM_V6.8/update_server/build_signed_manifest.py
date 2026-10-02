import argparse, base64, hashlib, json
from datetime import datetime, timezone
from pathlib import Path
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def canonical(payload): return json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')
def sha256(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for c in iter(lambda:f.read(1024*1024),b''): h.update(c)
    return h.hexdigest()


def main():
    p=argparse.ArgumentParser(); p.add_argument('--package',required=True); p.add_argument('--version',required=True); p.add_argument('--url',required=True); p.add_argument('--published-on',default=''); p.add_argument('--channel',default='stable',choices=['stable','beta','internal']); p.add_argument('--min-version',default='6.8.0'); p.add_argument('--schema-version',type=int,default=2); p.add_argument('--notes',default=''); p.add_argument('--private-key',required=True,help='必須指向工作區外的離線 Ed25519 私鑰'); p.add_argument('--out',default='public/update.json'); a=p.parse_args()
    base=Path(__file__).resolve().parent; package=Path(a.package).resolve(); key_path=(base/a.private_key).resolve() if not Path(a.private_key).is_absolute() else Path(a.private_key)
    key=serialization.load_pem_private_key(key_path.read_bytes(),password=None)
    if not isinstance(key,Ed25519PrivateKey): raise SystemExit('private key 不是 Ed25519')
    out=(base/a.out).resolve()
    if base==key_path.parent or base in key_path.parents: raise SystemExit('私鑰必須位於專案工作區外')
    payload={
      'app':'taco_smart_procurement','channel':a.channel,'latest_version':a.version,'min_version':a.min_version,
      'published_on':a.published_on or datetime.now(timezone.utc).date().isoformat(),'notes':a.notes,'schema_version':a.schema_version,
      'packages':{'win-x64':{'filename':package.name,'url':a.url,'sha256':sha256(package),'size':package.stat().st_size}}
    }
    sig=base64.b64encode(key.sign(canonical(payload))).decode('ascii'); out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps({'manifest':payload,'signature':sig},ensure_ascii=False,indent=2),encoding='utf-8'); print(out)
if __name__=='__main__': main()
