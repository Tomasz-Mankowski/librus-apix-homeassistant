"""Grades of one student: regular grades, semester/final grades, averages (F11, F13).

The library's get_grades reads the grades page once and returns the regular and
descriptive grades and the averages Librus shows, but it skips the semester and
final grades (the (I), (II) and (R) cells). A thin client wrapper keeps the page
it fetched, so those cells are read from the same page without a second request.
"""

from dataclasses import asdict, dataclass, field
import hashlib
import re
from typing import Any

from bs4 import BeautifulSoup, Tag
import requests

from librus_apix.client import Client
from librus_apix.grades import Gpa, Grade, GradeDescriptive, get_grades

from .average import (
    AverageRules,
    GradeInput,
    grade_value,
    overall_average,
    subject_average,
)
from .tracker import Change

SEMESTER_1 = "semester_1"
SEMESTER_2 = "semester_2"
YEAR = "year"
PERIODS = (SEMESTER_1, SEMESTER_2, YEAR)

# Grade cells after the toggle cell: 0 subject, 1-3 semester 1 (grades, average,
# (I)), 4-6 semester 2 (grades, average, (II)), 7 year average, 8 (R).
_FINAL_CELLS = {3: SEMESTER_1, 6: SEMESTER_2, 8: YEAR}
_TOGGLE = ["center", "micro", "screen-only"]
_COMMENT = re.compile(r"Komentarz: (.*)")
_CONTENT = re.compile(r"Treść oceny: (.*)")
# Rows of the grades table that never count towards the GPA (D-103).
NOT_IN_GPA = frozenset({"zachowanie"})


@dataclass
class FinalGrade:
    """A semester or year grade, final or proposed."""

    period: str
    grade: str
    proposed: bool
    category: str
    date: str
    teacher: str
    id: str


@dataclass
class SubjectGrades:
    """Grades of one subject."""

    name: str
    grades: dict[int, list[Grade]]
    librus_averages: dict[str, float | None]
    finals: list[FinalGrade] = field(default_factory=list)


@dataclass(frozen=True)
class GradeItem:
    """A regular grade with its place; ``original`` is the grade it corrects."""

    subject: str
    semester: int
    grade: Grade
    original: Grade | None = None


@dataclass(frozen=True)
class FinalItem:
    """A semester or year grade with its subject."""

    subject: str
    final: FinalGrade


@dataclass(frozen=True)
class DescriptiveItem:
    """A descriptive grade with its subject and semester."""

    subject: str
    semester: int
    grade: GradeDescriptive


@dataclass
class GradesPage:
    """Everything read from the grades page; ``semester`` is the current one.

    ``corrections`` maps the id of a correction to the id of the grade it
    corrects. The coordinator fills in the changes of the poll.
    """

    subjects: dict[str, SubjectGrades]
    descriptive: list[dict[str, list[GradeDescriptive]]]
    semester: int
    corrections: dict[str, str] = field(default_factory=dict)
    grade_changes: list[Change[GradeItem]] = field(default_factory=list)
    final_changes: list[Change[FinalItem]] = field(default_factory=list)
    descriptive_changes: list[Change[DescriptiveItem]] = field(default_factory=list)

    def descriptive_items(self) -> list[DescriptiveItem]:
        """All descriptive grades in date order."""
        items = [
            DescriptiveItem(subject, semester, grade)
            for semester, by_subject in enumerate(self.descriptive, 1)
            for subject, grades in by_subject.items()
            for grade in grades
        ]
        return sorted(items, key=lambda item: (item.grade.date, descriptive_id(item)))

    def descriptive_subjects(self) -> dict[str, list[DescriptiveItem]]:
        """Descriptive grades by subject; subjects without any are left out."""
        subjects: dict[str, list[DescriptiveItem]] = {}
        for item in self.descriptive_items():
            subjects.setdefault(item.subject, []).append(item)
        return subjects


