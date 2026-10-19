# `librus-apix-homeassistant` - Librus dla Home Assistant

Integracja [HACS](https://hacs.xyz/) dla Home Assistant. Odczytuje dane ucznia z Librus Synergia (oceny, wiadomości, ogłoszenia, terminarz) i udostępnia je jako encje oraz wyzwalacze automatyzacji.

> [!IMPORTANT]
> Projekt nieoficjalny. Nie jest powiązany z firmą Librus ani przez nią wspierany.

Karty do panelu (terminarz, wiadomości, ogłoszenia): [librus-apix-homeassistant-ui](https://github.com/Tomasz-Mankowski/librus-apix-homeassistant-ui).

> [!NOTE]
> Wersja przedpremierowa 0.1.0. Integracja jest przetestowana z symulatorem Librusa. Błędy zgłaszaj w [Issues](https://github.com/Tomasz-Mankowski/librus-apix-homeassistant/issues).

## Co potrafi

- Dane ucznia: imię i nazwisko, klasa, wychowawca, szkoła, numer w dzienniku, szczęśliwy numerek.
- Oceny: jeden czujnik na przedmiot ze średnią, oceny śródroczne i roczne (także proponowane), oceny opisowe, średnia ogólna.
- Wiadomości: ostatnie wiadomości odebrane (1–100). Treść jest czytana tylko na żądanie, bo Librus oznacza wtedy wiadomość jako przeczytaną.
- Ogłoszenia: wszystkie ogłoszenia z pełną treścią.
- Terminarz: kalendarz z godzinami lekcji dla bieżącego miesiąca i 0–6 kolejnych.
- Wyzwalacze: nowa wiadomość, nowe ogłoszenie, nowa lub zmieniona ocena, ocena okresowa, nowa ocena opisowa, nowe lub zmienione wydarzenie w terminarzu.
- Kilku uczniów: każdy uczeń to osobny wpis integracji z własnym urządzeniem i encjami.
- Język polski i angielski (według języka Home Assistant).

## Wymagania

- Home Assistant 2026.3 lub nowszy.
- [HACS](https://hacs.xyz/).
- Login i hasło do Librus Synergia (konto ucznia lub rodzica). Jeden login = jeden uczeń.

## Instalacja

[![Otwórz repozytorium w HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Tomasz-Mankowski&repository=librus-apix-homeassistant&category=integration)

Albo ręcznie:

1. HACS → menu **⋮** → **Własne repozytoria**.
2. Repozytorium: `https://github.com/Tomasz-Mankowski/librus-apix-homeassistant`, typ: **Integracja**.
3. Znajdź **Librus APIX** w HACS i kliknij **Pobierz**.
4. Uruchom Home Assistant ponownie.

## Konfiguracja

1. **Ustawienia** → **Urządzenia oraz usługi** → **Dodaj integrację** → **Librus APIX**.
2. Podaj login i hasło do Librus Synergia. Sekcję **Opcje deweloperskie** zostaw pustą (służy do testów z symulatorem).
3. Sprawdź krok **Ustawienia odświeżania** (tabela niżej) i zapisz.

Drugiego ucznia dodajesz tak samo: **Dodaj integrację** → **Librus APIX** → login drugiego ucznia.

| Ustawienie | Znaczenie | Domyślnie | Zakres |
|---|---|---|---|
| Dane ucznia | minuty między odczytami danych ucznia i szczęśliwego numerka | 360 | 10–1440 |
| Oceny | minuty między odczytami ocen | 15 | 10–1440 |
| Wiadomości | minuty między odczytami listy wiadomości | 15 | 10–1440 |
| Ogłoszenia | minuty między odczytami ogłoszeń | 15 | 10–1440 |
| Terminarz | minuty między odczytami terminarza | 60 | 10–1440 |
| Miesiące terminarza do przodu | bieżący miesiąc plus tyle kolejnych | 1 | 0–6 |
| Liczba wiadomości | ile ostatnich wiadomości czytać | 20 | 1–100 |

Ustawienia zmienisz później przyciskiem **Konfiguruj** przy wpisie integracji. Drugi krok tego okna ustala sposób liczenia średniej:

| Ustawienie | Domyślnie |
|---|---|
| Uwzględniaj wagi ocen | tak |
| Tylko oceny liczone do średniej | tak |
| Wartość plusa | 0,5 |
| Wartość minusa | 0,25 |

Gdy hasło do Librusa się zmieni, Home Assistant pokaże powiadomienie i poprosi o nowe hasło.

## Encje

Przykłady dotyczą uczennicy „Zofia Testowa” w Home Assistant po polsku. Identyfikatory encji powstają z nazw w języku Home Assistant w chwili dodania integracji.

| Encja | Przykład | Stan | Najważniejsze atrybuty |
|---|---|---|---|
| Uczeń | `sensor.zofia_testowa_uczen` | imię i nazwisko | |
| Klasa | `sensor.zofia_testowa_klasa` | np. `5a` | |
| Wychowawca | `sensor.zofia_testowa_wychowawca` | imię i nazwisko | |
| Szkoła | `sensor.zofia_testowa_szkola` | nazwa szkoły | |
| Numer w dzienniku | `sensor.zofia_testowa_numer_w_dzienniku` | numer | |
| Szczęśliwy numerek | `sensor.zofia_testowa_szczesliwy_numerek` | numer | |
| Przedmiot (jeden na przedmiot) | `sensor.zofia_testowa_matematyka` | średnia z bieżącego okresu | `grades`, `final_grades`, `averages`, `average_source`, `semester` |
| Oceny opisowe przedmiotu | `sensor.zofia_testowa_edukacja_zdrowotna_oceny_opisowe` | liczba ocen | `grades` |
| Średnia ocen | `sensor.zofia_testowa_srednia_ocen` | średnia ze średnich przedmiotów | `averages`, `subjects`, `average_source` |
| Wiadomości | `sensor.zofia_testowa_wiadomosci` | liczba nieprzeczytanych | `messages` (autor, tytuł, data, przeczytana, załącznik) |
| Ogłoszenia | `sensor.zofia_testowa_ogloszenia` | liczba ogłoszeń | `announcements` (z pełną treścią) |
| Terminarz | `calendar.zofia_testowa_terminarz` | kalendarz | opis wydarzenia: czytelne linie i jedna linia JSON ze wszystkimi polami |

`average_source` mówi, skąd jest średnia: `librus` (pokazana w Librusie), `calculated` (policzona według ustawień) albo `mixed`.

## Wyzwalacze

Każdy uczeń ma pięć encji zdarzeń. Jedno zdarzenie to jeden nowy lub zmieniony element. Kilka nowych elementów z jednego odczytu daje kilka osobnych zdarzeń.

| Encja zdarzeń | Przykład | Typy zdarzeń |
|---|---|---|
| Wiadomości | `event.zofia_testowa_wiadomosci` | `new_message` |
| Ogłoszenia | `event.zofia_testowa_ogloszenia` | `new_announcement` |
| Oceny | `event.zofia_testowa_oceny` | `new_grade`, `grade_changed`, `final_grade` |
| Oceny opisowe | `event.zofia_testowa_oceny_opisowe` | `new_descriptive_grade` |
| Terminarz | `event.zofia_testowa_terminarz` | `new_event`, `changed_event` |

Dane zdarzenia (atrybuty stanu encji zdarzeń):

| Typ | Pola |
|---|---|
| `new_message` | `id`, `title`, `author`, `date`, `unread`, `has_attachment` (bez treści) |
| `new_announcement` | `id`, `title`, `author`, `date`, `content` |
| `new_grade` | `id`, `subject`, `semester`, `grade`, `value`, `category`, `date`, `weight`, `counts`, `teacher`, `comment`, `is_correction`, `original_grade` |
| `grade_changed` | jak `new_grade` oraz `old_grade` |
| `final_grade` | `id`, `subject`, `period` (`semester_1`, `semester_2`, `year`), `grade`, `proposed`, `category`, `date`, `teacher`, `old_grade` |
| `new_descriptive_grade` | `id`, `subject`, `semester`, `grade`, `date`, `teacher`, `content`, `description` |
| `new_event` | `id`, `date`, `type`, `subject`, `teacher`, `lesson`, `hour`, `description`, `date_added`, `summary`, `start`, `end`, `all_day`, `details` |
| `changed_event` | jak `new_event` oraz `old` (wartości przed zmianą) i `changed` (nazwy zmienionych pól) |

Każde zdarzenie ma też `student` (imię i nazwisko ucznia) i `config_entry_id` (wpis integracji). Pierwszy odczyt po dodaniu integracji, restart i zmiana ustawień nie wywołują zdarzeń.

### Gotowe powiadomienia (blueprinty)

Kliknij przycisk, żeby dodać blueprint, potem utwórz z niego automatyzację: wybierz encje zdarzeń uczniów i sposób powiadomienia. Teksty powiadomień można zmienić.

| Powiadomienie | Import |
|---|---|
| Nowa wiadomość | [![Import blueprintu](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2FTomasz-Mankowski%2Flibrus-apix-homeassistant%2Fblob%2Fmaster%2Fblueprints%2Fautomation%2Flibrus_apix%2Fnew_message.yaml) |
| Nowe ogłoszenie | [![Import blueprintu](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2FTomasz-Mankowski%2Flibrus-apix-homeassistant%2Fblob%2Fmaster%2Fblueprints%2Fautomation%2Flibrus_apix%2Fnew_announcement.yaml) |
| Oceny (nowe, zmienione, okresowe) | [![Import blueprintu](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2FTomasz-Mankowski%2Flibrus-apix-homeassistant%2Fblob%2Fmaster%2Fblueprints%2Fautomation%2Flibrus_apix%2Fnew_grade.yaml) |
| Nowa ocena opisowa | [![Import blueprintu](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2FTomasz-Mankowski%2Flibrus-apix-homeassistant%2Fblob%2Fmaster%2Fblueprints%2Fautomation%2Flibrus_apix%2Fnew_descriptive_grade.yaml) |
| Terminarz (nowe, zmienione) | [![Import blueprintu](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2FTomasz-Mankowski%2Flibrus-apix-homeassistant%2Fblob%2Fmaster%2Fblueprints%2Fautomation%2Flibrus_apix%2Fschedule_event.yaml) |

### Własna automatyzacja

Przykład: powiadomienie na telefon o każdej nowej ocenie Zosi. `mode: queued` sprawia, że kilka ocen z jednego odczytu daje kilka powiadomień.

Home Assistant 2026.8 lub nowszy:

```yaml
alias: Librus – nowa ocena Zosi
mode: queued
max: 50
triggers:
  - trigger: event.received
    target:
      entity_id: event.zofia_testowa_oceny
    options:
      event_type:
        - new_grade
actions:
  - action: notify.mobile_app_telefon
    data:
      title: "{{ trigger.to_state.attributes.student }}: nowa ocena"
      message: >-
        {{ trigger.to_state.attributes.subject }}: {{ trigger.to_state.attributes.grade }}
        ({{ trigger.to_state.attributes.category }})
```

Home Assistant 2026.3–2026.7: wyzwalacz stanu bez `from`/`to` i warunek, który pomija przywrócenie stanu po restarcie:

```yaml
triggers:
  - trigger: state
    entity_id: event.zofia_testowa_oceny
conditions:
  - condition: template
    value_template: >-
      {{ trigger.from_state is not none
         and trigger.from_state.state != 'unavailable'
         and trigger.to_state.state not in ['unavailable', 'unknown']
         and trigger.to_state.attributes.event_type == 'new_grade' }}
```

Zamień `notify.mobile_app_telefon` na swoją usługę powiadomień.

## Akcja: treść wiadomości

`librus_apix.get_message_content` zwraca pełną treść wiadomości. Librus oznacza wtedy wiadomość jako przeczytaną. Treść jest czytana raz i zapamiętana; kolejne wywołania nie łączą się z Librusem.

Przykład: nowa wiadomość z treścią w powiadomieniu (akcje automatyzacji z wyzwalaczem jak wyżej, na `event.zofia_testowa_wiadomosci`):

```yaml
actions:
  - action: librus_apix.get_message_content
    data:
      entity_id: sensor.zofia_testowa_wiadomosci
      message_id: "{{ trigger.to_state.attributes.id }}"
    response_variable: wiadomosc
  - action: notify.mobile_app_telefon
    data:
      title: "{{ trigger.to_state.attributes.student }}: {{ trigger.to_state.attributes.title }}"
      message: "{{ wiadomosc.content }}"
```

Odpowiedź: `id`, `author`, `title`, `date`, `content`, `attachments` (nazwy plików).

## Przykłady kart

Terminarz, wiadomości i ogłoszenia pokazują karty z [librus-apix-homeassistant-ui](https://github.com/Tomasz-Mankowski/librus-apix-homeassistant-ui). Oceny i dane ucznia pokażesz standardowymi kartami:

```yaml
# Średnia ocen
type: tile
entity: sensor.zofia_testowa_srednia_ocen
```

```yaml
# Dane ucznia
type: entities
title: Zofia
entities:
  - sensor.zofia_testowa_klasa
  - sensor.zofia_testowa_wychowawca
  - sensor.zofia_testowa_szczesliwy_numerek
```

```yaml
# Średnie przedmiotów w czasie
type: statistics-graph
title: Średnie
entities:
  - sensor.zofia_testowa_matematyka
  - sensor.zofia_testowa_jezyk_polski
stat_types:
  - mean
days_to_show: 30
```

```yaml
# Oceny z matematyki w 1. okresie
type: markdown
title: Matematyka
content: >-
  {% for g in state_attr('sensor.zofia_testowa_matematyka', 'grades').semester_1 %}
  - **{{ g.grade }}** {{ g.category }}, {{ g.date }}{{ ', waga ' ~ g.weight if g.weight }}
  {% endfor %}
```

## Diagnostyka

**Ustawienia** → **Urządzenia oraz usługi** → **Librus APIX** → wpis ucznia → **⋮** → **Pobierz diagnostykę**. Plik nie zawiera loginu, hasła, ciasteczek ani danych ucznia, tylko stan odczytów i liczby elementów.

## Podziękowania

Integracja korzysta z biblioteki [librus-apix](https://github.com/RustySnek/librus-apix) autorstwa [RustySnek](https://github.com/RustySnek). Dziękujemy za jej stworzenie i rozwój.

## Licencja

[GPL-3.0](LICENSE), tak jak biblioteka `librus-apix`.

---

## English

Home Assistant integration (HACS) that reads student data from Librus Synergia: grades, messages, announcements and schedule. The data is available as entities, a calendar and automation triggers.

> [!IMPORTANT]
> Unofficial project, not affiliated with or endorsed by Librus.

- **Status:** pre-release 0.1.0, tested with a Librus simulator.
- **Requires:** Home Assistant 2026.3 or newer, HACS, a Librus Synergia login (one login = one student).
- **Install:** HACS → **⋮** → **Custom repositories** → `https://github.com/Tomasz-Mankowski/librus-apix-homeassistant`, type **Integration** → **Download** → restart Home Assistant. Then **Settings** → **Devices & services** → **Add integration** → **Librus APIX**, enter the login and password, keep the defaults. Add the integration once per student.
- **Options:** poll interval per data type (student info 360 min, grades, messages and announcements 15 min, schedule 60 min; 10–1440 min), schedule months ahead (1, 0–6), number of messages (20, 1–100), average rules (weights, only counted grades, plus 0.5, minus 0.25).
- **Entities** (English Home Assistant, student "Zofia Testowa"): `sensor.zofia_testowa_student`, `_class`, `_tutor`, `_school`, `_student_number`, `_lucky_number`, one sensor per subject (current-semester average), descriptive-grade sensors, `sensor.zofia_testowa_gpa`, `sensor.zofia_testowa_messages` (unread count, `messages` attribute), `sensor.zofia_testowa_announcements`, `calendar.zofia_testowa_schedule`. Entity IDs follow the Home Assistant language at setup.
- **Triggers:** event entities `messages` (`new_message`), `announcements` (`new_announcement`), `grades` (`new_grade`, `grade_changed`, `final_grade`), `descriptive_grades` (`new_descriptive_grade`), `schedule` (`new_event`, `changed_event`). Every event carries `student` and `config_entry_id`. One event per new item; use `mode: queued`. The first poll, restarts and option changes fire nothing.
- **Notifications:** five blueprints in [`blueprints/automation/librus_apix`](blueprints/automation/librus_apix) (import buttons above), or your own automation as in the YAML example above.
- **Action:** `librus_apix.get_message_content` (`entity_id`: messages sensor, `message_id`) returns the full message; Librus marks it read. The content is read once and kept.
- **Cards:** [librus-apix-homeassistant-ui](https://github.com/Tomasz-Mankowski/librus-apix-homeassistant-ui) for schedule, messages and announcements; standard cards for grades and student info (examples above).
- **Credits:** built on the [librus-apix](https://github.com/RustySnek/librus-apix) library by RustySnek.
- **License:** [GPL-3.0](LICENSE).
