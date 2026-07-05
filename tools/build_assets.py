#!/usr/bin/env python3
"""Build Pax Germanica's game art from SVG sources.

Reads tools/assets_manifest.json and converts each SVG under gfx/_src/ into the binary
formats Hearts of Iron IV expects:

  * flags    -> uncompressed 32-bit BGRA .tga
  * interface-> uncompressed 32-bit BGRA .dds  (DX9 header, loads natively in HOI4)
  * misc     -> .png

Rasterization backend (first available wins):
  1. external CLI on PATH: resvg / rsvg-convert / inkscape  (best SVG fidelity)
  2. a built-in, pure-Pillow SVG-subset renderer (no native deps; used by CI)

The built-in renderer supports the subset used by this mod's sources:
  rect (incl. rx), circle, ellipse, line, polygon, polyline, path (M/L/H/V/C/Q/Z),
  text (font-size, text-anchor), <g> grouping with translate()/scale()/matrix() and
  inherited presentation attributes. It supersamples then downscales (Lanczos) for AA.

Usage:
    python tools/build_assets.py            # build everything in the manifest
    python tools/build_assets.py --check    # build to temp + diff committed files (CI)

--check compares the uncompressed outputs (TGA/DDS) byte-for-byte, but compares PNG by
decoded pixels: PNG is zlib-compressed and the deflate stream is not reproducible across
platforms, so a byte diff would false-positive in CI even when the image is identical.
"""

from __future__ import annotations

import argparse
import io
import json
import math
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:  # pragma: no cover
    sys.exit("Pillow is required:  python -m pip install pillow")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(ROOT, "tools", "assets_manifest.json")
SUPERSAMPLE = 4  # render at NxN then downscale for antialiasing

# ----------------------------------------------------------------------------- colors

_NAMED = {
    "none": None, "black": (0, 0, 0), "white": (255, 255, 255), "red": (255, 0, 0),
    "green": (0, 128, 0), "blue": (0, 0, 255), "yellow": (255, 255, 0),
    "gray": (128, 128, 128), "grey": (128, 128, 128), "silver": (192, 192, 192),
    "navy": (0, 0, 128), "gold": (255, 215, 0), "maroon": (128, 0, 0),
    "orange": (255, 165, 0), "darkred": (139, 0, 0),
}


def parse_color(value):
    """Return an (r, g, b) tuple, or None for 'none'/empty/unparseable."""
    if value is None:
        return None
    v = value.strip().lower()
    if v in ("", "none", "transparent"):
        return None
    if v in _NAMED:
        return _NAMED[v]
    if v.startswith("#"):
        h = v[1:]
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        if len(h) == 6:
            return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    m = re.match(r"rgb\(\s*(\d+)\D+(\d+)\D+(\d+)\s*\)", v)
    if m:
        return tuple(min(255, int(g)) for g in m.groups())
    return None

# ----------------------------------------------------------------------- 2x3 affine


def mat_mul(a, b):
    """Combine two affine transforms expressed as (a,b,c,d,e,f)."""
    a0, a1, a2, a3, a4, a5 = a
    b0, b1, b2, b3, b4, b5 = b
    return (
        a0 * b0 + a2 * b1,
        a1 * b0 + a3 * b1,
        a0 * b2 + a2 * b3,
        a1 * b2 + a3 * b3,
        a0 * b4 + a2 * b5 + a4,
        a1 * b4 + a3 * b5 + a5,
    )


def apply_pt(m, x, y):
    return (m[0] * x + m[2] * y + m[4], m[1] * x + m[3] * y + m[5])


def avg_scale(m):
    sx = math.hypot(m[0], m[1])
    sy = math.hypot(m[2], m[3])
    return (sx + sy) / 2.0


def parse_transform(text):
    m = (1, 0, 0, 1, 0, 0)
    for name, args in re.findall(r"(\w+)\s*\(([^)]*)\)", text or ""):
        nums = [float(n) for n in re.findall(r"-?[\d.eE+]+", args)]
        if name == "translate":
            tx = nums[0] if nums else 0.0
            ty = nums[1] if len(nums) > 1 else 0.0
            m = mat_mul(m, (1, 0, 0, 1, tx, ty))
        elif name == "scale":
            sx = nums[0] if nums else 1.0
            sy = nums[1] if len(nums) > 1 else sx
            m = mat_mul(m, (sx, 0, 0, sy, 0, 0))
        elif name == "matrix" and len(nums) == 6:
            m = mat_mul(m, tuple(nums))
        elif name == "rotate" and nums:
            a = math.radians(nums[0])
            ca, sa = math.cos(a), math.sin(a)
            r = (ca, sa, -sa, ca, 0, 0)
            if len(nums) == 3:
                cx, cy = nums[1], nums[2]
                r = mat_mul((1, 0, 0, 1, cx, cy), mat_mul(r, (1, 0, 0, 1, -cx, -cy)))
            m = mat_mul(m, r)
    return m

