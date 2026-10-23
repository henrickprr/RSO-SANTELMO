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
from .firebase_backend import CloudConflict
from .models import DAYS, WEATHER, Report, ResourceRow, ValidationError, parse_date
from .pdf_generator import PDFGenerator
from .project_catalog import ProjectCatalog
from .projects import COMMON, ProjectProfile, apply_project, is_fixed_field
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
                 on_name_change=None, on_copy=None):
        super().__init__(expand=True, spacing=0)
        self.host_page = page
        apply_project(report)
        self.report = report
        self.repository = repository
        self.on_name_change = on_name_change
        self.on_copy = on_copy
        self.stale = False
        self.fields: dict[str, ft.TextField] = {}
        self.status = ft.Text("Rascunho • pronto para editar", size=12, color=MUTED)
        self.summary = ft.Text(size=12, color=MUTED)
        self.daily_labels: list[ft.Text] = []
        self.table_bodies: dict[str, ft.Column] = {}
        self.photo_body = ft.Column(spacing=10)
        self.pending_uploads: dict[str, tuple[Path, None]] = {}
        self.finishing_uploads: set[str] = set()
        self.importing_photos = False
        self._photo_selection_handled = False
        self._photo_import_lock = asyncio.Lock()
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
            if self.repository.cloud_enabled:
                if notify:
                    self.repository.request_sync(self.report.id)
                    self.toast("Sincronização solicitada. Aguarde a indicação Salvo no Firebase.")
                self.refresh_cloud_status()
                self.refresh_summary()
                self.host_page.update()
                return True
            temporary = os.environ.get("RSO_STORAGE_MODE") == "ephemeral"
            label = "Salvo temporariamente" if temporary else "Rascunho salvo"
            self.status.value = f"{label} às {datetime.now():%H:%M:%S}"
            self.status.color = MUTED
            if notify:
                message = ("Salvo no servidor temporário. Baixe o backup para guardar os dados."
                           if temporary else "Rascunho salvo, incluindo atividades e legendas.")
                self.toast(message)
        except OSError as exc:
            self.stale = isinstance(exc, CloudConflict)
            self.copy_button.visible = self.stale
            self.status.value = (str(exc) if self.stale else
                "Não foi possível salvar. Verifique o espaço e as permissões da pasta.")
            self.status.color = "#A33232"
            if notify:
                self.toast(f"Falha ao salvar: {exc}", True)
            self.host_page.update()
            return False
        self.refresh_summary()
        self.host_page.update()
        return True

    def refresh_cloud_status(self):
        if not self.repository.cloud_enabled or self.busy or self.stale:
            return
        if self.importing_photos or self.pending_uploads:
            self.status.value = "Recebendo fotos • aguarde o salvamento antes de fechar"
            self.status.color = "#8A5B12"
            return
        state = self.repository.sync_status(self.report.id)
        status = state["status"]
        self.copy_button.visible = status == "conflict"
        if status == "synced":
            stamp = datetime.fromisoformat(state["saved_at"]).astimezone().strftime("%H:%M:%S")
            self.status.value = f"Salvo no Firebase às {stamp} • dados e fotos"
            self.status.color = GREEN
        elif status == "syncing":
            self.status.value = "Salvando dados e fotos no Firebase…"
            self.status.color = MUTED
        elif status in ("error", "conflict"):
            self.status.value = state["error"]
            self.status.color = "#A33232"
        else:
            self.status.value = "Salvamento na nuvem pendente • mantenha o aplicativo aberto"
            self.status.color = "#8A5B12"

    async def keep_copy(self, event):
        try:
            copy = await asyncio.to_thread(self.repository.keep_as_copy, self.report)
            if self.on_copy:
                self.on_copy(copy)
            self.toast("Edição preservada em uma nova aba. Aguarde o salvamento no Firebase. "
                       "Reabra o aplicativo para atualizar a aba original.")
        except OSError:
            self.toast("Não foi possível guardar a cópia. Mantenha esta janela aberta.", True)

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
                               on_change=None if is_fixed_field(self.report, name) else self.bind(self.report, name),
                               read_only=is_fixed_field(self.report, name),
                               disabled=is_fixed_field(self.report, name), col=col,
                               multiline=multiline, min_lines=3 if multiline else 1,
                               max_lines=6 if multiline else 1, border_radius=9,
                               border_color="#D5DDD6", focused_border_color=GREEN,
                               text_size=14, hint_text=hint or ("Não informado no modelo" if is_fixed_field(self.report, name) else None),
                               filled=True, bgcolor="#F3F5F2" if is_fixed_field(self.report, name) else "white",
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
                           disabled=is_fixed_field(self.report, name),
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

    def holiday_selector(self) -> ft.Column:
        # Duas caixas, uma única resposta: marcar Sim desmarca Não e vice-versa.
        # A descrição é opcional e só aparece na impressão quando Sim está marcado.
        async def choose_yes(event):
            self.set_holidays(True)

        async def choose_no(event):
            self.set_holidays(False)

        self.holiday_yes = ft.Checkbox(label="Sim", value=self.report.holidays,
                                      on_change=choose_yes, active_color=GREEN)
        self.holiday_no = ft.Checkbox(label="Não", value=not self.report.holidays,
                                     on_change=choose_no, active_color=GREEN)
        self.holiday_description = self.field(
            "holiday_description", "Qual foi o feriado?",
            hint="Ex.: 12/10 — Nossa Senhora Aparecida")
        self.holiday_description.expand = True
        self.holiday_description.disabled = not self.report.holidays
        return ft.Column([
            ft.Text("Feriados na semana?", weight=ft.FontWeight.W_600, color=INK),
            ft.Row([self.holiday_yes, self.holiday_description], spacing=12),
            self.holiday_no,
            ft.Text("Ao marcar Sim, descreva o feriado ao lado. O texto aparece no PDF e no Excel.",
                    size=12, color=MUTED),
        ], spacing=4)

    def set_holidays(self, value: bool) -> None:
        self.report.holidays = value
        self.holiday_yes.value = value
        self.holiday_no.value = not value
        # Preservar a digitação caso Não seja marcado por engano. O exportador
        # omite essa descrição enquanto não houver feriado na semana.
        self.holiday_description.disabled = not value
        self.commit()

    def build_form(self) -> None:
        metadata = [ft.ResponsiveRow([
            self.field("tab_name", "Nome da aba", col={"xs": 12, "md": 4}),
            self.field("cliente", "Cliente", col={"xs": 12, "md": 8}),
            self.field("obra", "Obra / descrição do empreendimento"),
            self.field("address", "Endereço da obra"),
            self.field("responsavel_tecnico", "Responsável técnico"),
            self.date_field("start", "Data de início"), self.date_field("end", "Data de fim"),
            self.dropdown("morning", "Tempo • manhã", [(v, v) for v in WEATHER], col={"xs": 12, "md": 4}),
            self.dropdown("afternoon", "Tempo • tarde", [(v, v) for v in WEATHER], col={"xs": 12, "md": 4}),
            self.field("evolution", "Evolução da obra (%)", col={"xs": 12, "md": 4}),
        ], run_spacing=16), self.holiday_selector()]
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
        photos = [self.field("materials", "Chegada de materiais", multiline=True,
                             hint="Um material por linha. Ex.: 50 sacos de cimento • 30/09"),
                  ft.Text("Fotos ampliadas no relatório, com a atividade em verde entre duas linhas.",
                          color=GREEN, size=13), self.upload_button,
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
            self.section("01", "Identificação da obra",
                "Dados preenchidos automaticamente a partir do cadastro da obra."
                if self.report.project_profile else
                "Cadastro fixo por obra; endereços e cliente do Átrio podem ser preenchidos.",
                metadata, f"{self.report.id}-metadata"),
            self.section("02", "Mão de obra e equipamentos", "Adicione as equipes e confira os totais calculados.", resources, f"{self.report.id}-resources"),
            self.section("03", "Atividades diárias", "Registre os serviços realizados de segunda a sexta-feira.", activities, f"{self.report.id}-activities"),
            self.section("04", "Materiais e registro fotográfico",
                         "Adicione as fotos ao longo da semana; elas permanecem neste relatório.",
                         photos, f"{self.report.id}-photos"),
            self.section("05", "Responsabilidade e exportação", "Responsáveis, CREA, ART e alvará fixos conforme o modelo da obra.", footer, f"{self.report.id}-footer"),
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
        self.copy_button = ft.TextButton("Guardar como cópia", icon=ft.Icons.CONTENT_COPY,
                                         on_click=self.keep_copy, visible=False)
        self.status.expand = True
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
                             ft.Row([self.copy_button,
                                     ft.TextButton("Salvar Rascunho", icon=ft.Icons.SAVE_OUTLINED, on_click=save),
                                     self.excel_button, self.pdf_button], wrap=True,
                                    alignment=ft.MainAxisAlignment.END, col={"xs": 12, "lg": 7}),
                         ], spacing=0, run_spacing=8),
                         padding=ft.padding.symmetric(vertical=14, horizontal=8), bgcolor=BACKGROUND)]
        self.refresh_summary()
        self.refresh_day_labels()
        self.render_photos()
        self.refresh_cloud_status()

    def refresh_day_labels(self) -> None:
        try:
            dates = self.report.week_dates()
        except ValidationError:
            dates = [None] * 5
        for label, name, date in zip(self.daily_labels, DAYS, dates):
            label.value = f"{name} • {date:%d/%m}" if date else name

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
        # O navegador fornece streams que só podem ser lidos uma vez. Um seletor
        # novo por lote evita reutilizar streams/comandos antigos após erro ou retry.
        previous = self.image_picker
        self.image_picker = ft.FilePicker(on_result=self.on_photos_selected,
                                          on_upload=self.on_photo_uploaded)
        self.host_page.overlay[self.host_page.overlay.index(previous)] = self.image_picker
        self._photo_selection_handled = False
        self.set_importing(True)  # Também impede abrir dois seletores ao mesmo tempo.
        try:
            self.image_picker.pick_files(dialog_title="Fotos gerais da semana", allow_multiple=True,
                                         file_type=ft.FilePickerFileType.CUSTOM,
                                         allowed_extensions=["jpg", "jpeg", "png", "webp"])
        except Exception as exc:
            self._photo_selection_handled = True
            self.set_importing(False)
            self.toast(f"Não foi possível abrir o seletor de fotos: {exc}", True)

    def set_importing(self, value: bool) -> None:
        self.importing_photos = value
        self.upload_button.disabled = value
        self.refresh_cloud_status()
        self.host_page.update()

    async def on_photos_selected(self, event: ft.FilePickerResultEvent):
        # Eventos atrasados de seletores substituídos e resultados repetidos não
        # podem iniciar um segundo envio do mesmo stream.
        if getattr(event, "control", self.image_picker) is not self.image_picker:
            return
        if self._photo_selection_handled or self.pending_uploads:
            return
        self._photo_selection_handled = True
        if not event.files:
            self.set_importing(False)
            return
        day = None  # Fotografias gerais da semana, sem vínculo com um dia.
        self.set_importing(True)
        if self.host_page.web:
            try:
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
                    # Flet 0.28.3 remove cada arquivo da lista após enviar, mudando
                    # os índices dos demais. id=-1 força busca por nome único;
                    # usar file.id faz lotes com 3+ fotos enviarem o arquivo errado.
                    uploads.append(ft.FilePickerUploadFile(name=file.name, id=-1,
                        upload_url=self.host_page.get_upload_url(relative, 600)))
                if uploads:
                    self.status.value = "Importando fotos…"
                    self.host_page.update()
                    self.image_picker.upload(uploads)
                else:
                    self.set_importing(False)
            except Exception as exc:
                self.pending_uploads.clear()
                self.set_importing(False)
                self.toast(f"Não foi possível iniciar o envio: {exc}. Selecione as fotos novamente.", True)
            return
        try:
            for file in event.files:
                if file.path:
                    await self.import_photo(Path(file.path), file.name, day)
        finally:
            self.set_importing(False)
            self.render_photos()
            self.commit()

    async def import_photo(self, path: Path, name: str, day: int | None) -> None:
        try:
            photo = await asyncio.to_thread(self.repository.import_photo, path, self.report.id)
            photo.original_name = name
            self.report.add_photo(photo, day)
        except (ValidationError, OSError) as exc:
            self.toast(f"{name}: {exc}", True)

    async def on_photo_uploaded(self, event: ft.FilePickerUploadEvent):
        if getattr(event, "control", self.image_picker) is not self.image_picker:
            return
        pending = self.pending_uploads.get(event.file_name)
        if pending is None or event.file_name in self.finishing_uploads:
            return
        if event.error or event.progress == 1:
            path, day = pending
            self.finishing_uploads.add(event.file_name)
            try:
                # Conclusões podem chegar enquanto a imagem anterior está sendo
                # normalizada. Serializar preserva a ordem das fotos selecionadas.
                async with self._photo_import_lock:
                    if event.error:
                        message = ("O navegador interrompeu a leitura. Clique em Adicionar fotos "
                                   "e selecione este arquivo novamente."
                                   if "Stream has already been listened to" in event.error
                                   else f"{event.error}. Selecione este arquivo novamente.")
                        self.toast(f"Falha no envio de {event.file_name}: {message}", True)
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
        if not self.report.photos:
            self.photo_body.controls.append(ft.Container(ft.Column([
                ft.Icon(ft.Icons.ADD_A_PHOTO_OUTLINED, color="#899C8A", size=30),
                ft.Text("O registro da semana começa aqui", color=INK, weight=ft.FontWeight.W_500),
                ft.Text("Adicione fotos e escreva uma legenda para cada imagem.", color=MUTED, size=12),
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=10),
                alignment=ft.alignment.center, padding=30, bgcolor=BACKGROUND, border_radius=12))
        for i, photo in enumerate(self.report.photos):
            peers = self.report.photos
            group_index = i
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
                same_day = self.report.photos
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

            self.photo_body.controls.append(ft.Container(ft.Row([
                preview, ft.Column([ft.Text(f"{i + 1:02d}  {photo.original_name}", size=12, color=MUTED),
                    ft.TextField(label="Atividade da foto (título acima da imagem)", value=photo.caption, multiline=True,
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
        self.catalog = ProjectCatalog(repository)
        self.tabs = ft.Tabs(expand=True, selected_index=0, animation_duration=150,
                            indicator_color=GREEN, label_color=GREEN, unselected_label_color=MUTED,
                            divider_color="#DCE2DA", scrollable=True)
        self.views: dict[str, ObraTab] = {}
        self.connected = True
        self._status_task = None

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
        loading = ft.Column([ft.ProgressRing(), ft.Text("Carregando os relatórios e as fotos…")],
                            horizontal_alignment=ft.CrossAxisAlignment.CENTER)
        page.add(loading)
        try:
            reports = await asyncio.to_thread(self.repository.load_all)
        except (OSError, ValidationError) as exc:
            async def retry(event):
                page.controls.clear()
                await self.mount()
            loading.controls = [ft.Text(str(exc), color="#A33232"),
                                ft.FilledButton("Tentar novamente", on_click=retry)]
            page.update()
            return
        page.controls.remove(loading)
        # Nunca substituir rascunhos ilegíveis por novos documentos silenciosamente.
        if not reports and not list(self.repository.drafts.glob("*.json")):
            reports = self.repository.ensure_default_reports()
        for report in reports:
            self.add_tab(report)
        logo = base64.b64encode((ASSETS / "logo.png").read_bytes()).decode()
        page.add(ft.Column([
            ft.Row([ft.Image(src_base64=logo, width=126, height=56, fit=ft.ImageFit.CONTAIN),
                    ft.Container(width=4),
                    ft.Column([ft.Text("Relatórios de obra", size=27, weight=ft.FontWeight.W_600, color=INK),
                               ft.Text("A semana documentada. Cada obra no seu lugar.", size=13, color=MUTED)],
                               expand=True, spacing=3),
                    ], spacing=12),
            ft.Row([
                ft.FilledButton("Adicionar obra", icon=ft.Icons.ADD_BUSINESS,
                                on_click=self.add_project, style=ft.ButtonStyle(bgcolor=GREEN)),
                ft.OutlinedButton("Novo relatório", icon=ft.Icons.NOTE_ADD_OUTLINED,
                                  on_click=self.new_report),
            ], spacing=12, wrap=True),
            ft.Row([
                ft.TextButton("Backup e restauração", icon=ft.Icons.SAVE_ALT,
                              on_click=lambda e: page.launch_url("/backup", web_window_name="_blank")),
                ft.Text("Salvamento automático • aguarde Salvo no Firebase antes de fechar."
                        if self.repository.cloud_enabled else
                        "Render Free: dados temporários. Baixe o backup antes de sair.",
                        color=GREEN if self.repository.cloud_enabled else "#8A5B12", size=12,
                        visible=self.repository.cloud_enabled or
                                os.environ.get("RSO_STORAGE_MODE") == "ephemeral"),
            ], wrap=True, visible=bool(page.web)),
            self.tabs,
        ], expand=True, spacing=14))
        if self.repository.cloud_enabled:
            page.on_disconnect = self.disconnected
            page.on_close = self.disconnected
            page.on_connect = self.reconnected
            self._status_task = page.run_task(self.watch_sync)
        if self.repository.warnings:
            recovery_dialog = ft.AlertDialog(title=ft.Text("Recuperação de rascunhos"),
                content=ft.Text("\n".join(self.repository.warnings)),
                actions=[ft.TextButton("Fechar", on_click=lambda e: page.close(recovery_dialog))])
            page.open(recovery_dialog)

    async def disconnected(self, event):
        self.connected = False
        if self._status_task:
            self._status_task.cancel()

    async def reconnected(self, event):
        self.connected = True
        if self._status_task:
            self._status_task.cancel()
        self._status_task = self.page.run_task(self.watch_sync)

    async def watch_sync(self):
        while self.connected:
            await asyncio.sleep(1)
            changed = False
            for view in list(self.views.values()):
                before = (view.status.value, view.copy_button.visible)
                view.refresh_cloud_status()
                changed |= before != (view.status.value, view.copy_button.visible)
            if changed:
                self.page.update()

    def copied(self, report: Report):
        self.add_tab(report)
        self.tabs.selected_index = len(self.tabs.tabs) - 1
        self.page.update()

    def name_changed(self, report: Report):
        for tab in self.tabs.tabs:
            if tab.content.report.id == report.id:
                tab.text = report.tab_name or "Nova obra"

    def add_tab(self, report: Report):
        view = ObraTab(self.page, report, self.repository, self.name_changed, self.copied)
        self.views[report.id] = view
        self.tabs.tabs.append(ft.Tab(text=report.tab_name, content=view))

    async def new_report(self, event):
        try:
            choices = self.catalog.choices()
        except ValueError as exc:
            self.page.open(ft.SnackBar(ft.Text(str(exc))))
            return
        project = ft.Dropdown(label="Obra", value="sintra", width=420,
            options=[ft.dropdown.Option(key, name) for key, name in choices.items()])
        async def select_project(event):
            project.value = event.data
        project.on_change = select_project
        saving = False

        async def create(event):
            nonlocal saving
            if saving:
                return
            saving = True
            create_button.disabled = True
            self.page.update()
            try:
                report = await asyncio.to_thread(self.catalog.new_report, project.value)
            except (OSError, ValueError) as exc:
                project.error_text = f"Não foi possível salvar: {exc}"
                saving = False
                create_button.disabled = False
                self.page.update()
                return
            self.add_tab(report)
            self.tabs.selected_index = len(self.tabs.tabs) - 1
            self.page.close(dialog)
            self.page.update()

        create_button = ft.FilledButton("Criar relatório", on_click=create)
        dialog = ft.AlertDialog(title=ft.Text("Novo relatório semanal"),
            content=ft.Column([project, ft.Text("Os dados cadastrais são preenchidos automaticamente.")],
                              tight=True, spacing=16),
            actions=[ft.TextButton("Cancelar", on_click=lambda e: self.page.close(dialog)),
                     create_button])
        self.page.open(dialog)

    async def add_project(self, event):
        fields = {}

        def field(name, label, *, value="", optional=False, full=False):
            async def changed(event):
                # Manter o valor recebido e limpar a indicação de erro durante a correção.
                control.value = event.data
                if control.error_text:
                    control.error_text = None
                    control.update()

            control = ft.TextField(label=label if optional else f"{label} *", value=value,
                col=12 if full else {"xs": 12, "sm": 6}, border_radius=9,
                max_length=80 if name == "name" else 400,
                focused_border_color=GREEN, text_size=14,
                helper_text="Se vazio, será usado o nome da obra." if optional else None,
                on_change=changed)
            fields[name] = control
            return control

        message = ft.Text(color="#A33232", visible=False)
        saving = False

        async def save(event):
            nonlocal saving
            if saving:
                return
            missing = False
            for name, control in fields.items():
                empty = name != "obra" and not (control.value or "").strip()
                control.error_text = "Preencha este campo." if empty else None
                # Flet transforma None em "" ao limpar um erro já exibido.
                missing |= empty
            if missing:
                message.value, message.visible = "Preencha os campos obrigatórios (*).", True
                self.page.update()
                return
            values = {name: (control.value or "").strip() for name, control in fields.items()}
            values["obra"] = values["obra"] or values["name"].upper()
            saving = True
            save_button.disabled = cancel_button.disabled = True
            self.page.update()
            try:
                report = await asyncio.to_thread(self.catalog.register, ProjectProfile(**values))
            except (OSError, ValueError) as exc:
                saving = False
                save_button.disabled = cancel_button.disabled = False
                message.value, message.visible = str(exc), True
                self.page.update()
                return
            self.add_tab(report)
            self.tabs.selected_index = len(self.tabs.tabs) - 1
            self.page.close(dialog)
            self.views[report.id].toast("Obra cadastrada. O primeiro relatório está pronto para preencher.")
            self.page.update()

        save_button = ft.FilledButton("Cadastrar obra", icon=ft.Icons.CHECK, on_click=save)
        cancel_button = ft.TextButton("Cancelar", on_click=lambda e: self.page.close(dialog))
        dialog = ft.AlertDialog(modal=True, title=ft.Text("Adicionar obra"),
            content=ft.Container(width=640, height=min(580, max(220, (self.page.height or 900) - 240)),
                content=ft.Column([
                    ft.Text("Informe estes dados uma única vez. Eles serão usados no cabeçalho e no "
                            "rodapé de todos os relatórios desta obra.", size=14, color=MUTED),
                    ft.Text("Dados da obra", weight=ft.FontWeight.BOLD, color=GREEN),
                    ft.ResponsiveRow([
                        field("name", "Nome da obra", full=True),
                        field("obra", "Descrição do empreendimento", optional=True, full=True),
                        field("cliente", "Cliente", full=True),
                        field("address", "Endereço da obra", full=True),
                        field("responsavel_tecnico", "Responsável técnico",
                              value=COMMON["responsavel_tecnico"], full=True),
                    ], spacing=14, run_spacing=14),
                    ft.Text("Assinatura / rodapé", weight=ft.FontWeight.BOLD, color=GREEN),
                    ft.ResponsiveRow([
                        field("engineer", "Engenheiro responsável", value=COMMON["engineer"], full=True),
                        field("crea", "CREA", value=COMMON["crea"]),
                        field("art", "ART nº"),
                        field("permit", "Alvará"),
                    ], spacing=14, run_spacing=14),
                    ft.Text("Os dados da Santelmo e a identidade visual seguem o modelo do relatório.",
                            size=12, color=MUTED),
                ], spacing=16, scroll=ft.ScrollMode.AUTO)),
            actions=[ft.Column([message, ft.Row([cancel_button, save_button],
                alignment=ft.MainAxisAlignment.END, wrap=True)], tight=True)])
        self.page.open(dialog)
