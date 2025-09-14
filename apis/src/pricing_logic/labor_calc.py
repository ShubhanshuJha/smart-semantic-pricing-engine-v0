"""
pricing_logic/labor_calc.py

Responsibilities:
- Estimate hours per task.
- Compute labor cost using an hourly rate (city-aware).
- Expose:
    - estimate_hours(task_type, area=None, complexity="standard") -> float
    - hourly_rate(city) -> float
    - compute_labor_cost(hours, city) -> float
"""

from typing import Optional
from pricing_logic.material_db import get_city_multiplier
from math import ceil
import re

# Base hourly rate in EUR (default)
_BASE_HOURLY_RATE = 40.0


def parse_transcript(text):
    """
    Very simple rule-based parser for the Donizo test case.
    Extracts: zone, area, tasks, city, budget-conscious flag.
    """

    zone = "bathroom" if "bathroom" in text.lower() else "general"

    # Area in m2
    area_match = re.search(r"(\d+)\s?m[²2]", text.lower())
    area_m2 = float(area_match.group(1)) if area_match else None

    # City (simplified)
    city_match = re.search(r"(marseille|paris|lyon)", text.lower())
    city = city_match.group(1).capitalize() if city_match else None

    budget_flag = "budget" in text.lower()

    # Tasks (rule-based)
    tasks = []
    if "tile" in text.lower():
        tasks.append({"task_name": "Floor Tiling (ceramic)", "area_m2": area_m2})
    if "paint" in text.lower() or "repaint" in text.lower():
        tasks.append({"task_name": "Repaint Walls"})
    if "plumb" in text.lower():
        tasks.append({"task_name": "Shower Plumbing (redo)"})
    if "toilet" in text.lower():
        tasks.append({"task_name": "Replace Toilet"})
    if "vanity" in text.lower():
        tasks.append({"task_name": "Install Vanity"})
    if "remove old tile" in text.lower() or "remove the old tiles" in text.lower():
        tasks.append({"task_name": "Demolition & Disposal"})

    return {
        "zone": zone,
        "city": city,
        "budget_flag": budget_flag,
        "tasks": tasks,
        "area_m2": area_m2,
    }


def hourly_rate(city: Optional[str]) -> float:
    """
    Return the hourly rate adjusted by city multiplier.
    """
    multiplier = get_city_multiplier(city)
    return round(_BASE_HOURLY_RATE * multiplier, 2)


def estimate_hours(task_type: str, area: Optional[float] = None, complexity: str = "standard") -> float:
    """
    Deterministic rules to estimate labor hours for common tasks.
    Uses simple heuristics suitable for a test assignment.

    - Tiling: ~0.9 hours per m² (if area provided) otherwise default 4 hrs
    - Painting: 1 hour per 10 m² (if area known) otherwise default 3 hrs
    - Plumbing (redo): 6 hrs, (repair): 3 hrs
    - Demolition & Disposal: 2 hrs (small bathroom)
    - Replace Toilet: 2 hrs
    - Install Vanity: 2 hrs
    """

    t = task_type.lower()

    if "til" in t or "tile" in t:
        if area and area > 0:
            hours = 0.9 * float(area)
        else:
            hours = 4.0  # fallback for small room
    elif "paint" in t:
        if area and area > 0:
            hours = max(1.0, (float(area) / 10.0))  # 1 hr per 10 m2
        else:
            hours = 3.0
    elif "plumb" in t:
        # detect redo vs repair from name
        if "redo" in t or "replace" in t or "redo" in t:
            hours = 6.0
        else:
            hours = 4.0
    elif "demol" in t or "disposal" in t or "remove" in t:
        hours = 2.0
    elif "toilet" in t:
        hours = 2.0
    elif "vanity" in t:
        hours = 2.0
    else:
        # generic fallback estimate
        hours = 3.0

    # complexity adjustments
    if complexity == "high":
        hours *= 1.25
    elif complexity == "low":
        hours *= 0.9

    # round to 0.25 hour increments for nicer output
    rounded = round(ceil(hours * 4) / 4.0, 2)
    return rounded


def compute_labor_cost(hours: float, city: Optional[str]) -> float:
    """
    Compute labor cost = hours * hourly_rate(city)
    """
    rate = hourly_rate(city)
    total = float(hours) * rate
    return round(total, 2)
