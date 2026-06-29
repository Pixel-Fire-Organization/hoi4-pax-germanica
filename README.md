# Pax Germanica

An **alternate-history overhaul scaffold** for *Hearts of Iron IV* (game version **1.19.\***).

> ⚠️ This is a **structure-only skeleton**. Every file is real, correctly formatted and wired
> together so the mod loads and plays, but the content is intentionally placeholder. The actual
> mod concept is implemented later on top of this scaffold.

It exercises every core HOI4 subsystem so they are ready to fill in:

| Subsystem        | Where                                                            |
|------------------|-----------------------------------------------------------------|
| Start date       | `common/bookmarks/pax_germanica.txt` (1950 default bookmark)     |
| Ideas            | `common/ideas/pax_germanica_ideas.txt` (national spirits)        |
| Focus tree       | `common/national_focus/pax_germanica.txt` (scored onto Germany)  |
| Characters       | `common/characters/pax_germanica.txt` (leader, generals, advisors)|
| Countries        | Germany (`GER`) extended + new tag `PAX` + cosmetic tag `GER_pax`|
| Order of battle  | `history/units/GER_pax_1950.txt`                                 |
| Custom graphics  | `gfx/` (built from editable SVG sources in `gfx/_src/`)          |

## Repository layout

```
descriptor.mod / .metadata/    Mod metadata read by the game + launcher
common/                        Ideas, focus tree, characters, bookmark, country/tag definitions
history/                       Country setup (GER override, new PAX tag) + OOB
gfx/                           Built game art (TGA flags, DDS icons) — generated, but committed
gfx/_src/                      Editable SVG source art (edit these, then rebuild)
interface/                     Sprite (.gfx) definitions for the custom art
localisation/english/          All on-screen strings (UTF-8 with BOM)
tools/                         build_assets.py (SVG→TGA/DDS), lint_mod.py (validator), install_mod.py (install into HOI4)
.github/workflows/             CI (lint + asset verification) and tagged-release packaging
```

## Building the art

Art is authored as SVG under `gfx/_src/` and converted to the binary formats HOI4 expects
(uncompressed **TGA** flags, uncompressed **DDS** icons). The committed binaries in `gfx/` are
generated from those SVGs — edit the SVG, then rebuild:

```bash
python -m pip install pillow      # only hard dependency
python tools/build_assets.py      # SVG (gfx/_src) -> gfx/**/*.tga, gfx/**/*.dds, thumbnail.png
```

`build_assets.py` rasterizes via the first available backend — `resvg`, `rsvg-convert` or
`inkscape` on `PATH` (best fidelity), otherwise a built-in pure-Pillow SVG renderer (no native
dependencies, used by CI). `tools/assets_manifest.json` maps each SVG to its output path(s), size(s)
and format.

## Validating

```bash
python tools/lint_mod.py          # braces/quotes balance, YAML BOM, GFX/idea/character cross-refs, image headers
```

## Installing & testing in-game

One command builds the art and registers the mod with HOI4 (cross-platform — it finds the
right `Documents/Paradox Interactive/Hearts of Iron IV/mod/` folder on Windows, macOS and Linux):

```bash
python tools/install_mod.py            # build art + write a dev pointer to this checkout
python tools/install_mod.py --package  # build art + install a clean, self-contained copy
python tools/install_mod.py --uninstall  # remove it again
```

- **Default (dev pointer)** writes a `<slug>.mod` launcher pointer whose `path=` points at
  this repo, so edits to your working tree are live in-game — best while developing.
- **`--package`** stages a clean copy (the same file set the release zip ships, no `tools/`,
  `gfx/_src/` or VCS files) into `.../mod/pax_germanica/` and points at it — best for testing
  the shippable artifact.
- Useful flags: `--skip-build` (don't rebuild art first), `--mods-dir PATH` or `$HOI4_MOD_DIR`
  (override the target folder, e.g. a non-standard install).

The pointer's metadata (name, version, tags, `replace_path`) is read from `descriptor.mod`, so
it's just an automated version of hand-writing `pax_germanica.mod` into the `mod/` folder.

Then:
1. Launch HOI4 **1.19.\***, enable *Pax Germanica* in the launcher's mod list, and play.
2. Check `Documents/Paradox Interactive/Hearts of Iron IV/logs/error.log` is clean.
3. Start a **1950** game as **Germany** and confirm: the custom flag, the two national spirits, the
   `pax_germanica_focus` tree, the recruited leader/commanders and the deployed OOB units appear.
   In the console, `tag PAX` switches to the new tag to confirm it loads.

## Publishing

- **GitHub Release zip** — push a `v*` tag; `.github/workflows/release.yml` builds a clean versioned
  zip + an install-ready `.mod` pointer and attaches them to a Release. Users extract into their
  `.../Hearts of Iron IV/mod/` folder.
- **Steam Workshop** — open the Paradox Launcher → *Mod Tools* → *Upload Mod* (reads `descriptor.mod`
  + `.metadata/metadata.json`). Automatable later via `steamcmd +workshop_build_item` (app `394360`)
  if you add Steam credentials; not wired up here.
- **Paradox Mods** — upload via the launcher / paradoxmods.com.

## License

MIT — see [LICENSE](LICENSE).
