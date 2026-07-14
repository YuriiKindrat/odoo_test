#!/usr/bin/env python3
"""Check that changed Odoo modules have bumped their version in __manifest__.py.

Usage:
    python3 scripts/module_version_bump.py <base_branch>

Example:
    python3 scripts/module_version_bump.py develop
    python3 scripts/module_version_bump.py main
"""

import ast
import os
import subprocess
import sys

CUSTOM_ADDONS_DIR = "custom_addons"

EXCLUDED_PATTERNS = (
    "/tests/",
    "/tests\\",
    "/i18n/",
)

EXCLUDED_EXTENSIONS = (".md", ".rst")


def run_git(args: list[str]) -> str:
    result = subprocess.run(
        ["git"] + args,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def parse_version(manifest_content: str) -> str | None:
    try:
        data = ast.literal_eval(manifest_content)
    except (ValueError, SyntaxError):
        return None
    return data.get("version")


def version_tuple(version: str) -> tuple[int, ...]:
    return tuple(int(x) for x in version.split("."))


def get_changed_files(base_branch: str) -> list[str]:
    committed = run_git(["diff", "--name-only", f"origin/{base_branch}...HEAD"])
    uncommitted = run_git(["diff", "--name-only", "HEAD"])
    all_files = set()
    if committed:
        all_files.update(committed.splitlines())
    if uncommitted:
        all_files.update(uncommitted.splitlines())
    return sorted(all_files)


def is_significant_change(file_path: str) -> bool:
    for pattern in EXCLUDED_PATTERNS:
        if pattern in file_path:
            return False
    _, ext = os.path.splitext(file_path)
    if ext.lower() in EXCLUDED_EXTENSIONS:
        return False
    return True


def get_changed_modules(changed_files: list[str]) -> set[str]:
    modules = set()
    for path in changed_files:
        parts = path.split("/")
        if len(parts) >= 2 and parts[0] == CUSTOM_ADDONS_DIR:
            if is_significant_change(path):
                modules.add(parts[1])
    return modules


def read_head_manifest(module: str) -> str | None:
    manifest_path = os.path.join(CUSTOM_ADDONS_DIR, module, "__manifest__.py")
    if not os.path.isfile(manifest_path):
        return None
    with open(manifest_path, "r") as f:
        return f.read()


def read_base_manifest(module: str, base_branch: str) -> str | None:
    ref_path = f"origin/{base_branch}:{CUSTOM_ADDONS_DIR}/{module}/__manifest__.py"
    try:
        return run_git(["show", ref_path])
    except subprocess.CalledProcessError:
        return None


def check_versions(base_branch: str) -> bool:
    changed_files = get_changed_files(base_branch)
    modules = get_changed_modules(changed_files)

    if not modules:
        print("No module changes detected. Nothing to check.")
        return True

    print(f"Checking version bumps against origin/{base_branch}...\n")

    failed = []
    for module in sorted(modules):
        head_content = read_head_manifest(module)
        if head_content is None:
            print(f"  {module}: (deleted module, skipping)")
            continue

        base_content = read_base_manifest(module, base_branch)
        if base_content is None:
            print(f"  {module}: (new module, skipping)")
            continue

        head_version = parse_version(head_content)
        base_version = parse_version(base_content)

        if head_version is None:
            print(f"  {module}: FAIL - cannot parse version from HEAD __manifest__.py")
            failed.append(module)
            continue

        if base_version is None:
            print(f"  {module}: FAIL - cannot parse version from base __manifest__.py")
            failed.append(module)
            continue

        try:
            head_tuple = version_tuple(head_version)
            base_tuple = version_tuple(base_version)
        except ValueError:
            print(f"  {module}: FAIL - invalid version format")
            failed.append(module)
            continue

        if head_tuple > base_tuple:
            print(f"  {module}: {base_version} -> {head_version} OK")
        elif head_tuple == base_tuple:
            print(f"  {module}: {base_version} -> {head_version} FAIL (version not bumped)")
            failed.append(module)
        else:
            print(f"  {module}: {base_version} -> {head_version} FAIL (version decreased)")
            failed.append(module)

    print()

    if failed:
        print("Version check failed. Bump the version in these modules:")
        for module in failed:
            print(f"  - {CUSTOM_ADDONS_DIR}/{module}/__manifest__.py")
        return False

    print("All version checks passed.")
    return True


def main() -> None:
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <base_branch>", file=sys.stderr)
        sys.exit(2)

    base_branch = sys.argv[1]

    try:
        success = check_versions(base_branch)
    except subprocess.CalledProcessError as e:
        print(f"Git command failed: {e}", file=sys.stderr)
        if e.stderr:
            print(e.stderr, file=sys.stderr)
        sys.exit(2)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
