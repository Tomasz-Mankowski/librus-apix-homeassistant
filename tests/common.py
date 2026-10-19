"""Shared test data: a fake Synergia server for requests-mock."""

from dataclasses import dataclass, field
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


def default_messages() -> list[FakeMessage]:
    """Eight messages, newest first: two unread, one with an attachment."""
    return [
        FakeMessage(
            5001 + i,
            f"Nauczyciel {i}",
            f"Temat {i}",
            f"2026-10-{18 - i:02d} 12:0{i}:00",
            unread=i < 2,
            attachment=i == 1,
        )
        for i in range(8)
    ]


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
class FakeServer:
    """Synergia pages of one student, served through requests-mock."""

    mocker: rm.Mocker
    messages: list[FakeMessage] = field(default_factory=default_messages)
    lucky: str | None = "7"

    def __post_init__(self) -> None:
        """Register the pages."""
        self.mocker.get(f"{MOCK_URL}/informacja", text=self._info)
        self.mocker.get(f"{MOCK_URL}/wiadomosci/1/5", text=self._messages)
        self.mocker.post(f"{MOCK_URL}/wiadomosci/1/5", text=self._messages)

    def _info(self, request: Any, context: Any) -> str:
        return info_page(lucky=self.lucky)

    def _messages(self, request: Any, context: Any) -> str:
        form = parse_qs(request.text or "")
        return messages_page(self.messages, int(form.get("numer_strony105", ["0"])[0]))

    def paths(self) -> list[str]:
        """Paths of all requests so far."""
        return [request.path for request in self.mocker.request_history]
