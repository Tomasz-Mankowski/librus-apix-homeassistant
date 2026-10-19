"""Tests for the notification blueprints (F16): one notification per event."""

from datetime import date
import logging
from pathlib import Path
import shutil
from typing import Any

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

from custom_components.librus_apix.const import DOMAIN

from .common import (
    FakeAnnouncement,
    FakeDescriptive,
    FakeEvent,
    FakeFinal,
    FakeGrade,
    FakeMessage,
    FakeServer,
)

BLUEPRINTS = Path(__file__).parents[1] / "blueprints" / "automation" / "librus_apix"


@pytest.fixture
def notifications(hass: HomeAssistant, tmp_path: Path) -> list[ServiceCall]:
    """Blueprints in a temporary config dir; persistent notifications captured."""
    hass.config.config_dir = str(tmp_path)
    shutil.copytree(BLUEPRINTS, tmp_path / "blueprints" / "automation" / "librus_apix")
    return async_mock_service(hass, "persistent_notification", "create")


def _event_entity(hass: HomeAssistant, entry: MockConfigEntry, key: str) -> str:
    entity_id = er.async_get(hass).async_get_entity_id(
        "event", DOMAIN, f"{entry.entry_id}_{key}"
    )
    assert entity_id
    return entity_id


async def _setup(
    hass: HomeAssistant, entry: MockConfigEntry, blueprint: str, key: str
) -> str:
    """Set up the entry and one automation from the blueprint; return the entity."""
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    entity_id = _event_entity(hass, entry, key)
    assert await async_setup_component(
        hass,
        "automation",
        {
            "automation": {
                "alias": blueprint,
                "use_blueprint": {
                    "path": f"librus_apix/{blueprint}.yaml",
                    "input": {"event_entities": [entity_id]},
                },
            }
        },
    )
    await hass.async_block_till_done()
    return entity_id


def _texts(calls: list[ServiceCall]) -> list[tuple[str, str]]:
    return [(call.data["title"], call.data["message"]) for call in calls]


@pytest.mark.parametrize(
    "path", sorted(BLUEPRINTS.glob("*.yaml")), ids=lambda p: p.stem
)
async def test_every_blueprint_loads(
    hass: HomeAssistant,
    notifications: list[ServiceCall],
    mock_server: FakeServer,
    config_entry: MockConfigEntry,
    path: Path,
) -> None:
    """An automation from each blueprint is valid and on."""
    await _setup(hass, config_entry, path.stem, "messages")

    state = hass.states.get(f"automation.{path.stem}")
    assert state is not None
    assert state.state == "on"


async def test_three_messages_give_three_notifications(
    hass: HomeAssistant,
    notifications: list[ServiceCall],
    mock_server: FakeServer,
    config_entry: MockConfigEntry,
) -> None:
    """Three new messages in one poll: three notifications, oldest first."""
    await _setup(hass, config_entry, "new_message", "messages")
    mock_server.messages[:0] = [
        FakeMessage(6003, "Sekretariat", "C", "2026-10-19 10:02:00", unread=True),
        FakeMessage(6002, "Sekretariat", "B", "2026-10-19 10:01:00", unread=True),
        FakeMessage(6001, "Dyrektor", "A", "2026-10-19 10:00:00"),
    ]

    await config_entry.runtime_data.messages.async_refresh()
    await hass.async_block_till_done(wait_background_tasks=True)

    assert _texts(notifications) == [
        ("Zofia Testowa: nowa wiadomość", "Dyrektor: A"),
        ("Zofia Testowa: nowa wiadomość", "Sekretariat: B"),
        ("Zofia Testowa: nowa wiadomość", "Sekretariat: C"),
    ]


async def test_restart_and_reload_do_not_notify(
    hass: HomeAssistant,
    notifications: list[ServiceCall],
    mock_server: FakeServer,
    config_entry: MockConfigEntry,
) -> None:
    """unavailable -> restored state is not a new message."""
    entity_id = await _setup(hass, config_entry, "new_message", "messages")
    mock_server.messages.insert(0, FakeMessage(6001, "Dyrektor", "A", "2026-10-19"))
    await config_entry.runtime_data.messages.async_refresh()
    await hass.async_block_till_done(wait_background_tasks=True)
    assert len(notifications) == 1

    assert await hass.config_entries.async_reload(config_entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)

    assert hass.states.get(entity_id).attributes["id"] == "6001"
    assert len(notifications) == 1


