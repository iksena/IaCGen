"""
generate_trivy_csv.py

Generates a CSV mapping Trivy policy IDs to their metadata and source code,
mirroring the structure of generate_checkov_csv.py.

Handles both .rego and .yaml check files from:
  https://github.com/aquasecurity/trivy-checks/tree/main/checks/cloud/aws

Usage:
    python Code/tools/generate_trivy_csv.py
    python Code/tools/generate_trivy_csv.py --framework all
    python Code/tools/generate_trivy_csv.py --no-fetch
"""

import csv
import os
import re
import sys
import json
import time
import argparse
import requests
import yaml
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# ─── Config ───────────────────────────────────────────────────────────────────

GITHUB_API     = "https://api.github.com"
REPO_OWNER     = "aquasecurity"
REPO_NAME      = "trivy-checks"
BRANCH         = "main"
RAW_BASE       = f"https://raw.githubusercontent.com/{REPO_OWNER}/{REPO_NAME}/{BRANCH}"

# Framework → subfolder mapping
FRAMEWORK_PATHS = {
    "cloudformation": "checks/cloud/aws",   # all AWS checks cover CFn + TF
    "terraform":      "checks/cloud/aws",
    "kubernetes":     "checks/kubernetes",
    "dockerfile":     "checks/docker",
    "all":            "checks",
}

OUTPUT_DIR      = Path("Code/data")
OUTPUT_FILE     = OUTPUT_DIR / "trivy_cfn_policy_map.csv"

CSV_COLUMNS = [
    "check_id",        # e.g. AVD-AWS-0086
    "check_name",      # human-readable title
    "severity",        # LOW / MEDIUM / HIGH / CRITICAL
    "short_code",      # slug, e.g. no-public-access-with-acl
    "description",     # one-line description
    "service",         # inferred from path, e.g. s3
    "framework",       # cloudformation / terraform / kubernetes / dockerfile
    "source_file_url", # raw GitHub URL to the policy file
    "source_code",     # full source code of the policy file
]

MAX_WORKERS = 10
HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}
# Optional: set GITHUB_TOKEN env var to avoid rate limits
_token = os.environ.get("GITHUB_TOKEN")
if _token:
    HEADERS["Authorization"] = f"Bearer {_token}"


# ─── GitHub API helpers ────────────────────────────────────────────────────────

def get_tree(base_path: str) -> list[dict]:
    """
    Fetch the full recursive file tree for a given path prefix.
    Returns list of items: {path, type, url, sha}
    """
    url = f"{GITHUB_API}/repos/{REPO_OWNER}/{REPO_NAME}/git/trees/{BRANCH}?recursive=1"
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    if data.get("truncated"):
        print("[WARN] GitHub tree response was truncated — some checks may be missing.", file=sys.stderr)

    items = data.get("tree", [])
    # Filter to the desired base path and only .rego / .yaml files
    return [
        item for item in items
        if item["type"] == "blob"
        and item["path"].startswith(base_path)
        and (item["path"].endswith(".rego") or item["path"].endswith(".yaml") or item["path"].endswith(".yml"))
        and not item["path"].endswith("_test.rego")       # skip test files
        and not item["path"].endswith("_test.yaml")
        and "__test__" not in item["path"]
    ]


def fetch_raw(path: str) -> str:
    """Fetch raw file content from GitHub."""
    url = f"{RAW_BASE}/{path}"
    for attempt in range(3):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=20)
            resp.raise_for_status()
            return resp.text
        except requests.RequestException as e:
            if attempt == 2:
                print(f"[ERROR] Failed to fetch {path}: {e}", file=sys.stderr)
                return ""
            time.sleep(1.5 * (attempt + 1))
    return ""


# ─── Metadata extraction ───────────────────────────────────────────────────────

def _infer_service(path: str) -> str:
    """Infer the AWS service from the file path, e.g. checks/cloud/aws/s3/... → s3"""
    parts = path.split("/")
    # Structure: checks/cloud/aws/<service>/...
    try:
        aws_idx = parts.index("aws")
        return parts[aws_idx + 1] if aws_idx + 1 < len(parts) else "unknown"
    except ValueError:
        pass
    # Kubernetes / Docker fallback
    if "kubernetes" in parts:
        try:
            k8s_idx = parts.index("kubernetes")
            return parts[k8s_idx + 1] if k8s_idx + 1 < len(parts) else "kubernetes"
        except ValueError:
            pass
    return "unknown"


