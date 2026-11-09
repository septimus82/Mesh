"""M17-L4A candidate presets (scratch): the grades and hazes the lab and the timing use."""
from __future__ import annotations

from postfx import srgb_to_linear


def lin(hexcol: str) -> tuple[float, float, float]:
    h = hexcol.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return srgb_to_linear((r, g, b))


GRADES = {
    "day": dict(grade=True, contrast=1.06, sat=1.06, protect=0.6),
    "morning": dict(grade=True, wb=(1.03, 1.0, 0.97), contrast=1.04, sat=1.02, shadow_tint=(0.94, 0.98, 1.08),
                    high_tint=(1.05, 1.01, 0.94), split=0.4, protect=0.7),
    "evening": dict(grade=True, wb=(1.06, 1.0, 0.9), contrast=1.08, sat=1.06, shadow_tint=(0.92, 0.95, 1.1),
                    high_tint=(1.06, 1.0, 0.9), split=0.5, protect=0.8),
    "night": dict(grade=True, wb=(0.95, 0.98, 1.05), contrast=1.0, exposure=1.03, sat=0.92,
                  shadow_tint=(0.94, 0.97, 1.08), high_tint=(1.04, 1.0, 0.95), split=0.4, protect=0.9),
    "interior": dict(grade=True, wb=(1.04, 1.0, 0.94), contrast=1.05, sat=1.04, shadow_tint=(0.95, 0.96, 1.06),
                     high_tint=(1.04, 1.0, 0.95), split=0.35, protect=0.85),
}
HAZES = {  # haze colour: the time of day's sky, lightened for day (aerial perspective), as is for night
    "day": dict(haze=True, haze_col=lin("#b4c8e2"), haze_start=3.0, haze_range=12.0, haze_max=0.12),
    "morning": dict(haze=True, haze_col=lin("#c9d5e4"), haze_start=3.0, haze_range=12.0, haze_max=0.22,
                    haze_height=1.0),
    "evening": dict(haze=True, haze_col=lin("#e0a27c"), haze_start=3.0, haze_range=12.0, haze_max=0.12),
    "night": dict(haze=True, haze_col=lin("#1c2440"), haze_start=3.0, haze_range=12.0, haze_max=0.15),
}
