# Code/checkov_context.py
"""
Source-code-only context builder for Checkov CloudFormation checks.
Stream 1 (SAT output) + Stream 2 (policy source code).

Source code is pre-cached in the CSV — no HTTP calls at runtime.
Regenerate the CSV with tools/generate_checkov_csv.py after updating Checkov.
"""

import csv
import os
from functools import lru_cache

POLICY_MAP_CSV = os.path.join(os.path.dirname(__file__), "data", "checkov_cfn_policy_map.csv")


@lru_cache(maxsize=1)
def _load_policy_map() -> dict:
    """Load CSV once and cache it in memory keyed by check_id."""
    policy_map = {}
    if not os.path.exists(POLICY_MAP_CSV):
        print(
            f"[WARNING] Checkov policy map CSV not found at {POLICY_MAP_CSV}. "
            f"Run tools/generate_checkov_csv.py to generate it."
        )
        return policy_map

    with open(POLICY_MAP_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            check_id = row.get("check_id", "").strip().upper()
            if check_id:
                policy_map[check_id] = {
                    "check_name": row.get("check_name", "").strip(),
                    "source_file_url": row.get("source_file_url", "").strip(),
                    "source_code": row.get("source_code", "").strip(),
                }
    return policy_map


def get_checkov_policy_context(failed_checks: list[dict]) -> str:
    """
    Build source-code context for a list of Checkov failed checks.
    All data comes from the pre-cached CSV — no network calls.

    Each block contains:
      - Stream 1: check_id, check_name, resource (SAT structured output)
      - Stream 2: cached Python source of the Checkov policy

    Args:
        failed_checks: List of dicts with keys: check_id, check_name, resource

    Returns:
        str: Context string ready to inject into the remediation prompt.
    """
    if not failed_checks:
        return ""

    policy_map = _load_policy_map()
    context_parts = []

    for check in failed_checks:
        check_id = check.get("check_id", "UNKNOWN").upper()
        entry = policy_map.get(check_id, {})
        check_name = check.get("check_name", entry.get("check_name", ""))
        resource = check.get("resource", "")

        # Stream 1: SAT structured output
        stream1 = (
            f"Check ID  : {check_id}\n"
            f"Check Name: {check_name}\n"
            f"Resource  : {resource}"
        )

        # Stream 2: Pre-cached policy source code (CSV lookup, no HTTP)
        source_code = entry.get("source_code", "")
        source_url = entry.get("source_file_url", "")

        if source_code:
            stream2 = (
                f"Policy Source ({source_url}):\n"
                f"```python\n{source_code}\n```"
            )
        else:
            stream2 = "(Policy source code not cached — fix based on check name and resource above.)"

        context_parts.append(f"--- {check_id} ---\n{stream1}\n\n{stream2}")

    return "\n\n".join(context_parts)
