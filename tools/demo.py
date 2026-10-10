"""Demonstração da regra diária; o agrupamento não comprova datas de captura das fotos."""

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rso.excel_generator import ExcelGenerator  # noqa: E402
from rso.layout import LayoutEngine  # noqa: E402
from rso.pdf_generator import PDFGenerator  # noqa: E402
from rso.storage import DraftRepository  # noqa: E402


def load_demo(repository: DraftRepository):
    report = DraftRepository.read(ROOT / "examples" / "casa_bosque.json")
    original = report.photos
    report.photos = []
    report.tab_name = "Demonstração Casa Bosque"
    report.notes = ("EXEMPLO DE AGRUPAMENTO DIÁRIO: dias atribuídos apenas para demonstração. "
                    "Há fotos repetidas para completar os pares. Não é um registro diário validado.")
    # O anexo tem oito fotos sem data individual confirmada. O exemplo usa 12 posições
    # (2, 4, 2, 2, 2), identificando as repetições, sem inventar evidência de captura.
    arrangement = [(0, 0), (0, 1), (1, 4), (1, 5), (1, 6), (1, 7),
                   (2, 6), (2, 7), (3, 2), (3, 3), (4, 0), (4, 1)]
    seen = set()
    for day, index in arrangement:
        photo = original[index]
        imported = repository.import_photo(ROOT / "examples" / photo.path, report.id)
        imported.caption = ("FOTO REPETIDA — SOMENTE DEMONSTRAÇÃO" if index in seen else photo.caption)
        imported.original_name = photo.original_name
        report.add_photo(imported, day)
        seen.add(index)
    repository.save(report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data-demo")
    parser.add_argument("--output", type=Path, default=ROOT / "examples" / "gerados")
    args = parser.parse_args()
    repository = DraftRepository(args.data_dir)
    report = load_demo(repository)
    layout = LayoutEngine(report, repository)
    plan = layout.build()
    args.output.mkdir(parents=True, exist_ok=True)
    for extension, generator in (("pdf", PDFGenerator(repository)), ("xlsx", ExcelGenerator(repository))):
        path = generator.generate(report, args.output / f"RSO-Demonstracao.{extension}", plan)
        print(f"Gerado: {path}")
    print(f"{len(plan)} páginas; {len(layout.overflow)} complementos.")
    print(f'Para abrir o exemplo na interface: python main.py --data-dir "{repository.root}"')


if __name__ == "__main__":
    main()

