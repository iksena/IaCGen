#!/usr/bin/env python3
"""
tools/generate_checkov_csv.py

Generates Code/data/checkov_cfn_policy_map.csv.
Columns:
  check_id, check_name, source_file_url, source_code

source_code is fetched from GitHub at generation time so the pipeline
never makes HTTP calls at runtime — pure CSV lookup only.

Usage:
  python tools/generate_checkov_csv.py
  python tools/generate_checkov_csv.py --output path/to/custom.csv
  python tools/generate_checkov_csv.py --no-fetch   # skip HTTP, leave source_code blank
"""

import ast
import csv
import os
import argparse
import sys
import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

CHECKOV_GITHUB_RAW_BASE = "https://raw.githubusercontent.com/bridgecrewio/checkov/main"
MAX_SOURCE_CODE_CHARS = 1500   # same cap used at runtime
MAX_FETCH_WORKERS = 8          # parallel HTTP workers
FETCH_TIMEOUT = 10             # seconds per request
RETRY_DELAY = 1.0              # seconds between retries on rate-limit

DEFAULT_OUTPUT = os.path.join(
    os.path.dirname(__file__), "..", "Code", "data", "checkov_cfn_policy_map.csv"
)


def get_checkov_package_root() -> str:
    import checkov
    return os.path.dirname(checkov.__file__)


def iter_cfn_check_files(checkov_root: str):
    cfn_checks_dir = os.path.join(checkov_root, "cloudformation", "checks", "resource")
    if not os.path.isdir(cfn_checks_dir):
        print(f"[ERROR] Directory not found: {cfn_checks_dir}")
        sys.exit(1)
    for root, dirs, files in os.walk(cfn_checks_dir):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for fname in files:
            if fname.endswith(".py") and not fname.startswith("__"):
                yield os.path.join(root, fname)


def extract_checks_via_ast(file_path: str) -> list[tuple[str, str]]:
    results = []
    try:
        with open(file_path, encoding="utf-8") as f:
            source = f.read()
        tree = ast.parse(source, filename=file_path)
    except Exception:
        return results

    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        check_id = None
        check_name = None
        for child in ast.walk(node):
            if not isinstance(child, ast.Assign):
                continue
            for target in child.targets:
                if not isinstance(target, ast.Name):
                    continue
                if target.id == "id" and isinstance(child.value, ast.Constant):
                    val = str(child.value.value)
                    if val.startswith("CKV_"):
                        check_id = val
                elif target.id == "name" and isinstance(child.value, ast.Constant):
                    check_name = str(child.value.value)
        if check_id:
            results.append((check_id, check_name or ""))
    return results


def abs_path_to_github_url(abs_path: str, checkov_root: str) -> str:
    rel = os.path.relpath(abs_path, os.path.dirname(checkov_root)).replace(os.sep, "/")
    return f"{CHECKOV_GITHUB_RAW_BASE}/{rel}"


def fetch_source_code(url: str, retries: int = 2) -> str:
    """Fetch and truncate source code from a GitHub raw URL. Returns '' on failure."""
    for attempt in range(retries + 1):
        try:
            resp = requests.get(url, timeout=FETCH_TIMEOUT)
            if resp.status_code == 429:
                time.sleep(RETRY_DELAY * (attempt + 1))
                continue
            resp.raise_for_status()
            return resp.text[:MAX_SOURCE_CODE_CHARS]
        except Exception as e:
            if attempt == retries:
                print(f"  [WARN] Failed to fetch {url}: {e}")
    return ""


def fetch_all_source_codes(rows: list[dict]) -> dict[str, str]:
    """
    Fetch source_code for all rows in parallel.
    Returns dict mapping source_file_url → source_code.
    """
    # Deduplicate URLs (multiple check_ids can live in the same file)
    unique_urls = list({r["source_file_url"] for r in rows if r["source_file_url"]})
    results: dict[str, str] = {}
    total = len(unique_urls)
    print(f"Fetching source code for {total} unique policy files ({MAX_FETCH_WORKERS} workers)...")

    with ThreadPoolExecutor(max_workers=MAX_FETCH_WORKERS) as executor:
        future_to_url = {executor.submit(fetch_source_code, url): url for url in unique_urls}
        for i, future in enumerate(as_completed(future_to_url), 1):
            url = future_to_url[future]
            results[url] = future.result()
            if i % 20 == 0 or i == total:
                print(f"  {i}/{total} fetched...")

    return results


def generate_csv(output_path: str, fetch: bool = True):
    checkov_root = get_checkov_package_root()
    print(f"Checkov root : {checkov_root}")

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    rows = []
    seen_ids: set[str] = set()

    for abs_path in iter_cfn_check_files(checkov_root):
        for check_id, check_name in extract_checks_via_ast(abs_path):
            if check_id in seen_ids:
                continue
            seen_ids.add(check_id)
            rows.append({
                "check_id": check_id,
                "check_name": check_name,
                "source_file_url": abs_path_to_github_url(abs_path, checkov_root),
                "source_code": "",   # filled below
            })

    rows.sort(key=lambda r: r["check_id"])
    print(f"Found {len(rows)} unique CloudFormation checks.")

    # Fetch source code in parallel at generation time
    if fetch:
        url_to_code = fetch_all_source_codes(rows)
        for row in rows:
            row["source_code"] = url_to_code.get(row["source_file_url"], "")
    else:
        print("Skipping source code fetch (--no-fetch). source_code column will be empty.")

    fieldnames = ["check_id", "check_name", "source_file_url", "source_code"]
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    fetched = sum(1 for r in rows if r["source_code"])
    print(f"[OK] {len(rows)} checks written to {output_path} ({fetched} with source code cached)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate Checkov CFn policy source map CSV")
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--no-fetch", dest="fetch", action="store_false",
        help="Skip HTTP fetching — leave source_code blank (faster, for offline use)"
    )
    args = parser.parse_args()
    generate_csv(args.output, fetch=args.fetch)
