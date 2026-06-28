#!/usr/bin/env python3
"""Static validator for the Pax Germanica mod.

Dependency-free (standard library only). Checks, without launching the game:

  * Paradox script files (.txt/.gfx/.mod): balanced { } and " (comment/string aware).
  * Localisation .yml: UTF-8 BOM present + `l_english:` header.
  * Generated art: TGA/DDS/PNG headers parse and DDS byte-size matches its dimensions.
  * Cross-references are resolvable:
      - focus icons / idea pictures / character portraits / bookmark picture -> a sprite
        defined in interface/*.gfx, whose texturefile exists on disk;
      - ideas used (add_ideas / bookmark / focus rewards) are defined in common/ideas;
      - recruited characters are defined in common/characters;
      - focus prerequisites / mutually_exclusive point at real focus ids;
      - the OOB named by `oob = "..."` exists in history/units;
      - localisation keys exist for focuses, ideas, characters, advisors, the bookmark,
        the new tag PAX and the cosmetic tag GER_pax.

Exit code 0 = clean, 1 = errors found.  Usage:  python tools/lint_mod.py
"""

from __future__ import annotations

import glob
import os
import re
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ERRORS: list[str] = []
WARNINGS: list[str] = []


def err(msg):
    ERRORS.append(msg)


def warn(msg):
    WARNINGS.append(msg)


def rel(path):
    return os.path.relpath(path, ROOT).replace("\\", "/")


def read_text(path):
    with open(path, "rb") as fh:
        raw = fh.read()
    return raw.decode("utf-8-sig", errors="replace")


# --------------------------------------------------------------- script structure

def check_braces_and_quotes(path):
    """Comment/string-aware balance check for Paradox script files."""
    text = _strip_comments(read_text(path))  # remove # comments first (string-aware)
    depth, in_str, line = 0, False, 1
    for ch in text:
        if ch == "\n":
            line += 1
            continue
        if in_str:
            if ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth < 0:
                err(f"{rel(path)}: unbalanced '}}' (extra closing brace near line {line})")
                depth = 0
    if depth != 0:
        err(f"{rel(path)}: unbalanced braces (net {depth:+d} unclosed)")
    if in_str:
        err(f"{rel(path)}: unterminated string literal (odd number of '\"')")


def _strip_comments(text):
    out = []
    for raw_line in text.splitlines():
        in_str = False
        cut = len(raw_line)
        for i, ch in enumerate(raw_line):
            if ch == '"':
                in_str = not in_str
            elif ch == "#" and not in_str:
                cut = i
                break
        out.append(raw_line[:cut])
    return "\n".join(out)


def load(path):
    return _strip_comments(read_text(path))


# ------------------------------------------------------------------- yml checks

def check_yml(path):
    with open(path, "rb") as fh:
        head = fh.read(3)
    if head != b"\xef\xbb\xbf":
        err(f"{rel(path)}: missing UTF-8 BOM (HOI4 requires BOM on localisation files)")
    text = read_text(path)
    first = next((ln for ln in text.splitlines() if ln.strip()), "")
    if first.strip() != "l_english:":
        err(f"{rel(path)}: first non-empty line must be 'l_english:' (found {first!r})")


def collect_loc_keys():
    keys = set()
    for path in glob.glob(os.path.join(ROOT, "localisation", "**", "*.yml"), recursive=True):
        for m in re.finditer(r"^\s*([\w.]+):\d*\s+\"", read_text(path), re.M):
            keys.add(m.group(1))
    return keys


# ------------------------------------------------------------------ image headers

def check_tga(path):
    with open(path, "rb") as fh:
        h = fh.read(18)
    if len(h) < 18:
        return err(f"{rel(path)}: truncated TGA header")
    w, ht, bpp, itype = struct.unpack("<H", h[12:14])[0], struct.unpack("<H", h[14:16])[0], h[16], h[2]
    if itype != 2:
        err(f"{rel(path)}: TGA image type {itype} (expected 2, uncompressed true-color)")
    if bpp != 32:
        warn(f"{rel(path)}: TGA is {bpp}bpp (32 expected for BGRA flags)")
    if w == 0 or ht == 0:
        err(f"{rel(path)}: TGA has zero dimension")