async def test_same_millisecond_event_still_notifies(
    hass: HomeAssistant,
    notifications: list[ServiceCall],
    mock_server: FakeServer,
    config_entry: MockConfigEntry,
) -> None:
    """Before HA 2026.8 two events in one millisecond keep the state, not the data."""
    entity_id = await _setup(hass, config_entry, "new_message", "messages")
    mock_server.messages.insert(0, FakeMessage(6001, "Dyrektor", "A", "2026-10-19"))
    await config_entry.runtime_data.messages.async_refresh()
    await hass.async_block_till_done(wait_background_tasks=True)
    state = hass.states.get(entity_id)
    attributes: dict[str, Any] = {**state.attributes, "id": "6002", "title": "Druga"}

    hass.states.async_set(entity_id, state.state, attributes)
    await hass.async_block_till_done()

    assert _texts(notifications) == [
        ("Zofia Testowa: nowa wiadomość", "Dyrektor: A"),
        ("Zofia Testowa: nowa wiadomość", "Dyrektor: Druga"),
    ]


async def test_other_options_notify_entities_and_actions(
    hass: HomeAssistant,
    notifications: list[ServiceCall],
    mock_server: FakeServer,
    config_entry: MockConfigEntry,
) -> None:
    """Notify entities and extra actions get the texts; the panel can be off."""
    sent = async_mock_service(hass, "notify", "send_message")
    extra = async_mock_service(hass, "test", "extra")
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    entity_id = _event_entity(hass, config_entry, "messages")
    assert await async_setup_component(
        hass,
        "automation",
        {
            "automation": {
                "alias": "custom",
                "use_blueprint": {
                    "path": "librus_apix/new_message.yaml",
                    "input": {
                        "event_entities": [entity_id],
                        "title": "Librus {{ student }}",
                        "message": "{{ event.title }} ({{ event.id }})",
                        "persistent": False,
                        "notify_targets": {"entity_id": ["notify.phone"]},
                        "extra_actions": [
                            {"action": "test.extra", "data": {"text": "{{ message }}"}}
                        ],
                    },
                },
            }
        },
    )
    mock_server.messages.insert(0, FakeMessage(6001, "Dyrektor", "A", "2026-10-19"))

    await config_entry.runtime_data.messages.async_refresh()
    await hass.async_block_till_done(wait_background_tasks=True)

    assert notifications == []
    assert [(c.data["title"], c.data["message"]) for c in sent] == [
        ("Librus Zofia Testowa", "A (6001)")
    ]
    assert sent[0].data["entity_id"] == ["notify.phone"]
    assert [c.data["text"] for c in extra] == ["A (6001)"]


async def test_grade_notifications(
    hass: HomeAssistant,
    notifications: list[ServiceCall],
    mock_server: FakeServer,
    config_entry: MockConfigEntry,
) -> None:
    """Changed, new, corrected and semester grades: one text each."""
    await _setup(hass, config_entry, "new_grade", "grades")
    math, polish = mock_server.subjects[0], mock_server.subjects[1]
    math.semester1[1].grade = "5"
    polish.semester1.append(
        FakeGrade(
            1250, "5+", "Recytacja", "2026-10-17", weight=2, comment="Pan Tadeusz"
        )
    )
    polish.semester1[0].correction = FakeGrade(
        1260, "5", "Dyktando", "2026-10-18", weight=2
    )
    polish.finals.append(FakeFinal(1290, "I", "4"))

    await config_entry.runtime_data.grades.async_refresh()
    await hass.async_block_till_done(wait_background_tasks=True)

    assert _texts(notifications) == [
        (
            "Zofia Testowa: zmiana oceny \N{EN DASH} Matematyka",
            "4+ → 5 (Odpowiedź ustna)",
        ),
        (
            "Zofia Testowa: nowa ocena \N{EN DASH} Język polski",
            "5+ (Recytacja, waga 2) \N{EN DASH} Pan Tadeusz",
        ),
        (
            "Zofia Testowa: nowa ocena \N{EN DASH} Język polski",
            "5 (Dyktando, waga 2) \N{EN DASH} poprawa oceny 4",
        ),
        (
            "Zofia Testowa: ocena okresowa \N{EN DASH} Język polski",
            "Ocena śródroczna: 4",
        ),
    ]


