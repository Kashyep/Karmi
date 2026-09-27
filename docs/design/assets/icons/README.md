# Karmi tier app icons (masters)

| Tier | Master | Source (Google Flow output in `docs/design/assets/`) |
| --- | --- | --- |
| Ananta | `ananta.png` | `Create_productivity_mobile_app_icon_20260926204114.jpg` (mint infinity on deep green) |
| Yanta | `yanta.png` | `Futuristic_compass_app_icon_design_20260926204114.jpg` (cyan compass on navy) |
| Trika | `trika.png` | `Design_mobile_app_icon_rings_20260926204114.jpg` (ember trinity rings on charcoal) |
| Parth | `parth.png` | `Arrow_striking_crown_icon_20260926204114.jpg` (gold crown and arrow on black) |

Processing (implementation_plan.md §1.1): each 1024×1024 JPEG had the generator's sparkle
watermark in the bottom-right corner. It was removed with OpenCV Telea inpainting restricted to
a 140×140 px corner mask, and the result saved as a lossless PNG master. Nothing else was changed.

All derived sizes are produced by `python mobile/tool/generate_app_icons.py`:
Android `mipmap-*/ic_launcher_<tier>.png` (activity-alias icons; `ic_launcher.png` = Ananta),
iOS `AppIcon` (Ananta) + `AppIcon-<Tier>` alternate sets, Flutter `mobile/assets/app_icons/<tier>.webp`
(Armory gallery), and web `src/daily_agent/web/static/icons/<tier>-{192,512}.png|.webp` (PWA manifest).

The animated `.mp4` launch/unlock sequences are not used yet.
