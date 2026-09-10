"""Document respiratory fields without detecting a device or converting samples."""

from collections.abc import Iterable
from typing import Any


TYMEWEAR_LINKS = (
    "https://www.tymewear.com/pages/faq",
    "https://www.tymewear.com/blogs/connectivity/software",
    "https://www.tymewear.com/pages/why-tymewear",
    "https://forum.intervals.icu/t/tymewear-an-interactive-activity-chart/90911",
    "https://forum.intervals.icu/t/importing-fit-with-tymewear-data-fields/26456/13",
    "https://www.tymewear.com/blogs/frequently-asked-questions/breathing-sensor",
)
TYMEWEAR_REVIEW_NOTE = (
    "Reviewed 2026-09-10 against Tymewear guides and Intervals.icu maintainer posts. "
    "Documentation context, not automatic device detection or calibration verification."
)
TYMEWEAR_LIMITATIONS = [
    "Apply Tymewear interpretation when the recording source is established by the "
    "athlete or source metadata. Native field names alone do not identify the device; "
    "check get_custom_items for custom code-to-FIT mappings and declared units.",
    "Tymewear volume values use a relative device scale, not calibrated liters. "
    "Intervals.icu reverted its /100-to-liters conversion on 2025-08-26. Preserve "
    "raw values; neither /100 nor /1000 is a supported conversion to L or mL.",
    "A custom L/br or L/min label is a declaration, not calibration evidence. "
    "VE = VT x BR requires compatible scales; do not diagnose a sensor fault from "
    "an apparent mismatch between the exported numbers or infer a scale factor.",
    "VT here means tidal volume per breath, not the ventilatory thresholds VT1/VT2. "
    "These streams alone do not establish thresholds or measured oxygen uptake.",
    "Compare within-athlete trends with consistent strap placement/tightness and "
    "unobstructed sensor movement. Absolute volume comparisons across athletes "
    "require calibration evidence.",
]

# Aliases identify a documentation entry, not the origin of an account's data.
# Custom codes can be edited and must be checked against get_custom_items.
RESPIRATORY_METRICS: tuple[dict[str, Any], ...] = (
    {
        "name": "tidal_volume",
        "label": "Tidal volume (VT): volume per breath",
        "unit": "unknown",
        "description": "Upstream per-breath volume signal; for Tymewear this is "
                       "a relative breathing-depth signal in device units.",
        "tymewear_unit": "i.u.",
        "fit_record_field": "tyme_tidal_volume",
        "aliases": ("VT", "tyme_tidal_volume", "average_tidal_volume", "MeanVT"),
    },
    {
        "name": "tidal_volume_min",
        "label": "Minute ventilation (VE): volume per minute",
        "unit": "unknown",
        "description": "Upstream minute ventilation, despite the native field's "
                       "tidal_volume_min name; Tymewear displays relative vol/min.",
        "tymewear_unit": "vol/min (relative device units)",
        "fit_record_field": "tyme_minute_volume",
        "aliases": ("VE", "tyme_minute_volume", "average_tidal_volume_min",
                    "TymeVentilation", "MeanVE"),
    },
    {
        "name": "respiration",
        "label": "Breathing rate (BR): breaths per minute",
        "unit": "breaths/min",
        "description": "Upstream breathing frequency; Intervals.icu maps Tymewear "
                       "tyme_breath_rate to respiration when importing that source.",
        "tymewear_unit": "breaths/min",
        "fit_record_field": "tyme_breath_rate",
        "aliases": ("BR", "tyme_breath_rate", "average_respiration",
                    "TymeBreathRate", "MeanBR"),
    },
)

_BY_FIELD = {
    field: metric
    for metric in RESPIRATORY_METRICS
    for field in (metric["name"], *metric["aliases"])
}


def respiratory_guidance(fields: Iterable[str]) -> dict[str, Any]:
    """Attach conditional documentation to present fields, including null/zero."""
    present = {
        field: {
            "metric": _BY_FIELD[field]["name"],
            "description": _BY_FIELD[field]["description"],
            "tymewear_fit_record_field": _BY_FIELD[field]["fit_record_field"],
            "documented_tymewear_unit": _BY_FIELD[field]["tymewear_unit"],
        }
        for field in fields if field in _BY_FIELD
    }
    if not present:
        return {}
    return {
        "fields": present,
        "applies_when": "The athlete or source metadata establishes Tymewear origin.",
        "device_source_verified_by_mcp": False,
        "automatic_conversion_applied": False,
        "raw_volume_to_liters_factor": None,
        "limitations": list(TYMEWEAR_LIMITATIONS),
        "primary_links": list(TYMEWEAR_LINKS),
        "link_note": TYMEWEAR_REVIEW_NOTE,
    }
