"""Shared test data: a fake Synergia server for requests-mock."""

import calendar
from dataclasses import dataclass, field
from datetime import date, timedelta
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
    # Librus texts of the average cells; None: the school hides averages, the
    # cells are empty and have no "right" class (live test I-003).
    averages: tuple[str, str, str] | None = ("-", "-", "-")
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


def _average_cell(average: str | None) -> str:
    return "<td></td>" if average is None else f'<td class="right">{average}</td>'


def grades_page(subjects: list[FakeSubject]) -> str:
    """Return the grades page like Synergia renders it."""
    rows = []
    for i, subject in enumerate(subjects):
        averages = subject.averages or (None, None, None)
        cells = [
            '<td class="center micro screen-only"><img src="/t.png"></td>',
            f"<td>{subject.name}</td>",
        ]
        for grades, average, column in (
            (subject.semester1, averages[0], "I"),
            (subject.semester2, averages[1], "II"),
        ):
            cells.append(f"<td>{_grade_cell(grades, subject.teacher)}</td>")
            cells.append(_average_cell(average))
            cells.append(f'<td class="center">{_final_cell(subject, column)}</td>')
        cells.append(_average_cell(averages[2]))
        cells.append(f'<td class="center">{_final_cell(subject, "R")}</td>')
        rows.append(f'<tr class="line{i % 2}">{"".join(cells)}</tr>')
        rows.append(f'<tr class="line{i % 2}" id="przedmioty_{i}_node"><td></td></tr>')
    return f'<table class="decorated stretch"><tbody>{"".join(rows)}</tbody></table>'


@dataclass
class FakeDescriptive:
    """An old-schema descriptive grade."""

    grade: str
    date: str
    content: str
    semester: int = 1


@dataclass
class FakeDescriptiveSubject:
    """A row of the old-schema descriptive grades table."""

    name: str
    teacher: str
    grades: list[FakeDescriptive] = field(default_factory=list)


def default_descriptive() -> list[FakeDescriptiveSubject]:
    """Two descriptive grades in semester 1, like mock A."""
    return [
        FakeDescriptiveSubject(
            "Edukacja zdrowotna",
            "Magdalena Przykładowa",
            [
                FakeDescriptive("OP", "2026-09-23", "Zna zasady zdrowego odżywiania."),
                FakeDescriptive("WY", "2026-10-15", "Wyróżniająca prezentacja."),
            ],
        )
    ]


def descriptive_table(subjects: list[FakeDescriptiveSubject]) -> str:
    """Return the old-schema descriptive grades table (empty without subjects)."""
    rows = []
    for i, subject in enumerate(subjects):
        cells = []
        for semester in (1, 2):
            boxes = "".join(
                '<span class="grade-box"><a href="javascript:void(0);" title="'
                + html.escape(
                    f"Data: {g.date} (pon.)<br>Nauczyciel: {subject.teacher}<br>"
                    f"Treść oceny: {g.content}"
                )
                + f'">{g.grade}</a></span>'
                for g in subject.grades
                if g.semester == semester
            )
            cells.append(f"<td>{boxes}</td>")
        rows.append(
            f'<tr class="line{i % 2}"><td class="micro center screen-only"></td>'
            f"<td>{subject.name}</td>{''.join(cells)}</tr>"
        )
    if not rows:
        return ""
    return f'<table class="decorated stretch"><tbody>{"".join(rows)}</tbody></table>'


def new_schema_table(subjects: dict[int, str]) -> str:
    """Return the new-schema table (grades come from the gateway API)."""
    if not subjects:
        return ""
    rows = "".join(
        f'<tr class="studentRow" data-subject_id="{number}"><td></td><td>{name}</td></tr>'
        for number, name in subjects.items()
    )
    return f'<table class="newSchemaGradesByStudentTable">{rows}</table>'


BELLS = {1: ("08:00", "08:45"), 2: ("08:55", "09:40"), 3: ("09:50", "10:35")}


@dataclass
class FakeLesson:
    """A lesson of the timetable; ``label`` and ``tooltip`` make it a change.

    ``tooltip`` holds the raw lines, for example
    "Nauczyciel: <b>Adam Rachunek</b> -> <b>Zenon Zastępczy</b>".
    """

    day: date
    number: int
    subject: str
    teacher: str = "Adam Rachunek"
    room: str = "12"
    label: str | None = None
    tooltip: list[str] = field(default_factory=list)