# ------------------------------------------------------------------- built-in render


def _local(tag):
    return tag.split("}", 1)[-1] if "}" in tag else tag


def _style(attrib):
    out = {}
    for decl in attrib.get("style", "").split(";"):
        if ":" in decl:
            k, val = decl.split(":", 1)
            out[k.strip()] = val.strip()
    return out


def _get(attrib, style, key, default=None):
    if key in style:
        return style[key]
    return attrib.get(key, default)


def _flatten_bezier(p0, p1, p2, p3, steps=16):
    pts = []
    for i in range(1, steps + 1):
        t = i / steps
        mt = 1 - t
        x = (mt ** 3) * p0[0] + 3 * mt * mt * t * p1[0] + 3 * mt * t * t * p2[0] + t ** 3 * p3[0]
        y = (mt ** 3) * p0[1] + 3 * mt * mt * t * p1[1] + 3 * mt * t * t * p2[1] + t ** 3 * p3[1]
        pts.append((x, y))
    return pts


def _parse_path(d):
    """Return a list of subpaths (each a list of (x,y) user-space points)."""
    tokens = re.findall(r"[MmLlHhVvCcQqZz]|-?[\d.eE+]+", d or "")
    subpaths, cur, start, i = [], [], (0.0, 0.0), 0
    cmd = None
    def num():
        nonlocal i
        v = float(tokens[i]); i += 1; return v
    while i < len(tokens):
        t = tokens[i]
        if re.match(r"[A-Za-z]", t):
            cmd = t; i += 1
        rel = cmd.islower()
        c = cmd.upper()
        if c == "M":
            x, y = num(), num()
            if rel and cur:
                x += cur[-1][0]; y += cur[-1][1]
            if cur:
                subpaths.append(cur)
            cur = [(x, y)]; start = (x, y); cmd = "l" if rel else "L"
        elif c == "L":
            x, y = num(), num()
            if rel:
                x += cur[-1][0]; y += cur[-1][1]
            cur.append((x, y))
        elif c == "H":
            x = num()
            if rel:
                x += cur[-1][0]
            cur.append((x, cur[-1][1]))
        elif c == "V":
            y = num()
            if rel:
                y += cur[-1][1]
            cur.append((cur[-1][0], y))
        elif c == "C":
            p1 = (num(), num()); p2 = (num(), num()); p3 = (num(), num())
            if rel:
                bx, by = cur[-1]
                p1 = (p1[0] + bx, p1[1] + by); p2 = (p2[0] + bx, p2[1] + by); p3 = (p3[0] + bx, p3[1] + by)
            cur.extend(_flatten_bezier(cur[-1], p1, p2, p3))
        elif c == "Q":
            q = (num(), num()); p3 = (num(), num())
            if rel:
                bx, by = cur[-1]
                q = (q[0] + bx, q[1] + by); p3 = (p3[0] + bx, p3[1] + by)
            p0 = cur[-1]
            c1 = (p0[0] + 2 / 3 * (q[0] - p0[0]), p0[1] + 2 / 3 * (q[1] - p0[1]))
            c2 = (p3[0] + 2 / 3 * (q[0] - p3[0]), p3[1] + 2 / 3 * (q[1] - p3[1]))
            cur.extend(_flatten_bezier(p0, c1, c2, p3))
        elif c == "Z":
            if cur:
                cur.append(start); subpaths.append(cur); cur = []
    if cur:
        subpaths.append(cur)
    return subpaths


def _font(size):
    size = max(1, int(round(size)))
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # very old Pillow
        return ImageFont.load_default()


