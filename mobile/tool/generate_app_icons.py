"""Generate every per-tier app icon from the cleaned 1024x1024 masters.

Masters: docs/design/assets/icons/<tier>.png (Google Flow outputs with the
bottom-right generator watermark inpainted; see docs/design/assets/icons/README.md).

Outputs (all committed, regenerate after changing a master):
- Android launcher mipmaps: mobile/android/app/src/main/res/mipmap-*/ic_launcher_<tier>.png
  (and ic_launcher.png = Ananta, the default icon).
- iOS: AppIcon.appiconset (Ananta, primary) and AppIcon-<Tier>.appiconset alternates.
- In-app Armory thumbnails: mobile/assets/app_icons/<tier>.webp (256px).
- Web/PWA: src/daily_agent/web/static/icons/<tier>-{192,512}.png and <tier>-512.webp.

Run from the repository root:  python mobile/tool/generate_app_icons.py  (needs Pillow)
"""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
MASTERS = ROOT / "docs/design/assets/icons"
TIERS = ("ananta", "yanta", "trika", "parth")
DEFAULT = "ananta"

ANDROID_RES = ROOT / "mobile/android/app/src/main/res"
ANDROID_SIZES = {"mdpi": 48, "hdpi": 72, "xhdpi": 96, "xxhdpi": 144, "xxxhdpi": 192}

IOS_ASSETS = ROOT / "mobile/ios/Runner/Assets.xcassets"
FLUTTER_ASSETS = ROOT / "mobile/assets/app_icons"
WEB_ICONS = ROOT / "src/daily_agent/web/static/icons"


def load(tier: str) -> Image.Image:
    image = Image.open(MASTERS / f"{tier}.png").convert("RGB")
    if image.size != (1024, 1024):
        image = image.resize((1024, 1024), Image.Resampling.LANCZOS)
    return image


def resized(image: Image.Image, size: int) -> Image.Image:
    return image.resize((size, size), Image.Resampling.LANCZOS)


def ios_set_name(tier: str) -> str:
    return "AppIcon" if tier == DEFAULT else f"AppIcon-{tier.capitalize()}"


def write_ios(tier: str, image: Image.Image) -> None:
    template = json.loads((IOS_ASSETS / "AppIcon.appiconset/Contents.json").read_text())
    target = IOS_ASSETS / f"{ios_set_name(tier)}.appiconset"
    target.mkdir(parents=True, exist_ok=True)
    for entry in template["images"]:
        points = float(entry["size"].split("x")[0])
        scale = int(entry["scale"].rstrip("x"))
        # iOS app icons must not have an alpha channel.
        resized(image, round(points * scale)).save(target / entry["filename"], optimize=True)
    (target / "Contents.json").write_text(json.dumps(template, indent=2) + "\n")


def main() -> None:
    FLUTTER_ASSETS.mkdir(parents=True, exist_ok=True)
    WEB_ICONS.mkdir(parents=True, exist_ok=True)
    for tier in TIERS:
        image = load(tier)
        for density, size in ANDROID_SIZES.items():
            folder = ANDROID_RES / f"mipmap-{density}"
            icon = resized(image, size)
            icon.save(folder / f"ic_launcher_{tier}.png", optimize=True)
            if tier == DEFAULT:
                icon.save(folder / "ic_launcher.png", optimize=True)
        write_ios(tier, image)
        resized(image, 256).save(FLUTTER_ASSETS / f"{tier}.webp", quality=90, method=6)
        for size in (192, 512):
            resized(image, size).save(WEB_ICONS / f"{tier}-{size}.png", optimize=True)
        resized(image, 512).save(WEB_ICONS / f"{tier}-512.webp", quality=90, method=6)
        print(f"{tier}: ok")


if __name__ == "__main__":
    main()
