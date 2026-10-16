"""Demonstração com as oito fotos gerais da semana do modelo Casa Bosque."""

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
    report.notes = "DEMONSTRAÇÃO: dados e fotos gerais da semana transcritos do PDF Casa Bosque."
    for photo in original:
        imported = repository.import_photo(ROOT / "examples" / photo.path, report.id)
        imported.caption = photo.caption
        imported.original_name = photo.original_name
        report.add_photo(imported)
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
    print(f"{len(plan)} páginas PDF; uma aba contínua no XLSX; {len(layout.overflow)} complementos.")
    print(f'Para abrir o exemplo na interface: python main.py --data-dir "{repository.root}"')


if __name__ == "__main__":
    main()

