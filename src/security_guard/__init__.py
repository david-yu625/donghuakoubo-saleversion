"""Offline license protection for the desktop application."""

from .license import (
    LicenseError,
    LicenseInfo,
    current_machine_code,
    load_license,
    save_license,
    verify_license,
)

__all__ = [
    "LicenseError",
    "LicenseInfo",
    "current_machine_code",
    "load_license",
    "save_license",
    "verify_license",
]
