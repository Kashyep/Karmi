"""Derive Karmi's semantic theme tokens for all 4 tiers x 2 modes.

Source of truth: docs/design/karmi_tier_color_palettes.md (the PALETTES table
below copies it verbatim). Every palette colour is used unchanged where its
documented role allows; tokens the palette does not define (muted surfaces,
borders, link/focus ink, status colours) are *derived* and nudged only as far
as WCAG 2.x requires (4.5:1 text, 3:1 non-text). Derivation is deterministic.

Outputs (committed; regenerate after editing the palette):
- docs/design/karmi_theme_tokens.json      (reviewable table + contrast audit)
- mobile/lib/theme/tier_tokens.g.dart      (Flutter ThemeExtension constants)
- src/daily_agent/web/static/karmi-tokens.css  (CSS custom properties keyed on
  html[data-tier][data-theme])

Run from the repository root:  python mobile/tool/derive_theme_tokens.py
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# docs/design/karmi_tier_color_palettes.md, verbatim.
PALETTES: dict[str, dict[str, str]] = {
    "ananta": {"accent": "#66C796", "base": "#1E422C", "light": "#F2F7F4",
               "dark": "#0B1A11", "text": "#050806"},
    "yanta": {"accent": "#00D4FF", "base": "#1A365D", "light": "#F4F6F9",
              "dark": "#0A111C", "text": "#8BA2C4"},
    "trika": {"accent": "#FF5722", "base": "#8C3B20", "light": "#FCF8F5",
              "dark": "#171210", "text": "#E0D4CD"},
    # Parth has no "Primary Base"; its second colour is the Secondary Accent.
    "parth": {"accent": "#D4AF37", "secondary_accent": "#9B4F96", "light": "#FFFFFF",
              "dark": "#000000", "text": "#1A1A1A"},
}
TIERS = ("ananta", "yanta", "trika", "parth")
LABELS = {"ananta": "Ananta", "yanta": "Yanta", "trika": "Trika", "parth": "Parth"}

# Status colours kept from Design.md (light, dark).
DESTRUCTIVE = ("#B42332", "#FF9CA7")
SUCCESS = ("#146B43", "#78DDAA")
WARNING = ("#805000", "#FFD48A")

# §5.1 legibility floor for glass tint alpha (UI_IMPLEMENTATION_PLAN.md).
GLASS_ALPHA = {"light": 0.72, "dark": 0.78}

RGB = tuple[float, float, float]


def rgb(hexcode: str) -> RGB:
    h = hexcode.lstrip("#")
    return (int(h[0:2], 16) / 255, int(h[2:4], 16) / 255, int(h[4:6], 16) / 255)


def hexify(c: RGB) -> str:
    return "#" + "".join(f"{round(max(0.0, min(1.0, v)) * 255):02X}" for v in c)


def mix(a: str, b: str, t: float) -> str:
    ca, cb = rgb(a), rgb(b)
    return hexify(tuple(x + (y - x) * t for x, y in zip(ca, cb, strict=True)))  # type: ignore[arg-type]


def luminance(hexcode: str) -> float:
    def ch(v: float) -> float:
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4

    r, g, b = (ch(v) for v in rgb(hexcode))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def over(fg: str, alpha: float, backdrop: str) -> str:
    """Composite `fg` at `alpha` over an opaque backdrop."""
    return mix(backdrop, fg, alpha)


def ensure(start: str, toward: str, backgrounds: list[str], minimum: float) -> str:
    """Mix `start` toward `toward` in 1% steps until it meets `minimum` on all backgrounds."""
    for step in range(101):
        candidate = mix(start, toward, step / 100)
        if all(contrast(candidate, bg) >= minimum for bg in backgrounds):
            return candidate
    raise ValueError(f"cannot reach {minimum}:1 from {start} toward {toward}")


def passes(color: str, backgrounds: list[str], minimum: float) -> bool:
    return all(contrast(color, bg) >= minimum for bg in backgrounds)


def derive(tier: str, mode: str) -> dict[str, str]:
    p = PALETTES[tier]
    accent = p["accent"]
    # Structural colour used for tinting: Primary Base, or Parth's ultra-dark grey.
    base = p.get("base", p["text"])
    accent2 = p.get("secondary_accent", base)
    t: dict[str, str] = {}
    if mode == "light":
        bg = p["light"]
        # Palette text is the primary ink only where the palette says so (Ananta,
        # Parth); Yanta/Trika text colours are secondary/dark-mode inks.
        fg = p["text"] if contrast(p["text"], bg) >= 7 else p["dark"]
        card = "#FFFFFF"
        muted = mix(bg, accent if tier == "parth" else base, 0.06)
        surfaces = [bg, card, muted]
        muted_fg = ensure(mix(fg, bg, 0.45), fg, surfaces, 4.5)
        on_accent = fg if contrast(fg, accent) >= 4.5 else "#000000"
        accent_text = base if tier != "parth" and passes(base, surfaces, 4.5) else ensure(
            accent, fg, surfaces, 4.5)
        ring = accent_text
        secondary = mix(bg, accent, 0.35)
        secondary_fg = fg
        on_accent2 = ensure(bg, "#FFFFFF", [accent2], 4.5)
        border = ensure(mix(fg, bg, 0.55), fg, [bg, card, muted], 3.0)
        border_subtle = mix(bg, fg, 0.10)
        destructive, success, warning = DESTRUCTIVE[0], SUCCESS[0], WARNING[0]
        destructive_fg = "#FFFFFF"
        glass_rgb = mix(card, base, 0.04)
        glass_border, glass_border_alpha = fg, 0.10
        highlight, highlight_alpha = "#FFFFFF", 0.55
    else:
        bg = p["dark"]
        fg = p["light"]
        card = mix(bg, base, 0.22)
        step = 0.22
        while contrast(card, bg) < 1.15:
            step += 0.02
            card = mix(bg, base if tier != "parth" else "#FFFFFF", step if tier != "parth" else step / 4)
        muted = mix(bg, base if tier != "parth" else accent2, 0.30 if tier != "parth" else 0.18)
        surfaces = [bg, card, muted]
        muted_fg = p["text"] if passes(p["text"], surfaces, 4.5) and tier != "ananta" else ensure(
            mix(fg, bg, 0.40), fg, surfaces, 4.5)
        on_accent = bg if contrast(bg, accent) >= 4.5 else "#000000"
        accent_text = accent if passes(accent, surfaces, 4.5) else ensure(accent, fg, surfaces, 4.5)
        ring = accent if passes(accent, [bg, card], 3.0) else accent_text
        secondary = accent2 if tier == "parth" else base
        secondary_fg = ensure(fg, "#FFFFFF", [secondary], 4.5)
        on_accent2 = ensure(fg, "#FFFFFF", [accent2], 4.5)
        border = p["text"] if passes(p["text"], [bg, card, muted], 3.0) else ensure(
            mix(fg, bg, 0.55), fg, [bg, card, muted], 3.0)
        border_subtle = mix(bg, fg, 0.14)
        destructive, success, warning = DESTRUCTIVE[1], SUCCESS[1], WARNING[1]
        destructive_fg = bg
        glass_rgb = mix(card, base, 0.10)
        glass_border, glass_border_alpha = "#FFFFFF", 0.10
        highlight, highlight_alpha = "#FFFFFF", 0.14
    # Status colours must stay text-grade on every surface of this tier.
    destructive = ensure(destructive, fg, surfaces, 4.5)
    success = ensure(success, fg, surfaces, 4.5)
    warning = ensure(warning, fg, surfaces, 4.5)
    destructive_fg = ensure(destructive_fg, "#FFFFFF" if mode == "light" else "#000000",
                            [destructive], 4.5)
    t.update(
        background=bg, foreground=fg, card=card, cardForeground=fg,
        primary=accent, primaryForeground=on_accent, primaryText=accent_text,
        secondary=secondary, secondaryForeground=secondary_fg,
        accent=accent2, accentForeground=on_accent2,
        muted=muted, mutedForeground=muted_fg,
        border=border, borderSubtle=border_subtle, ring=ring,
        destructive=destructive, destructiveForeground=destructive_fg,
        success=success, warning=warning,
        header=base if tier != "parth" else (fg if mode == "light" else card),
        glassBase=glass_rgb, glassBorder=glass_border, glassHighlight=highlight,
    )
    t["_glassAlpha"] = str(GLASS_ALPHA[mode])
    t["_glassBorderAlpha"] = str(glass_border_alpha)
    t["_glassHighlightAlpha"] = str(highlight_alpha)
    return t


def audit(tier: str, mode: str, t: dict[str, str]) -> list[dict[str, object]]:
    """Every text/non-text pairing the UI uses, plus text over glass."""
    alpha = float(t["_glassAlpha"])
    rows: list[tuple[str, str, str, float]] = []
    for surface in ("background", "card", "muted"):
        rows += [
            (f"foreground on {surface}", t["foreground"], t[surface], 4.5),
            (f"mutedForeground on {surface}", t["mutedForeground"], t[surface], 4.5),
            (f"primaryText on {surface}", t["primaryText"], t[surface], 4.5),
            (f"destructive on {surface}", t["destructive"], t[surface], 4.5),
            (f"success on {surface}", t["success"], t[surface], 4.5),
            (f"warning on {surface}", t["warning"], t[surface], 4.5),
        ]
    rows += [
        ("primaryForeground on primary", t["primaryForeground"], t["primary"], 4.5),
        ("secondaryForeground on secondary", t["secondaryForeground"], t["secondary"], 4.5),
        ("accentForeground on accent", t["accentForeground"], t["accent"], 4.5),
        ("destructiveForeground on destructive", t["destructiveForeground"], t["destructive"], 4.5),
        ("border on background", t["border"], t["background"], 3.0),
        ("border on card", t["border"], t["card"], 3.0),
        ("ring on background", t["ring"], t["background"], 3.0),
        ("ring on card", t["ring"], t["card"], 3.0),
    ]
    # Text on glass: worst-case backdrops scrolling behind the glass bars.
    for name in ("background", "card", "primary", "secondary", "foreground"):
        composite = over(t["glassBase"], alpha, t[name])
        rows.append((f"foreground on glass over {name}", t["foreground"], composite, 4.5))
    return [
        {"pair": label, "fg": fg, "bg": bg, "ratio": round(contrast(fg, bg), 2),
         "min": minimum, "pass": contrast(fg, bg) >= minimum}
        for label, fg, bg, minimum in rows
    ]


def raise_glass_alpha(tier: str, mode: str, t: dict[str, str]) -> None:
    """Raise the glass tint alpha above the floor until text on glass passes."""
    while not all(r["pass"] for r in audit(tier, mode, t) if "glass" in str(r["pair"])):
        t["_glassAlpha"] = str(round(float(t["_glassAlpha"]) + 0.02, 2))
        if float(t["_glassAlpha"]) > 1:
            raise ValueError(f"{tier} {mode}: glass cannot reach 4.5:1")


def dart_color(hexcode: str, alpha: float = 1.0) -> str:
    return f"Color(0x{round(alpha * 255):02X}{hexcode.lstrip('#').upper()})"


def main() -> None:
    table: dict[str, dict[str, dict[str, str]]] = {}
    report: dict[str, object] = {}
    for tier in TIERS:
        table[tier] = {}
        for mode in ("light", "dark"):
            tokens = derive(tier, mode)
            raise_glass_alpha(tier, mode, tokens)
            rows = audit(tier, mode, tokens)
            failing = [r for r in rows if not r["pass"]]
            if failing:
                raise SystemExit(f"{tier} {mode} fails: {failing}")
            table[tier][mode] = tokens
            report[f"{tier}-{mode}"] = rows

    doc = {"source": "docs/design/karmi_tier_color_palettes.md", "palettes": PALETTES,
           "tokens": table, "audit": report}
    (ROOT / "docs/design/karmi_theme_tokens.json").write_text(json.dumps(doc, indent=2) + "\n")

    # Dart
    fields = [k for k in table["ananta"]["light"] if not k.startswith("_") and not k.startswith("glass")]
    lines = [
        "// GENERATED by mobile/tool/derive_theme_tokens.py from",
        "// docs/design/karmi_tier_color_palettes.md. Do not edit by hand.",
        "part of 'karmi_colors.dart';",
        "",
        "const Map<KarmiTier, Map<Brightness, KarmiColors>> _tierTokens = {",
    ]
    for tier in TIERS:
        lines.append(f"  KarmiTier.{tier}: {{")
        for mode in ("light", "dark"):
            t = table[tier][mode]
            lines.append(f"    Brightness.{mode}: KarmiColors(")
            for f in fields:
                lines.append(f"      {f}: {dart_color(t[f])},")
            lines.append(f"      glassBase: {dart_color(t['glassBase'], float(t['_glassAlpha']))},")
            lines.append(f"      glassBorder: {dart_color(t['glassBorder'], float(t['_glassBorderAlpha']))},")
            lines.append(
                f"      glassHighlight: {dart_color(t['glassHighlight'], float(t['_glassHighlightAlpha']))},")
            lines.append("    ),")
        lines.append("  },")
    lines.append("};")
    (ROOT / "mobile/lib/theme/tier_tokens.g.dart").write_text("\n".join(lines) + "\n")

    # CSS
    def kebab(name: str) -> str:
        return "".join(f"-{c.lower()}" if c.isupper() else c for c in name)

    def rgba(hexcode: str, alpha: str) -> str:
        r, g, b = (round(v * 255) for v in rgb(hexcode))
        return f"rgba({r},{g},{b},{alpha})"

    css = ["/* GENERATED by mobile/tool/derive_theme_tokens.py from",
           "   docs/design/karmi_tier_color_palettes.md. Do not edit by hand.",
           "   Switching html[data-tier][data-theme] swaps every token at once. */"]
    for tier in TIERS:
        for mode in ("light", "dark"):
            t = table[tier][mode]
            selector = f'html[data-tier="{tier}"][data-theme="{mode}"]'
            if tier == "ananta" and mode == "light":
                selector = ":root," + selector
            props = [f"color-scheme:{mode}"]
            props += [f"--color{kebab(k if k[0].isupper() else k[0].upper() + k[1:])}:{v}"
                      for k, v in t.items() if not k.startswith("_") and not k.startswith("glass")]
            props += [
                f"--color-glass-base:{rgba(t['glassBase'], t['_glassAlpha'])}",
                f"--color-glass-border:{rgba(t['glassBorder'], t['_glassBorderAlpha'])}",
                f"--color-glass-highlight:{rgba(t['glassHighlight'], t['_glassHighlightAlpha'])}",
                f"--color-glass-fallback:{t['card']}",
                f"--color-canvas:{t['background']}",
                f"--color-text-main:{t['foreground']}",
                f"--color-accent-primary:{t['primary']}",
            ]
            css.append(selector + "{" + ";".join(props) + "}")
    target = ROOT / "src/daily_agent/web/static/karmi-tokens.css"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(css) + "\n")
    for key, rows in report.items():
        worst = min(r["ratio"] for r in rows if r["min"] == 4.5)  # type: ignore[union-attr]
        print(f"{key}: worst text ratio {worst}, glass alpha {table[key.split('-')[0]][key.split('-')[1]]['_glassAlpha']}")


if __name__ == "__main__":
    main()
