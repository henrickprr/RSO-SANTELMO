"""Calendário do diário: semanas úteis e localização dos relatórios salvos."""

from calendar import monthrange
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from .models import Report, parse_date

MONTHS = ("Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho",
          "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro")


def today() -> date:
    return datetime.now(ZoneInfo("America/Fortaleza")).date()


def monday(day: date) -> date:
    return day - timedelta(days=day.weekday())


def month_weeks(year: int, month: int) -> list[date]:
    """Segundas das semanas cujo intervalo de segunda a sexta cruza o mês.

    Meses podem ter 4 ou 5 semanas úteis. Uma semana que cruza a virada do
    mês aparece nos dois filtros, sempre apontando ao mesmo relatório.
    """
    first = date(year, month, 1)
    last = date(year, month, monthrange(year, month)[1])
    start = monday(first)
    result = []
    while start <= last:
        if start + timedelta(days=4) >= first:
            result.append(start)
        start += timedelta(days=7)
    return result


def report_day(report: Report) -> date:
    # Datas ainda em digitação continuam acessíveis, sem descartar o rascunho.
    for value in (report.start, report.end):
        try:
            return parse_date(value)
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(report.created_at).date()
    except ValueError:
        return today()


def report_monday(report: Report) -> date:
    return monday(report_day(report))


def available_years(reports: list[Report], current: date | None = None) -> list[int]:
    current = current or today()
    years = {current.year, min(9999, current.year + 1), *(report_day(r).year for r in reports)}
    return list(range(min(years), max(years) + 1))
