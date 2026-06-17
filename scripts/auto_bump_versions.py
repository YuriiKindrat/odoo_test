#!/usr/bin/env python3
import ast
import re
import subprocess
import sys
from pathlib import Path

CUSTOM_ADDONS = Path("custom_addons")
EXCLUDE_DIRS = {"tests", "i18n"}


def git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True)


def git_check(*args):
    result = git(*args)
    if result.returncode != 0:
        print(f"git {' '.join(args)} failed: {result.stderr}", file=sys.stderr)
        sys.exit(1)
    return result.stdout.strip()


def get_changed_modules():
    diff = git_check("diff", "HEAD~1..HEAD", "--name-only")
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


def read_version_at_head1(module):
    manifest_path = CUSTOM_ADDONS / module / "__manifest__.py"
    result = git("show", f"HEAD~1:{manifest_path}")
    if result.returncode != 0:
        return None
    return ast.literal_eval(result.stdout).get("version")


def bump_version(version):
    parts = version.split(".")
    parts[-1] = str(int(parts[-1]) + 1)
    return ".".join(parts)


def write_manifest_version(module, new_version):
    manifest_path = CUSTOM_ADDONS / module / "__manifest__.py"
    content = manifest_path.read_text()
    updated = re.sub(
        r"(['\"]version['\"]:\s*['\"])[^'\"]+(['\"])",
        lambda m: f"{m.group(1)}{new_version}{m.group(2)}",
        content,
    )
    manifest_path.write_text(updated)


MIGRATION_PLACEHOLDER = "current_version"


def has_placeholder_migration(module):
    placeholder = CUSTOM_ADDONS / module / "migrations" / MIGRATION_PLACEHOLDER
    return placeholder.is_dir()


def process_module(module):
    base_version = read_version_at_head1(module)
    if base_version is None:
        print(f"  {module}: not found in HEAD~1, skipping")
        return

    new_version = bump_version(base_version)

    if has_placeholder_migration(module):
        old_path = CUSTOM_ADDONS / module / "migrations" / MIGRATION_PLACEHOLDER
        new_path = CUSTOM_ADDONS / module / "migrations" / new_version
        old_path.rename(new_path)
        print(f"  {module}: renamed migration {MIGRATION_PLACEHOLDER} -> {new_version}")

    write_manifest_version(module, new_version)
    print(f"  {module}: {base_version} -> {new_version}")


def main():
    modules = get_changed_modules()
    if not modules:
        print("No relevant module changes detected.")
        return

    print(f"Bumping: {', '.join(sorted(modules))}")
    for module in sorted(modules):
        process_module(module)

    git_check("add", str(CUSTOM_ADDONS))

    if subprocess.run(["git", "diff", "--cached", "--quiet"]).returncode == 0:
        print("Nothing to commit.")
        return

    git_check("commit", "-m", "auto: bump module versions [skip-bump]")
    git_check("pull", "--rebase")
    git_check("push")
    print("Done.")


if __name__ == "__main__":
    main()