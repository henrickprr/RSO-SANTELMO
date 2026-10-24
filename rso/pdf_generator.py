"""Exportação vetorial em fpdf2. Não depende de Excel, Word ou impressora PDF."""

from pathlib import Path

from fpdf import FPDF
from PIL import Image

from .layout import LayoutEngine, PagePlan, configure_fonts
from .models import Report
from .settings import PAGE_HEIGHT, PAGE_WIDTH
from .storage import DraftRepository, atomic_write


def rgb(hex_color: str) -> tuple[int, int, int]:
    return tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))


class PDFGenerator:
    def __init__(self, repository: DraftRepository):
        self.repository = repository

    def generate(self, report: Report, destination: str | Path,
                 plan: list[PagePlan] | None = None) -> Path:
        self.repository.apply_registration(report)
        report.validate()
        pages = plan if plan is not None else LayoutEngine(report, self.repository).build()
        pdf = FPDF(unit="pt", format=(PAGE_WIDTH, PAGE_HEIGHT))
        pdf.set_auto_page_break(False)
        # As margens de impressão já estão nas coordenadas do layout compartilhado.
        pdf.set_margins(0, 0, 0)
        pdf.set_title(f"RSO — {report.tab_name} — {report.start} a {report.end}")
        pdf.set_author("Santelmo Engenharia Ltda")
        configure_fonts(pdf)
        for page in pages:
            pdf.add_page()
            # Logotipo e marca d'água vêm primeiro para não encobrir o texto.
            for picture in page.pictures:
                with Image.open(picture.path) as img:
                    pdf.image(img, x=picture.x, y=picture.y, w=picture.w, h=picture.h,
                              keep_aspect_ratio=True)
            for box in page.boxes:
                pdf.set_draw_color(*rgb(box.border_color))
                pdf.set_line_width(box.border_width)
                pdf.set_fill_color(*rgb(box.fill or "FFFFFF"))
                pdf.set_text_color(*rgb(box.color))
                pdf.set_font("Modelo", "B" if box.bold else "", box.size)
                pdf.set_xy(box.x, box.y)
                # GRID: a célula exterior define as bordas. As larguras e posições estão
                # em settings.py/layout.py; True desenha quatro arestas, "TB" somente
                # superior/inferior. Cor e espessura são reutilizadas no Excel.
                border = box.border if isinstance(box.border, str) else int(box.border)
                pdf.cell(box.w, box.h, "", border=border,
                         fill=bool(box.fill))
                if box.progress is not None and box.progress > 0:
                    pdf.set_fill_color(84, 130, 53)
                    pdf.rect(box.x + 1, box.y + 1, (box.w - 2) * box.progress / 100,
                             box.h - 2, style="F")
                leading = box.size * 1.2
                y = box.y + (box.h - len(box.lines) * leading) / 2
                for line in box.lines:
                    pdf.set_xy(box.x + 3, y)
                    pdf.cell(box.w - 6, leading, line, align=box.align)
                    y += leading
            # Checkboxes vetoriais: quadrado + marca de seleção, nítidos na impressão.
            for checkbox in page.checkboxes:
                pdf.set_draw_color(*rgb(checkbox.color))
                pdf.set_fill_color(255, 255, 255)
                pdf.set_line_width(1.1)
                pdf.rect(checkbox.x, checkbox.y, checkbox.size, checkbox.size, style="DF")
                if checkbox.checked:
                    pdf.set_line_width(1.8)
                    points = checkbox.tick_points()
                    for start, end in zip(points, points[1:]):
                        pdf.line(*start, *end)
        path = Path(destination)
        atomic_write(path, bytes(pdf.output()))
        return path

