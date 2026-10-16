"""Mapa de páginas compartilhado por PDF e XLSX; nenhuma medida depende da UI.

Os retângulos usam coordenadas absolutas em pontos, origem no canto superior esquerdo.
Tabelas longas e textos extensos ganham complemento, nunca são descartados.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path

from fpdf import FPDF

from .models import DAY_SHORT, Report, ValidationError, parse_date, quantity
from .settings import (
    ASSETS, COMPANY, EMAIL, PAGE_HEIGHT, PAGE_WIDTH, PALETTES, PRINT_MARGIN, TEMPLATES,
)
from .storage import DraftRepository


def configure_fonts(pdf: FPDF) -> None:
    # Os subsets Tw Cen MT vieram dos próprios anexos. Noto Sans supre glifos ausentes.
    # Para usar a fonte completa licenciada, defina as duas variáveis abaixo.
    for style, name in (("", "Regular"), ("B", "Bold")):
        custom = os.environ.get(f"RSO_FONT_{name.upper()}")
        pdf.add_font("Modelo", style=style,
                     fname=custom or str(ASSETS / "fonts" / f"Template-{name}.ttf"))
        pdf.add_font("Fallback", style=style,
                     fname=str(ASSETS / "fonts" / f"NotoSans-{name}.ttf"))
    pdf.set_fallback_fonts(["Fallback"])


@dataclass
class Box:
    x: float
    y: float
    w: float
    h: float
    text: str = ""
    size: float = 9.4
    bold: bool = False
    align: str = "L"
    fill: str | None = None
    color: str = "000000"
    border: bool | str = True
    lines: list[str] = field(default_factory=list)
    numeric: int | float | None = None
    progress: float | None = None
    border_color: str = "737373"
    border_width: float = .45


@dataclass
class Picture:
    x: float
    y: float
    w: float
    h: float
    path: Path
    decorative: bool = False


@dataclass
class Checkbox:
    """Caixa gráfica de impressão; o estado vem do mesmo booleano da interface."""

    x: float
    y: float
    size: float
    checked: bool
    color: str = "548235"

    def tick_points(self) -> list[tuple[float, float]]:
        return [(self.x + x * self.size, self.y + y * self.size)
                for x, y in ((.20, .51), (.43, .75), (.81, .24))]


@dataclass
class PagePlan:
    title: str
    boxes: list[Box] = field(default_factory=list)
    pictures: list[Picture] = field(default_factory=list)
    checkboxes: list[Checkbox] = field(default_factory=list)


class Typography:
    def __init__(self):
        self.pdf = FPDF(unit="pt", format=(PAGE_WIDTH, PAGE_HEIGHT))
        configure_fonts(self.pdf)

    def wrap(self, text: str, width: float, size: float, bold: bool = False) -> list[str]:
        pdf = self.pdf
        pdf.set_font("Modelo", "B" if bold else "", size)
        # Falhar com mensagem útil é preferível a exportar caracteres silenciosamente vazios.
        supported = set(pdf.current_font.cmap) | set(pdf.fonts["fallback" + ("B" if bold else "")].cmap)
        missing = sorted({c for c in text if ord(c) not in supported and c not in "\n\r\t"})
        if missing:
            raise ValidationError(f"A fonte não contém estes caracteres: {''.join(missing)}. "
                                  "Substitua-os no texto ou configure uma fonte com esses glifos.")
        lines = []
        for paragraph in text.replace("\r", "").expandtabs(4).split("\n"):
            line = ""
            for word in paragraph.split():
                candidate = f"{line} {word}" if line else word
                if pdf.get_string_width(candidate) <= width:
                    line = candidate
                    continue
                if line:
                    lines.append(line)
                line = ""
                # Também quebrar palavras/URLs sem espaços, evitando estouro horizontal.
                for character in word:
                    if line and pdf.get_string_width(line + character) > width:
                        lines.append(line)
                        line = ""
                    line += character
            lines.append(line)
        return lines or [""]


class LayoutEngine:
    def __init__(self, report: Report, repository: DraftRepository):
        report.validate()
        self.report = report
        self.repository = repository
        self.t = TEMPLATES[report.template]
        self.fill, self.foreground = PALETTES[report.theme]
        self.type = Typography()
        self.overflow: list[tuple[str, str]] = []

    def add_overflow(self, label: str, text: str) -> int:
        entry = (label, text)
        if entry not in self.overflow:
            self.overflow.append(entry)
        return self.overflow.index(entry) + 1

    def box(self, page: PagePlan, x: float, y: float, w: float, h: float,
            text: str = "", *, label: str = "Informação", size: float | None = None,
            bold: bool = False, align: str = "L", fill: str | None = None,
            color: str = "000000", border: bool | str = True,
            numeric: int | float | None = None,
            border_color: str = "737373", border_width: float = .45) -> Box:
        font_size = size or self.t.font_size
        # Área interna de 3 pt em cada lateral. Reduzir só até 8 pt para legibilidade.
        while True:
            lines = self.type.wrap(str(text), w - 6, font_size, bold)
            if len(lines) * font_size * 1.2 <= h - 2:
                break
            if font_size <= 8:
                number = self.add_overflow(label, str(text))
                text = f"Ver complemento {number}"
                lines = self.type.wrap(text, w - 6, 8, bold)
                if len(lines) * 9.6 > h - 2:
                    text = f"[{number}]"
                    lines = [text]
                font_size = 8
                numeric = None
                break
            font_size = max(8, font_size - 0.25)
        item = Box(x, y, w, h, str(text), font_size, bold, align, fill, color, border,
                   lines, numeric, border_color=border_color, border_width=border_width)
        page.boxes.append(item)
        return item

    def band(self, page: PagePlan, y: float, text: str, *, x: float | None = None,
             w: float | None = None, h: float | None = None) -> None:
        self.box(page, self.t.left if x is None else x, y, w or self.t.width,
                 h or self.t.title_h, text, bold=True, align="C", fill=self.fill,
                 color=self.foreground, size=self.t.font_size + 1, label=text)

    def header(self, page: PagePlan) -> None:
        t, r = self.t, self.report
        page.pictures.extend([
            Picture(*t.watermark_rect, ASSETS / "watermark.png", True),
            Picture(*t.logo_rect, ASSETS / "logo.png", True),
        ])
        start = 89 if r.template == "compact" else 74
        for i, line in enumerate(COMPANY):
            self.box(page, t.left + 20, start + i * 13.6, 328, 13.6, line,
                     size=t.font_size + 0.5, bold=i == 0, color="009900" if i == 0 else "000000",
                     border=False, label="Cabeçalho da empresa")
        self.band(page, t.title_y, "RELATÓRIO SEMANAL DE OBRA (RSO)")
        pairs = [("OBRA:", r.obra + (" — " + r.address if r.address else "")), ("CLIENTE:", r.cliente),
                 ("RESPONS. TÉCNICO:", r.responsavel_tecnico),
                 ("REFERÊNCIA:", f"DE {r.start} A {r.end}")]
        for i, (label, value) in enumerate(pairs):
            y = t.title_y + t.title_h + 6 + i * t.team_row
            lw = 87 if i == 2 else (62 if i == 3 else 46)
            self.box(page, t.left, y, lw, t.team_row, label, bold=True, border=False)
            self.box(page, t.left + lw, y, 390 - lw, t.team_row, value,
                     border=False, label=label)

    def weather(self, page: PagePlan) -> None:
        t, r = self.t, self.report
        widths = (t.width * .272, t.width * .412, t.width * .316)
        x, y = t.left, t.weather_y
        for text, width in zip(("TEMPO PREDOMINANTE", "FERIADOS NA SEMANA?", "EVOLUÇÃO DA OBRA"), widths):
            self.band(page, y, text, x=x, w=width, h=t.team_row)
            x += width
        y += t.team_row + 6
        for i, (label, value) in enumerate((("MANHÃ", r.morning), ("TARDE", r.afternoon))):
            self.box(page, t.left, y + i * 24, 58, 24, label, align="C")
            has_icon = value in ("Ensolarado", "Parcialmente nublado")
            self.box(page, t.left + 58, y + i * 24, widths[0] - 58, 24,
                     "" if has_icon else value, align="C", size=8, label=f"Tempo: {label}")
            if has_icon:
                icon = "sun.png" if value == "Ensolarado" else "sun-cloud.png"
                page.pictures.append(Picture(t.left + 58 + (widths[0] - 80) / 2,
                                             y + i * 24 + 1, 22, 22, ASSETS / icon, True))
        for i, (label, checked) in enumerate((("Sim", r.holidays), ("Não", not r.holidays))):
            self.box(page, t.left + widths[0], y + i * 24, widths[1], 24,
                     label, bold=True)
            # Caixa de 12 pt, alinhada às duas opções. Não depende de glifos da fonte.
            page.checkboxes.append(Checkbox(t.left + widths[0] + 42,
                                            y + i * 24 + 6, 12, checked))
        progress = self.box(page, t.left + widths[0] + widths[1], y + 13, widths[2], 22,
                            f"{r.progress:g}%", bold=True, align="C", label="Evolução")
        progress.progress = r.progress

    def resources(self, page: PagePlan) -> None:
        t, r = self.t, self.report
        # Três blocos paralelos. Mude estas proporções para alterar as larguras de coluna.
        widths = (t.width * .325, t.width * .359, t.width * .316)
        groups = (("FUNCIONÁRIOS DA SANTELMO", "FUNÇÃO / CARGO", r.employees),
                  ("EQUIPE DE TERCEIROS", "EMPRESA / FUNÇÃO", r.contractors),
                  ("EQUIPAMENTOS", "DESCRIÇÃO", r.equipment))
        x = t.left
        for (title, label, rows), width in zip(groups, widths):
            self.band(page, t.team_y, title, x=x, w=width, h=t.team_row)
            quantity_width = 38
            y = t.team_y + t.team_row
            self.box(page, x, y, width - quantity_width, t.team_row, label,
                     align="C", fill="E7E6E6", size=9)
            self.box(page, x + width - quantity_width, y, quantity_width, t.team_row,
                     "QTDE", align="C", fill="E7E6E6", size=9)
            y += t.team_row
            limit = 14
            displayed = rows[:limit]
            for i in range(max(12, len(displayed))):
                row = displayed[i] if i < len(displayed) else None
                text = row.description if row else ""
                if row and row.company:
                    text = f"{row.company} / {text}"
                self.box(page, x, y, width - quantity_width, t.team_row, text,
                         label=f"{title}: linha {i + 1}")
                number = quantity(row.quantity) if row else None
                self.box(page, x + width - quantity_width, y, quantity_width, t.team_row,
                         str(number) if number is not None else "", align="C", numeric=number)
                y += t.team_row
            total = sum(quantity(row.quantity) for row in rows)
            self.box(page, x, y, width - quantity_width, t.team_row, "TOTAL", bold=True)
            self.box(page, x + width - quantity_width, y, quantity_width, t.team_row,
                     str(total), bold=True, align="C", numeric=total)
            if len(rows) > limit:
                extra = "\n".join(f"{row.company + ' / ' if row.company else ''}"
                                  f"{row.description}: {quantity(row.quantity)}" for row in rows[limit:])
                number = self.add_overflow(f"{title} — linhas {limit + 1} em diante (já incluídas no total)", extra)
                self.box(page, x, y + t.team_row, width, 13,
                         f"Demais linhas: complemento {number}", size=8, border=False)
            x += width
        employees, contractors, equipment = r.totals()
        self.band(page, t.totals_y, f"TOTAL DE FUNCIONÁRIOS: {employees + contractors}",
                  w=sum(widths[:2]) - 7, h=t.team_row)
        self.band(page, t.totals_y, f"TOTAL DE EQUIPAMENTOS: {equipment}",
                  x=t.left + sum(widths[:2]), w=widths[2], h=t.team_row)
        self.box(page, t.left, t.totals_y + 25, t.width, 33,
                 "OBSERVAÇÕES: " + r.notes, label="Observações", border=True)

    def days(self, page: PagePlan, indices: range, y: float, with_header: bool) -> None:
        t, r = self.t, self.report
        day_w = t.width * .216
        if with_header:
            self.band(page, y, "DIA", w=day_w)
            self.band(page, y, "SERVIÇOS EXECUTADOS", x=t.left + day_w, w=t.width - day_w)
            y += t.title_h
        start, end = parse_date(r.start), parse_date(r.end)
        row_height = (t.materials_y - t.second_day_y) / 3 if not with_header else t.activity_row
        for i in indices:
            date = r.week_dates()[i]
            text = r.activities[i]
            if not start <= date <= end:
                text = "Fora do período informado."
            self.box(page, t.left, y, day_w * .42, row_height,
                     f"{date:%d}", fill="92D050", align="C", size=12)
            self.box(page, t.left + day_w * .42, y, day_w * .58, row_height,
                     DAY_SHORT[i], fill="A9D18E", align="C", size=11)
            self.box(page, t.left + day_w, y, t.width - day_w, row_height,
                     text, label=f"Serviços de {DAY_SHORT[i]} — {date:%d/%m/%Y}")
            y += row_height

    def materials(self, page: PagePlan) -> None:
        t = self.t
        self.band(page, t.materials_y, "CHEGADA DE MATERIAIS")
        lines = self.report.materials.splitlines()
        # As cinco linhas numeradas são as mesmas do modelo físico.
        row_h = (t.photos_y - t.materials_y - t.title_h - 8) / 5
        for i in range(5):
            y = t.materials_y + t.title_h + i * row_h
            self.box(page, t.left, y, 18, row_h, f"{i + 1})", align="C")
            self.box(page, t.left + 18, y, t.width - 18, row_h,
                     lines[i] if i < len(lines) else "", label=f"Material {i + 1}")
        if len(lines) > 5:
            self.add_overflow("Chegada de materiais — itens 6 em diante", "\n".join(lines[5:]))

    def signature(self, page: PagePlan) -> None:
        t, r = self.t, self.report
        self.box(page, t.left, t.footer_y, t.width, 18,
                 f"ENGENHEIRO RESPONSÁVEL: {r.engineer} | CREA: {r.crea}",
                 align="C", border=False, label="Assinatura")
        for i, text in enumerate((f"ART Nº: {r.art}", f"ALVARÁ: {r.permit}",
                                  "EMPRESA: SANTELMO ENGENHARIA")):
            self.box(page, t.left, t.footer_y + 18 + i * 13, t.width - 128, 13,
                     text, border=False, label="Rodapé")
        page.pictures.append(Picture(t.right - 118, t.footer_y + 18, 108, 43,
                                     ASSETS / "logo.png", True))
        self.box(page, t.left, t.footer_y + 65, t.width, 14, EMAIL,
                 align="C", fill=self.fill, color="FFFFFF", size=t.font_size + 1)

    def photo_pages(self, second: PagePlan) -> list[PagePlan]:
        t, r = self.t, self.report
        pages = [second]
        current = second
        self.band(current, t.photos_y, "RELATÓRIO FOTOGRÁFICO")
        y = t.photos_y + t.title_h + 10
        columns = r.photo_columns
        # Medidas em pontos (72 pt = 1 polegada). Ajuste estes valores para mudar
        # o tamanho das fotos; a paginação considera também título e assinatura.
        gap, title_gap, row_gap = 8, 6, 14
        photo_w = (t.width - (columns - 1) * gap) / columns
        image_h = 210 if columns == 2 else 300
        # Agrupar fotos consecutivas da mesma atividade. O título vem ACIMA
        # de uma ou duas imagens, como nos anexos, sem rótulo de dia/data.
        groups = []
        for photo in r.photos:
            title = photo.caption.strip() or "REGISTRO DA SEMANA"
            if groups and groups[-1][0] == title:
                groups[-1][1].append(photo)
            else:
                groups.append((title, [photo]))
        for title, group in groups:
            for offset in range(0, len(group), columns):
                caption_h = min(70, max(28, len(self.type.wrap(title, t.width - 8, 10, True)) * 12 + 10))
                if y + caption_h + title_gap + image_h > t.footer_y - 10:
                    current = PagePlan("Fotos")
                    pages.append(current)
                    self.band(current, 38, "RELATÓRIO FOTOGRÁFICO")
                    y = 66
                self.box(current, t.left, y, t.width, caption_h, title,
                         bold=True, align="C", color="548235", size=10, border="TB",
                         border_color="385723", border_width=1.6,
                         label="Atividade do registro fotográfico")
                for col, photo in enumerate(group[offset:offset + columns]):
                    x = t.left + col * (photo_w + gap)
                    current.pictures.append(Picture(x, y + caption_h + title_gap, photo_w, image_h,
                                                   self.repository.resolve_photo(photo)))
                y += caption_h + title_gap + image_h + row_gap
        for page in pages:
            self.signature(page)
        return pages

    def appendices(self) -> list[PagePlan]:
        pages = []
        t = self.t
        pending = list(self.overflow)
        # Layout fluido apenas no complemento; as páginas-base conservam as medidas.
        for number, (label, text) in enumerate(pending, 1):
            lines = self.type.wrap(text, t.width - 8, 10)
            while lines:
                page = PagePlan("Complemento")
                pages.append(page)
                self.band(page, 38, "COMPLEMENTO DO RSO")
                self.box(page, t.left, 64, t.width, 40, f"{number}. {label}", bold=True)
                capacity = int((t.footer_y - 120) / 12)
                chunk, lines = lines[:capacity], lines[capacity:]
                self.box(page, t.left, 108, t.width, len(chunk) * 12 + 4,
                         "\n".join(chunk), size=10)
                self.signature(page)
        return pages

    def fill_print_area(self, page: PagePlan) -> None:
        """Ampliar o conteúdo para as quatro margens, sem mudar o papel A4.

        A paginação ainda usa as coordenadas medidas dos modelos. Só depois
        todos os retângulos recebem a mesma transformação, preservando os
        alinhamentos, as distâncias relativas e a separação da assinatura.
        Os geradores contêm as imagens nesses retângulos sem distorcer a foto.
        """
        items = [*page.boxes, *page.pictures]
        top = min(item.y for item in items)
        bottom = max(item.y + item.h for item in items)
        scale_x = (PAGE_WIDTH - 2 * PRINT_MARGIN) / self.t.width
        scale_y = (PAGE_HEIGHT - 2 * PRINT_MARGIN) / (bottom - top)
        # A fonte cresce proporcionalmente, nunca esticada em apenas um eixo.
        font_scale = min(scale_x, scale_y)
        for item in items:
            item.x = PRINT_MARGIN + (item.x - self.t.left) * scale_x
            item.y = PRINT_MARGIN + (item.y - top) * scale_y
            item.w *= scale_x
            item.h *= scale_y
        for box in page.boxes:
            box.size *= font_scale
        for checkbox in page.checkboxes:
            # Manter caixinhas quadradas de 12 pt, centradas na linha ampliada.
            center_x = PRINT_MARGIN + (checkbox.x + checkbox.size / 2 - self.t.left) * scale_x
            center_y = PRINT_MARGIN + (checkbox.y + checkbox.size / 2 - top) * scale_y
            checkbox.x = center_x - checkbox.size / 2
            checkbox.y = center_y - checkbox.size / 2

    def build(self) -> list[PagePlan]:
        first, second = PagePlan("RSO"), PagePlan("RSO e fotos")
        self.header(first)
        self.weather(first)
        self.resources(first)
        self.days(first, range(2), self.t.activity_y, True)
        self.days(second, range(2, 5), self.t.second_day_y, False)
        self.materials(second)
        photo_pages = self.photo_pages(second)
        extra = self.appendices()
        # Complementos são identificados; fotos de continuação ficam nas páginas finais.
        pages = [first, photo_pages[0], *extra, *photo_pages[1:]]
        for page in pages:
            self.fill_print_area(page)
        return pages

