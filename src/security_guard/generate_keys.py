"""Generate a release Ed25519 key pair for the offline license issuer."""

from __future__ import annotations

import argparse
import base64
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def main() -> int:
    parser = argparse.ArgumentParser(description="生成离线许可证签发密钥")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    private = Ed25519PrivateKey.generate()
    private_path = args.output_dir / "private_key.pem"
    public_path = args.output_dir / "public_key.txt"
    private_path.write_bytes(
        private.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    private_path.chmod(0o600)
    public_raw = private.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    public_path.write_text(base64.b64encode(public_raw).decode("ascii") + "\n", encoding="ascii")
    print(f"私钥：{private_path}")
    print(f"公钥：{public_path}")
    print("将 public_key.txt 的内容填入 license.py 的 PUBLIC_KEY_B64；private_key.pem 只保存在你自己的电脑。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
