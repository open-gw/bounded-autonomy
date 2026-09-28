"""Validate a run manifest or result.json against schemas/ plus extra-schema rules.

Extra rules (study-design §1):
  * write_mix values sum to 1.0 within 1e-9
  * declared ∪ undeclared == the eight names in rig/services.yaml
  * the two sets are disjoint
  * injection.undeclared_service ∈ undeclared
  * injection.at_step ∈ 1..spec.steps
  * services.declared_count, when set, equals len(declared)
  * spec.variant kN, when set, matches |declared| and the frozen sweep list
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "rig") not in sys.path:
    sys.path.insert(0, str(ROOT / "rig"))
SCHEMA_PATH = ROOT / "schemas" / "manifest.schema.json"
RESULT_SCHEMA_PATH = ROOT / "schemas" / "result.schema.json"
SERVICES_PATH = ROOT / "rig" / "services.yaml"
WRITE_MIX_TOLERANCE = 1e-9
WRITE_CLASSES = ("idempotent", "versioned", "derived", "irreversible")
EVASION_VERDICTS = ("allowed", "refused", "error", "host-refused")


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

    declared_count = services.get("declared_count")
    if declared_count is not None and declared_count != len(declared):
        errors.append(
            f"services.declared_count {declared_count} != |declared|={len(declared)}"
        )

    profile = spec.get("profile")
    if profile == "data-intensive":
        if steps != 20:
            errors.append(f"data-intensive requires spec.steps=20; got {steps}")
        declared_need = {"records", "docs", "search"}
        if not declared_need <= declared_set:
            errors.append(
                "data-intensive declared must include records, docs, search "
                f"(postgres/minio/qdrant); got {declared}"
            )
        expected_mix = {
            "idempotent": 0.2,
            "versioned": 0.3,
            "derived": 0.4,
            "irreversible": 0.1,
        }
        for cls, want in expected_mix.items():
            got = mix.get(cls)
            try:
                if got is None or abs(float(got) - want) > WRITE_MIX_TOLERANCE:
                    errors.append(
                        f"data-intensive write_mix.{cls} must be {want}; got {got}"
                    )
            except (TypeError, ValueError):
                errors.append(f"data-intensive write_mix.{cls} is not numeric: {got}")
        at_step = injection.get("at_step")
        if at_step != 3:
            errors.append(f"data-intensive injection.at_step must be 3; got {at_step}")

    variant = spec.get("variant")
    if variant is not None:
        from sweep import VARIANTS, undeclared as sweep_undeclared

        expected = VARIANTS.get(variant)
        if expected is None:
            errors.append(f"unknown spec.variant {variant!r}")
        else:
            if declared != expected:
                errors.append(
                    f"spec.variant {variant} requires declared {expected}; got {declared}"
                )
            if declared_count is not None and declared_count != len(expected):
                errors.append(
                    f"spec.variant {variant} requires declared_count {len(expected)}"
                )
            expected_undeclared = sweep_undeclared(variant)
            if undeclared != expected_undeclared:
                errors.append(
                    f"spec.variant {variant} requires undeclared {expected_undeclared}; "
                    f"got {undeclared}"
                )

    if profile == "redeclaration":
        if steps != 30:
            errors.append(f"redeclaration requires spec.steps=30; got {steps}")
        if injection.get("enabled") is not False:
            errors.append("redeclaration requires injection.enabled=false (legitimate undeclared, not drift)")
        if injection.get("at_step") != 15:
            errors.append(
                f"redeclaration step-plan undeclared tool is at step 15; injection.at_step={injection.get('at_step')}"
            )
        if list(declared) != ["records", "search", "notify"]:
            errors.append(
                f"redeclaration initial declared must be [records, search, notify]; got {declared}"
            )

    observer = spec.get("observer") or {}
    if "probe" in observer and not isinstance(observer.get("probe"), bool):
        errors.append("spec.observer.probe must be a boolean")

    if spec.get("gateway_bypass") and spec.get("mode") not in ("full", "gateway-bypass"):
        errors.append(
            "spec.gateway_bypass is only combinable with mode=full "
            "(or redundant with mode=gateway-bypass)"
        )
    return errors


def extra_errors_result(doc: dict) -> list[str]:
    errors: list[str] = []
    matrix = doc.get("evasion_matrix")
    if matrix is None:
        errors.extend(_extra_errors_result_q4(doc))
        return errors
    if not isinstance(matrix, list):
        return ["evasion_matrix must be an array"]
    if len(matrix) != 9:
        errors.append(f"evasion_matrix length {len(matrix)}, expected 9")
    rows: list[int] = []
    for i, item in enumerate(matrix):
        if not isinstance(item, dict):
            errors.append(f"evasion_matrix[{i}] is not an object")
            continue
        row = item.get("row")
        if not isinstance(row, int) or not (1 <= row <= 9):
            errors.append(f"evasion_matrix[{i}].row must be 1..9")
        else:
            rows.append(row)
        verdict = item.get("verdict")
        if verdict not in EVASION_VERDICTS:
            errors.append(
                f"evasion_matrix[{i}].verdict {verdict!r} not in {EVASION_VERDICTS}"
            )
        lat = item.get("latency_ms")
        if not isinstance(lat, (int, float)) or float(lat) < 0:
            errors.append(f"evasion_matrix[{i}].latency_ms must be >= 0")
    if rows and sorted(rows) != list(range(1, 10)):
        errors.append(f"evasion_matrix rows must be 1–9 unique; got {sorted(rows)}")
    artefacts = doc.get("artefacts") or {}
    if artefacts.get("evasion") != "evasion.parquet":
        errors.append("artefacts.evasion must be 'evasion.parquet' when evasion_matrix is set")
    errors.extend(_extra_errors_result_q4(doc))
    return errors


def _extra_errors_result_q4(doc: dict) -> list[str]:
    errors: list[str] = []
    split = doc.get("step_cost_split")
    if isinstance(split, dict):
        err = split.get("reconcile_error_pct")
        if isinstance(err, (int, float)) and float(err) > 5.0:
            errors.append(
                f"step_cost_split.reconcile_error_pct {err} exceeds 5% acceptance"
            )
        totals = split.get("totals") or {}
        try:
            accounted = (
                float(totals.get("propagation_ms") or 0)
                + float(totals.get("svid_reissue_ms") or 0)
                + float(totals.get("probe_ms") or 0)
                + float(totals.get("other_ms") or 0)
            )
            observed = float(totals.get("boundary_ms") or 0)
            if observed > 0 and abs(accounted - observed) / observed * 100.0 > 5.0:
                errors.append(
                    "step_cost_split totals do not reconcile with boundary_ms within 5%"
                )
        except (TypeError, ValueError):
            errors.append("step_cost_split.totals are not numeric")
    if doc.get("profile") == "redeclaration":
        if doc.get("redeclaration_cost_ms") is None:
            errors.append("redeclaration result requires redeclaration_cost_ms")
    return errors


def validate_result(path: Path) -> list[str]:
    try:
        doc = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        return [f"JSON parse error: {exc}"]
    if not isinstance(doc, dict):
        return ["result is not a mapping"]
    schema = json.loads(RESULT_SCHEMA_PATH.read_text())
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    messages = [
        f"{'/'.join(str(p) for p in e.path) or '<root>'}: {e.message}"
        for e in validator.iter_errors(doc)
    ]
    messages.extend(extra_errors_result(doc))
    return messages


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
    name = args.manifest.name
    if name == "result.json" or args.manifest.suffix == ".json":
        errors = validate_result(args.manifest)
    else:
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
