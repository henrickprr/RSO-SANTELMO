"""Fluxo contínuo do Excel: todas as seções em uma única aba de relatório."""

from dataclasses import replace

from .layout import LayoutEngine, PagePlan


class ExcelLayoutEngine(LayoutEngine):
    def build_sheet(self) -> PagePlan:
        page = PagePlan("RSO")
        self.header(page)
        self.weather(page)
        self.resources(page)
        # Os cinco dias ficam juntos; materiais e fotos seguem logo abaixo.
        self.days(page, range(5), self.t.activity_y, True)
        materials_y = self.t.activity_y + self.t.title_h + 5 * self.t.activity_row + 12
        materials_height = self.t.photos_y - self.t.materials_y
        self.t = replace(self.t, materials_y=materials_y,
                         photos_y=materials_y + materials_height)
        self.materials(page)
        self.band(page, self.t.photos_y, "RELATÓRIO FOTOGRÁFICO")
        y = self.t.photos_y + self.t.title_h + 10
        for title, photos in self.photo_rows():
            y = self.draw_photo_row(page, title, photos, y)

        # Textos excedentes continuam preservados, sem criar novas abas ou
        # repetir cabeçalhos/assinaturas a cada página física do PDF.
        if self.overflow:
            y += 8
            self.band(page, y, "COMPLEMENTO DO RSO")
            y += self.t.title_h + 10
        for number, (label, text) in enumerate(list(self.overflow), 1):
            self.box(page, self.t.left, y, self.t.width, 40, f"{number}. {label}", bold=True)
            y += 44
            lines = self.type.wrap(text, self.t.width - 8, 10)
            # Blocos curtos evitam os limites de altura e conteúdo das células
            # do Excel, mesmo em observações extensas.
            for offset in range(0, len(lines), 24):
                chunk = lines[offset:offset + 24]
                height = len(chunk) * 12 + 4
                self.box(page, self.t.left, y, self.t.width, height,
                         "\n".join(chunk), size=10)
                y += height
            y += 12

        self.t = replace(self.t, footer_y=y + 14)
        self.signature(page)
        self.fill_print_area(page, continuous=True)
        return page
