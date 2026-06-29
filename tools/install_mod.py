#!/usr/bin/env python3
"""Package and install Pax Germanica into the HOI4 user mod folder.

Dependency-free (standard library only). Cross-platform: locates the per-OS
"Documents/Paradox Interactive/Hearts of Iron IV/mod" directory the game reads,
builds the art, then makes HOI4 see this checkout in one of two ways:

  * dev pointer (default) - write "<mods>/<slug>.mod" whose path= points at this
    repo. No copy; edits to the working tree are live in-game.
  * --package           - stage a clean, shippable copy into "<mods>/<slug>/" and
    write a pointer with path="mod/<slug>". Same file set as the release zip.

Metadata (name/version/supported_version/replace_path/tags) is read from
descriptor.mod so the generated pointer stays correct as the version bumps.

Usage:
    python tools/install_mod.py                 # build art + dev pointer to repo
    python tools/install_mod.py --package       # build art + clean copy into mod/<slug>/
    python tools/install_mod.py --skip-build    # don't run build_assets first
    python tools/install_mod.py --mods-dir PATH # override the HOI4 mod directory
    python tools/install_mod.py --uninstall     # remove the pointer (+ copied folder)

The mod directory is resolved in this order: --mods-dir, $HOI4_MOD_DIR, then the
platform default.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DESCRIPTOR = os.path.join(ROOT, "descriptor.mod")

# Files/dirs the game needs - mirrors the whitelist in .github/workflows/release.yml.
PACKAGE_ITEMS = [
    "descriptor.mod", ".metadata", "common", "history", "gfx", "interface",
    "localisation", "thumbnail.png", "LICENSE", "README.md",
]
# Never copied into a packaged install (editable sources / tooling / vcs).
PACKAGE_IGNORE = shutil.ignore_patterns("_src", "tools", ".github", ".git", ".claude", ".vscode")


# ------------------------------------------------------------------- descriptor

def read_descriptor():
    """Parse name/version/supported_version/replace_path/tags from descriptor.mod."""
    with open(DESCRIPTOR, encoding="utf-8-sig") as fh:
        text = fh.read()

    def scalar(key):
        m = re.search(rf'{key}\s*=\s*"([^"]*)"', text)
        return m.group(1) if m else None

    name = scalar("name")
    if not name:
        sys.exit("install_mod: descriptor.mod has no name=\"...\"")
    tags_block = re.search(r"tags\s*=\s*\{([^}]*)\}", text)
    tags = re.findall(r'"([^"]+)"', tags_block.group(1)) if tags_block else []
    return {
        "name": name,
        "version": scalar("version") or "0.0.0",
        "supported_version": scalar("supported_version") or "*",
        "replace_path": scalar("replace_path"),
        "tags": tags,
        "slug": re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_"),
    }


# ----------------------------------------------------------- mod-dir resolution

def default_mods_dir():
    """Platform-default '.../Hearts of Iron IV/mod' the game reads."""
    if sys.platform == "win32":
        base = os.path.join(_windows_documents(), "Paradox Interactive")
    elif sys.platform == "darwin":
        base = os.path.join(os.path.expanduser("~"), "Documents", "Paradox Interactive")
    else:  # linux / other
        base = os.path.join(os.path.expanduser("~"), ".local", "share", "Paradox Interactive")
    return os.path.join(base, "Hearts of Iron IV", "mod")


def _windows_documents():
    """Real Documents path (handles OneDrive redirection), with a safe fallback."""
    try:
        import winreg  # noqa: PLC0415 - Windows-only stdlib

        key = r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as h:
            personal, _ = winreg.QueryValueEx(h, "Personal")
        personal = os.path.expandvars(personal)
        if personal and os.path.isdir(personal):
            return personal
    except OSError:
        pass
    return os.path.join(os.path.expanduser("~"), "Documents")


def resolve_mods_dir(cli_value):
    return os.path.abspath(cli_value or os.environ.get("HOI4_MOD_DIR") or default_mods_dir())


# ----------------------------------------------------------------- pointer file

def pointer_text(meta, path_value):
    lines = [
        f'name="{meta["name"]}"',
        f'version="{meta["version"]}"',
        f'supported_version="{meta["supported_version"]}"',
        f'path="{path_value}"',
    ]
    if meta["replace_path"]:
        lines.append(f'replace_path="{meta["replace_path"]}"')
    if meta["tags"]:
        lines.append("tags={ " + " ".join(f'"{t}"' for t in meta["tags"]) + " }")
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------------------ steps

def run_build():
    print("[install_mod] building art (build_assets.py)...")
    try:
        subprocess.run([sys.executable, os.path.join(ROOT, "tools", "build_assets.py")],
                       check=True)
    except subprocess.CalledProcessError:
        sys.exit("install_mod: art build failed. Install deps "
                 "(python -m pip install -r tools/requirements.txt) or pass --skip-build.")


def stage_package(dest_dir):
    """Clean-copy the whitelisted file set into dest_dir."""
    if os.path.exists(dest_dir):
        shutil.rmtree(dest_dir)
    os.makedirs(dest_dir, exist_ok=True)
    for item in PACKAGE_ITEMS:
        src = os.path.join(ROOT, item)
        if not os.path.exists(src):
            print(f"  WARN  whitelisted item missing, skipping: {item}")
            continue
        dst = os.path.join(dest_dir, item)
        if os.path.isdir(src):
            shutil.copytree(src, dst, ignore=PACKAGE_IGNORE)
        else:
            shutil.copy2(src, dst)


def ensure_mods_dir(mods_dir):
    parent = os.path.dirname(mods_dir)  # .../Hearts of Iron IV
    if not os.path.isdir(parent):
        print(f"  WARN  {parent} does not exist - HOI4 may not be installed or has "
              f"not been run yet. Creating the mod folder anyway.")
    os.makedirs(mods_dir, exist_ok=True)


def do_install(meta, mods_dir, package):
    ensure_mods_dir(mods_dir)
    pointer = os.path.join(mods_dir, f"{meta['slug']}.mod")
    if package:
        dest = os.path.join(mods_dir, meta["slug"])
        stage_package(dest)
        with open(pointer, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(pointer_text(meta, f"mod/{meta['slug']}"))
        print(f"[install_mod] packaged copy -> {dest}")
    else:
        repo_path = ROOT.replace("\\", "/")  # HOI4 wants forward slashes
        with open(pointer, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(pointer_text(meta, repo_path))
        print(f"[install_mod] dev pointer -> repo ({repo_path})")
    print(f"[install_mod] wrote pointer -> {pointer}")
    print(f"[install_mod] done. Enable \"{meta['name']}\" in the HOI4 launcher's mod list.")


def do_uninstall(meta, mods_dir):
    pointer = os.path.join(mods_dir, f"{meta['slug']}.mod")
    folder = os.path.join(mods_dir, meta["slug"])
    removed = False
    if os.path.isfile(pointer):
        os.remove(pointer)
        print(f"[install_mod] removed pointer -> {pointer}")
        removed = True
    if os.path.isdir(folder):
        shutil.rmtree(folder)
        print(f"[install_mod] removed packaged copy -> {folder}")
        removed = True
    if not removed:
        print(f"[install_mod] nothing to uninstall in {mods_dir}")


# ------------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description="Package and install Pax Germanica into the HOI4 mod folder.")
    ap.add_argument("--package", action="store_true",
                    help="stage a clean copy into mod/<slug>/ instead of a dev pointer")
    ap.add_argument("--skip-build", action="store_true",
                    help="do not run build_assets.py before installing")
    ap.add_argument("--mods-dir",
                    help="override the HOI4 mod directory (else $HOI4_MOD_DIR or the platform default)")
    ap.add_argument("--uninstall", action="store_true",
                    help="remove the installed pointer (and packaged copy, if any)")
    args = ap.parse_args()

    meta = read_descriptor()
    mods_dir = resolve_mods_dir(args.mods_dir)
    print(f"[install_mod] mod dir: {mods_dir}")

    if args.uninstall:
        do_uninstall(meta, mods_dir)
        return

    if not args.skip_build:
        run_build()
    do_install(meta, mods_dir, args.package)


if __name__ == "__main__":
    main()
