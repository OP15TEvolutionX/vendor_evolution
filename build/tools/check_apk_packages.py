#!/usr/bin/env python3
"""Fail OTA packaging on conflicting APK package names in target-files."""
import argparse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import re
import subprocess
import sys

PARTITIONS = ("SYSTEM", "SYSTEM_EXT", "PRODUCT", "VENDOR", "ODM", "OEM",
              "SYSTEM_DLKM", "VENDOR_DLKM", "ODM_DLKM")


def run_aapt(aapt, command, apk):
    result = subprocess.run([str(aapt), "dump", command, str(apk)],
                            capture_output=True, text=True, timeout=60)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "aapt2 failed")
    return result.stdout


def split_identity(aapt, apk):
    header = next((line for line in run_aapt(aapt, "badging", apk).splitlines()
                   if line.startswith("package:")), "")
    version = re.search(r"versionCode='([^']+)'", header)
    split = re.search(r"split='([^']+)'", header)
    if not version:
        raise RuntimeError("cannot read APK version/split identity")
    return split.group(1) if split else "", version.group(1)


def is_split_set(paths, identity):
    # A base plus distinct splits in one code path is one installed package.
    # Multiple base APKs, repeated splits, or different code paths are conflicts.
    if len({p.parent for p in paths}) != 1:
        return False
    entries = [identity(p) for p in paths]
    splits = [split for split, _ in entries]
    return (splits.count("") == 1 and len(set(splits)) == len(splits)
            and len({version for _, version in entries}) == 1)


def audit(root, aapt, jobs=4):
    if not root.is_dir():
        raise RuntimeError("target-files directory is missing: " + str(root))
    files = sorted(p for part in PARTITIONS for p in (root / part).rglob("*.apk"))
    if not files:
        raise RuntimeError("no APKs found in target-files; refusing an empty audit")

    def inspect(apk):
        try:
            package = run_aapt(aapt, "packagename", apk).strip()
            if not re.fullmatch(r"[A-Za-z0-9_.]+", package):
                raise RuntimeError("cannot read APK package name")
            return apk, package, None
        except (OSError, RuntimeError, subprocess.TimeoutExpired) as error:
            return apk, None, str(error)

    groups = defaultdict(list)
    problems = []
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        for apk, package, error in pool.map(inspect, files):
            if error:
                problems.append("Unreadable APK: " + str(apk.relative_to(root)) + ": " + error)
            else:
                groups[package].append(apk)
    for package, paths in sorted(groups.items()):
        if len(paths) < 2:
            continue
        try:
            if is_split_set(paths, lambda p: split_identity(aapt, p)):
                continue
        except (OSError, RuntimeError, subprocess.TimeoutExpired) as error:
            problems.append("Cannot validate split APKs for " + package + ": " + str(error))
        problems.append("Duplicate package " + package + ":\n" + "\n".join(
            "  " + str(p.relative_to(root)) for p in paths))
    return len(files), len(groups), problems


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--aapt2", type=Path, required=True)
    args = parser.parse_args()
    try:
        count, packages, problems = audit(args.root, args.aapt2)
    except (OSError, RuntimeError) as error:
        print("APK package audit FAILED: " + str(error), file=sys.stderr)
        return 1
    if problems:
        print("APK package audit FAILED; OTA packaging blocked:", file=sys.stderr)
        print("\n".join(problems), file=sys.stderr)
        print("Fix package identities/product selection; run installclean if alternate APKs "
              "were installed by module tests.", file=sys.stderr)
        return 1
    print(f"APK package audit OK: {count} APKs, {packages} packages")
    return 0


if __name__ == "__main__":
    sys.exit(main())