def _draw_element(el, draw, ctm, inherited):
    tag = _local(el.tag)
    style = dict(inherited)
    style.update({k: v for k, v in el.attrib.items() if k in (
        "fill", "stroke", "stroke-width", "text-anchor", "font-size")})
    style.update(_style(el.attrib))
    m = mat_mul(ctm, parse_transform(el.attrib.get("transform")))

    def fa(name, dflt=0.0):
        try:
            return float(el.attrib.get(name, dflt))
        except (TypeError, ValueError):
            return dflt

    fill = parse_color(_get(el.attrib, style, "fill", "black"))
    stroke = parse_color(_get(el.attrib, style, "stroke", "none"))
    sw = float(_get(el.attrib, style, "stroke-width", 1.0) or 1.0) * avg_scale(m)
    sw_i = max(1, int(round(sw))) if stroke else 0

    def dev(pts):
        return [apply_pt(m, x, y) for x, y in pts]

    if tag == "g":
        for child in el:
            _draw_element(child, draw, m, style)
    elif tag == "rect":
        x, y, w, h = fa("x"), fa("y"), fa("width"), fa("height")
        rx = fa("rx") or fa("ry")
        (x0, y0), (x1, y1) = apply_pt(m, x, y), apply_pt(m, x + w, y + h)
        box = [min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)]
        if rx:
            r = rx * avg_scale(m)
            draw.rounded_rectangle(box, radius=r, fill=fill, outline=stroke, width=sw_i)
        else:
            draw.rectangle(box, fill=fill, outline=stroke, width=sw_i)
    elif tag in ("circle", "ellipse"):
        cx, cy = fa("cx"), fa("cy")
        rx = fa("r") if tag == "circle" else fa("rx")
        ry = fa("r") if tag == "circle" else fa("ry")
        (cxd, cyd) = apply_pt(m, cx, cy)
        rxd, ryd = rx * math.hypot(m[0], m[1]), ry * math.hypot(m[2], m[3])
        draw.ellipse([cxd - rxd, cyd - ryd, cxd + rxd, cyd + ryd],
                     fill=fill, outline=stroke, width=sw_i)
    elif tag == "line":
        p = dev([(fa("x1"), fa("y1")), (fa("x2"), fa("y2"))])
        if stroke:
            draw.line(p, fill=stroke, width=sw_i)
    elif tag in ("polygon", "polyline"):
        nums = [float(n) for n in re.findall(r"-?[\d.eE+]+", el.attrib.get("points", ""))]
        pts = dev(list(zip(nums[0::2], nums[1::2])))
        if len(pts) >= 2:
            if tag == "polygon" and fill:
                draw.polygon(pts, fill=fill)
            if stroke:
                loop = pts + [pts[0]] if tag == "polygon" else pts
                draw.line(loop, fill=stroke, width=sw_i, joint="curve")
    elif tag == "path":
        for sub in _parse_path(el.attrib.get("d", "")):
            pts = dev(sub)
            if len(pts) >= 2:
                if fill and len(pts) >= 3:
                    draw.polygon(pts, fill=fill)
                if stroke:
                    draw.line(pts, fill=stroke, width=sw_i, joint="curve")
    elif tag == "text":
        txt = "".join(el.itertext()).strip()
        if txt:
            size = float(_get(el.attrib, style, "font-size", 16) or 16) * avg_scale(m)
            anchor = {"start": "l", "middle": "m", "end": "r"}.get(
                _get(el.attrib, style, "text-anchor", "start"), "l") + "s"
            x, y = apply_pt(m, fa("x"), fa("y"))
            col = fill if fill else (stroke if stroke else (0, 0, 0))
            try:
                draw.text((x, y), txt, font=_font(size), fill=col, anchor=anchor)
            except (ValueError, OSError):
                draw.text((x, y), txt, font=_font(size), fill=col)


def builtin_rasterize(svg_path, out_w, out_h):
    tree = ET.parse(svg_path)
    root = tree.getroot()
    vb = root.attrib.get("viewBox")
    if vb:
        minx, miny, vbw, vbh = (float(n) for n in re.split(r"[\s,]+", vb.strip()))
    else:
        minx = miny = 0.0
        vbw = float(re.sub(r"[a-z%]+$", "", root.attrib.get("width", str(out_w))))
        vbh = float(re.sub(r"[a-z%]+$", "", root.attrib.get("height", str(out_h))))
    W, H = out_w * SUPERSAMPLE, out_h * SUPERSAMPLE
    sx, sy = W / vbw, H / vbh
    ctm = (sx, 0, 0, sy, -minx * sx, -miny * sy)
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img, "RGBA")
    base = {"fill": "black", "stroke": "none", "stroke-width": "1",
            "text-anchor": "start", "font-size": "16"}
    for child in root:
        _draw_element(child, draw, ctm, base)
    return img.resize((out_w, out_h), Image.LANCZOS)

# ----------------------------------------------------------------- external backends


def _detect_backend():
    for exe in ("resvg", "rsvg-convert", "inkscape"):
        path = shutil.which(exe)
        if path:
            return exe
    return None


