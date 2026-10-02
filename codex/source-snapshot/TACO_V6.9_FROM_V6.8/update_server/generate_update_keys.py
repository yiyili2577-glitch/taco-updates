"""一次性產生更新簽章 Ed25519 金鑰。私鑰只留 update_server/secret。"""
import argparse
from pathlib import Path
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def main():
    p=argparse.ArgumentParser(); p.add_argument('--desktop-resources',default='../desktop_app/resources'); p.add_argument('--force',action='store_true'); a=p.parse_args()
    base=Path(__file__).resolve().parent; secret=base/'secret'; secret.mkdir(parents=True,exist_ok=True)
    priv=secret/'update_private_key.pem'; pub=Path(a.desktop_resources).resolve()/'update_public_key.pem'
    if priv.exists() and not a.force: raise SystemExit(f'私鑰已存在：{priv}。只有正式換鑰才使用 --force。')
    key=Ed25519PrivateKey.generate(); priv.write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption())); pub.parent.mkdir(parents=True,exist_ok=True); pub.write_bytes(key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo))
    print('Update 私鑰：',priv); print('Desktop Public Key：',pub); print('警告：secret/ 不可放進客戶安裝包。')
if __name__=='__main__': main()
