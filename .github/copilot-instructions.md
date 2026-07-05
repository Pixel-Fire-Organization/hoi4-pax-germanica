# Pax Germanica — Repository Instructions

> **Standing context for AI assistants working in this repo.** GitHub Copilot reads this file
> directly; Claude Code reads it via the `@`-import in the root `CLAUDE.md`. It is the single source
> of truth for "you are here." The **Project Status** section at the bottom is *auto-maintained* —
> see the Maintenance Protocol before you finish a task.

---

## Purpose

**Pax Germanica** is an alternate-history overhaul mod for **Hearts of Iron IV** (target game
version **1.19.\***). The setting is **1950, after an Axis victory** — a continent ordered around
German leadership. The project is currently transitioning from a **structure-only scaffold** (every
HOI4 subsystem wired up with placeholder content) into **authored content**, starting with the
written lore in `docs/`.

## What's in the repo / capabilities

| Subsystem | Where |
|-----------|-------|
| Start bookmark (1950) | `common/bookmarks/pax_germanica.txt` |
| National spirits / ideas | `common/ideas/pax_germanica_ideas.txt` |
| Focus tree (scored onto Germany) | `common/national_focus/pax_germanica.txt` |
| Characters (leader, generals, advisors) | `common/characters/pax_germanica.txt` |
| Countries / tags | `common/countries/`, `common/country_tags/` (GER extended, new `PAX`, cosmetic `GER_pax`) |
| Country setup + order of battle | `history/countries/`, `history/units/GER_pax_1950.txt` |
| Art (built TGA/DDS) | `gfx/` — generated from editable SVGs in `gfx/_src/` |
| Sprite definitions | `interface/pax_germanica.gfx` |
| On-screen strings | `localisation/english/*.yml` (UTF-8 **with BOM**) |
| Lore / design docs | `docs/` |

**Tooling** (Python; `pillow` is the only hard dependency):
- `python tools/build_assets.py` — rasterize `gfx/_src/**.svg` → `gfx/**.tga` / `**.dds` + thumbnail.
- `python tools/lint_mod.py` — validate braces/quotes, YAML BOM, GFX/idea/character cross-refs, image headers.
- `python tools/install_mod.py` — build art + register the mod with HOI4 (dev pointer; `--package` / `--uninstall`).

**CI**: `.github/workflows/ci.yml` (lint + asset verification), `release.yml` (tagged-release zip).

## Key conventions / gotchas

- `descriptor.mod` declares `replace_path="common/bookmarks"` — this mod's bookmark **replaces** the
  vanilla 1936/1939 ones.
- Localisation YAML must be **UTF-8 with BOM**.
- **Edit SVGs in `gfx/_src/`, then rebuild** — the binaries in `gfx/` are generated, not hand-edited.
- **The scaffold is placeholder, NOT canon.** Names (Reinhardt, Faber, Vogt, Adler, Stein), the two
  national spirits, the focus-tree fork, and the stability/popularity numbers are stand-ins to be
  replaced. Lore in `docs/` is authoritative; game files will be brought in line with it later.
- Run `python tools/lint_mod.py` before committing changes to game files.

## The story / canon (current — summary only; `docs/` is authoritative)

An Axis victory built on a small, two-lever point of divergence: in **spring 1941** Barbarossa
launches on its original mid-May schedule (no Balkan delay), and in **August** the panzers hold
their drive on Moscow instead of turning to Kiev — so **Moscow falls ~30 September 1941**. That
collapse forces Britain to terms, and the resulting world of 1950 is:

- **Tripolar** — Germany (Europe to the Volga), Japan (East Asia/Pacific), and a **communist
  America** — plus a **rump Soviet Russia** clinging on east of the Volga.
- **Germany**: the strained, overextended hegemon — a total-war economy it can't demobilize, and
  **Hitler alive but failing** at the 1950 start (a figurehead; succession open and contested). He dies
  **~early 1952** and the succession is **resolved before 1954**.
- **Britain**: defeated and **dismembered** — its Mediterranean/African empire carved up among **Italy,
  Germany and Spain** (Spain, a late Axis entrant, also takes **Gibraltar**; the Gulf cut loose; India
  left unwritten) — and **split three ways** (**Halifax** / restored **Edward VIII** / **democratic
  resistance**). The white Dominions stay British but restive. Britain did **not** aid Japan; **Japan
  won the Pacific alone**, seizing Britain's Asian colonies by force.
- **The horizon**: a rearmed, revanchist communist bloc that never accepted the map — pointing toward a
  great war in **1955**, touched off by the **Volga incident**.

