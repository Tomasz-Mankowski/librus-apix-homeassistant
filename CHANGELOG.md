# Changelog

All notable changes of the `librus-apix-homeassistant` integration.
Versions follow [Semantic Versioning](https://semver.org/).

## 1.1.0 — 2026-10-21

The integration is now called **HALibrus**. The domain (`librus_apix`), entity IDs, the action
and the blueprints' file names stay, so existing entries, automations and dashboards keep working.

### Added

- Timetable calendar "Timetable" / "Plan lekcji" per student: one event per lesson with its times
  and classroom; substitutions, cancelled lessons and classroom changes in the title and in the
  JSON line of the description. Options: timetable interval (default 360 min) and weeks ahead
  (current week + 0–4, default 1; one request per week).
- The lucky number has its own update interval (default 180 min).
- Subject sensors: each grade names the grade it corrects (`corrects`).

### Changed

- Display names: integration `HALibrus`, device model `HALibrus`, blueprints `HALibrus - …`.
- The student info is read once a day by default (1440 min).
- README: larger blueprint import buttons and a manual import path (Home Assistant 2026.10 does not
  open the import window after the import link).

### Upgrade

- Entries of 1.0.0 are migrated (config entry 1.2): the new options get their defaults; a student
  info interval still at the old default (360 min) becomes 1440 min, a value you set stays.

## 1.0.0 — 2026-10-19

First release. Requires Home Assistant 2026.3 or newer and uses
[librus-apix](https://github.com/RustySnek/librus-apix) 1.6.0.

### Setup

- Config flow: Librus Synergia login and password, then the read settings. One entry per student.
- Options in two steps: poll interval per data type (10–1440 min), schedule months ahead (0–6),
  number of messages (1–100), and the rules of the calculated averages (weights, only counted
  grades, plus and minus values).
- Re-authentication when the password changes.

### Entities

- Student info: student, class, tutor, school, student number, lucky number.
- Grades: one sensor per subject (current-semester average from Librus, or calculated when the
  school hides averages), semester and final grades (also proposed), descriptive grades, GPA.
  The behaviour row (`Zachowanie`) is not part of the GPA.
- Messages (state: unread count) and announcements (with full text).
- Schedule calendar with lesson times from the bell schedule, including substitutions
  (`Zastępstwo`) and cancelled lessons (`Odwołane zajęcia`).

### Triggers

- Event entities with the types `new_message`, `new_announcement`, `new_grade`, `grade_changed`,
  `final_grade`, `new_descriptive_grade`, `new_event` and `changed_event`. One event per new item;
  the first poll, restarts and option changes fire nothing.
- Five blueprints for notifications: messages, announcements, grades, descriptive grades,
  schedule.

### Other

- Action `librus_apix.get_message_content`: the full message on request (Librus marks it read).
- Diagnostics without credentials or student data.
- One request queue per Librus host with a gap between requests and a backoff after failures.
- Polish and English texts; brand icons.
