#!/usr/bin/env python3
"""Generate Report Passport — pipeline stage metadata.

Called by run.sh after extract+grounding+compliance stages.
Reads grounding_check JSON output to populate extract stage data.

Usage:
  python gen_passport.py <passport.json> <project> <report_path> <compliance_path> \
    <contract> <grounding_json> <compliance_status> <report_chars>
"""
import json
import sys
from datetime import datetime
from pathlib import Path


def main(argv):
    if len(argv) != 8:
        print("usage: gen_passport.py <out.json> <project> <report> <compliance> "
              "<contract> <grounding_json> <compliance_status> <report_chars>", file=sys.stderr)
        return 2

    passport_path = argv[0]
    project = argv[1]
    report_path = argv[2]
    compliance_path = argv[3]
    contract = argv[4]
    grounding_json = argv[5]
    compliance_status = argv[6]
    report_chars = int(argv[7])

    # Parse grounding JSON
    try:
        grounding = json.loads(grounding_json)
        rate = round(grounding.get("rate", 0), 4)
    except (json.JSONDecodeError, TypeError):
        rate = 0.0
    grounding_pass = rate >= 0.85

    # Integrity gate
    report_status = "READY" if (grounding_pass and compliance_status == "pass") else "NEEDS_REVIEW"

    passport = {
        "project": project,
        "created_at": datetime.now().isoformat(),
        "report_path": report_path,
        "compliance_path": compliance_path,
        "report_status": report_status,
        "stages": {
            "extract": {
                "contract": contract,
                "grounding_rate": rate,
                "grounding_pass": grounding_pass,
                "compliance_status": compliance_status,
                "report_chars": report_chars,
            },
            "format": {"applied": False},
            "enrich": {"applied": False},
            "polish": {"applied": False},
        },
    }

    Path(passport_path).write_text(
        json.dumps(passport, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"PASSPORT: {passport_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