async def test_grade_event_types_can_be_chosen(
    hass: HomeAssistant,
    notifications: list[ServiceCall],
    mock_server: FakeServer,
    config_entry: MockConfigEntry,
) -> None:
    """Only the chosen event types notify."""
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    entity_id = _event_entity(hass, config_entry, "grades")
    assert await async_setup_component(
        hass,
        "automation",
        {
            "automation": {
                "alias": "finals only",
                "use_blueprint": {
                    "path": "librus_apix/new_grade.yaml",
                    "input": {
                        "event_entities": [entity_id],
                        "event_types": ["final_grade"],
                    },
                },
            }
        },
    )
    mock_server.subjects[0].semester1[1].grade = "5"
    mock_server.subjects[1].finals.append(FakeFinal(1290, "R", "5", proposed=True))

    await config_entry.runtime_data.grades.async_refresh()
    await hass.async_block_till_done(wait_background_tasks=True)

    assert _texts(notifications) == [
        (
            "Zofia Testowa: ocena okresowa \N{EN DASH} Język polski",
            "Proponowana ocena roczna: 5",
        )
    ]


async def test_descriptive_grade_notification(
    hass: HomeAssistant,
    notifications: list[ServiceCall],
    mock_server: FakeServer,
    config_entry: MockConfigEntry,
) -> None:
    """A new descriptive grade: grade and text."""
    await _setup(hass, config_entry, "new_descriptive_grade", "descriptive_grades")
    mock_server.descriptive[0].grades.append(
        FakeDescriptive("DB", "2026-10-18", "Dobra praca w grupie.")
    )

    await config_entry.runtime_data.grades.async_refresh()
    await hass.async_block_till_done(wait_background_tasks=True)

    assert _texts(notifications) == [
        (
            "Zofia Testowa: ocena opisowa \N{EN DASH} Edukacja zdrowotna",
            "DB: Dobra praca w grupie.",
        )
    ]


async def test_announcement_notification(
    hass: HomeAssistant,
    notifications: list[ServiceCall],
    mock_server: FakeServer,
    config_entry: MockConfigEntry,
) -> None:
    """A new announcement: its title and the start of the text."""
    await _setup(hass, config_entry, "new_announcement", "announcements")
    mock_server.announcements[:0] = [
        FakeAnnouncement("Wycieczka", "Dyrektor", "2026-10-19", "Zbiórka o 8:00.")
    ]

    await config_entry.runtime_data.announcements.async_refresh()
    await hass.async_block_till_done(wait_background_tasks=True)

    assert _texts(notifications) == [
        ("Zofia Testowa: Wycieczka", "Dyrektor: Zbiórka o 8:00.")
    ]


async def test_schedule_notifications(
    hass: HomeAssistant,
    notifications: list[ServiceCall],
    mock_server: FakeServer,
    config_entry: MockConfigEntry,
    freezer: Any,
) -> None:
    """A moved event and a new event: one text each, the old date for the move."""
    freezer.move_to("2026-10-19T08:00:00+00:00")
    await _setup(hass, config_entry, "schedule_event", "schedule")
    mock_server.events[0].day = date(2026, 10, 22)
    mock_server.events.append(
        FakeEvent(3020, date(2026, 11, 9), "Kartkówka", subject="Przyroda", lesson=1)
    )

    await config_entry.runtime_data.schedule.async_refresh()
    await hass.async_block_till_done(wait_background_tasks=True)

    assert _texts(notifications) == [
        (
            "Zofia Testowa: zmiana w terminarzu",
            "Sprawdzian: Matematyka, 2026-10-22, lekcja 3 (było: 2026-10-21)",
        ),
        ("Zofia Testowa: nowe wydarzenie", "Kartkówka: Przyroda, 2026-11-09, lekcja 1"),
    ]


@pytest.mark.parametrize(
    ("blueprint", "key"),
    [
        ("new_message", "messages"),
        ("new_announcement", "announcements"),
        ("new_grade", "grades"),
        ("new_descriptive_grade", "descriptive_grades"),
        ("schedule_event", "schedule"),
    ],
)
async def test_reload_without_events_logs_nothing(
    hass: HomeAssistant,
    notifications: list[ServiceCall],
    mock_server: FakeServer,
    config_entry: MockConfigEntry,
    caplog: pytest.LogCaptureFixture,
    blueprint: str,
    key: str,
) -> None:
    """unavailable -> unknown on a reload: no notification, no template warning."""
    await _setup(hass, config_entry, blueprint, key)
    caplog.clear()

    assert await hass.config_entries.async_reload(config_entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)

    assert notifications == []
    assert [
        r.getMessage()
        for r in caplog.records
        if r.levelno >= logging.WARNING
        and r.name.startswith(("homeassistant", "custom_components"))
    ] == []
