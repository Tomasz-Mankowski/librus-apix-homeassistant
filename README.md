# HALibrus - Librus dla Home Assistant

Integracja [HACS](https://hacs.xyz/) dla Home Assistant. Odczytuje dane ucznia z Librus Synergia (oceny, wiadomości, ogłoszenia, terminarz, plan lekcji) i udostępnia je jako encje oraz wyzwalacze automatyzacji. Implementacja w sposób minimalny i maksymalnie funkcjonalny. Integracja korzysta z [librus-apix](https://github.com/RustySnek/librus-apix).

> [!IMPORTANT]
> Projekt nieoficjalny. **Nie jest powiązany z firmą Librus** ani przez nią wspierany. Do logowania używaj tylko swojego prywatnego loginu i hasła do systemu Librus Synergia. Używaj na własną odpowiedzialność. **Autor nie ponosi odpowiedzialności za użycie integracji**, a także jakiekolwiek konsekwecje wynikające z korzystania z niej.

## Dedykowane karty panelu

Dedykowane karty panelu: **HALibrus Cards** ([librus-apix-homeassistant-ui](https://github.com/Tomasz-Mankowski/librus-apix-homeassistant-ui)).

## Instalacja

[![Otwórz repozytorium w HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Tomasz-Mankowski&repository=librus-apix-homeassistant&category=integration)

Lub ręcznie:

1. HACS → menu **⋮** → **Własne repozytoria**.
2. Repozytorium: `https://github.com/Tomasz-Mankowski/librus-apix-homeassistant`, typ: **Integracja**.
3. Znajdź **HALibrus** w HACS i kliknij **Pobierz**.
4. Uruchom Home Assistant ponownie.

## Co potrafi

- Dane ucznia i szczęśliwy numerek.
- Oceny: średnia każdego przedmiotu i średnia ogólna, oceny okresowe i opisowe.
- Wiadomości (treść tylko na żądanie) i ogłoszenia.
- Terminarz i plan lekcji jako kalendarze, z zastępstwami i odwołanymi lekcjami.
- Wyzwalacze i gotowe powiadomienia o nowościach.
- Kilku uczniów; język polski i angielski.

## Wymagania

- Home Assistant 2026.3 lub nowszy.
- [HACS](https://hacs.xyz/).
- Login i hasło do Librus Synergia (konto ucznia lub rodzica). Jeden login = jeden uczeń.

## Konfiguracja

1. **Ustawienia** → **Urządzenia oraz usługi** → **Dodaj integrację** → **HALibrus**.
2. Podaj login i hasło do Librus Synergia. Sekcję **Opcje deweloperskie** zostaw pustą (służy do testów z symulatorem).
3. Skonfiguruj krok **Ustawienia odświeżania** i Zatwierdź.

Drugiego ucznia dodajesz tak samo: **Dodaj integrację** → **HALibrus** → login drugiego ucznia.

Ustawienia odświeżania:

| Ustawienie | Domyślnie | Zakres |
|---|---|---|
| Dane ucznia (i godziny lekcji) | 1440 min | 10–1440 min |
| Szczęśliwy numerek | 180 min | 10–1440 min |
| Oceny | 15 min | 10–1440 min |
| Wiadomości | 15 min | 10–1440 min |
| Ogłoszenia | 15 min | 10–1440 min |
| Terminarz | 60 min | 10–1440 min |
| Plan lekcji | 360 min | 10–1440 min |
| Miesiące terminarza do przodu | 1 | 0–6 |
| Tygodnie planu lekcji do przodu | 1 (jedno zapytanie na tydzień) | 0–4 |
| Liczba wiadomości | 20 | 1–100 |

Aby zmienić ustawienia lub sposób liczenia średniej, po dodaniu integracji kliknij przycisk **Konfiguruj** i skonfiguruj ponownie **Ustawienia odświeżania**, a następnie **Obliczane średnie**.

## Kalendarze

Każdy uczeń ma dwa kalendarze:

- **Terminarz** (`calendar.<uczen>_terminarz`): sprawdziany, wycieczki, zebrania, zastępstwa i odwołane lekcje.
- **Plan lekcji** (`calendar.<uczen>_plan_lekcji`): jedna lekcja to jedno wydarzenie z godzinami i salą. Zmiana jest w tytule, np. `Matematyka (zastępstwo)` lub `Historia (odwołane)`.

Opis wydarzenia to czytelne linie, a w ostatniej linii wszystkie pola w formacie JSON (do automatyzacji i kart).

## Wyzwalacze

### Gotowe powiadomienia/notyfikacje (blueprinty)

Kliknij przycisk importu, a potem w Home Assistant **Podgląd** i **Importuj schemat**. Z zaimportowanego schematu utwórz automatyzację i wybierz uczniów.

| Powiadomienie | Import |
|---|---|
| Nowa wiadomość | <a href="https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2FTomasz-Mankowski%2Flibrus-apix-homeassistant%2Fblob%2Fmaster%2Fblueprints%2Fautomation%2Flibrus_apix%2Fnew_message.yaml"><img src="https://my.home-assistant.io/badges/blueprint_import.svg" alt="Importuj: nowa wiadomość" width="346"></a> |
| Nowe ogłoszenie | <a href="https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2FTomasz-Mankowski%2Flibrus-apix-homeassistant%2Fblob%2Fmaster%2Fblueprints%2Fautomation%2Flibrus_apix%2Fnew_announcement.yaml"><img src="https://my.home-assistant.io/badges/blueprint_import.svg" alt="Importuj: nowe ogłoszenie" width="346"></a> |
| Oceny (nowe, zmienione, okresowe) | <a href="https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2FTomasz-Mankowski%2Flibrus-apix-homeassistant%2Fblob%2Fmaster%2Fblueprints%2Fautomation%2Flibrus_apix%2Fnew_grade.yaml"><img src="https://my.home-assistant.io/badges/blueprint_import.svg" alt="Importuj: oceny (nowe, zmienione, okresowe)" width="346"></a> |
| Nowa ocena opisowa | <a href="https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2FTomasz-Mankowski%2Flibrus-apix-homeassistant%2Fblob%2Fmaster%2Fblueprints%2Fautomation%2Flibrus_apix%2Fnew_descriptive_grade.yaml"><img src="https://my.home-assistant.io/badges/blueprint_import.svg" alt="Importuj: nowa ocena opisowa" width="346"></a> |
| Terminarz (nowe, zmienione) | <a href="https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2FTomasz-Mankowski%2Flibrus-apix-homeassistant%2Fblob%2Fmaster%2Fblueprints%2Fautomation%2Flibrus_apix%2Fschedule_event.yaml"><img src="https://my.home-assistant.io/badges/blueprint_import.svg" alt="Importuj: terminarz (nowe, zmienione)" width="346"></a> |

**Jeśli po kliknięciu otwiera się tylko lista schematów, bez okna importu** (tak działa Home Assistant 2026.10), zaimportuj schemat ręcznie:

1. [Otwórz listę schematów w Home Assistant](https://my.home-assistant.io/redirect/blueprints/).
2. Kliknij **Importuj schemat**.
3. Wklej adres schematu z listy poniżej, kliknij **Podgląd**, a potem **Importuj schemat**.

- Nowa wiadomość: `https://github.com/Tomasz-Mankowski/librus-apix-homeassistant/blob/master/blueprints/automation/librus_apix/new_message.yaml`
- Nowe ogłoszenie: `https://github.com/Tomasz-Mankowski/librus-apix-homeassistant/blob/master/blueprints/automation/librus_apix/new_announcement.yaml`
- Oceny (nowe, zmienione, okresowe): `https://github.com/Tomasz-Mankowski/librus-apix-homeassistant/blob/master/blueprints/automation/librus_apix/new_grade.yaml`
- Nowa ocena opisowa: `https://github.com/Tomasz-Mankowski/librus-apix-homeassistant/blob/master/blueprints/automation/librus_apix/new_descriptive_grade.yaml`
- Terminarz (nowe, zmienione): `https://github.com/Tomasz-Mankowski/librus-apix-homeassistant/blob/master/blueprints/automation/librus_apix/schedule_event.yaml`

### Szczegóły

Każdy uczeń ma pięć encji zdarzeń. Jedno zdarzenie to jeden nowy lub zmieniony element. Kilka nowych elementów z jednego odczytu daje kilka osobnych zdarzeń.

| Encja zdarzeń | Przykład | Typy zdarzeń |
|---|---|---|
| Wiadomości | `event.<uczen>_wiadomosci` | `new_message` |
| Ogłoszenia | `event.<uczen>_ogloszenia` | `new_announcement` |
| Oceny | `event.<uczen>_oceny` | `new_grade`, `grade_changed`, `final_grade` |
| Oceny opisowe | `event.<uczen>_oceny_opisowe` | `new_descriptive_grade` |
| Terminarz | `event.<uczen>_terminarz` | `new_event`, `changed_event` |

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

Zastępstwo ma typ `Zastępstwo`, odwołana lekcja typ `Odwołane zajęcia`; `teacher` to nauczyciel podany przez Librusa, `subject` to przedmiot lekcji.

Każde zdarzenie ma też `student` (imię i nazwisko ucznia) i `config_entry_id` (wpis integracji). Pierwszy odczyt po dodaniu integracji, restart i zmiana ustawień nie wywołują zdarzeń.

## Podziękowanie

Podziękowania dla twórców biblioteki [librus-apix](https://github.com/RustySnek/librus-apix) autorstwa [RustySnek](https://github.com/RustySnek).

## Licencja

[GPL-3.0](LICENSE)
