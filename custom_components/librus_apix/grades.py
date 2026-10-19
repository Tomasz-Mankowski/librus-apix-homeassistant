"""Grades of one student: regular grades, semester/final grades, averages (F11, F13).

The library's get_grades reads the grades page once and returns the regular and
descriptive grades and the averages Librus shows, but it skips the semester and
final grades (the (I), (II) and (R) cells). A thin client wrapper keeps the page
it fetched, so those cells are read from the same page without a second request.
"""

from dataclasses import asdict, dataclass, field
import re
from typing import Any

from bs4 import BeautifulSoup, Tag
import requests

from librus_apix.client import Client
from librus_apix.grades import Gpa, Grade, GradeDescriptive, get_grades

from .average import AverageRules, GradeInput, grade_value, subject_average

SEMESTER_1 = "semester_1"
SEMESTER_2 = "semester_2"
YEAR = "year"
PERIODS = (SEMESTER_1, SEMESTER_2, YEAR)

# Grade cells after the toggle cell: 0 subject, 1-3 semester 1 (grades, average,
# (I)), 4-6 semester 2 (grades, average, (II)), 7 year average, 8 (R).
_FINAL_CELLS = {3: SEMESTER_1, 6: SEMESTER_2, 8: YEAR}
_TOGGLE = ["center", "micro", "screen-only"]
_COMMENT = re.compile(r"Komentarz: (.*)")


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


@dataclass
class GradesPage:
    """Everything read from the grades page; ``semester`` is the current one."""

    subjects: dict[str, SubjectGrades]
    descriptive: list[dict[str, list[GradeDescriptive]]]
    semester: int


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
    """Average shown by Librus as a number; "-" or empty when not shown."""
    try:
        return float(str(value).replace(",", "."))
    except ValueError:
        return None


def _tooltip(tag: Tag) -> dict[str, str]:
    """Key: value pairs of a grade tooltip."""
    pairs = {}
    for part in str(tag.attrs.get("title", "")).replace("<br/>", "<br>").split("<br>"):
        key, sep, value = part.partition(": ")
        if sep:
            pairs[key.strip()] = value.strip()
    return pairs


def read_final_grades(page: str) -> dict[str, list[FinalGrade]]:
    """Return the semester and year grades by subject from the grades page."""
    finals: dict[str, list[FinalGrade]] = {}
    soup = BeautifulSoup(page, "lxml")
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
    finals = read_final_grades(keeper.page)
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
    return GradesPage(subjects, descriptive, semester)


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
