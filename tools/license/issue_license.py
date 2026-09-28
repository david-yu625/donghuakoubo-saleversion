"""Seller-only license signing implementation."""

from __future__ import annotations

import argparse
import base64
import json
import uuid
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization

from src.security_guard.license import _canonical_payload


def issue_license(
    *,
    private_key_path: Path,
    machine_code: str,
    customer: str,
    expires_at: date,
    features: list[str],
    license_id: str | None = None,
) -> dict[str, Any]:
    key = serialization.load_pem_private_key(private_key_path.read_bytes(), password=None)
    payload: dict[str, Any] = {
        "customer": customer.strip(),
        "machine_code": machine_code.strip().upper(),
        "expires_at": expires_at.isoformat(),
        "features": sorted({item.strip() for item in features if item.strip()}),
        "license_id": license_id or f"lic_{uuid.uuid4().hex[:12]}",
    }
    signature = key.sign(_canonical_payload(payload))
    return {"payload": payload, "signature": base64.b64encode(signature).decode("ascii")}


def main() -> int:
    parser = argparse.ArgumentParser(description="签发动画口播软件离线许可证")
    parser.add_argument("--private-key", type=Path, required=True)
    parser.add_argument("--machine-code", required=True)
    parser.add_argument("--customer", default="")
    parser.add_argument("--expires", type=date.fromisoformat)
    parser.add_argument("--days", type=int, default=365)
    parser.add_argument("--features", default="image,voice,render")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    expires_at = args.expires or (date.today() + timedelta(days=args.days))
    document = issue_license(
        private_key_path=args.private_key,
        machine_code=args.machine_code,
        customer=args.customer,
        expires_at=expires_at,
        features=args.features.split(","),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"许可证已生成：{args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
