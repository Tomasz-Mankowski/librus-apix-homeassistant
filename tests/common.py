"""Shared test data: a fake Synergia server for requests-mock."""

from dataclasses import dataclass, field
import html
import re
from typing import Any
from urllib.parse import parse_qs

import requests_mock as rm

MOCK_URL = "http://librus-mock-a:8000"
SCHOOL = "Szkoła Podstawowa nr 999\nul. Fikcyjna 1"
MESSAGES_PER_PAGE = 5


def info_page(
    name: str = "Zofia Testowa", lucky: str | None = "7", school: str = SCHOOL
) -> str:
    """Return the student information page like Synergia renders it."""
    lucky_html = (
        f'<span class="luckyNumber">Szczęśliwy numerek: <b>{lucky}</b></span>'
        if lucky is not None
        else ""
    )
    rows = [
        ("Uczeń", name),
        ("Klasa", "5a"),
        ("Nr w dzienniku", "14"),
        ("Wychowawca", "Magdalena Przykładowa"),
        ("Szkoła", school),
    ]
    lines = "".join(
        f'<tr class="line{i % 2}"><th>{label}</th><td>{value}</td></tr>'
        for i, (label, value) in enumerate(rows)
    )
    return (
        f'{lucky_html}<table class="decorated big center"><tbody>{lines}'
        "</tbody></table>"
    )


@dataclass
class FakeMessage:
    """A received message on the list."""

    id: int
    author: str
    title: str
    date: str
    unread: bool = False
    attachment: bool = False
    body: str = "Treść wiadomości.\nDruga linia."
    files: list[str] = field(default_factory=list)


def default_messages() -> list[FakeMessage]:
    """Eight messages, newest first: two unread, one with two attachments."""
    return [
        FakeMessage(
            5001 + i,
            f"Nauczyciel {i}",
            f"Temat {i}",
            f"2026-10-{18 - i:02d} 12:0{i}:00",
            unread=i < 2,
            attachment=i == 1,
            files=["Plan_lekcji.pdf", "Zgoda.docx"] if i == 1 else [],
        )
        for i in range(8)
    ]


def message_page(message: FakeMessage) -> str:
    """Return the page of one message with its body and attachments."""
    files = "".join(
        '<tr><td>&nbsp;<img src="/assets/img/filetype_icons/file.png">'
        f"&nbsp;{name}</td><td></td></tr>"
        for name in message.files
    )
    body = "<br>\n".join(message.body.split("\n"))
    return (
        '<table class="stretch"><tbody>'
        f'<tr><td class="medium">Nadawca</td><td class="left">{message.author}</td></tr>'
        f'<tr><td class="medium">Temat</td><td class="left">{message.title}</td></tr>'
        f'<tr><td class="medium">Wysłano</td><td class="left">{message.date}</td></tr>'
        f'</tbody></table><div class="container-message-content">{body}</div>'
        f"<table><tbody>{files}</tbody></table>"
    )


