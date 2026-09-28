"""Signed, offline licenses with a small local activation footprint.

The private signing key is never shipped with the application.  The client
only contains the public key and can therefore verify licenses without a
network connection.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import platform
import secrets
import subprocess
import sys
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


APP_ID = "donghuakoubo"
LICENSE_DIR = Path.home() / f".{APP_ID}"
LICENSE_PATH = LICENSE_DIR / "license.json"
INSTALL_ID_PATH = LICENSE_DIR / "install-id"

# Replaced during release-key generation.  It is safe to ship a public key.
PUBLIC_KEY_B64 = "NnmbvNlTD5O2eRIqq7n++koLjVsVf+lsAVdnpKqa3mM="


class LicenseError(RuntimeError):
    """Raised when a local license is missing or invalid."""


@dataclass(frozen=True)
class LicenseInfo:
    customer: str
    machine_code: str
    expires_at: date
    features: tuple[str, ...]
    license_id: str


def _canonical_payload(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _read_or_create_install_id() -> str:
    try:
        if INSTALL_ID_PATH.is_file():
            value = INSTALL_ID_PATH.read_text(encoding="ascii").strip()
            if value:
                return value
        INSTALL_ID_PATH.parent.mkdir(parents=True, exist_ok=True)
        value = secrets.token_hex(16)
        INSTALL_ID_PATH.write_text(value + "\n", encoding="ascii")
        try:
            INSTALL_ID_PATH.chmod(0o600)
        except OSError:
            pass
        return value
    except OSError:
        # Read-only environments still get a stable value for the process.
        return "ephemeral:" + platform.node()


def _system_identifier() -> str:
    parts = [platform.system(), platform.release(), platform.machine(), platform.node()]
    if sys.platform == "linux":
        for path in (Path("/etc/machine-id"), Path("/var/lib/dbus/machine-id")):
            try:
                value = path.read_text(encoding="utf-8").strip()
            except OSError:
                value = ""
            if value:
                parts.append(value)
                break
    elif sys.platform == "darwin":
        try:
            result = subprocess.run(
                ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            )
            for line in result.stdout.splitlines():
                if "IOPlatformUUID" in line:
                    parts.append(line.split("=", 1)[-1].strip().strip('"'))
                    break
        except (OSError, subprocess.SubprocessError):
            pass
    return "|".join(parts)


def current_machine_code() -> str:
    """Return a stable, non-reversible code suitable for manual activation."""
    raw = f"{APP_ID}|{_read_or_create_install_id()}|{_system_identifier()}".encode("utf-8")
    digest = hashlib.sha256(raw).digest()
    return base64.b32encode(digest[:15]).decode("ascii").rstrip("=")


def _decode_public_key() -> Ed25519PublicKey:
    if PUBLIC_KEY_B64.startswith("REPLACE_"):
        raise LicenseError("当前版本尚未配置发布公钥")
    try:
        return Ed25519PublicKey.from_public_bytes(base64.b64decode(PUBLIC_KEY_B64))
    except (ValueError, TypeError) as exc:
        raise LicenseError("发布公钥配置无效") from exc


def verify_license(document: dict[str, Any], *, today: date | None = None) -> LicenseInfo:
    """Verify a license document and return its normalized information."""
    if not isinstance(document, dict):
        raise LicenseError("许可证格式无效")
    payload = document.get("payload")
    encoded_signature = document.get("signature")
    if not isinstance(payload, dict) or not isinstance(encoded_signature, str):
        raise LicenseError("许可证缺少签名或内容")
    try:
        signature = base64.b64decode(encoded_signature, validate=True)
        _decode_public_key().verify(signature, _canonical_payload(payload))
    except (ValueError, InvalidSignature) as exc:
        raise LicenseError("许可证签名无效") from exc

    machine_code = str(payload.get("machine_code", "")).strip().upper()
    if machine_code != current_machine_code():
        raise LicenseError("许可证不是当前设备的许可证")
    try:
        expires_at = date.fromisoformat(str(payload["expires_at"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise LicenseError("许可证有效期无效") from exc
    if (today or datetime.now(timezone.utc).date()) > expires_at:
        raise LicenseError(f"许可证已于 {expires_at.isoformat()} 到期")
    features = tuple(str(item) for item in payload.get("features", []) if str(item).strip())
    return LicenseInfo(
        customer=str(payload.get("customer", "")).strip(),
        machine_code=machine_code,
        expires_at=expires_at,
        features=features,
        license_id=str(payload.get("license_id", "")).strip(),
    )


def load_license(path: Path = LICENSE_PATH) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise LicenseError("尚未安装许可证") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise LicenseError("无法读取许可证文件") from exc
    if not isinstance(payload, dict):
        raise LicenseError("许可证文件格式无效")
    return payload


def save_license(document: dict[str, Any], path: Path = LICENSE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
    try:
        path.chmod(0o600)
    except OSError:
        pass
