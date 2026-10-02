import base64
import json
import os
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def canonical_json_bytes(payload):
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def private_key_path():
    env = str(os.environ.get("LICENSE_PRIVATE_KEY_PATH", "")).strip()
    return Path(env) if env else Path(__file__).resolve().parent / "secret" / "license_private_key.pem"


def load_private_key():
    path = private_key_path()
    if not path.exists():
        raise RuntimeError(f"找不到 License Server 私鑰：{path}。請先執行 generate_signing_keys.py。")
    key = serialization.load_pem_private_key(path.read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise RuntimeError("License 私鑰不是 Ed25519。")
    return key


def sign_payload(payload):
    sig = load_private_key().sign(canonical_json_bytes(payload))
    return base64.b64encode(sig).decode("ascii")
