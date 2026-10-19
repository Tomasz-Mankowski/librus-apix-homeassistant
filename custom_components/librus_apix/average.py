"""Calculated averages (F13), for schools that do not show them in Librus.

Rules (configurable in the options, T-019):
- weights: weighted mean with the Librus weights, or every grade counts once,
- "Licz do średniej": grades marked "nie" are skipped,
- plus and minus: 4+ = 4 + plus, 5- = 5 - minus, 3= = 3 - 2 x minus.

Non-numeric grades (np, bz, +, -, ...) and semester/final grades never count.
The overall average is the plain mean of the subject averages (D-026).
"""

from collections.abc import Iterable
from dataclasses import dataclass
import re

_NUMERIC = re.compile(r"([0-6](?:\.\d+)?)([+\-=]?)")


@dataclass(frozen=True)
class AverageRules:
    """How the average is calculated."""

    use_weights: bool = True
    only_counted: bool = True
    plus: float = 0.5
    minus: float = 0.25


@dataclass(frozen=True)
class GradeInput:
    """What the calculation needs to know about one grade."""

    grade: str
    weight: int
    counts: bool
    final: bool = False


def grade_value(grade: str, rules: AverageRules) -> float | None:
    """Return the number of a grade, or None for a non-numeric grade."""
    match = _NUMERIC.fullmatch(grade.strip().replace(",", "."))
    if match is None:
        return None
    value = float(match[1])
    modifier = match[2]
    if modifier == "+":
        return value + rules.plus
    if modifier == "-":
        return value - rules.minus
    if modifier == "=":
        return value - 2 * rules.minus
    return value


def subject_average(grades: Iterable[GradeInput], rules: AverageRules) -> float | None:
    """Return the average of one subject, or None if no grade counts."""
    total = 0.0
    weights = 0
    for grade in grades:
        if grade.final or (rules.only_counted and not grade.counts):
            continue
        value = grade_value(grade.grade, rules)
        weight = grade.weight if rules.use_weights else 1
        if value is None or weight <= 0:
            continue
        total += value * weight
        weights += weight
    return total / weights if weights else None


def overall_average(averages: Iterable[float | None]) -> float | None:
    """Return the plain mean of the subject averages; subjects without one skip."""
    values = [average for average in averages if average is not None]
    return sum(values) / len(values) if values else None
