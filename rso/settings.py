"""Medidas extraídas dos quatro PDFs fornecidos. Unidade: ponto (1/72 polegada)."""

from dataclasses import dataclass
from pathlib import Path

ASSETS = Path(__file__).resolve().parent.parent / "assets"
PAGE_WIDTH, PAGE_HEIGHT = 595.2, 841.8
COMPANY = (
    "SANTELMO ENGENHARIA LTDA",
    "CNPJ: 26.913.287/0001-34",
    "Rua Crescêncio Ferreira, nº 1726 - Bairro Morada do Sol - Teresina (PI)",
    "E-mail: santelmoengenharia@gmail.com",
    "Fone: (86) 3011-2104",
)
EMAIL = "santelmoengenharia@gmail.com"


@dataclass(frozen=True)
class Template:
    left: float
    right: float
    title_y: float
    title_h: float
    weather_y: float
    team_y: float
    team_row: float
    totals_y: float
    activity_y: float
    activity_row: float
    second_day_y: float
    materials_y: float
    photos_y: float
    footer_y: float
    font_size: float
    logo_rect: tuple[float, float, float, float]
    watermark_rect: tuple[float, float, float, float]

    @property
    def width(self) -> float:
        return self.right - self.left


# Para reposicionar o modelo, altere somente estas coordenadas. O Excel usa o mesmo mapa.
COMPACT = Template(39, 556.2, 162.225, 17.225, 247.25, 325.88, 13.6,
                   577.55, 642.15, 51.5, 60.9, 202.65, 318.27, 714,
                   9.4, (394.9, 90.204, 158.81, 68.546), (429.64, 78, 126.18, 161.91))
WIDE = Template(31.2, 571.6, 150.42, 18, 239.45, 321.67, 14.2,
                584.55, 652.145, 54, 68.5, 218.45, 339.68, 728,
                10, (403.24, 74.995, 165.9, 71.765), (439.58, 62.2, 131.65, 169.81))
SINTRA = Template(31.2, 571.6, 150.42, 18, 239.45, 321.67, 14.2,
                  584.55, 652.145, 54, 61.9, 211.85, 333.08, 728,
                  10, (403.24, 74.995, 165.9, 71.765), (439.58, 62.2, 131.65, 169.81))
TEMPLATES = {"compact": COMPACT, "wide": WIDE, "sintra": SINTRA}
PALETTES = {"gray": ("34383D", "FFFFFF"), "green": ("548235", "000000")}

