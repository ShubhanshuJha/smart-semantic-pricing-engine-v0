"""
pricing_logic/material_db.py

Responsibilities:
- Load material unit prices from data/materials.json (if present), otherwise use built-in defaults.
- Load city modifiers from data/city_modifiers.json (if present), otherwise use built-in defaults.
- Expose helper functions:
    - load_materials(path=None) -> dict
    - get_unit_cost(item_name, city=None) -> float
    - get_material_cost(item_name, quantity=1, city=None) -> float   # returns total cost for quantity
    - get_city_multiplier(city) -> float
"""

from pathlib import Path
import json
from typing import Dict, Any

# Default fallback data (used if no data file is present)
_DEFAULT_MATERIALS = {
    "tiles_ceramic_m2": {"unit": "m2", "cost": 25.0},
    "toilet_standard": {"unit": "each", "cost": 120.0},
    "vanity_basic": {"unit": "each", "cost": 100.0},
    "paint_litre": {"unit": "litre", "cost": 12.0},
    "plumbing_parts": {"unit": "job", "cost": 150.0},
    "disposal_fee": {"unit": "job", "cost": 50.0}
}

_DEFAULT_CITY_MODIFIERS = {
    # Multipliers applied to both labor hourly rate and material costs
    "Generic": 1.0,
    "Marseille": 1.00,
    "Paris": 1.25,
    "Lyon": 1.10
}

# Cached loads
_MATERIALS_CACHE: Dict[str, Any] = {}
_CITY_MOD_CACHE: Dict[str, float] = {}


def _data_dir():
    # Assume repository structure: repo_root/data/*.json
    # pricing_logic is at repo_root/pricing_logic/
    return Path(__file__).resolve().parents[1] / "data"


def load_materials(path: Path = None) -> Dict[str, Any]:
    """
    Load materials from data/materials.json if present, otherwise return defaults.
    """
    global _MATERIALS_CACHE
    if _MATERIALS_CACHE:
        return _MATERIALS_CACHE

    if path is None:
        path = _data_dir() / "materials.json"

    try:
        if path.exists():
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
                _MATERIALS_CACHE = data
                return _MATERIALS_CACHE
    except Exception:
        # Fall back to defaults on any error
        pass

    _MATERIALS_CACHE = _DEFAULT_MATERIALS.copy()
    return _MATERIALS_CACHE


def load_city_modifiers(path: Path = None) -> Dict[str, float]:
    """
    Load city modifiers from data/city_modifiers.json if present, otherwise return defaults.
    """
    global _CITY_MOD_CACHE
    if _CITY_MOD_CACHE:
        return _CITY_MOD_CACHE

    if path is None:
        path = _data_dir() / "city_modifiers.json"

    try:
        if path.exists():
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
                # normalize keys capitalization to Title case for convenience
                _CITY_MOD_CACHE = {k.capitalize(): float(v) for k, v in data.items()}
                return _CITY_MOD_CACHE
    except Exception:
        pass

    _CITY_MOD_CACHE = _DEFAULT_CITY_MODIFIERS.copy()
    return _CITY_MOD_CACHE


def get_city_multiplier(city: str) -> float:
    """
    Return multiplier for the given city. If city is None or unknown, return 1.0.
    City lookup is case-insensitive; stored keys are Title-cased.
    """
    if not city:
        return _DEFAULT_CITY_MODIFIERS["Generic"]
    mods = load_city_modifiers()
    key = city.capitalize()
    return float(mods.get(key, mods.get("Generic", 1.0)))


def get_unit_cost(item_name: str, city: str = None) -> float:
    """
    Return per-unit cost for an item, applying the city multiplier.
    If item is not found, raises KeyError.
    """
    materials = load_materials()
    if item_name not in materials:
        # Helpful error message to reviewers and tests
        raise KeyError(f"Material '{item_name}' not found in materials database.")
    base = float(materials[item_name].get("cost", 0.0))
    multiplier = get_city_multiplier(city)
    return round(base * multiplier, 2)


def get_material_cost(item_name: str, quantity: float = 1.0, city: str = None) -> float:
    """
    Return total cost for 'quantity' units of item_name for given city.
    """
    unit_cost = get_unit_cost(item_name, city)
    total = float(quantity) * unit_cost
    return round(total, 2)
