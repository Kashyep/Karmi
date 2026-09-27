"""Dynamic web app manifest generator for Karmi tier themes."""

from __future__ import annotations

from typing import Any, Final

TIER_PALETTES: Final[dict[str, dict[str, str]]] = {
    "ananta": {
        "theme_color": "#66C796",
        "background_color": "#F2F7F4",
    },
    "yanta": {
        "theme_color": "#00D4FF",
        "background_color": "#F4F6F9",
    },
    "trika": {
        "theme_color": "#FF5722",
        "background_color": "#FCF8F5",
    },
    "parth": {
        "theme_color": "#D4AF37",
        "background_color": "#FFFFFF",
    },
}

DEFAULT_TIER: Final[str] = "ananta"


def build_manifest(tier: str | None = None) -> dict[str, Any]:
    """Generate the dynamic PWA webmanifest dictionary for the given tier.

    If the tier is unknown, None, or empty, defaults to 'ananta'.
    """
    tier_key = (tier or "").strip().lower()
    if tier_key not in TIER_PALETTES:
        tier_key = DEFAULT_TIER
    palette = TIER_PALETTES[tier_key]
    return {
        "name": "Karmi",
        "short_name": "Karmi",
        "start_url": "/",
        "display": "standalone",
        "background_color": palette["background_color"],
        "theme_color": palette["theme_color"],
        "description": "A calm, accessible workspace for daily tasks.",
        "icons": [
            {
                "src": f"/static/icons/{tier_key}-192.png",
                "sizes": "192x192",
                "type": "image/png",
            },
            {
                "src": f"/static/icons/{tier_key}-512.png",
                "sizes": "512x512",
                "type": "image/png",
            },
            {
                "src": f"/static/icons/{tier_key}-512.webp",
                "sizes": "512x512",
                "type": "image/webp",
            },
        ],
    }
