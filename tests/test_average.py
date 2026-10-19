"""Tests for the calculated averages (F13)."""

import pytest

from custom_components.librus_apix.average import (
    AverageRules,
    GradeInput,
    grade_value,
    overall_average,
    subject_average,
)

DEFAULT = AverageRules()


def g(
    grade: str, weight: int = 1, counts: bool = True, final: bool = False
) -> GradeInput:
    return GradeInput(grade, weight, counts, final)


@pytest.mark.parametrize(
    ("grade", "value"),
    [
        ("5", 5.0),
        ("4+", 4.5),
        ("5-", 4.75),
        ("3=", 2.5),
        (" 6 ", 6.0),
        ("1+", 1.5),
        ("0", 0.0),
        ("4,5", 4.5),
        ("4.5", 4.5),
        ("np", None),
        ("bz", None),
        ("+", None),
        ("-", None),
        ("nb", None),
        ("7", None),
        ("85%", None),
        ("", None),
    ],
)
def test_grade_value(grade: str, value: float | None) -> None:
    """Numbers with +, - and = get the default values; other grades have none."""
    assert grade_value(grade, DEFAULT) == value


def test_plus_and_minus_values_are_configurable() -> None:
    """Other schools use other values, for example +0.25 / -0.25."""
    rules = AverageRules(plus=0.25, minus=0.33)

    assert grade_value("4+", rules) == 4.25
    assert grade_value("4-", rules) == pytest.approx(3.67)
    assert grade_value("4=", rules) == pytest.approx(3.34)


def test_weighted_mean_with_librus_weights() -> None:
    """(5*2 + 4.5*1 + 1*3 + 4*3 + 4.75*1 + 3*2) / 12 = 3.354..."""
    grades = [g("5", 2), g("4+", 1), g("1", 3), g("4", 3), g("5-", 1), g("3", 2)]

    assert subject_average(grades, DEFAULT) == pytest.approx(40.25 / 12)


def test_unweighted_mean_when_weights_are_off() -> None:
    """Every grade counts once."""
    grades = [g("5", 3), g("3", 1)]

    assert subject_average(grades, AverageRules(use_weights=False)) == 4.0


def test_not_counted_grades_are_skipped_when_the_rule_is_on() -> None:
    """'Licz do średniej: nie' grades count only when the rule is off."""
    grades = [g("6", 3), g("5", 1), g("1", 1, counts=False)]

    assert subject_average(grades, DEFAULT) == 5.75
    assert subject_average(grades, AverageRules(only_counted=False)) == 24 / 5


def test_non_numeric_and_final_grades_are_skipped() -> None:
    """np, bz, +, - and semester/final grades never count."""
    grades = [
        g("4", 2),
        g("np", 1),
        g("bz", 1),
        g("+", 1),
        g("-", 1),
        g("6", 1, final=True),
        g("1", 2, final=True),
    ]

    assert subject_average(grades, DEFAULT) == 4.0


def test_weight_zero_counts_only_without_weights() -> None:
    """A grade with weight 0 adds nothing to a weighted mean."""
    grades = [g("5", 1), g("1", 0)]

    assert subject_average(grades, DEFAULT) == 5.0
    assert subject_average(grades, AverageRules(use_weights=False)) == 3.0


def test_subject_without_counting_grades_has_no_average() -> None:
    """No counting grade gives None, not 0."""
    assert subject_average([], DEFAULT) is None
    assert subject_average([g("np"), g("5", 1, counts=False)], DEFAULT) is None


def test_overall_is_the_plain_mean_of_subject_averages() -> None:
    """Subjects without an average are skipped."""
    assert overall_average([3.35, 3.54, None, 5.75]) == pytest.approx(
        (3.35 + 3.54 + 5.75) / 3
    )
    assert overall_average([None, None]) is None
    assert overall_average([]) is None