def external_rasterize(backend, svg_path, out_w, out_h):
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    tmp.close()
    try:
        if backend == "resvg":
            cmd = [backend, "-w", str(out_w), "-h", str(out_h), svg_path, tmp.name]
        elif backend == "rsvg-convert":
            cmd = [backend, "-w", str(out_w), "-h", str(out_h), svg_path, "-o", tmp.name]
        else:  # inkscape
            cmd = [backend, svg_path, "--export-type=png",
                   f"--export-width={out_w}", f"--export-height={out_h}",
                   f"--export-filename={tmp.name}"]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return Image.open(tmp.name).convert("RGBA")
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass

# ------------------------------------------------------------------------- encoders


def encode_dds(img):
    """Uncompressed 32-bit BGRA DDS (DX9 header)."""
    img = img.convert("RGBA")
    w, h = img.size
    rgba = img.tobytes()
    bgra = bytearray(len(rgba))
    bgra[0::4] = rgba[2::4]
    bgra[1::4] = rgba[1::4]
    bgra[2::4] = rgba[0::4]
    bgra[3::4] = rgba[3::4]
    flags = 0x1 | 0x2 | 0x4 | 0x8 | 0x1000  # CAPS|HEIGHT|WIDTH|PITCH|PIXELFORMAT
    header = struct.pack(
        "<7I11I8I5I",
        124, flags, h, w, w * 4, 0, 0,            # size..mipcount
        *([0] * 11),                              # reserved1
        32, 0x41, 0, 32,                          # ddspf: size, RGB|ALPHAPIXELS, fourCC, bits
        0x00FF0000, 0x0000FF00, 0x000000FF, 0xFF000000,  # R G B A masks (BGRA)
        0x1000, 0, 0, 0, 0,                       # caps..reserved2
    )
    return b"DDS " + header + bytes(bgra)


def write_output(img, fmt, abspath):
    os.makedirs(os.path.dirname(abspath), exist_ok=True)
    if fmt == "dds":
        with open(abspath, "wb") as fh:
            fh.write(encode_dds(img))
    elif fmt == "tga":
        img.convert("RGBA").save(abspath, format="TGA")
    elif fmt == "png":
        img.convert("RGBA").save(abspath, format="PNG")
    else:
        raise ValueError(f"unknown format: {fmt}")

# ----------------------------------------------------------------------------- main


def build(check=False):
    with open(MANIFEST, encoding="utf-8") as fh:
        manifest = json.load(fh)
    backend = _detect_backend()
    print(f"[build_assets] rasterizer: {backend or 'built-in (Pillow)'}")

    rasterize = (lambda s, w, h: external_rasterize(backend, s, w, h)) if backend else builtin_rasterize
    written, mismatched, count = [], [], 0
    for asset in manifest["assets"]:
        src = os.path.join(ROOT, asset["src"])
        fmt = asset["format"]
        if not os.path.isfile(src):
            sys.exit(f"missing source SVG: {asset['src']}")
        for out in asset["outputs"]:
            img = rasterize(src, out["width"], out["height"])
            data = encode_dds(img) if fmt == "dds" else None
            abspath = os.path.join(ROOT, out["path"])
            if check:
                if fmt == "png":
                    # PNG is the only zlib-compressed output; the deflate stream is not
                    # byte-reproducible across platforms (Pillow's win/linux wheels bundle
                    # different zlib builds), so compare the decoded pixels, not the file
                    # bytes. TGA/DDS are uncompressed and stay a byte comparison.
                    new_img = img.convert("RGBA")
                    if os.path.isfile(abspath):
                        with Image.open(abspath) as committed:
                            old_img = committed.convert("RGBA")
                            match = (old_img.size == new_img.size
                                     and old_img.tobytes() == new_img.tobytes())
                    else:
                        match = False
                    if not match:
                        mismatched.append(out["path"])
                else:
                    if fmt == "dds":
                        new = data
                    else:
                        buf = io.BytesIO()
                        img.convert("RGBA").save(buf, format=fmt.upper())
                        new = buf.getvalue()
                    old = open(abspath, "rb").read() if os.path.isfile(abspath) else None
                    if old != new:
                        mismatched.append(out["path"])
            else:
                write_output(img, fmt, abspath)
                written.append(out["path"])
            count += 1

    if check:
        if mismatched:
            print(f"[build_assets] {len(mismatched)} committed asset(s) differ from sources:")
            for p in mismatched:
                print(f"    - {p}")
            sys.exit(1)
        print(f"[build_assets] OK - {count} asset(s) match their SVG sources.")
    else:
        print(f"[build_assets] wrote {len(written)} file(s).")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Build HOI4 art from SVG sources.")
    ap.add_argument("--check", action="store_true",
                    help="verify committed assets match the SVG sources (no writes)")
    build(check=ap.parse_args().check)