def _infer_framework(path: str) -> str:
    if "cloud/aws" in path:
        return "cloudformation"
    if "kubernetes" in path:
        return "kubernetes"
    if "docker" in path:
        return "dockerfile"
    return "unknown"


# ── REGO metadata extraction ──────────────────────────────────────────────────

_REGO_METADATA_BLOCK = re.compile(
    r"# METADATA\s*\n((?:#[^\n]*\n)*)",
    re.MULTILINE
)

_CHECK_ID_RE = re.compile(r"^(?:AVD-)?(AWS-\d+)$", re.IGNORECASE)


def _normalize_check_id(raw_id: str) -> str:
    """Normalize check IDs to canonical AVD-AWS-XXXX format when possible."""
    if not raw_id:
        return ""
    value = raw_id.strip().upper()
    m = _CHECK_ID_RE.match(value)
    if m:
        return f"AVD-{m.group(1)}"
    return value

def _parse_rego_metadata(source: str) -> dict:
    """
    Extract OPA annotation metadata from a .rego file.

    Two formats exist in trivy-checks:
    1. OPA annotations (# METADATA block with YAML under #)
    2. Inline comments like:  # avd_id: AVD-AWS-0086
    """
    result = {
        "check_id":    "",
        "check_name":  "",
        "severity":    "",
        "short_code":  "",
        "description": "",
    }

    # Method 1: OPA METADATA block
    m = _REGO_METADATA_BLOCK.search(source)
    if m:
        # Strip leading "# " from each line and parse as YAML
        raw_yaml = "\n".join(
            line[2:] if line.startswith("# ") else line[1:]
            for line in m.group(1).splitlines()
        )
        try:
            meta = yaml.safe_load(raw_yaml) or {}
        except yaml.YAMLError:
            meta = {}

        result["check_name"]  = meta.get("title", "")
        result["description"] = meta.get("description", "")

        custom = meta.get("custom", {}) or {}
        result["check_id"] = _normalize_check_id(custom.get("avd_id", "") or custom.get("id", ""))
        if not result["check_id"]:
            aliases = custom.get("aliases", []) or []
            for alias in aliases:
                candidate = _normalize_check_id(str(alias))
                if candidate:
                    result["check_id"] = candidate
                    break
        result["severity"]   = custom.get("severity", "")
        result["short_code"] = custom.get("short_code", "")

        if result["check_id"]:
            return result

    # Method 2: Inline # key: value comments (older format)
    patterns = {
        "check_id":    r"#\s*(?:avd_id|id)\s*:\s*(.+)",
        "check_name":  r"#\s*title\s*:\s*(.+)",
        "severity":    r"#\s*severity\s*:\s*(.+)",
        "short_code":  r"#\s*short_code\s*:\s*(.+)",
        "description": r"#\s*description\s*:\s*(.+)",
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, source, re.IGNORECASE)
        if match and not result[key]:
            result[key] = match.group(1).strip()

    result["check_id"] = _normalize_check_id(result["check_id"])

    # Method 3: Extract package name as fallback check_id
    if not result["check_id"]:
        pkg_match = re.search(r"^package\s+(.+)$", source, re.MULTILINE)
        if pkg_match:
            # e.g. builtin.aws.s3.aws0086 → AVD-AWS-0086
            pkg = pkg_match.group(1).strip()
            # Try to find a numeric ID in the package name
            num_match = re.search(r"(\d+)", pkg)
            if num_match:
                cloud_match = re.search(r"\.(aws|gcp|azure)\.", pkg)
                cloud = cloud_match.group(1).upper() if cloud_match else "AWS"
                result["check_id"] = f"AVD-{cloud}-{num_match.group(1).zfill(4)}"

    return result


# ── YAML metadata extraction ──────────────────────────────────────────────────

