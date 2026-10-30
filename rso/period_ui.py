"""Uma aba por obra, com seleção de ano, mês e semana dentro da própria aba."""

import asyncio
from datetime import date, timedelta

import flet as ft

from .models import Report
from .periods import MONTHS, available_years, monday, month_weeks, report_day, report_monday, today
from .project_state import project_key


class ProjectReportsTab(ft.Column):
    def __init__(self, app, key: str):
        super().__init__(expand=True, spacing=8)
        self.app, self.key = app, key
        current = today()
        self.selected_id = None
        self.creating = False
        self.year = ft.Dropdown(label="Ano", value=str(current.year), col={"xs": 4, "sm": 3},
                                on_change=self.change_month)
        self.month = ft.Dropdown(label="Mês", value=str(current.month), col={"xs": 8, "sm": 3},
            options=[ft.dropdown.Option(str(i), name) for i, name in enumerate(MONTHS, 1)],
            on_change=self.change_month)
        self.week = ft.Dropdown(label="Semana", value=monday(current).isoformat(),
                                col={"xs": 12, "sm": 6}, text_size=14, on_change=self.change_week)
        self.variant = ft.Dropdown(label="Relatórios salvos nesta semana", visible=False,
                                   on_change=self.change_variant)
        self.empty = ft.Text(color="#69756E")
        self.create_button = ft.FilledButton("Criar relatório desta semana", on_click=self.open_week)
        self.body = ft.Container(expand=True)
        self.controls = [ft.Container(ft.ResponsiveRow([self.year, self.month, self.week], run_spacing=8),
                                      padding=ft.padding.only(top=10)),
                         self.variant, self.body]

    @property
    def reports(self) -> list[Report]:
        return [r for r in self.app.reports.values() if project_key(r) == self.key]

    def refresh(self):
        reports = self.reports
        years = sorted({*available_years(reports), int(self.year.value)})
        self.year.options = [ft.dropdown.Option(str(year)) for year in years]
        weeks = month_weeks(int(self.year.value), int(self.month.value))
        self.week.options = [ft.dropdown.Option(start.isoformat(),
            f"Semana {i} • {start:%d/%m} a {start + timedelta(days=4):%d/%m}")
            for i, start in enumerate(weeks, 1)]
        if self.week.value not in {w.isoformat() for w in weeks}:
            self.week.value = weeks[0].isoformat()
        selected = date.fromisoformat(self.week.value)
        matches = sorted([r for r in reports if report_monday(r) == selected],
                         key=lambda r: (r.created_at, r.id))
        self.variant.visible = len(matches) > 1
        self.variant.options = [ft.dropdown.Option(r.id, f"Relatório {i} • {r.start} a {r.end}")
                                for i, r in enumerate(matches, 1)]
        if matches:
            report = next((r for r in matches if r.id == self.selected_id), matches[-1])
            self.selected_id = self.variant.value = report.id
            self.body.content = self.app.view_for(report)
        else:
            self.selected_id = None
            self.empty.value = f"Ainda não há relatório de {selected:%d/%m/%Y} a {selected + timedelta(days=4):%d/%m/%Y}."
            self.body.content = ft.Column([self.empty, self.create_button], spacing=12)

    def select_report(self, report: Report):
        day, start = report_day(report), report_monday(report)
        # Ao criar a semana que atravessa dois meses, manter o mês escolhido.
        if self.week.value != start.isoformat():
            self.year.value, self.month.value = str(day.year), str(day.month)
        self.week.value = start.isoformat()
        self.selected_id = report.id
        self.refresh()

    async def change_month(self, event):
        event.control.value = event.data
        self.week.value = None
        self.selected_id = None
        self.refresh()
        self.app.page.update()

    async def change_week(self, event):
        self.week.value = event.data
        self.selected_id = None
        self.refresh()
        self.app.page.update()

    async def change_variant(self, event):
        self.selected_id = event.data
        self.refresh()
        self.app.page.update()

    async def open_week(self, event):
        if self.creating:
            return
        self.creating = self.create_button.disabled = True
        for control in (self.year, self.month, self.week, self.variant):
            control.disabled = True
        self.app.page.update()
        try:
            # Cache/repositório consultado sob lock. Clicar novamente abre o
            # relatório já existente, sem criar outra aba nem outra cópia.
            report = await asyncio.to_thread(self.app.catalog.new_report, self.key,
                                              week_start=date.fromisoformat(self.week.value))
            self.app.add_tab(report)
        except (OSError, ValueError) as exc:
            self.app.page.open(ft.SnackBar(ft.Text(str(exc))))
        finally:
            self.creating = self.create_button.disabled = False
            for control in (self.year, self.month, self.week, self.variant):
                control.disabled = False
            self.app.page.update()