def default_lessons() -> list[FakeLesson]:
    """Lessons of the weeks of 2026-10-19, 10-26 and 11-02 with every kind of change."""
    return [
        FakeLesson(date(2026, 10, 19), 1, "Matematyka"),
        FakeLesson(date(2026, 10, 19), 2, "Język polski", "Ewa Ortografia", "8"),
        FakeLesson(
            date(2026, 10, 21),
            3,
            "Matematyka",
            "Zenon Zastępczy",
            label="zastępstwo",
            tooltip=[
                "Nauczyciel: <b>Adam Rachunek</b> -> <b>Zenon Zastępczy</b>",
                "Data dodania: 2026-10-18 12:00:00",
            ],
        ),
        FakeLesson(
            date(2026, 10, 27), 3, "Historia", "Barbara Dawna", "10", "odwołane"
        ),
        FakeLesson(
            date(2026, 10, 29),
            1,
            "Język angielski",
            "Kate Grammar",
            "21",
            "zmiana sali",
            ["Sala: <b>15</b> -> <b>21</b>"],
        ),
        FakeLesson(
            date(2026, 11, 2), 2, "Wychowanie fizyczne", "Marek Biegowy", "sala gim."
        ),
    ]


def _lesson_cell(lesson: FakeLesson) -> str:
    text = (
        f'<div class="text"><b>{lesson.subject}</b><br>'
        f"&nbsp;-&nbsp;{lesson.teacher}&nbsp;s.&nbsp;{lesson.room}</div>"
    )
    if lesson.label is None:
        return text
    notice = f'<div class="center plan-lekcji-info">{lesson.label}</div>'
    if lesson.tooltip:
        title = html.escape("<br>".join(lesson.tooltip))
        notice = f'<a href="javascript:void(0);" title="{title}">{notice}</a>'
    if lesson.label == "odwołane":
        return f"{notice}<s><s>{text}</s></s>"
    return notice + text


def timetable_page(
    bells: dict[int, tuple[str, str]],
    monday: date,
    lessons: list[FakeLesson] | None = None,
) -> str:
    """Return the timetable of one week: lesson times and the lessons in it."""
    cells_of = {(lesson.day, lesson.number): lesson for lesson in lessons or []}
    rows = []
    for number, (start, end) in bells.items():
        cells = []
        for d in range(7):
            lesson = cells_of.get((monday + timedelta(days=d), number))
            cells.append(
                '<td id="timetableEntryBox" class="line1" '
                f'data-date="{monday + timedelta(days=d)}" data-date_from="{start}" '
                f'data-date_to="{end}">{_lesson_cell(lesson) if lesson else ""}</td>'
            )
        rows.append(
            f'<tr class="line1"><td class="center">{number}</td>{"".join(cells)}</tr>'
        )
    return f'<table class="decorated plan-lekcji">{"".join(rows)}</table>'


@dataclass
class FakeEvent:
    """A schedule event; ``day`` is its date."""

    id: int
    day: date
    type: str
    teacher: str = "Adam Rachunek"
    description: str = ""
    subject: str = ""
    lesson: int | None = None
    hour: str | None = None
    added: str = "2026-10-01 12:00:00"
    prefix: str = "szczegoly"
    # "substitution" or "cancelled": a lesson change, a list text without a
    # title or detail page (live test I-004); needs teacher, lesson and subject.
    kind: str | None = None

    @property
    def href(self) -> str:
        """Detail page path."""
        return f"/terminarz/{self.prefix}/{self.id}"


def default_events() -> list[FakeEvent]:
    """Events of October to December 2026 (tests freeze time at 2026-10-19)."""
    return [
        FakeEvent(
            3003,
            date(2026, 10, 21),
            "Sprawdzian",
            description="Ułamki zwykłe",
            subject="Matematyka",
            lesson=3,
        ),
        FakeEvent(3005, date(2026, 10, 23), "Wycieczka", description="Muzeum Techniki"),
        FakeEvent(3007, date(2026, 10, 28), "Zebranie z rodzicami", hour="17:00"),
        FakeEvent(
            3008,
            date(2026, 11, 4),
            "Klasówka",
            description="Średniowiecze",
            subject="Historia",
            lesson=2,
        ),
        FakeEvent(
            3009,
            date(2026, 11, 5),
            "Dzień wolny",
            description="Wolne",
            prefix="szczegoly_wolne",
        ),
        FakeEvent(3013, date(2026, 12, 2), "Kartkówka", subject="Przyroda", lesson=9),
    ]


def schedule_page(events: list[FakeEvent], year: int, month: int) -> str:
    """Return the calendar of one month."""
    days = []
    for number in range(1, calendar.monthrange(year, month)[1] + 1):
        rows = []
        for e in events:
            if (e.day.year, e.day.month, e.day.day) != (year, month, number):
                continue
            if e.kind:
                rows.append(f"<tr>{_lesson_change_cell(e)}</tr>")
                continue
            title = (
                f"Nauczyciel: {e.teacher}<br />Opis: {e.description}"
                f"<br />Data dodania: {e.added}"
            )
            text = f"Nr lekcji: {e.lesson}<br />" if e.lesson else ""
            if e.subject:
                text += f'<span class="przedmiot">{e.subject}</span>, '
            text += e.type
            if e.hour:
                text += f"<br />godz. {e.hour}"
            rows.append(
                f'<tr><td title="{html.escape(title)}" '
                f"onclick=\"location.href='{e.href}'\">{text}</td></tr>"
            )
        days.append(
            '<div class="kalendarz-dzien">'
            f'<div class="kalendarz-numer-dnia">{number}</div>'
            f"<table><tbody>{''.join(rows)}</tbody></table></div>"
        )
    return "".join(days)


