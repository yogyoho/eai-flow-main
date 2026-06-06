"""Generate RSA-2048 key pair for license signing/verification.

Usage:
    python generate_keys.py

Outputs:
    tools/license/private_key.pem  — Keep secret, used by license_generator.py
    tools/license/public_key.pem   — Embed in product for verification
"""

import os

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


def generate_keys(output_dir: str = ".") -> tuple[str, str]:
    """Generate RSA-2048 key pair. Returns (private_key_path, public_key_path)."""
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )

    private_path = os.path.join(output_dir, "private_key.pem")
    with open(private_path, "wb") as f:
        f.write(private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ))

    public_key = private_key.public_key()
    public_path = os.path.join(output_dir, "public_key.pem")
    with open(public_path, "wb") as f:
        f.write(public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ))

    return private_path, public_path


if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    priv, pub = generate_keys(script_dir)
    print(f"Private key: {priv}")
    print(f"Public key:  {pub}")
    print("\nKeep private_key.pem SECRET. Embed public_key.pem in the product.")
