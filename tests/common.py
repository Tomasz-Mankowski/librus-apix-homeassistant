"""Shared test data: a mock server URL and its student information page."""

MOCK_URL = "http://librus-mock-a:8000"
SCHOOL = "Szkoła Podstawowa nr 999\nul. Fikcyjna 1"


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