class _PageKeeper:
    """Client wrapper that keeps the text of the grades page."""

    def __init__(self, client: Client) -> None:
        self._client = client
        self.page = ""

    def __getattr__(self, name: str) -> Any:
        return getattr(self._client, name)

    def post(self, url: str, data: dict[str, str]) -> requests.Response:
        response = self._client.post(url, data)
        if url == self._client.GRADES_URL:
            self.page = response.text
        return response


def grade_id(href: str) -> str:
    """Librus id of a grade: the last part of its link."""
    return href.rstrip("/").rsplit("/", 1)[-1]


def _number(value: float | str) -> float | None:
    """Average shown by Librus as a number; None when not shown.

    "-" or empty: no average. A school that hides averages has empty cells
    without the "right" class; librus-apix then gives the float 0.0 (I-003).
    Librus never shows an average of 0 or less.
    """
    try:
        number = float(str(value).replace(",", "."))
    except ValueError:
        return None
    return number if number > 0 else None


def _tooltip(tag: Tag) -> dict[str, str]:
    """Key: value pairs of a grade tooltip."""
    pairs = {}
    for part in str(tag.attrs.get("title", "")).replace("<br/>", "<br>").split("<br>"):
        key, sep, value = part.partition(": ")
        if sep:
            pairs[key.strip()] = value.strip()
    return pairs


def read_corrections(soup: BeautifulSoup) -> dict[str, str]:
    """Return {correction id: corrected grade id} from the grades page.

    A corrected grade and its correction share a wrapper span: [old new].
    """
    corrections = {}
    for wrapper in soup.select("td:not([class='center']) > span:not(.grade-box)"):
        ids = [
            grade_id(str(link.get("href", "")))
            for link in wrapper.select(":scope > span.grade-box > a")
        ]
        for correction in ids[1:]:
            corrections[correction] = ids[0]
    return corrections


def read_final_grades(soup: BeautifulSoup) -> dict[str, list[FinalGrade]]:
    """Return the semester and year grades by subject from the grades page."""
    finals: dict[str, list[FinalGrade]] = {}
    for row in soup.find_all("tr", attrs={"class": ["line0", "line1"], "id": None}):
        cells = row.find_all("td", recursive=False)
        if not any(cell.get("class") == _TOGGLE for cell in cells):
            continue
        cells = [cell for cell in cells if cell.get("class") != _TOGGLE]
        if len(cells) < 9:
            continue
        subject = cells[0].text.replace("\n", "").strip()
        for index, period in _FINAL_CELLS.items():
            for link in cells[index].select("span.grade-box > a"):
                info = _tooltip(link)
                category = info.get("Kategoria", "")
                finals.setdefault(subject, []).append(
                    FinalGrade(
                        period=period,
                        grade=link.text.strip(),
                        proposed="propon" in category.lower(),
                        category=category,
                        date=info.get("Data", "")[:10],
                        teacher=info.get("Nauczyciel", ""),
                        id=grade_id(str(link.get("href", ""))),
                    )
                )
    return finals


def read_grades(client: Client) -> GradesPage:
    """Read the grades page once (runs in the executor)."""
    keeper = _PageKeeper(client)
    numeric, averages, descriptive = get_grades(keeper)
    soup = BeautifulSoup(keeper.page, "lxml")
    finals = read_final_grades(soup)
    names = dict.fromkeys([*numeric[0], *numeric[1], *averages])
    subjects = {}
    for name in names:
        shown: dict[int, Gpa] = {gpa.semester: gpa for gpa in averages.get(name, [])}
        subjects[name] = SubjectGrades(
            name=name,
            grades={
                1: list(numeric[0].get(name, [])),
                2: list(numeric[1].get(name, [])),
            },
            librus_averages={
                SEMESTER_1: _number(shown[1].gpa) if 1 in shown else None,
                SEMESTER_2: _number(shown[2].gpa) if 2 in shown else None,
                YEAR: _number(shown[0].gpa) if 0 in shown else None,
            },
            finals=finals.get(name, []),
        )
    # The second semester has started once any subject has a grade in it.
    semester = 2 if any(subject.grades[2] for subject in subjects.values()) else 1
    return GradesPage(subjects, descriptive, semester, read_corrections(soup))


