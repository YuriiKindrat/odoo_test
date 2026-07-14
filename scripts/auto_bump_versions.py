#!/usr/bin/env python3
"""Auto-bump Odoo module versions on push to feature/bug/fix branches.

Compares each changed module's version against develop. If the PR branch
version is not ahead of develop, bumps it to develop_version + 1.
If a migration folder named "current_version" exists, renames it to the
new version as well.

Usage:
    python3 scripts/auto_bump_versions.py
"""

import ast
import re
import shutil
import subprocess
import sys
from pathlib import Path

CUSTOM_ADDONS = Path("custom_addons")
EXCLUDE_DIRS = {"tests", "i18n"}
MIGRATION_PLACEHOLDER = "current_version"
BASE_BRANCH = "origin/develop"


def git(*args) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], capture_output=True, text=True)


def git_check(*args) -> str:
    result = git(*args)
    if result.returncode != 0:
        print(f"git {' '.join(args)} failed: {result.stderr}", file=sys.stderr)
        sys.exit(1)
    return result.stdout.strip()


def version_tuple(version: str) -> tuple:
    return tuple(int(x) for x in version.split("."))


def get_changed_modules() -> set[str]:
    diff = git_check("diff", f"{BASE_BRANCH}...HEAD", "--name-only")
    if not diff:
        return set()

    modules = set()
    for line in diff.splitlines():
        p = Path(line)
        parts = p.parts
        if len(parts) < 3 or parts[0] != str(CUSTOM_ADDONS):
            continue
        if parts[2] in EXCLUDE_DIRS:
            continue
        if p.suffix == ".md":
            continue
        modules.add(parts[1])
    return modules


def read_version_on_develop(module: str) -> str | None:
    manifest_path = CUSTOM_ADDONS / module / "__manifest__.py"
    result = git("show", f"{BASE_BRANCH}:{manifest_path}")
    if result.returncode != 0:
        return None
    return ast.literal_eval(result.stdout).get("version")


def read_current_version(module: str) -> str | None:
    manifest_path = CUSTOM_ADDONS / module / "__manifest__.py"
    if not manifest_path.exists():
        return None
    return ast.literal_eval(manifest_path.read_text()).get("version")


def bump_version(version: str) -> str:
    parts = version.split(".")
    parts[-1] = str(int(parts[-1]) + 1)
    return ".".join(parts)


def write_manifest_version(module: str, new_version: str) -> None:
    manifest_path = CUSTOM_ADDONS / module / "__manifest__.py"
    content = manifest_path.read_text()
    updated = re.sub(
        r'([\'"]version[\'"]\s*:\s*[\'"])[^\'"]+([\'"])',
        lambda m: f"{m.group(1)}{new_version}{m.group(2)}",
        content,
    )
    manifest_path.write_text(updated)


def has_placeholder_migration(module: str) -> bool:
    placeholder = CUSTOM_ADDONS / module / "migrations" / MIGRATION_PLACEHOLDER
    return placeholder.is_dir()


def migration_folder_exists_locally(module: str, version: str) -> bool:
    return (CUSTOM_ADDONS / module / "migrations" / version).is_dir()


def migration_folder_differs_from_develop(module: str, version: str) -> bool:
    path = f"{CUSTOM_ADDONS}/{module}/migrations/{version}"
    develop_result = git("ls-tree", BASE_BRANCH, path)
    local_result = git("ls-tree", "HEAD", path)
    if not develop_result.stdout.strip() or not local_result.stdout.strip():
        return False
    develop_sha = develop_result.stdout.split()[2]
    local_sha = local_result.stdout.split()[2]
    return develop_sha != local_sha


def process_module(module: str) -> None:
    develop_version = read_version_on_develop(module)
    if develop_version is None:
        print(f"  {module}: not found in develop, skipping")
        return

    current_version = read_current_version(module)
    if current_version is None:
        print(f"  {module}: manifest not found locally, skipping")
        return

    if version_tuple(current_version) > version_tuple(develop_version):
        print(f"  {module}: already bumped ({current_version} > {develop_version}), skipping")
        if has_placeholder_migration(module):
            print(f"  {module}: WARNING - migrations/{MIGRATION_PLACEHOLDER}/ still exists, rename it to migrations/{current_version}/ manually")
        return

    new_version = bump_version(develop_version)

    migrations_dir = CUSTOM_ADDONS / module / "migrations"
    if has_placeholder_migration(module):
        old_path = migrations_dir / MIGRATION_PLACEHOLDER
        new_path = migrations_dir / new_version
        old_path.rename(new_path)
        print(f"  {module}: renamed migrations/{MIGRATION_PLACEHOLDER}/ -> migrations/{new_version}/")
    elif (
        migration_folder_exists_locally(module, develop_version)
        and migration_folder_differs_from_develop(module, develop_version)
    ):
        # Race condition: current_version/ was already renamed to develop_version/ by a
        # previous auto-bump, but another branch claimed the same version first.
        # Copy our migration content to the new version folder, then restore the
        # develop_version/ folder from develop so it is not deleted on merge.
        old_path = migrations_dir / develop_version
        new_path = migrations_dir / new_version
        shutil.copytree(str(old_path), str(new_path))
        git_check("checkout", BASE_BRANCH, "--", str(old_path))
        print(f"  {module}: created migrations/{new_version}/ and restored migrations/{develop_version}/ from develop (race condition recovery)")
    elif migration_folder_exists_locally(module, current_version):
        # Develop moved ahead while this branch was open: current_version/ was already
        # renamed to current_version (e.g. 0.1.18/) by a previous auto-bump, but now
        # develop is at a higher version (e.g. 0.1.23) so we need to move it forward.
        old_path = migrations_dir / current_version
        new_path = migrations_dir / new_version
        if migration_folder_differs_from_develop(module, current_version):
            # Develop also has this version folder with different content → copy + restore
            shutil.copytree(str(old_path), str(new_path))
            git_check("checkout", BASE_BRANCH, "--", str(old_path))
        else:
            # Only on this branch (develop has no such folder) → simple rename
            old_path.rename(new_path)
        print(f"  {module}: migration folder moved migrations/{current_version}/ -> migrations/{new_version}/")

    write_manifest_version(module, new_version)
    print(f"  {module}: {current_version} -> {new_version} (develop: {develop_version})")


def main() -> None:
    modules = get_changed_modules()
    if not modules:
        print("No relevant module changes detected.")
        return

    print(f"Checking: {', '.join(sorted(modules))}")
    for module in sorted(modules):
        process_module(module)

    print("Done.")


if __name__ == "__main__":
    main()