def _parse_yaml_metadata(source: str, path: str) -> dict:
    """
    Extract metadata from a YAML-based Trivy check.

    YAML checks in trivy-checks look like:
    ---
    id: AVD-AWS-0086
    title: "S3 Bucket Has Public Access Block"
    description: "..."
    severity: HIGH
    short_code: no-public-access-with-acl
    ...
    """
    result = {
        "check_id":    "",
        "check_name":  "",
        "severity":    "",
        "short_code":  "",
        "description": "",
    }
    try:
        # YAML files may contain multiple documents; take the first
        docs = list(yaml.safe_load_all(source))
        meta = docs[0] if docs else {}
        if not isinstance(meta, dict):
            return result

        result["check_id"]    = _normalize_check_id(meta.get("id", meta.get("avd_id", "")))
        result["check_name"]  = meta.get("title", meta.get("name", ""))
        result["description"] = meta.get("description", "")
        result["severity"]    = str(meta.get("severity", "")).upper()
        result["short_code"]  = meta.get("short_code", meta.get("shortCode", ""))

        # Some YAML checks nest metadata under `spec.policy.metadata`
        spec = meta.get("spec", {}) or {}
        policy = spec.get("policy", {}) or {}
        policy_meta = policy.get("metadata", {}) or {}
        if not result["check_id"]:
            result["check_id"] = _normalize_check_id(policy_meta.get("id", ""))
        if not result["check_name"]:
            result["check_name"] = policy_meta.get("title", "")

    except yaml.YAMLError as e:
        print(f"[WARN] YAML parse error in {path}: {e}", file=sys.stderr)

    return result


def extract_metadata(source: str, path: str) -> dict:
    """Dispatch to the correct parser based on file extension."""
    if path.endswith(".rego"):
        return _parse_rego_metadata(source)
    else:
        return _parse_yaml_metadata(source, path)


# ─── Main processing ───────────────────────────────────────────────────────────

def process_file(item: dict, fetch_source: bool) -> dict | None:
    """
    Fetch and parse a single policy file (rego or yaml).
    Returns a CSV row dict; returns None only when source fetch fails.
    """
    path = item["path"]
    raw_url = f"{RAW_BASE}/{path}"

    source = fetch_raw(path) if fetch_source else ""
    if fetch_source and not source:
        return None

    meta = extract_metadata(source, path)

    return {
        "check_id":        meta["check_id"],
        "check_name":      meta["check_name"],
        "severity":        meta["severity"],
        "short_code":      meta["short_code"],
        "description":     meta["description"],
        "service":         _infer_service(path),
        "framework":       _infer_framework(path),
        "source_file_url": raw_url,
        "source_code":     source,
    }


def generate_trivy_csv(framework: str = "cloudformation", fetch_source: bool = True):
    base_path = FRAMEWORK_PATHS.get(framework, FRAMEWORK_PATHS["cloudformation"])

    print(f"[INFO] Fetching file tree from {REPO_OWNER}/{REPO_NAME} at '{base_path}' ...")
    items = get_tree(base_path)
    print(f"[INFO] Found {len(items)} policy files (.rego + .yaml)")

    if not items:
        print("[ERROR] No files found. Check the base_path or GitHub API rate limits.", file=sys.stderr)
        print(f"[DEBUG] base_path used: {base_path}", file=sys.stderr)
        print(f"[DEBUG] Token present: {'yes' if _token else 'no'}", file=sys.stderr)
        sys.exit(1)

    rows = []
    fetch_failed = 0
    missing_check_id = 0

    if fetch_source:
        print(f"[INFO] Fetching source for {len(items)} files with {MAX_WORKERS} workers ...")
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {executor.submit(process_file, item, True): item for item in items}
            for i, future in enumerate(as_completed(futures), 1):
                result = future.result()
                if result:
                    rows.append(result)
                    if not result["check_id"]:
                        missing_check_id += 1
                else:
                    fetch_failed += 1
                if i % 50 == 0:
                    print(f"[INFO]   processed {i}/{len(items)} files ...")
    else:
        # Fast path: use GitHub Trees API metadata only, no source fetch
        print("[INFO] Skipping source fetch (--no-fetch mode). Extracting IDs from paths only.")
        for item in items:
            path = item["path"]
            # Infer a plausible check ID from path
            # e.g. checks/cloud/aws/s3/enable_versioning.rego
            name_part = Path(path).stem.replace("_", " ").title()
            svc = _infer_service(path)
            rows.append({
                "check_id":        "",  # unknown without source
                "check_name":      name_part,
                "severity":        "",
                "short_code":      Path(path).stem,
                "description":     "",
                "service":         svc,
                "framework":       _infer_framework(path),
                "source_file_url": f"{RAW_BASE}/{path}",
                "source_code":     "",
            })

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\n[DONE] Wrote {len(rows)} checks to {OUTPUT_FILE}")
    if fetch_failed:
        print(f"[WARN] {fetch_failed} files could not be fetched")
    if missing_check_id:
        print(f"[WARN] {missing_check_id} files were saved with empty check_id")
    print(f"[INFO] Sample IDs: {[r['check_id'] for r in rows[:5]]}")