def grade_items(page: GradesPage) -> list[GradeItem]:
    """All regular grades in date order, corrections linked to their originals."""
    items = []
    for subject in page.subjects.values():
        for semester, grades in subject.grades.items():
            by_id = {grade_id(grade.href): grade for grade in grades}
            for grade in grades:
                original = page.corrections.get(grade_id(grade.href))
                items.append(
                    GradeItem(subject.name, semester, grade, by_id.get(original or ""))
                )
    return sorted(items, key=lambda item: (item.grade.date, item_id(item)))


def item_id(item: GradeItem) -> str:
    """Id of a grade; without a link: subject|semester|date|category."""
    grade = item.grade
    return grade_id(grade.href) or (
        f"{item.subject}|{item.semester}|{grade.date}|{grade.category}"
    )


def period_average(
    subject: SubjectGrades, period: str, rules: AverageRules
) -> tuple[float | None, str | None]:
    """Return (average, source) of a period: Librus if shown, else calculated."""
    if (shown := subject.librus_averages[period]) is not None:
        return shown, "librus"
    grades = {
        SEMESTER_1: subject.grades[1],
        SEMESTER_2: subject.grades[2],
        YEAR: subject.grades[1] + subject.grades[2],
    }[period]
    calculated = subject_average(
        (GradeInput(g.grade, g.weight, g.counts) for g in grades), rules
    )
    return calculated, "calculated" if calculated is not None else None


def grade_details(grade: Grade, rules: AverageRules) -> dict[str, Any]:
    """All details of a regular grade for attributes and events."""
    comment = _COMMENT.search(grade.desc)
    return {
        "id": grade_id(grade.href),
        "grade": grade.grade,
        "value": grade_value(grade.grade, rules),
        "category": grade.category,
        "date": grade.date,
        "weight": grade.weight,
        "counts": grade.counts,
        "teacher": grade.teacher,
        "comment": comment[1].strip() if comment else "",
    }


def final_details(final: FinalGrade) -> dict[str, Any]:
    """All details of a semester or year grade."""
    return asdict(final)


def descriptive_id(item: DescriptiveItem) -> str:
    """Stable id of a descriptive grade: the library gives none."""
    grade = item.grade
    key = "|".join(
        (
            item.subject,
            str(item.semester),
            grade.date,
            grade.grade,
            grade.teacher,
            grade.desc,
        )
    )
    return hashlib.sha1(key.encode()).hexdigest()[:16]


def descriptive_details(item: DescriptiveItem) -> dict[str, Any]:
    """All details of a descriptive grade; ``content`` is the teacher's text."""
    grade = item.grade
    content = _CONTENT.search(grade.desc)
    return {
        "id": descriptive_id(item),
        "subject": item.subject,
        "semester": item.semester,
        "grade": grade.grade,
        "date": grade.date,
        "teacher": grade.teacher,
        "content": content[1].strip() if content else grade.desc.strip(),
        "description": grade.desc.strip(),
    }


def overall(
    page: GradesPage, period: str, rules: AverageRules
) -> tuple[float | None, str | None, dict[str, float]]:
    """Return (GPA, source, subject averages) of a period (D-026).

    GPA = plain mean of the subject averages; subjects without one and the
    behaviour row (NOT_IN_GPA) are skipped.
    Source: "librus", "calculated" or "mixed", from the subject averages used.
    """
    averages: dict[str, float] = {}
    sources = set()
    for name, subject in page.subjects.items():
        if name.strip().casefold() in NOT_IN_GPA:
            continue
        value, source = period_average(subject, period, rules)
        if value is not None:
            averages[name] = value
            sources.add(source)
    gpa = overall_average(averages.values())
    source = None if not sources else sources.pop() if len(sources) == 1 else "mixed"
    return gpa, source, averages