def check_dds(path):
    with open(path, "rb") as fh:
        d = fh.read(128)
    if d[:4] != b"DDS ":
        return err(f"{rel(path)}: bad DDS magic")
    h, w = struct.unpack("<I", d[12:16])[0], struct.unpack("<I", d[16:20])[0]
    bits = struct.unpack("<I", d[88:92])[0]
    size = os.path.getsize(path)
    if bits == 32 and size != 128 + w * h * 4:
        err(f"{rel(path)}: DDS size {size} != header {128 + w * h * 4} for {w}x{h} BGRA")


def check_png(path):
    with open(path, "rb") as fh:
        if fh.read(8) != b"\x89PNG\r\n\x1a\n":
            err(f"{rel(path)}: bad PNG signature")


# ------------------------------------------------------------------- cross-refs

def main():
    # 1. script structure
    script_globs = ["descriptor.mod", "common/**/*.txt", "history/**/*.txt", "interface/**/*.gfx"]
    for pat in script_globs:
        for path in glob.glob(os.path.join(ROOT, pat), recursive=True):
            check_braces_and_quotes(path)

    # 2. localisation
    yml = glob.glob(os.path.join(ROOT, "localisation", "**", "*.yml"), recursive=True)
    if not yml:
        err("no localisation .yml files found")
    for path in yml:
        check_yml(path)
    loc_keys = collect_loc_keys()

    # 3. art headers
    for path in glob.glob(os.path.join(ROOT, "gfx", "**", "*.tga"), recursive=True):
        check_tga(path)
    for path in glob.glob(os.path.join(ROOT, "gfx", "**", "*.dds"), recursive=True):
        check_dds(path)
    if os.path.isfile(os.path.join(ROOT, "thumbnail.png")):
        check_png(os.path.join(ROOT, "thumbnail.png"))

    # 4. sprites defined in interface/*.gfx + their texturefiles exist
    sprites = {}
    for path in glob.glob(os.path.join(ROOT, "interface", "*.gfx")):
        body = load(path)
        for block in re.findall(r"spriteType\s*=\s*\{(.*?)\}", body, re.S):
            name = re.search(r'name\s*=\s*"([^"]+)"', block)
            tex = re.search(r'texturefile\s*=\s*"([^"]+)"', block)
            if name and tex:
                sprites[name.group(1)] = tex.group(1)
                if not os.path.isfile(os.path.join(ROOT, tex.group(1))):
                    err(f"sprite {name.group(1)}: texturefile not found -> {tex.group(1)}")

    def need_sprite(name, ctx):
        if name not in sprites:
            err(f"{ctx}: references undefined sprite '{name}'")

    # 5. flag files exist for each tag
    for tag in ("GER", "GER_pax", "PAX"):
        for sub in ("", "medium/", "small/"):
            fp = os.path.join(ROOT, "gfx", "flags", sub, f"{tag}.tga")
            if not os.path.isfile(fp):
                err(f"missing flag: gfx/flags/{sub}{tag}.tga")

    # 6. ideas defined
    ideas = set()
    for path in glob.glob(os.path.join(ROOT, "common", "ideas", "*.txt")):
        for m in re.finditer(r"^\s*(pax_\w+)\s*=\s*\{", load(path), re.M):
            ideas.add(m.group(1))

    # idea pictures -> GFX_idea_<picture> sprite + loc name
    for path in glob.glob(os.path.join(ROOT, "common", "ideas", "*.txt")):
        body = load(path)
        for pic in re.findall(r"picture\s*=\s*(\w+)", body):
            need_sprite(f"GFX_idea_{pic}", f"idea picture '{pic}'")
    for idea in ideas:
        if idea not in loc_keys:
            err(f"idea '{idea}': no localisation name key")

    # 7. focuses
    focus_file = os.path.join(ROOT, "common", "national_focus", "pax_germanica.txt")
    focus_ids, focus_icons, focus_refs, focus_add_ideas = set(), [], [], []
    if os.path.isfile(focus_file):
        body = load(focus_file)
        focus_ids = set(re.findall(r"id\s*=\s*(PAX_\w+)", body))
        focus_icons = re.findall(r"icon\s*=\s*(GFX_\w+)", body)
        for blk in re.findall(r"(?:prerequisite|mutually_exclusive)\s*=\s*\{([^}]*)\}", body):
            focus_refs += re.findall(r"focus\s*=\s*(\w+)", blk)
        focus_add_ideas = re.findall(r"add_ideas\s*=\s*(\w+)", body)
    for icon in focus_icons:
        need_sprite(icon, "focus icon")
    for ref in focus_refs:
        if ref not in focus_ids:
            err(f"focus prerequisite/mutually_exclusive references unknown focus '{ref}'")
    for fid in focus_ids:
        if fid not in loc_keys:
            err(f"focus '{fid}': no localisation name key")

    # 8. characters
    char_file = os.path.join(ROOT, "common", "characters", "pax_germanica.txt")
    characters, char_portraits, advisor_tokens, char_name_keys = set(), [], [], []
    if os.path.isfile(char_file):
        body = load(char_file)
        characters = set(re.findall(r"^\s*(pax_ger_\w+)\s*=\s*\{", body, re.M))
        char_portraits = re.findall(r"(?:large|small)\s*=\s*\"(GFX_\w+)\"", body)
        advisor_tokens = re.findall(r"idea_token\s*=\s*(\w+)", body)
        char_name_keys = re.findall(r"name\s*=\s*\"([\w.]+)\"", body)
    for gfx in set(char_portraits):
        need_sprite(gfx, "character portrait")
    for key in char_name_keys:
        if key not in loc_keys:
            err(f"character name key '{key}': no localisation entry")
    for tok in advisor_tokens:
        if tok not in loc_keys:
            err(f"advisor idea_token '{tok}': no localisation name key")

    # 9. GER history wiring: add_ideas / recruit_character / oob
    ger_hist = os.path.join(ROOT, "history", "countries", "GER - Germany.txt")
    used_ideas, recruited, oobs = set(focus_add_ideas), set(), []
    if os.path.isfile(ger_hist):
        body = load(ger_hist)
        for blk in re.findall(r"add_ideas\s*=\s*\{([^}]*)\}", body):
            used_ideas |= set(blk.split())
        recruited = set(re.findall(r"recruit_character\s*=\s*(\w+)", body))
        oobs = re.findall(r'oob\s*=\s*"(\w+)"', body)
    # bookmark ideas
    bm = os.path.join(ROOT, "common", "bookmarks", "pax_germanica.txt")
    bm_pictures = []
    if os.path.isfile(bm):
        body = load(bm)
        for blk in re.findall(r"ideas\s*=\s*\{([^}]*)\}", body):
            used_ideas |= set(blk.split())
        bm_pictures = re.findall(r'picture\s*=\s*"(GFX_\w+)"', body)
        for key in ("PAXGER_bookmark", "PAXGER_bookmark_desc", "GER_PAXGER_DESC"):
            if key not in loc_keys:
                err(f"bookmark localisation key '{key}' missing")
    for pic in bm_pictures:
        need_sprite(pic, "bookmark picture")
    for idea in used_ideas:
        if idea not in ideas:
            err(f"add_ideas/bookmark uses undefined idea '{idea}'")
    for ch in recruited:
        if ch not in characters:
            err(f"recruit_character references undefined character '{ch}'")
    for oob in oobs:
        if not os.path.isfile(os.path.join(ROOT, "history", "units", f"{oob}.txt")):
            err(f"oob \"{oob}\" referenced but history/units/{oob}.txt not found")

    # 10. country / cosmetic localisation
    if "PAX" not in loc_keys:
        err("new tag 'PAX' has no localisation name key")
    if "GER_pax" not in loc_keys:
        err("cosmetic tag 'GER_pax' has no localisation name key")

    # ----------------------------------------------------------------- report
    print(f"sprites: {len(sprites)} | ideas: {len(ideas)} | focuses: {len(focus_ids)} | "
          f"characters: {len(characters)} | loc keys: {len(loc_keys)}")
    for w in WARNINGS:
        print(f"  WARN  {w}")
    for e in ERRORS:
        print(f"  ERROR {e}")
    if ERRORS:
        print(f"\nlint_mod: FAILED with {len(ERRORS)} error(s), {len(WARNINGS)} warning(s).")
        return 1
    print(f"\nlint_mod: OK ({len(WARNINGS)} warning(s)).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
