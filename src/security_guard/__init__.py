"""Offline license protection for the desktop application."""

from .license import (
    LicenseError,
    LicenseInfo,
    current_machine_code,
    load_license,
    save_license,
    verify_license,
)
from .secure_files import decrypt_file, encrypt_file, is_encrypted, read_text, unlocked_files

__all__ = [
    "LicenseError",
    "LicenseInfo",
    "current_machine_code",
    "load_license",
    "save_license",
    "verify_license",
    "decrypt_file",
    "encrypt_file",
    "is_encrypted",
    "read_text",
    "unlocked_files",
]
