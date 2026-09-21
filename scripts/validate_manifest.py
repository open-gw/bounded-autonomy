"""Validate a run manifest against schemas/manifest.schema.json plus extra-schema rules.

Extra rules (study-design §1):
  * write_mix values sum to 1.0 within 1e-9
  * declared ∪ undeclared == the eight names in rig/services.yaml
  * the two sets are disjoint
  * injection.undeclared_service ∈ undeclared
  * injection.at_step ∈ 1..spec.steps
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "manifest.schema.json"
SERVICES_PATH = ROOT / "rig" / "services.yaml"
WRITE_MIX_TOLERANCE = 1e-9
WRITE_CLASSES = ("idempotent", "versioned", "derived", "irreversible")


def load_inventory() -> set[str]:
    doc = yaml.safe_load(SERVICES_PATH.read_text())
    return {s["name"] for s in doc["services"]}


def load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text())


def extra_errors(doc: dict, inventory: set[str]) -> list[str]:
    errors: list[str] = []
    spec = doc.get("spec") or {}
    mix = spec.get("write_mix") or {}
    try:
        total = sum(float(mix[c]) for c in WRITE_CLASSES)
        if abs(total - 1.0) > WRITE_MIX_TOLERANCE:
            errors.append(
                f"write_mix sums to {total:.12g}, not 1.0 (±{WRITE_MIX_TOLERANCE:g})"
            )
    except (KeyError, TypeError, ValueError) as exc:
        errors.append(f"write_mix is not a complete numeric map: {exc}")

    services = spec.get("services") or {}
    declared = list(services.get("declared") or [])
    undeclared = list(services.get("undeclared") or [])
    declared_set, undeclared_set = set(declared), set(undeclared)
    if declared_set & undeclared_set:
        errors.append(
            f"declared and undeclared overlap: {sorted(declared_set & undeclared_set)}"
        )
    union = declared_set | undeclared_set
    if union != inventory:
        errors.append(
            "services.declared ∪ undeclared must equal the rig inventory "
            f"{sorted(inventory)}; got {sorted(union)}"
        )

    injection = spec.get("injection") or {}
    target = injection.get("undeclared_service")
    if target is not None and target not in undeclared_set:
        errors.append(
            f"injection.undeclared_service {target!r} is not in services.undeclared"
        )
    at_step = injection.get("at_step")
    steps = spec.get("steps")
    if isinstance(at_step, int) and isinstance(steps, int):
        if not (1 <= at_step <= steps):
            errors.append(f"injection.at_step {at_step} not in 1..{steps}")
    return errors


def validate_manifest(path: Path) -> list[str]:
    try:
        doc = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        return [f"YAML parse error: {exc}"]
    if not isinstance(doc, dict):
        return ["manifest is not a mapping"]

    validator = Draft202012Validator(load_schema(), format_checker=FormatChecker())
    messages = [
        f"{'/'.join(str(p) for p in e.path) or '<root>'}: {e.message}"
        for e in validator.iter_errors(doc)
    ]
    messages.extend(extra_errors(doc, load_inventory()))
    return messages


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args(argv)
    if not args.manifest.is_file():
        print(f"not a file: {args.manifest}", file=sys.stderr)
        return 2
    errors = validate_manifest(args.manifest)
    if errors:
        print(f"INVALID {args.manifest}", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1
    print(f"OK {args.manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
