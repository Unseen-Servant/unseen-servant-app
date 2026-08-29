#!/usr/bin/env python3
"""Validate the shipped-component inventory.

The normal mode is intentionally CI-safe while migration work is in progress:
it verifies that every direct component has a complete review record. Release
mode fails closed unless every shipped component is approved.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "third_party" / "components.json"
ALLOWED_LICENSES = {
    "Apache-2.0", "MIT", "ISC", "BSD-2-Clause", "BSD-3-Clause", "Zlib",
    "HPND", "public-domain",
}
REQUIRED_FIELDS = {"name", "version", "kind", "license", "upstream", "distribution", "status"}
VALID_STATUSES = {"approved", "review_required", "blocked"}


def load_inventory(path: Path = INVENTORY) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        raise ValueError("third-party inventory must use schema_version 1")
    components = payload.get("components")
    if not isinstance(components, list) or not components:
        raise ValueError("third-party inventory must contain at least one component")
    return components


def validate(components: list[dict], release: bool = False) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    for component in components:
        missing = sorted(REQUIRED_FIELDS - component.keys())
        name = component.get("name", "<unnamed>")
        if missing:
            errors.append(f"{name}: missing fields: {', '.join(missing)}")
            continue
        if name in seen:
            errors.append(f"{name}: duplicate component name")
        seen.add(name)
        status = component["status"]
        if status not in VALID_STATUSES:
            errors.append(f"{name}: invalid status {status!r}")
        if status == "approved" and component["license"] not in ALLOWED_LICENSES:
            errors.append(f"{name}: approved license {component['license']!r} is not allowlisted")
        if status != "approved" and not component.get("replacement"):
            errors.append(f"{name}: {status} components need a replacement or review note")
        if release and status != "approved":
            errors.append(f"{name}: release blocked until its license review is approved")
    return errors


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--release", action="store_true", help="fail unless every shipped component is approved")
    args = ap.parse_args()
    try:
        components = load_inventory()
        errors = validate(components, release=args.release)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"third-party inventory invalid: {exc}")
        return 1
    if errors:
        print("third-party inventory check failed:")
        for error in errors:
            print(f"  - {error}")
        return 1
    pending = sum(component["status"] != "approved" for component in components)
    print(f"third-party inventory valid: {len(components)} components, {pending} pending release review")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
