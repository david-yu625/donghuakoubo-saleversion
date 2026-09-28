"""At-rest encryption for generated process artifacts.

Files are decrypted only while the local pipeline needs them. The encrypted
bytes stay at the original path, so existing stage commands keep their normal
file names and contracts.
"""

from __future__ import annotations

import base64
import hashlib
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from cryptography.fernet import Fernet, InvalidToken

from .license import _read_or_create_install_id


MAGIC = b"DKSEC1\n"
PROTECTED_SUFFIXES = frozenset({".txt", ".csv", ".json", ".md", ".tmp"})


def _cipher() -> Fernet:
    digest = hashlib.sha256(
        ("donghuakoubo-process-key-v1:" + _read_or_create_install_id()).encode("utf-8")
    ).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def is_protected_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in PROTECTED_SUFFIXES


def is_encrypted(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        with path.open("rb") as handle:
            return handle.read(len(MAGIC)) == MAGIC
    except OSError:
        return False


def _atomic_write(path: Path, data: bytes) -> None:
    temporary = path.with_name(f".{path.name}.secure-tmp")
    temporary.write_bytes(data)
    temporary.replace(path)


def encrypt_file(path: Path) -> bool:
    """Encrypt one process artifact in place; return whether it changed."""
    path = path.expanduser().resolve()
    if not is_protected_file(path) or is_encrypted(path):
        return False
    _atomic_write(path, MAGIC + _cipher().encrypt(path.read_bytes()))
    return True


def decrypt_file(path: Path) -> bool:
    """Decrypt one process artifact in place; return whether it changed."""
    path = path.expanduser().resolve()
    if not is_encrypted(path):
        return False
    try:
        plain = _cipher().decrypt(path.read_bytes()[len(MAGIC) :])
    except InvalidToken as exc:
        raise ValueError(f"无法解密过程文件：{path}") from exc
    _atomic_write(path, plain)
    return True


def protected_files(root: Path) -> list[Path]:
    root = root.expanduser().resolve()
    if root.is_file():
        return [root] if is_protected_file(root) else []
    if not root.is_dir():
        return []
    return sorted(path for path in root.rglob("*") if is_protected_file(path))


@contextmanager
def unlocked_files(root: Path) -> Iterator[Path]:
    """Temporarily decrypt a project tree and re-encrypt it on exit."""
    root = root.expanduser().resolve()
    try:
        for path in protected_files(root):
            decrypt_file(path)
    except Exception:
        # A corrupted file must never leave earlier files in plaintext.
        for path in protected_files(root):
            encrypt_file(path)
        raise
    try:
        yield root
    finally:
        for path in protected_files(root):
            encrypt_file(path)


def read_text(path: Path, *, encoding: str = "utf-8-sig", errors: str = "strict") -> str:
    """Read a protected or ordinary text file without leaving it decrypted."""
    path = path.expanduser().resolve()
    if not is_encrypted(path):
        return path.read_text(encoding=encoding, errors=errors)
    with unlocked_files(path):
        return path.read_text(encoding=encoding, errors=errors)
