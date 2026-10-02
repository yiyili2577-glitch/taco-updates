from __future__ import annotations

import argparse
import base64
from pathlib import Path

from cryptography.hazmat.primitives.serialization import load_pem_private_key

from desktop_app.updater import build_manifest, canonical_manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="建立 TACO 已簽署更新發佈檔")
    parser.add_argument("package", type=Path)
    parser.add_argument("--private-key", required=True, type=Path, help="只能指向外部離線 Ed25519 私鑰")
    parser.add_argument("--version", required=True)
    parser.add_argument("--channel", choices=("stable", "beta", "internal"), default="stable")
    parser.add_argument("--url", required=True)
    parser.add_argument("--min-version", default="6.9.0")
    parser.add_argument("--schema-version", type=int, default=2)
    parser.add_argument("--published-at", required=True)
    parser.add_argument("--release-notes", default="")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    key_path = args.private_key.resolve()
    if args.output.resolve() in key_path.parents or key_path == args.output.resolve():
        raise SystemExit("私鑰不可位於發佈輸出目錄")
    key = load_pem_private_key(key_path.read_bytes(), password=None)
    manifest = build_manifest(args.package, args.version, args.channel, args.url, args.min_version,
                              args.schema_version, args.published_at, args.release_notes)
    raw = canonical_manifest(manifest)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "manifest.json").write_bytes(raw)
    (args.output / "manifest.sig").write_text(base64.b64encode(key.sign(raw)).decode("ascii"), encoding="ascii")


if __name__ == "__main__":
    main()