# ─── Debug helper ─────────────────────────────────────────────────────────────

def debug_tree_sample(base_path: str, n: int = 5):
    """Print a few raw paths and their content for debugging."""
    items = get_tree(base_path)
    print(f"\n=== Found {len(items)} files under '{base_path}' ===")
    for item in items[:n]:
        print(f"\n--- {item['path']} ---")
        src = fetch_raw(item["path"])
        print(src[:500])
        print("...")
        meta = extract_metadata(src, item["path"])
        print(f"Extracted: {meta}")


# ─── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate Trivy policy CSV for IaC security remediation")
    parser.add_argument(
        "--framework",
        choices=list(FRAMEWORK_PATHS.keys()),
        default="cloudformation",
        help="Which framework's checks to collect (default: cloudformation)"
    )
    parser.add_argument(
        "--no-fetch",
        action="store_true",
        help="Skip fetching source code (fast, IDs from path only)"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Print sample raw file content and extracted metadata for debugging"
    )
    args = parser.parse_args()

    if args.debug:
        base_path = FRAMEWORK_PATHS[args.framework]
        debug_tree_sample(base_path, n=3)
    else:
        generate_trivy_csv(
            framework=args.framework,
            fetch_source=not args.no_fetch
        )

import requests, csv, re, os
from concurrent.futures import ThreadPoolExecutor, as_completed

GITHUB_API   = "https://api.github.com"
REPO_OWNER   = "aquasecurity"
REPO_NAME    = "trivy-checks"
RAW_BASE     = f"https://raw.githubusercontent.com/{REPO_OWNER}/{REPO_NAME}/main"
HEADERS      = {"Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28"}

# --- Layer 1: Parse Rego checks (your existing 175) ---
def get_rego_checks() -> list[dict]:
    """Get all non-test .rego files under checks/cloud/aws/"""
    url = f"{GITHUB_API}/repos/{REPO_OWNER}/{REPO_NAME}/git/trees/main?recursive=1"
    tree = requests.get(url, headers=HEADERS, timeout=30).json().get("tree", [])
    return [
        item for item in tree
        if item["path"].startswith("checks/cloud/aws/")
        and item["path"].endswith(".rego")
        and "_test.rego" not in item["path"]
    ]

def parse_rego_metadata(content: str, path: str) -> dict | None:
    """Extract METADATA block from a Rego file."""
    avd_id      = re.search(r"#\s*avd_id:\s*((?:AVD-)?AWS-\d+)", content)
    custom_id   = re.search(r"#\s*id:\s*((?:AVD-)?AWS-\d+)", content)
    alias_id    = re.search(r"#\s*-\s*((?:AVD-)?AWS-\d+)", content)
    title       = re.search(r"#\s*title:\s*(.+)",               content)
    description = re.search(r"#\s*description:\s*(.+)",         content)
    severity    = re.search(r"#\s*severity:\s*(\w+)",            content)
    short_code  = re.search(r"#\s*short_code:\s*(.+)",           content)

    service = path.split("/")[3] if len(path.split("/")) > 3 else "unknown"
    raw_url = f"{RAW_BASE}/{path}"

    return {
        "check_id":    _normalize_check_id(
            avd_id.group(1) if avd_id else (custom_id.group(1) if custom_id else (alias_id.group(1) if alias_id else ""))
        ),
        "check_name":  title.group(1).strip()       if title       else "",
        "description": description.group(1).strip() if description else "",
        "severity":    severity.group(1).upper()    if severity    else "",
        "short_code":  short_code.group(1).strip()  if short_code  else "",
        "service":     service,
        "source":      "rego",
        "source_file_url": raw_url,
        "source_code": content,
    }

