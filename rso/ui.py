"""Interface Flet 0.28.3. Cada ObraTab possui modelo, controles e seletores próprios."""

from __future__ import annotations

import asyncio
import base64
from datetime import datetime
from io import BytesIO
import os
from pathlib import Path
import re
from uuid import uuid4

import flet as ft
from PIL import Image

from .excel_generator import ExcelGenerator
from .models import DAYS, WEATHER, Report, ResourceRow, ValidationError, parse_date
from .pdf_generator import PDFGenerator
from .settings import ASSETS
from .storage import DraftRepository, atomic_write

GREEN = "#315D40"
MUTED = "#69756E"
INK = "#202E26"
BACKGROUND = "#F3F5F2"


class ObraTab(ft.Column):
    """Subclasse de Column substitui o antigo UserControl removido do Flet atual.

    Nenhuma lista ou controle mutável é atributo de classe. Handlers capturam a
    instância/linha correta, inclusive enquanto outra aba exporta em background.
    """

    def __init__(self, page: ft.Page, report: Report, repository: DraftRepository,
                 on_name_change=None):
        super().__init__(expand=True, spacing=0)
        self.host_page = page
        self.report = report
        self.repository = repository
        self.on_name_change = on_name_change
        self.fields: dict[str, ft.TextField] = {}
        self.status = ft.Text("Rascunho • pronto para editar", size=12, color=MUTED)
        self.summary = ft.Text(size=12, color=MUTED)
        self.daily_labels: list[ft.Text] = []
        self.table_bodies: dict[str, ft.Column] = {}
        self.photo_body = ft.Column(spacing=10)
        self.pending_uploads: dict[str, tuple[Path, int]] = {}
        self.finishing_uploads: set[str] = set()
        self.importing_photos = False
        self.picker_day = 0
        self.pending_export: Path | None = None
        self.busy = False
        self.image_picker = ft.FilePicker(on_result=self.on_photos_selected,
                                          on_upload=self.on_photo_uploaded)
        self.export_picker = ft.FilePicker(on_result=self.on_export_destination)
        page.overlay.extend([self.image_picker, self.export_picker])
        self.build_form()

    def toast(self, message: str, error: bool = False) -> None:
        self.host_page.open(ft.SnackBar(ft.Text(message, color="#FFFFFF"),
                                       bgcolor="#A33232" if error else GREEN,
                                       duration=6500 if error else 3500))

    def commit(self, notify: bool = False) -> bool:
        try:
            self.repository.save(self.report)
            temporary = os.environ.get("RSO_STORAGE_MODE") == "ephemeral"
            label = "Salvo temporariamente" if temporary else "Rascunho salvo"
            self.status.value = f"{label} às {datetime.now():%H:%M:%S}"
            self.status.color = MUTED
            if notify:
                message = ("Salvo no servidor temporário. Baixe o backup para guardar os dados."
                           if temporary else "Rascunho salvo, incluindo atividades e legendas.")
                self.toast(message)
        except OSError as exc:
            self.status.value = "Não foi possível salvar. Verifique o espaço e as permissões da pasta."
            self.status.color = "#A33232"
            if notify:
                self.toast(f"Falha ao salvar: {exc}", True)
            self.host_page.update()
            return False
        self.refresh_summary()
        self.host_page.update()
        return True

    def bind(self, obj, attribute: str):
        async def changed(event):
            setattr(obj, attribute, event.control.value)
            if obj is self.report and attribute in ("start", "end"):
                self.refresh_day_labels()
            if obj is self.report and attribute == "tab_name" and self.on_name_change:
                self.on_name_change(self.report)
            self.commit()
        return changed

    def field(self, name: str, label: str, *, multiline: bool = False,
              col=12, hint: str | None = None) -> ft.TextField:
        control = ft.TextField(label=label, value=getattr(self.report, name),
                               on_change=self.bind(self.report, name), col=col,
                               multiline=multiline, min_lines=3 if multiline else 1,
                               max_lines=6 if multiline else 1, border_radius=9,
                               border_color="#D5DDD6", focused_border_color=GREEN,
                               text_size=14, hint_text=hint, filled=True, bgcolor="white",
                               content_padding=14)
        self.fields[name] = control
        return control

    def date_field(self, name: str, label: str) -> ft.TextField:
        control = self.field(name, label, col={"xs": 12, "md": 6}, hint="DD/MM/AAAA")

        async def selected(event):
            if picker.value:
                value = picker.value.strftime("%d/%m/%Y")
                control.value = value
                setattr(self.report, name, value)
                control.error_text = None
                self.refresh_day_labels()
                self.commit()

        picker = ft.DatePicker(first_date=datetime(2000, 1, 1), last_date=datetime(2100, 12, 31),
                               on_change=selected)
        self.host_page.overlay.append(picker)

        async def open_picker(event):
            try:
                picker.value = datetime.combine(parse_date(control.value), datetime.min.time())
            except ValidationError:
                picker.value = datetime.now()
            self.host_page.open(picker)

        control.suffix = ft.IconButton(ft.Icons.CALENDAR_MONTH_OUTLINED, on_click=open_picker,
                                      tooltip=f"Selecionar {label.lower()}", icon_color=GREEN)
        return control

    def dropdown(self, name: str, label: str, options: list[tuple[str, str]], *, col=12):
        async def changed(event):
            value = int(event.control.value) if name == "photo_columns" else event.control.value
            setattr(self.report, name, value)
            self.commit()
        return ft.Dropdown(value=str(getattr(self.report, name)), label=label, col=col,
                           expanded_insets=0, width=1400,
                           options=[ft.dropdown.Option(key=k, text=v) for k, v in options],
                           on_change=changed, border_radius=9, text_size=14,
                           border_color="#D5DDD6", filled=True, bgcolor="white")

    @staticmethod
    def section(number: str, title: str, subtitle: str, controls: list, key: str) -> ft.Container:
        return ft.Container(key=key, content=ft.Card(elevation=0, color="white",
            content=ft.Container(padding=24, content=ft.Column([
                ft.Row([ft.Container(ft.Text(number, color=GREEN, weight=ft.FontWeight.BOLD),
                                     bgcolor="#EDF3E9", padding=10, border_radius=9),
                        ft.Column([ft.Text(title, size=18, weight=ft.FontWeight.W_600, color=INK),
                                   ft.Text(subtitle, size=12, color=MUTED)], spacing=3, expand=True)],
                       spacing=14), ft.Container(height=2), *controls], spacing=16))))

    def build_form(self) -> None:
        metadata = [ft.ResponsiveRow([
            self.field("tab_name", "Nome da aba", col={"xs": 12, "md": 4}),
            self.field("cliente", "Cliente", col={"xs": 12, "md": 8}),
            self.field("obra", "Obra / descrição do empreendimento"),
            self.field("responsavel_tecnico", "Responsável técnico"),
            self.date_field("start", "Data de início"), self.date_field("end", "Data de fim"),
            self.dropdown("morning", "Tempo • manhã", [(v, v) for v in WEATHER], col={"xs": 12, "md": 4}),
            self.dropdown("afternoon", "Tempo • tarde", [(v, v) for v in WEATHER], col={"xs": 12, "md": 4}),
            self.field("evolution", "Evolução da obra (%)", col={"xs": 12, "md": 4}),
        ], run_spacing=16), ft.Checkbox(label="Houve feriados na semana", value=self.report.holidays,
                                         on_change=self.bind(self.report, "holidays"))]
        resources = [self.resource_table("employees", "Funcionários da empresa"),
                     self.resource_table("contractors", "Equipe de terceiros"),
                     self.resource_table("equipment", "Equipamentos"), self.summary,
                     self.field("notes", "Observações", multiline=True)]
        activities = []
        for index, day in enumerate(DAYS):
            label = ft.Text(day, weight=ft.FontWeight.W_600, color=GREEN, size=13)
            self.daily_labels.append(label)

            async def change_activity(event, index=index):
                self.report.activities[index] = event.control.value
                self.commit()

            activities.append(ft.Column([label, ft.TextField(value=self.report.activities[index],
                label=f"Serviços executados • {day}", multiline=True, min_lines=3, max_lines=8,
                border_radius=9, text_size=14, border_color="#D5DDD6", focused_border_color=GREEN,
                on_change=change_activity)], spacing=8))
        self.upload_button = ft.OutlinedButton("Adicionar fotos", icon=ft.Icons.ADD_PHOTO_ALTERNATE_OUTLINED,
                                               on_click=self.pick_photos)
        self.upload_day = ft.Dropdown(label="Dia das novas fotos", value="0", width=300,
                                     options=[ft.dropdown.Option(str(i), day) for i, day in enumerate(DAYS)])
        self.photo_counts = ft.Row(wrap=True, spacing=8, run_spacing=8)
        photos = [self.field("materials", "Chegada de materiais", multiline=True,
                             hint="Um material por linha. Ex.: 50 sacos de cimento • 30/09"),
                  ft.Text("Cada dia do período precisa de 2 ou 4 fotos para exportar. Máximo: 4 por dia.",
                          color=GREEN, size=13), self.photo_counts,
                  ft.Row([self.upload_day, self.upload_button], wrap=True),
                  ft.Text("JPG, PNG ou WebP • até 30 MB por foto • rascunhos podem ficar incompletos",
                          size=12, color=MUTED), self.photo_body]
        footer = [ft.ResponsiveRow([
            self.field("engineer", "Engenheiro responsável", col={"xs": 12, "md": 8}),
            self.field("crea", "CREA", col={"xs": 12, "md": 4}),
            self.field("art", "ART nº", col={"xs": 12, "md": 6}),
            self.field("permit", "Alvará", col={"xs": 12, "md": 6}),
            self.dropdown("template", "Geometria do modelo", [
                ("compact", "Átrio / Bosque"), ("wide", "Bella Vista"), ("sintra", "Sintra")],
                col={"xs": 12, "md": 4}),
            self.dropdown("theme", "Cabeçalhos do relatório", [
                ("green", "Verde dos anexos • texto preto"), ("gray", "Cinza escuro • texto branco")],
                col={"xs": 12, "md": 4}),
            self.dropdown("photo_columns", "Organização das fotos", [("2", "Duas colunas"),
                                                                      ("1", "Uma coluna")],
                col={"xs": 12, "md": 4}),
        ], run_spacing=16)]
        self.form = ft.Column([
            self.section("01", "Identificação da obra", "Dados da semana e condições do canteiro.", metadata, f"{self.report.id}-metadata"),
            self.section("02", "Mão de obra e equipamentos", "Adicione as equipes e confira os totais calculados.", resources, f"{self.report.id}-resources"),
            self.section("03", "Atividades diárias", "Registre os serviços realizados de segunda a sexta-feira.", activities, f"{self.report.id}-activities"),
            self.section("04", "Materiais e registro fotográfico", "As fotos são copiadas para a pasta de dados do aplicativo.", photos, f"{self.report.id}-photos"),
            self.section("05", "Responsabilidade e exportação", "Dados de assinatura e aparência do documento.", footer, f"{self.report.id}-footer"),
            ft.Container(height=12),
        ], expand=True, scroll=ft.ScrollMode.AUTO, spacing=16)

        async def save(event):
            self.commit(notify=True)

        async def export_pdf(event):
            await self.export("pdf")

        async def export_excel(event):
            await self.export("xlsx")

        self.pdf_button = ft.FilledButton("Exportar PDF", icon=ft.Icons.PICTURE_AS_PDF_OUTLINED,
                                          on_click=export_pdf, style=ft.ButtonStyle(bgcolor=GREEN, color="white"))
        self.excel_button = ft.OutlinedButton("Exportar XLSX", icon=ft.Icons.TABLE_CHART_OUTLINED,
                                               on_click=export_excel)
        self.busy_indicator = ft.ProgressRing(width=18, height=18, stroke_width=2, visible=False)
        navigation = []
        for key, label in [("metadata", "Identificação"), ("resources", "Equipes"),
                           ("activities", "Atividades"), ("photos", "Fotos"), ("footer", "Assinatura")]:
            async def scroll(event, key=key):
                self.form.scroll_to(key=f"{self.report.id}-{key}", duration=250)
            navigation.append(ft.TextButton(label, on_click=scroll, style=ft.ButtonStyle(color=GREEN)))
        self.controls = [ft.Container(ft.Row(navigation, wrap=True, spacing=0), padding=ft.padding.only(top=6, bottom=4)),
                         self.form,
                         ft.Container(content=ft.ResponsiveRow([
                             ft.Row([self.busy_indicator, self.status], spacing=8,
                                    col={"xs": 12, "lg": 5}),
                             ft.Row([ft.TextButton("Salvar Rascunho", icon=ft.Icons.SAVE_OUTLINED, on_click=save),
                                     self.excel_button, self.pdf_button], wrap=True,
                                    alignment=ft.MainAxisAlignment.END, col={"xs": 12, "lg": 7}),
                         ], spacing=0, run_spacing=8),
                         padding=ft.padding.symmetric(vertical=14, horizontal=8), bgcolor=BACKGROUND)]
        self.refresh_summary()
        self.refresh_day_labels()
        self.render_photos()

    def refresh_day_labels(self) -> None:
        try:
            dates = self.report.week_dates()
        except ValidationError:
            dates = [None] * 5
        for label, name, date in zip(self.daily_labels, DAYS, dates):
            label.value = f"{name} • {date:%d/%m}" if date else name
        if hasattr(self, "upload_day"):
            self.upload_day.options = [ft.dropdown.Option(str(i),
                f"{name} • {date:%d/%m}" if date else name)
                for i, (name, date) in enumerate(zip(DAYS, dates))]
            self.render_photos()

    def refresh_summary(self) -> None:
        try:
            employees, contractors, equipment = self.report.totals()
            self.summary.value = (f"{employees} funcionários da empresa + {contractors} terceiros "
                                  f"= {employees + contractors} pessoas  •  {equipment} equipamentos")
        except ValidationError:
            self.summary.value = "Revise as quantidades para calcular os totais."

    def resource_table(self, name: str, title: str) -> ft.Column:
        body = ft.Column(spacing=8)
        self.table_bodies[name] = body

        async def add(event):
            getattr(self.report, name).append(ResourceRow())
            self.render_table(name)
            self.commit()

        self.render_table(name)
        return ft.Column([ft.Row([ft.Text(title, weight=ft.FontWeight.W_600, color=INK, expand=True),
                                  ft.TextButton("Adicionar linha", icon=ft.Icons.ADD, on_click=add)]),
                          body], spacing=8)

    def render_table(self, name: str) -> None:
        rows = getattr(self.report, name)
        body = self.table_bodies[name]
        body.controls.clear()
        if not rows:
            body.controls.append(ft.Container(ft.Text("Nenhum registro. Adicione uma linha para começar.",
                                                       color=MUTED, size=13), padding=12, bgcolor=BACKGROUND,
                                               border_radius=8))
        for row in rows:
            fields = []
            if name == "contractors":
                fields.append(ft.TextField(label="Empresa terceira", value=row.company, expand=2,
                                            text_size=13, dense=True, border_radius=8,
                                            on_change=self.bind(row, "company")))
            fields.extend([
                ft.TextField(label="Equipamento" if name == "equipment" else "Função / cargo",
                             value=row.description, expand=3, text_size=13, dense=True,
                             border_radius=8, border_color="#D5DDD6",
                             focused_border_color=GREEN, on_change=self.bind(row, "description")),
                ft.TextField(label="Qtde", value=row.quantity, width=84, dense=True, text_size=13,
                             keyboard_type=ft.KeyboardType.NUMBER, border_radius=8,
                             on_change=self.bind(row, "quantity")),
            ])

            async def remove(event, row=row):
                # Excluir somente a linha desta instância; outras obras têm listas próprias.
                rows.remove(row)
                self.render_table(name)
                self.commit()

            fields.append(ft.IconButton(ft.Icons.DELETE_OUTLINE, tooltip="Remover linha",
                                         icon_color=MUTED, on_click=remove))
            body.controls.append(ft.Row(fields, spacing=8))

    async def pick_photos(self, event):
        if self.importing_photos or self.pending_uploads:
            return
        self.picker_day = int(self.upload_day.value)
        count = len(self.report.photos_for_day(self.picker_day))
        if count >= 4:
            self.toast(f"{DAYS[self.picker_day]} já tem 4 fotos. Remova ou mova uma para adicionar outra.", True)
            return
        self.image_picker.pick_files(dialog_title=f"Fotos de {DAYS[self.picker_day]} • até {4 - count}", allow_multiple=True,
                                     file_type=ft.FilePickerFileType.CUSTOM,
                                     allowed_extensions=["jpg", "jpeg", "png", "webp"])

    def set_importing(self, value: bool) -> None:
        self.importing_photos = value
        self.upload_button.disabled = self.upload_day.disabled = value
        self.host_page.update()

    async def on_photos_selected(self, event: ft.FilePickerResultEvent):
        if not event.files:
            return
        day = self.picker_day  # Capturado ao abrir o seletor, independentemente da aba ativa.
        available = 4 - len(self.report.photos_for_day(day))
        if len(event.files) > available:
            self.toast(f"{DAYS[day]} permite adicionar mais {max(0, available)} foto(s). "
                       "Nenhuma foto desta seleção foi importada.", True)
            return
        self.set_importing(True)
        if self.host_page.web:
            uploads = []
            for file in event.files:
                if file.size > 30 * 1024 * 1024:
                    self.toast(f"{file.name}: limite de 30 MB excedido.", True)
                    continue
                if file.name in self.pending_uploads:
                    self.toast(f"Selecione arquivos com nomes diferentes: {file.name}", True)
                    continue
                relative = f"{self.report.id}/{uuid4().hex}{Path(file.name).suffix.lower()}"
                self.pending_uploads[file.name] = (self.repository.uploads / relative, day)
                uploads.append(ft.FilePickerUploadFile(name=file.name, id=file.id,
                    upload_url=self.host_page.get_upload_url(relative, 600)))
            if uploads:
                self.status.value = "Importando fotos…"
                self.host_page.update()
                try:
                    self.image_picker.upload(uploads)
                except Exception as exc:
                    self.pending_uploads.clear()
                    self.set_importing(False)
                    self.toast(f"Não foi possível iniciar o envio: {exc}", True)
            else:
                self.set_importing(False)
            return
        try:
            for file in event.files:
                if file.path:
                    await self.import_photo(Path(file.path), file.name, day)
        finally:
            self.set_importing(False)
            self.render_photos()
            self.commit()

    async def import_photo(self, path: Path, name: str, day: int) -> None:
        try:
            photo = await asyncio.to_thread(self.repository.import_photo, path, self.report.id)
            photo.original_name = name
            self.report.add_photo(photo, day)
        except (ValidationError, OSError) as exc:
            self.toast(f"{name}: {exc}", True)

    async def on_photo_uploaded(self, event: ft.FilePickerUploadEvent):
        pending = self.pending_uploads.get(event.file_name)
        if pending is None or event.file_name in self.finishing_uploads:
            return
        if event.error or event.progress == 1:
            path, day = pending
            self.finishing_uploads.add(event.file_name)
            try:
                if event.error:
                    self.toast(f"Falha no envio de {event.file_name}: {event.error}", True)
                else:
                    await self.import_photo(path, event.file_name, day)
            finally:
                path.unlink(missing_ok=True)
                self.pending_uploads.pop(event.file_name, None)
                self.finishing_uploads.discard(event.file_name)
                self.set_importing(bool(self.pending_uploads))
                self.render_photos()
                self.commit()

    def render_photos(self) -> None:
        self.photo_body.controls.clear()
        try:
            active = self.report.active_days()
            dates = self.report.week_dates()
        except ValidationError:
            active, dates = list(range(5)), [None] * 5
        self.photo_counts.controls = []
        for day, name in enumerate(DAYS):
            count = len(self.report.photos_for_day(day))
            status = "completo" if count in (2, 4) else "incompleto"
            if day not in active:
                status = "fora do período"
            self.photo_counts.controls.append(ft.Container(
                ft.Text(f"{name}: {count}/4 • {status}", size=12,
                        color=GREEN if count in (2, 4) and day in active else "#8A5B12"),
                padding=10, bgcolor="#EDF3E9" if count in (2, 4) and day in active else "#FFF5E3",
                border_radius=8))
        if self.report.photos_for_day(None):
            self.photo_body.controls.append(ft.Text(
                "Há fotos de rascunhos antigos sem dia definido. Selecione o dia em cada foto para exportar.",
                color="#8A5B12", size=13))
        if not self.report.photos:
            self.photo_body.controls.append(ft.Container(ft.Column([
                ft.Icon(ft.Icons.ADD_A_PHOTO_OUTLINED, color="#899C8A", size=30),
                ft.Text("O registro da semana começa aqui", color=INK, weight=ft.FontWeight.W_500),
                ft.Text("Adicione fotos e escreva uma legenda para cada imagem.", color=MUTED, size=12),
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=10),
                alignment=ft.alignment.center, padding=30, bgcolor=BACKGROUND, border_radius=12))
        ordered = [photo for day in (None, *range(5)) for photo in self.report.photos_for_day(day)]
        last_day = object()
        for i, photo in enumerate(ordered):
            peers = self.report.photos_for_day(photo.day)
            group_index = peers.index(photo)
            if photo.day != last_day:
                label = "Fotos sem dia definido" if photo.day is None else DAYS[photo.day]
                if photo.day is not None and dates[photo.day]:
                    label += f" • {dates[photo.day]:%d/%m/%Y}"
                self.photo_body.controls.append(ft.Text(label, size=15, color=GREEN,
                                                        weight=ft.FontWeight.W_600))
                last_day = photo.day
            try:
                with Image.open(self.repository.resolve_photo(photo)) as im:
                    im.thumbnail((210, 150))
                    buffer = BytesIO()
                    im.save(buffer, "JPEG")
                preview = ft.Image(src_base64=base64.b64encode(buffer.getvalue()).decode(),
                                   width=130, height=94, fit=ft.ImageFit.CONTAIN, border_radius=8,
                                   semantics_label=f"Foto {i + 1}: {photo.original_name}")
            except (ValidationError, OSError):
                preview = ft.Container(ft.Text("Foto ausente", color="#A33232"), width=130, height=94)

            async def move(event, photo=photo, delta=-1):
                same_day = self.report.photos_for_day(photo.day)
                position = same_day.index(photo) + delta
                if 0 <= position < len(same_day):
                    index = self.report.photos.index(photo)
                    target = self.report.photos.index(same_day[position])
                    self.report.photos[index], self.report.photos[target] = self.report.photos[target], photo
                    self.render_photos()
                    self.commit()

            async def down(event, photo=photo):
                await move(event, photo=photo, delta=1)

            async def remove(event, photo=photo):
                self.report.photos.remove(photo)
                # Arquivo preservado para que o backup JSON continue recuperável.
                self.render_photos()
                self.commit()

            async def change_day(event, photo=photo):
                try:
                    if self.importing_photos:
                        raise ValidationError("Aguarde a importação das fotos para mudar o dia.")
                    self.report.assign_photo(photo, int(event.control.value))
                except (ValidationError, ValueError) as exc:
                    event.control.value = str(photo.day) if photo.day is not None else None
                    self.toast(str(exc), True)
                    self.host_page.update()
                    return
                self.render_photos()
                self.commit()

            self.photo_body.controls.append(ft.Container(ft.Row([
                preview, ft.Column([ft.Text(f"{i + 1:02d}  {photo.original_name}", size=12, color=MUTED),
                    ft.Dropdown(label="Dia da foto", value=str(photo.day) if photo.day is not None else None,
                                options=[ft.dropdown.Option(str(d), name) for d, name in enumerate(DAYS)],
                                width=320, on_change=change_day),
                    ft.TextField(label="Legenda da foto", value=photo.caption, multiline=True,
                                 min_lines=2, max_lines=4, text_size=13, border_radius=8,
                                 on_change=self.bind(photo, "caption"))], expand=True),
                ft.Column([ft.IconButton(ft.Icons.ARROW_UPWARD, tooltip="Mover foto para cima", on_click=move, disabled=group_index == 0),
                           ft.IconButton(ft.Icons.ARROW_DOWNWARD, tooltip="Mover foto para baixo", on_click=down,
                                         disabled=group_index == len(peers) - 1),
                           ft.IconButton(ft.Icons.DELETE_OUTLINE, tooltip="Remover foto", on_click=remove)], spacing=0)
            ], spacing=14), padding=12, bgcolor=BACKGROUND, border_radius=12))

    def set_busy(self, value: bool) -> None:
        self.busy = value
        self.pdf_button.disabled = self.excel_button.disabled = value
        self.busy_indicator.visible = value
        self.host_page.update()

    async def export(self, extension: str) -> None:
        if self.busy:
            return
        snapshot = Report.from_dict(self.report.to_dict())
        try:
            snapshot.validate()
            if self.pending_uploads or self.importing_photos:
                raise ValidationError("Aguarde o envio das fotos antes de exportar.")
        except ValidationError as exc:
            self.toast(str(exc), True)
            return
        if not self.commit():
            self.toast("Não foi possível salvar o rascunho antes da exportação.", True)
            return
        self.set_busy(True)
        self.status.value = f"Gerando {extension.upper()}…"
        self.host_page.update()
        stem = re.sub(r"[^\w-]+", "-", snapshot.tab_name, flags=re.UNICODE).strip("-") or "Obra"
        filename = f"RSO-{stem}-{parse_date(snapshot.end):%Y%m%d}.{extension}"
        destination = self.repository.exports / uuid4().hex / filename
        try:
            generator = PDFGenerator(self.repository) if extension == "pdf" else ExcelGenerator(self.repository)
            await asyncio.to_thread(generator.generate, snapshot, destination)
            if self.host_page.web:
                # No servidor publicado, estas URLs também exigem autenticação.
                relative = Path("downloads") / uuid4().hex / filename
                public = self.repository.root / "public" / relative
                atomic_write(public, destination.read_bytes())
                self.host_page.launch_url("/" + relative.as_posix(), web_window_name="_blank")
                self.status.value = f"{extension.upper()} pronto • arquivo aberto para download"
                self.set_busy(False)
                self.toast("Exportação concluída. Uma cópia permanece na pasta de exportações do aplicativo.")
            else:
                self.pending_export = destination
                self.export_picker.save_file(dialog_title=f"Salvar relatório {extension.upper()}",
                    file_name=filename, file_type=ft.FilePickerFileType.CUSTOM,
                    allowed_extensions=[extension], initial_directory=str(Path.home()))
        except Exception as exc:
            self.status.value = "Exportação não concluída. O rascunho está salvo."
            self.set_busy(False)
            self.toast(f"Não foi possível exportar: {exc}", True)

    async def on_export_destination(self, event: ft.FilePickerResultEvent):
        source = self.pending_export
        self.pending_export = None
        try:
            if source and event.path:
                target = Path(event.path)
                if target.suffix.lower() != source.suffix:
                    target = target.with_suffix(source.suffix)
                await asyncio.to_thread(atomic_write, target, source.read_bytes())
                self.toast(f"Relatório salvo em {target}")
            self.status.value = "Rascunho salvo • pronto para editar"
        except OSError as exc:
            self.status.value = "Não foi possível copiar a exportação para a pasta escolhida."
            self.toast(f"{exc}. O arquivo gerado está em {source}", True)
        finally:
            self.set_busy(False)


class RSOApp:
    def __init__(self, page: ft.Page, repository: DraftRepository):
        self.page, self.repository = page, repository
        self.tabs = ft.Tabs(expand=True, selected_index=0, animation_duration=150,
                            indicator_color=GREEN, label_color=GREEN, unselected_label_color=MUTED,
                            divider_color="#DCE2DA", scrollable=True)
        self.views: dict[str, ObraTab] = {}

    async def mount(self):
        page = self.page
        page.title = "Santelmo • Relatórios de Obra"
        page.bgcolor = BACKGROUND
        page.padding = ft.padding.symmetric(horizontal=28, vertical=20)
        page.theme_mode = ft.ThemeMode.LIGHT
        page.theme = ft.Theme(color_scheme_seed=GREEN, use_material3=True)
        page.locale_configuration = ft.LocaleConfiguration(supported_locales=[ft.Locale("pt", "BR")],
                                                           current_locale=ft.Locale("pt", "BR"))
        page.window.width, page.window.height = 1220, 900
        page.window.min_width, page.window.min_height = 780, 620
        reports = self.repository.load_all()
        # Nunca substituir rascunhos ilegíveis por novos documentos silenciosamente.
        if not reports and not list(self.repository.drafts.glob("*.json")):
            for name, template in (("Casa Bella Vista", "wide"), ("Casa Bosque", "compact"),
                                    ("Casa Sintra", "sintra"), ("Casa Átrio", "compact")):
                report = Report.new(name, template)
                self.repository.save(report)
                reports.append(report)
        for report in reports:
            self.add_tab(report)
        logo = base64.b64encode((ASSETS / "logo.png").read_bytes()).decode()
        page.add(ft.Column([
            ft.Row([ft.Image(src_base64=logo, width=126, height=56, fit=ft.ImageFit.CONTAIN),
                    ft.Container(width=4),
                    ft.Column([ft.Text("Relatórios de obra", size=27, weight=ft.FontWeight.W_600, color=INK),
                               ft.Text("A semana documentada. Cada obra no seu lugar.", size=13, color=MUTED)],
                               expand=True, spacing=3),
                    ft.OutlinedButton("Nova obra", icon=ft.Icons.ADD, on_click=self.new_report)], spacing=12),
            ft.Row([
                ft.TextButton("Backup e restauração", icon=ft.Icons.SAVE_ALT,
                              on_click=lambda e: page.launch_url("/backup", web_window_name="_blank")),
                ft.Text("Render Free: dados temporários. Baixe o backup antes de sair.",
                        color="#8A5B12", size=12,
                        visible=os.environ.get("RSO_STORAGE_MODE") == "ephemeral"),
            ], wrap=True, visible=bool(page.web)),
            self.tabs,
        ], expand=True, spacing=14))
        if self.repository.warnings:
            recovery_dialog = ft.AlertDialog(title=ft.Text("Recuperação de rascunhos"),
                content=ft.Text("\n".join(self.repository.warnings)),
                actions=[ft.TextButton("Fechar", on_click=lambda e: page.close(recovery_dialog))])
            page.open(recovery_dialog)

    def name_changed(self, report: Report):
        for tab in self.tabs.tabs:
            if tab.content.report.id == report.id:
                tab.text = report.tab_name or "Nova obra"

    def add_tab(self, report: Report):
        view = ObraTab(self.page, report, self.repository, self.name_changed)
        self.views[report.id] = view
        self.tabs.tabs.append(ft.Tab(text=report.tab_name, content=view))

    async def new_report(self, event):
        name = ft.TextField(label="Nome da obra", autofocus=True, value="", width=400)
        template = ft.Dropdown(label="Modelo base", value="compact", options=[
            ft.dropdown.Option("compact", "Átrio / Bosque"), ft.dropdown.Option("wide", "Bella Vista"),
            ft.dropdown.Option("sintra", "Sintra")])

        async def create(event):
            if not name.value.strip():
                name.error_text = "Informe um nome para a obra."
                self.page.update()
                return
            report = Report.new(name.value.strip(), template.value)
            try:
                self.repository.save(report)
            except OSError as exc:
                name.error_text = f"Não foi possível salvar: {exc}"
                self.page.update()
                return
            self.add_tab(report)
            self.tabs.selected_index = len(self.tabs.tabs) - 1
            self.page.close(dialog)
            self.page.update()

        dialog = ft.AlertDialog(title=ft.Text("Adicionar obra"),
            content=ft.Column([name, template], tight=True, spacing=16),
            actions=[ft.TextButton("Cancelar", on_click=lambda e: self.page.close(dialog)),
                     ft.FilledButton("Criar obra", on_click=create)])
        self.page.open(dialog)

