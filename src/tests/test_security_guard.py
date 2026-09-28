import base64
import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from src.security_guard import license as license_module
from tools.license.issue_license import issue_license


class SecurityGuardTests(unittest.TestCase):
    def test_machine_code_is_stable_for_same_installation(self):
        with patch.object(license_module, "_read_or_create_install_id", return_value="install"):
            with patch.object(license_module, "_system_identifier", return_value="system"):
                self.assertEqual(license_module.current_machine_code(), license_module.current_machine_code())

    def test_signed_license_round_trip_and_tamper_detection(self):
        key = Ed25519PrivateKey.generate()
        public = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        with tempfile.TemporaryDirectory() as directory:
            private_path = Path(directory) / "private.pem"
            private_path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
            document = issue_license(
                private_key_path=private_path,
                machine_code="MACHINE",
                customer="Test",
                expires_at=date.today() + timedelta(days=2),
                features=["render"],
            )
            with patch.object(license_module, "PUBLIC_KEY_B64", base64.b64encode(public).decode()):
                with patch.object(license_module, "current_machine_code", return_value="MACHINE"):
                    info = license_module.verify_license(document)
                    self.assertEqual(info.customer, "Test")
                    tampered = json.loads(json.dumps(document))
                    tampered["payload"]["customer"] = "Other"
                    with self.assertRaises(license_module.LicenseError):
                        license_module.verify_license(tampered)


if __name__ == "__main__":
    unittest.main()