Full detail in the documents below.

## Documentation map

- `docs/world/` — shared setting lore (the canonical backstory every country doc points back to).
- `docs/countries/` — per-nation histories (Germany done; Japan, America, Russia, Britain, Italy planned).
- `docs/README.MD` — describes the `docs/` folder.

---

## Maintenance Protocol — read before finishing a task

This file is the single source of truth (the root `CLAUDE.md` imports it). Keep it from drifting:

1. **At the end of any task that changes the repo**, refresh the **Project Status (auto-maintained)**
   section below: update `Last updated`, the **document inventory**, the **current-story state**, the
   **recent changes**, and **next up**. A Stop hook (`tools/update_context_hook.py`) will remind you.
2. Keep it **terse** — this is a pointer/summary, not a copy of `docs/`.
3. **Never contradict `docs/`.** If this file and a doc disagree, the doc wins; fix this file.
4. Update the static sections above only when the repo's purpose, structure, tooling, or conventions
   actually change.

---

## Project Status (auto-maintained)

- **Last updated:** 2026-07-05
- **Phase:** structure-only scaffold + initial lore authoring.
- **Documents present:**
  - `docs/world/the-road-to-victory.md` — shared 1939–1945 backstory (the two-lever POD → the 1950 world).
  - `docs/countries/germany.md` — Germany 1950 country history (New Order, the failing-Führer succession, the road to the 1955 war).
  - `docs/countries/russia.md` — rump Soviet Russia 1950 (Zhukov's military junta beyond the Urals: Stalin poisoned by Beria → NKVD rule 1943–49 → the "one night" army coup → a junta on the hinge, elections promised, alignment undecided; bloc membership contingent on a loyalist restoration).
- **Current story state:** Core canon is set — a tripolar 1950 (Germany / Japan / communist America)
  plus a rump Soviet Russia east of the Volga, a defeated-and-dismembered Britain split three ways, and
  a strained Germany under an ailing Hitler heading toward a **1955 war** (touched off by the *Volga
  incident*). Britain did not aid Japan — **Japan won the Pacific alone** — and was stripped of its
  Mediterranean/African empire (Italy / Germany / Spain, the last a late Axis entrant that also took
  Gibraltar); the Dominions stay loyal but restive; India is left unwritten. The **atomic bomb has been
  cut** from the setting: the war's driver is a rearmed revanchist bloc, and Germany's succession
  resolves before 1954 (Hitler dies ~early 1952). Germany and Russia are authored; Russia's start is a
  freshly-couped military junta whose bloc membership is the canonical *loyalist-restoration* default
  (its payoff now the reforged Red Army, not a joint bomb). Lore lives in `docs/`; the game files are
  still the original placeholder scaffold and have **not** yet been aligned to the canon.
- **Recent changes:** Revised the story canon (see summary above): war moved to **1955** / the **Volga
  incident**; **Britain no longer aids Japan** (Japan wins the Pacific alone and seizes British SE Asia
  by force) and is **dismembered** (Mediterranean/African empire to Italy/Germany/Spain, Gibraltar to
  Spain, Gulf independent, India unwritten), keeping loyal-but-restive Dominions; **Spain** added as a
  late Axis entrant; the **atomic bomb cut** entirely (Germany's monopoly and the Russia+America "joint
  bomb" removed → a rearmed-revanchist-bloc driver, and a reforged Red Army as Russia's loyalist payoff);
  **Hitler dies ~early 1952**, succession resolved before 1954. Updated all three docs and this file.
  Earlier: fixed failing CI in two steps: (1) added the missing UTF-8 BOM to
  `localisation/english/decisions_l_english.yml` (unblocked the `lint_mod.py` gate); (2) made
  `build_assets.py --check` compare PNGs by decoded pixels instead of raw bytes, since zlib's
  compressed stream is not reproducible across platforms (thumbnail.png was false-failing on
  Linux CI). Earlier: authored `docs/countries/russia.md` (the rump-Soviet junta history). Earlier:
  added this AI-context file (`.github/copilot-instructions.md`), a root `CLAUDE.md` that imports it,
  and a Stop hook (`tools/update_context_hook.py`); wrote the world and Germany docs and refined the
  POD (on-schedule mid-May-1941 Barbarossa + Moscow-over-Kiev → Moscow falls ~30 Sept 1941).
- **Next up:** remaining sibling country docs (Japan, America, Britain, Italy); then replace the
  scaffold (focus tree, ideas, characters, OOB) with content matching the canon.
