"""Test script for V2.0 Art Direction Production Specification Compilation."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

from pipeline.universal.v5_story_director import (
    V5UniversalStoryDirector,
    V2_CANONICAL_EXPRESSIONS,
    normalize_v2_expression,
    chunk_caption_mobile_safe,
)
from scripts.build_blob_head_documentary_draft import build_documentary_blob_head_package

director = V5UniversalStoryDirector()
pkg = build_documentary_blob_head_package()
v2_spec = director.compile_v2_production_specification(pkg)

print("--- V2.0 SPEC COMPILED SUCCESSFULLY ---")
print(f"Table Rows Count: {len(v2_spec.get('table_rows', []))}")
assert len(v2_spec.get("table_rows", [])) == 3, "Expected 3 story beats / shots"

first_row = v2_spec["table_rows"][0]
print("First Row 19 Fields:")
for k, v in first_row.items():
    print(f"  {k}: {v}")

assert len(first_row) == 19, f"Expected 19 fields in row, got {len(first_row)}"

print("\n--- 6 PRODUCTION PROMPTS GENERATED ---")
for p_key, p_val in v2_spec["prompts"].items():
    print(f"\n[{p_key}] (len={len(p_val)}):\n{p_val[:180]}...")

print("\n--- COMPLIANCE AUDIT ---")
for check, res in v2_spec["compliance_audit"]["checklist"].items():
    print(f"  {check}: {res}")

assert v2_spec["compliance_audit"]["compliant"] is True
print("\nALL ASSERTIONS PASSED 100%!")
