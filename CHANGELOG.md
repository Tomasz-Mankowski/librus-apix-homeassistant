# Changelog

All notable changes of the `librus-apix-homeassistant` integration.
Versions follow [Semantic Versioning](https://semver.org/).

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
