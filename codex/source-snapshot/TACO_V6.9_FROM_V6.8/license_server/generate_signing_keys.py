"""一次性產生 License Server 2.0 的 Ed25519 金鑰。

私鑰只留在 license_server/secret，絕對不要複製到客戶端或 Git。
Public Key 複製到 desktop_app/resources 後再 build TACO.exe。
"""
import argparse
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--desktop-resources", default="../desktop_app/resources")
    p.add_argument("--force", action="store_true")
    a = p.parse_args()
    base = Path(__file__).resolve().parent
    secret = base / "secret"; secret.mkdir(parents=True, exist_ok=True)
    priv_path = secret / "license_private_key.pem"
    pub_path = Path(a.desktop_resources).resolve() / "license_public_key.pem"
    if priv_path.exists() and not a.force:
        raise SystemExit(f"私鑰已存在：{priv_path}。如確定要換金鑰才使用 --force。")
    key = Ed25519PrivateKey.generate()
    priv_path.write_bytes(key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ))
    pub_path.parent.mkdir(parents=True, exist_ok=True)
    pub_path.write_bytes(key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ))
    print("License 私鑰：", priv_path)
    print("Desktop Public Key：", pub_path)
    print("警告：secret/ 只能留在伺服器，不可包進客戶 EXE。")


if __name__ == "__main__": main()
