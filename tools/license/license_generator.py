"""Generate signed license files for DeerFlow deployments.

Usage:
    # 30-day trial
    python license_generator.py license_request.json --days 30

    # Permanent, all modules
    python license_generator.py license_request.json --permanent --all-modules \\
        --customer "XX科技" --max-users 50 --output license.lic

    # Specify modules
    python license_generator.py license_request.json --permanent \\
        --modules project,docmgr,knowledge --max-users 100
"""

import argparse
import json
import os
import uuid
from datetime import datetime, timedelta, timezone

import jwt

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PRIVATE_KEY_PATH = os.path.join(SCRIPT_DIR, "private_key.pem")
ALGORITHM = "RS256"

ALL_MODULES = [
    "project", "docmgr", "knowledge", "collab",
    "report", "approval", "workflow", "dashboard",
]


def load_private_key() -> bytes:
    if not os.path.exists(PRIVATE_KEY_PATH):
        print(f"Error: Private key not found at {PRIVATE_KEY_PATH}")
        print("Run generate_keys.py first.")
        exit(1)
    with open(PRIVATE_KEY_PATH, "rb") as f:
        return f.read()


def generate_license(
    request_file: str,
    days: int | None = None,
    permanent: bool = False,
    all_modules: bool = False,
    modules: str | None = None,
    customer: str = "",
    max_users: int | None = None,
    features: str | None = None,
    output: str = "license.lic",
) -> None:
    """Generate a signed license file from a request JSON."""
    # Load request
    with open(request_file) as f:
        request_data = json.load(f)

    machine_id = request_data.get("machine_id")
    if not machine_id:
        print("Error: missing machine_id in request file")
        return

    print(f"Generating license for Machine ID: {machine_id}")

    # Build modules dict
    if all_modules:
        modules_dict = {m: True for m in ALL_MODULES}
    elif modules:
        enabled = set(modules.split(","))
        modules_dict = {m: (m in enabled) for m in ALL_MODULES}
    else:
        modules_dict = {"project": True, "docmgr": True}

    # Build features dict
    features_dict: dict = {}
    if features:
        for pair in features.split(","):
            k, v = pair.strip().split("=")
            features_dict[k.strip()] = int(v) if v.isdigit() else v

    # Build JWT payload
    now = datetime.now(timezone.utc)
    payload: dict = {
        "iss": "DeerFlow",
        "iat": int(now.timestamp()),
        "jti": f"LIC-{uuid.uuid4().hex[:8].upper()}",
        "sub": machine_id,
        "type": "permanent" if permanent else "trial",
        "customer": customer,
        "max_users": max_users,
        "modules": modules_dict,
        "features": features_dict,
        "meta": {
            "contact": "support@deerflow.com",
            "order_id": f"ORD-{uuid.uuid4().hex[:8].upper()}",
        },
    }

    if not permanent:
        actual_days = days or 30
        expiry = now + timedelta(days=actual_days)
        payload["exp"] = int(expiry.timestamp())
        print(f"Type: trial ({actual_days} days), Expires: {expiry.isoformat()}")
    else:
        print("Type: permanent")

    # Sign
    private_key = load_private_key()
    encoded_jwt = jwt.encode(payload, private_key, algorithm=ALGORITHM)

    # Save
    with open(output, "w") as f:
        f.write(encoded_jwt)

    print(f"Success! License saved to {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DeerFlow License Generator")
    parser.add_argument("request_file", help="Path to license_request.json")
    parser.add_argument("--days", type=int, help="Days until expiry (trial)")
    parser.add_argument("--permanent", action="store_true", help="Generate permanent license")
    parser.add_argument("--all-modules", action="store_true", help="Enable all modules")
    parser.add_argument("--modules", help="Comma-separated module names")
    parser.add_argument("--customer", default="", help="Customer name")
    parser.add_argument("--max-users", type=int, help="Max active users")
    parser.add_argument("--features", help="Features as key=value pairs, comma-separated")
    parser.add_argument("--output", default="license.lic", help="Output file path")

    args = parser.parse_args()
    generate_license(
        request_file=args.request_file,
        days=args.days,
        permanent=args.permanent,
        all_modules=args.all_modules,
        modules=args.modules,
        customer=args.customer,
        max_users=args.max_users,
        features=args.features,
        output=args.output,
    )
