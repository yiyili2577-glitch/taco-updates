import base64
import json
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


def canonical_json_bytes(payload):
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def load_ed25519_public_key(path):
    raw = Path(path).read_bytes()
    key = serialization.load_pem_public_key(raw)
    if not isinstance(key, Ed25519PublicKey):
        raise ValueError("不是 Ed25519 public key。")
    return key


def verify_signed_payload(payload, signature_b64, public_key_path):
    key = load_ed25519_public_key(public_key_path)
    signature = base64.b64decode(signature_b64, validate=True)
    key.verify(signature, canonical_json_bytes(payload))
    return True