def messages_page(messages: list[FakeMessage], page: int) -> str:
    """Return one page of the received message list."""
    pages = max(1, -(-len(messages) // MESSAGES_PER_PAGE))
    chunk = messages[page * MESSAGES_PER_PAGE : (page + 1) * MESSAGES_PER_PAGE]
    rows = (
        "".join(
            f'<tr class="line{i % 2}"><td><input type="checkbox"></td>'
            f"<td>{'<img src="/a.png">' if m.attachment else '&nbsp;'}</td>"
            f'<td><a href="/wiadomosci/1/5/{m.id}/f0">{m.author}</a></td>'
            f"<td{' style="font-weight: bold;"' if m.unread else ''}>"
            f'<a href="/wiadomosci/1/5/{m.id}/f0">{m.title}</a></td>'
            f"<td>{m.date}</td><td></td></tr>"
            for i, m in enumerate(chunk)
        )
        or '<tr class="line0"><td colspan="6">Brak wiadomości</td></tr>'
    )
    return (
        f'<table class="decorated stretch"><tbody>{rows}</tbody></table>'
        f'<div class="pagination"><span>Strona&nbsp;{page + 1}&nbsp;z&nbsp;{pages}'
        "</span></div>"
    )


@dataclass
class FakeAnnouncement:
    """An announcement on the announcements page."""

    title: str
    author: str
    date: str
    content: str


def default_announcements() -> list[FakeAnnouncement]:
    """Three announcements, newest first."""
    return [
        FakeAnnouncement(
            "Zebrania z rodzicami",
            "Dyrektor Szkoły",
            "2026-10-16",
            "Zebrania odbędą się w środę o 17:00.\nSale według listy.",
        ),
        FakeAnnouncement("Zbiórka makulatury", "Samorząd", "2026-10-09", "Do końca."),
        FakeAnnouncement("Szczepienia", "Pielęgniarka", "2026-09-28", "Klasy piąte."),
    ]


def announcements_page(items: list[FakeAnnouncement]) -> str:
    """Return the announcements page (or the 'no announcements' box)."""
    if not items:
        return (
            '<div class="container border-red resizeable center"><div>'
            "<p>Brak ogłoszeń.</p></div></div>"
        )
    return "".join(
        '<table class="decorated big center printable margin-top">'
        f'<thead><tr><td colspan="2">{a.title}</td></tr></thead><tbody>'
        f'<tr class="line0"><th>Dodał</th><td>{a.author}</td></tr>'
        f'<tr class="line1"><th>Data publikacji</th><td>{a.date}</td></tr>'
        f'<tr class="line0"><th>Treść</th><td>{a.content}</td></tr>'
        "</tbody></table>"
        for a in items
    )


@dataclass
class FakeGrade:
    """A regular grade; ``correction`` is the grade that corrects it."""

    id: int
    grade: str
    category: str = "Kartkówka"
    date: str = "2026-10-01"
    weight: int = 1
    counts: bool = True
    comment: str = ""
    correction: FakeGrade | None = None


@dataclass
class FakeFinal:
    """A semester (I, II) or year (R) grade, final or proposed."""

    id: int
    column: str
    grade: str
    proposed: bool = False
    date: str = "2026-10-15"


@dataclass
class FakeSubject:
    """A row of the grades table."""

    name: str
    teacher: str = "Adam Rachunek"
    semester1: list[FakeGrade] = field(default_factory=list)
    semester2: list[FakeGrade] = field(default_factory=list)
    averages: tuple[str, str, str] = ("-", "-", "-")
    finals: list[FakeFinal] = field(default_factory=list)


def default_subjects() -> list[FakeSubject]:
    """Subjects like mock A: Librus shows the averages."""
    return [
        FakeSubject(
            "Matematyka",
            semester1=[
                FakeGrade(1101, "5", weight=2),
                FakeGrade(1102, "4+", "Odpowiedź ustna", "2026-09-10"),
                FakeGrade(
                    1103,
                    "1",
                    "Sprawdzian",
                    "2026-09-20",
                    weight=3,
                    comment="Działania",
                    correction=FakeGrade(
                        1104, "4", "Sprawdzian", "2026-09-30", weight=3
                    ),
                ),
                FakeGrade(1105, "np", "Nieprzygotowanie", weight=0, counts=False),
            ],
            averages=("3.69", "-", "3.69"),
            finals=[FakeFinal(1190, "I", "4", proposed=True)],
        ),
        FakeSubject(
            "Język polski",
            teacher="Ewa Ortografia",
            semester1=[FakeGrade(1201, "4", "Dyktando", weight=2)],
            averages=("4.00", "-", "4.00"),
        ),
        FakeSubject("Plastyka", teacher="Anna Kolorowa"),
    ]


def _grade_box(grade: FakeGrade, teacher: str, extra: str = "") -> str:
    parts = [
        f"Kategoria: {grade.category}",
        f"Data: {grade.date} (pon.)",
        f"Nauczyciel: {teacher}",
        f"Licz do średniej: {'tak' if grade.counts else 'nie'}",
    ]
    if grade.weight:
        parts.append(f"Waga: {grade.weight}")
    if extra:
        parts.append(extra)
    parts.append(f"Dodał: {teacher}")
    title = "<br>".join(parts)
    if grade.comment:
        title += f"<br/><br/>Komentarz: {grade.comment}"
    return (
        f'<span class="grade-box"><a href="/przegladaj_oceny/szczegoly/{grade.id}" '
        f'title="{html.escape(title)}">{grade.grade}</a></span>'
    )


def _grade_cell(grades: list[FakeGrade], teacher: str) -> str:
    boxes = []
    for grade in grades:
        if grade.correction:
            note = f"Poprawa oceny: {grade.grade} ({grade.category})"
            boxes.append(
                f"<span>[{_grade_box(grade, teacher)}"
                f"{_grade_box(grade.correction, teacher, note)}]</span>"
            )
        else:
            boxes.append(_grade_box(grade, teacher))
    return "".join(boxes) or "Brak ocen"


FINAL_CATEGORIES = {
    ("I", False): "Śródroczna",
    ("I", True): "Proponowana (śródroczna)",
    ("II", False): "Końcowa (okres 2)",
    ("II", True): "Proponowana (okres 2)",
    ("R", False): "Roczna",
    ("R", True): "Proponowana (roczna)",
}


def _final_cell(subject: FakeSubject, column: str) -> str:
    boxes = []
    for final in subject.finals:
        if final.column != column:
            continue
        title = (
            f"Kategoria: {FINAL_CATEGORIES[column, final.proposed]}<br>"
            f"Data: {final.date} (śr.)<br>Nauczyciel: {subject.teacher}"
        )
        boxes.append(
            f'<span class="grade-box"><a href="/przegladaj_oceny/szczegoly/{final.id}" '
            f'title="{html.escape(title)}">{final.grade}</a></span>'
        )
    return "".join(boxes) or "-"


def grades_page(subjects: list[FakeSubject]) -> str:
    """Return the grades page like Synergia renders it."""
    rows = []
    for i, subject in enumerate(subjects):
        cells = [
            '<td class="center micro screen-only"><img src="/t.png"></td>',
            f"<td>{subject.name}</td>",
        ]
        for grades, average, column in (
            (subject.semester1, subject.averages[0], "I"),
            (subject.semester2, subject.averages[1], "II"),
        ):
            cells.append(f"<td>{_grade_cell(grades, subject.teacher)}</td>")
            cells.append(f'<td class="right">{average}</td>')
            cells.append(f'<td class="center">{_final_cell(subject, column)}</td>')
        cells.append(f'<td class="right">{subject.averages[2]}</td>')
        cells.append(f'<td class="center">{_final_cell(subject, "R")}</td>')
        rows.append(f'<tr class="line{i % 2}">{"".join(cells)}</tr>')
        rows.append(f'<tr class="line{i % 2}" id="przedmioty_{i}_node"><td></td></tr>')
    return f'<table class="decorated stretch"><tbody>{"".join(rows)}</tbody></table>'


@dataclass
class FakeServer:
    """Synergia pages of one student, served through requests-mock."""

    mocker: rm.Mocker
    messages: list[FakeMessage] = field(default_factory=default_messages)
    announcements: list[FakeAnnouncement] = field(default_factory=default_announcements)
    subjects: list[FakeSubject] = field(default_factory=default_subjects)
    lucky: str | None = "7"

    def __post_init__(self) -> None:
        """Register the pages."""
        self.mocker.get(f"{MOCK_URL}/informacja", text=self._info)
        self.mocker.post(
            f"{MOCK_URL}/przegladaj_oceny/uczen",
            text=lambda request, context: grades_page(self.subjects),
        )
        self.mocker.get(
            f"{MOCK_URL}/ogloszenia",
            text=lambda request, context: announcements_page(self.announcements),
        )
        self.mocker.get(f"{MOCK_URL}/wiadomosci/1/5", text=self._messages)
        self.mocker.post(f"{MOCK_URL}/wiadomosci/1/5", text=self._messages)
        self.mocker.get(
            re.compile(rf"{re.escape(MOCK_URL)}/wiadomosci/1/5/\d+$"),
            text=self._message,
        )

    def _info(self, request: Any, context: Any) -> str:
        return info_page(lucky=self.lucky)

    def _messages(self, request: Any, context: Any) -> str:
        form = parse_qs(request.text or "")
        return messages_page(self.messages, int(form.get("numer_strony105", ["0"])[0]))

    def _message(self, request: Any, context: Any) -> str:
        msg_id = int(request.path.rsplit("/", 1)[1])
        message = next((m for m in self.messages if m.id == msg_id), None)
        if message is None:
            context.status_code = 404
            return ""
        message.unread = False
        return message_page(message)

    def paths(self) -> list[str]:
        """Paths of all requests so far."""
        return [request.path for request in self.mocker.request_history]
