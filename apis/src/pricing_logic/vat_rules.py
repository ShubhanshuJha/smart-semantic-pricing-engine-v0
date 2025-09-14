"""
pricing_logic/vat_rules.py

Responsibilities:
- Provide VAT rates for tasks based on task_type and (optionally) location.
- Loads data/vat_rates.json when available, otherwise uses sensible defaults.

Exposed function:
    - get_vat_rate(task_type, location) -> float  (e.g., 0.20)
"""

from pathlib import Path
import json

# Default VAT mapping (task keyword -> vat rate)
_DEFAULT_VAT = {
    "default": 0.20,      # 20% default
    "tiling": 0.20,
    "painting": 0.20,
    "plumbing": 0.20,
    "materials": 0.20,
    "labor": 0.20,
    "demolition": 0.20,
    "toilet": 0.20,
    "vanity": 0.20
}

_VAT_CACHE = {}


def _data_dir():
    return Path(__file__).resolve().parents[1] / "data"


def load_vat_rates(path: Path = None):
    global _VAT_CACHE
    if _VAT_CACHE:
        return _VAT_CACHE
    if path is None:
        path = _data_dir() / "vat_rates.json"
    try:
        if path.exists():
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
                # ensure floats
                _VAT_CACHE = {k.lower(): float(v) for k, v in data.items()}
                return _VAT_CACHE
    except Exception:
        pass
    # fallback
    _VAT_CACHE = {k.lower(): float(v) for k, v in _DEFAULT_VAT.items()}
    return _VAT_CACHE


def get_vat_rate(task_type: str, location: str = None) -> float:
    """
    Return VAT rate as a decimal (e.g., 0.20). Uses keyword matching on task_type.
    If no rule matches, returns default VAT (0.20).
    """
    vat_map = load_vat_rates()
    t = (task_type or "").lower()

    # exact keyword matches
    for key in vat_map.keys():
        if key != "default" and key in t:
            return float(vat_map[key])

    return float(vat_map.get("default", 0.20))
