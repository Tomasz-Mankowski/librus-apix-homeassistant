"""Shared test data: a fake Synergia server for requests-mock."""

from dataclasses import dataclass, field
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
class FakeServer:
    """Synergia pages of one student, served through requests-mock."""

    mocker: rm.Mocker
    messages: list[FakeMessage] = field(default_factory=default_messages)
    announcements: list[FakeAnnouncement] = field(default_factory=default_announcements)
    lucky: str | None = "7"

    def __post_init__(self) -> None:
        """Register the pages."""
        self.mocker.get(f"{MOCK_URL}/informacja", text=self._info)
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