# --- Layer 2: AVD Docs (catches Go-native checks missing from Rego layer) ---
def get_avd_doc_checks() -> list[dict]:
    """
    Enumerate avd_docs/aws/ to find ALL check IDs including Go-native ones.
    Each subdirectory is a service; each .md file is one check.
    """
    url = f"{GITHUB_API}/repos/{REPO_OWNER}/{REPO_NAME}/git/trees/main?recursive=1"
    tree = requests.get(url, headers=HEADERS, timeout=30).json().get("tree", [])
    md_files = [
        item for item in tree
        if item["path"].startswith("avd_docs/aws/")
        and item["path"].endswith(".md")
    ]
    return md_files

def parse_avd_doc(content: str, path: str) -> dict | None:
    """Parse an AVD markdown doc for check metadata."""
    # Path: avd_docs/aws/<service>/<avd_id>.md  e.g. avd_docs/aws/s3/AVD-AWS-0086.md
    parts    = path.split("/")
    service  = parts[2] if len(parts) > 2 else "unknown"
    filename = parts[-1].replace(".md", "")

    # Extract from markdown frontmatter or headings
    avd_id    = re.search(r"avd_id:\s*((?:AVD-)?AWS-\d+)", content) or \
                re.search(r"#\s*((?:AVD-)?AWS-\d+)",        content)
    title     = re.search(r"title:\s*[\"']?(.+?)[\"']?\n", content)
    severity  = re.search(r"severity:\s*(\w+)",             content)
    # The filename itself is usually the AVD ID
    check_id  = _normalize_check_id(avd_id.group(1) if avd_id else filename.upper())

    raw_url = f"{RAW_BASE}/{path}"
    return {
        "check_id":    check_id,
        "check_name":  title.group(1).strip() if title else filename,
        "description": "",   # fill from content body below
        "severity":    severity.group(1).upper() if severity else "",
        "short_code":  filename.lower().replace("avd-aws-", ""),
        "service":     service,
        "source":      "avd_doc",
        "source_file_url": raw_url,
        "source_code": "",   # docs don't have Rego source
    }

# --- Merge both layers ---
def generate_full_trivy_csv(output_path: str = "trivy_policy_map.csv"):
    rego_items = get_rego_checks()
    avd_items  = get_avd_doc_checks()

    results: dict[str, dict] = {}   # keyed by check_id

    # Step 1: fetch and parse all Rego files in parallel
    def fetch_rego(item):
        raw_url = f"{RAW_BASE}/{item['path']}"
        content = requests.get(raw_url, timeout=15).text
        return parse_rego_metadata(content, item["path"])

    with ThreadPoolExecutor(max_workers=20) as pool:
        futures = {pool.submit(fetch_rego, item): item for item in rego_items}
        for future in as_completed(futures):
            row = future.result()
            if row:
                key = row["check_id"] or f"NO-ID-REGO:{futures[future]['path']}"
                results[key] = row

    print(f"[1/2] Rego layer: {len(results)} checks parsed")

    # Step 2: fetch AVD docs and FILL IN any missing check IDs
    def fetch_avd(item):
        raw_url = f"{RAW_BASE}/{item['path']}"
        content = requests.get(raw_url, timeout=15).text
        return parse_avd_doc(content, item["path"])

    added = 0
    with ThreadPoolExecutor(max_workers=20) as pool:
        futures = {pool.submit(fetch_avd, item): item for item in avd_items}
        for future in as_completed(futures):
            row = future.result()
            if row:
                key = row["check_id"] or f"NO-ID-AVD:{futures[future]['path']}"
                if key not in results:
                    results[key] = row
                    added += 1

    print(f"[2/2] AVD doc layer added {added} Go-native checks  →  total: {len(results)}")

    # Step 3: write CSV
    fieldnames = ["check_id", "check_name", "description", "severity",
                  "short_code", "service", "source", "source_file_url", "source_code"]
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(sorted(results.values(), key=lambda r: r["check_id"]))

    print(f"Written to {output_path}")

if __name__ == "__main__":
    generate_full_trivy_csv("trivy_cfn_policy_map.csv")