def _lesson_change_cell(event: FakeEvent) -> str:
    """A substitution or cancelled lesson like Synergia renders it."""
    text = f"{event.teacher} na lekcji nr: {event.lesson} ({event.subject})"
    if event.kind == "substitution":
        text = f"Zastępstwo z {text}"
    else:
        text = f"Odwołane zajęcia <br/>{text}"
    padding = "\n" + " " * 28
    return f'<td style="background-color: #6A9604; ">{padding}{text}{padding}</td>'


def event_page(event: FakeEvent) -> str:
    """Return the detail page of one event."""
    rows = [("Data", event.day.isoformat())]
    if event.lesson:
        rows.append(("Nr lekcji", str(event.lesson)))
    rows.append(("Rodzaj", event.type))
    if event.subject:
        rows.append(("Przedmiot", event.subject))
    rows += [
        ("Nauczyciel", event.teacher),
        ("Opis", event.description),
        ("Data dodania", event.added),
    ]
    lines = "".join(
        f'<tr class="line{i % 2}"><th>{k}</th><td>{v}</td></tr>'
        for i, (k, v) in enumerate(rows)
    )
    return f'<div class="container-background"><table>{lines}</table></div>'


@dataclass
class FakeServer:
    """Synergia pages of one student, served through requests-mock."""

    mocker: rm.Mocker
    messages: list[FakeMessage] = field(default_factory=default_messages)
    announcements: list[FakeAnnouncement] = field(default_factory=default_announcements)
    subjects: list[FakeSubject] = field(default_factory=default_subjects)
    descriptive: list[FakeDescriptiveSubject] = field(
        default_factory=default_descriptive
    )
    new_schema: dict[int, str] = field(default_factory=dict)
    events: list[FakeEvent] = field(default_factory=default_events)
    bells: dict[int, tuple[str, str]] = field(default_factory=lambda: dict(BELLS))
    lessons: list[FakeLesson] = field(default_factory=default_lessons)
    # Mondays whose timetable page cannot be parsed (holidays, broken page).
    broken_weeks: set[date] = field(default_factory=set)
    lucky: str | None = "7"
    school: str = SCHOOL

    def __post_init__(self) -> None:
        """Register the pages."""
        self.mocker.get(f"{MOCK_URL}/informacja", text=self._info)
        self.mocker.post(f"{MOCK_URL}/przegladaj_plan_lekcji", text=self._timetable)
        self.mocker.post(f"{MOCK_URL}/terminarz/", text=self._schedule)
        self.mocker.get(
            re.compile(rf"{re.escape(MOCK_URL)}/terminarz/szczegoly(_wolne)?/\d+$"),
            text=self._event,
        )
        self.mocker.post(
            f"{MOCK_URL}/przegladaj_oceny/uczen",
            text=lambda request, context: (
                grades_page(self.subjects)
                + descriptive_table(self.descriptive)
                + new_schema_table(self.new_schema)
            ),
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
        return info_page(lucky=self.lucky, school=self.school)

    def _timetable(self, request: Any, context: Any) -> str:
        monday = date.fromisoformat(self.weeks_requested(request)[0])
        if monday in self.broken_weeks:
            return "<p>Brak planu lekcji</p>"
        return timetable_page(self.bells, monday, self.lessons)

    @staticmethod
    def weeks_requested(*requests: Any) -> list[str]:
        """Monday of each timetable request (from the tydzien field)."""
        return [parse_qs(r.text or "")["tydzien"][0][:10] for r in requests]

    def _schedule(self, request: Any, context: Any) -> str:
        form = parse_qs(request.text or "")
        return schedule_page(self.events, int(form["rok"][0]), int(form["miesiac"][0]))

    def _event(self, request: Any, context: Any) -> str:
        event_id = int(request.path.rsplit("/", 1)[1])
        event = next(e for e in self.events if e.id == event_id)
        return event_page(event)

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

    def timetable_weeks(self, start: int = 0) -> list[str]:
        """Mondays of the timetable requests since request number ``start``."""
        return self.weeks_requested(
            *(
                request
                for request in self.mocker.request_history[start:]
                if request.path == "/przegladaj_plan_lekcji"
            )
        )
