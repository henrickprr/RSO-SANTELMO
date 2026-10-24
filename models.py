"""Modelos independentes da interface. Rascunhos preservam até inputs incompletos."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from uuid import UUID, uuid4

from .projects import FIXED_FIELDS, ProjectProfile, apply_project

DAYS = ("Segunda-feira", "Terça-feira", "Quarta-feira", "Quinta-feira", "Sexta-feira")
DAY_SHORT = ("SEG", "TER", "QUA", "QUI", "SEX")
WEATHER = ("Ensolarado", "Parcialmente nublado", "Nublado", "Chuvoso", "Não informado")
ROLES = (
    "ENG. CIVIL", "ENG. ELETRICISTA", "ESTAGIÁRIO", "MESTRE DE OBRAS", "PEDREIRO",
    "ELETRICISTA", "SERVENTE", "CARPINTEIRO", "FERREIRO", "BOMBEIRO HIDRÁULICO", "PINTOR",
)


class ValidationError(ValueError):
    """Erro corrigível no formulário, exibido antes da exportação."""


def quantity(value: str) -> int:
    value = str(value).strip() or "0"
    if not value.isascii() or not value.isdigit() or len(value) > 6:
        raise ValidationError("As quantidades devem ser números inteiros de 0 a 999999.")
    return int(value)


def parse_date(value: str) -> date:
    try:
        return datetime.strptime(value.strip(), "%d/%m/%Y").date()
    except ValueError as exc:
        raise ValidationError("Informe as datas no formato DD/MM/AAAA.") from exc


@dataclass
class ResourceRow:
    description: str = ""
    quantity: str = "0"
    company: str = ""
    id: str = field(default_factory=lambda: uuid4().hex)


@dataclass
class Photo:
    path: str
    caption: str = ""
    original_name: str = ""
    id: str = field(default_factory=lambda: uuid4().hex)
    # Campo legado dos JSONs antigos. Fotos atuais são gerais da semana; dia não é exibido.
    day: int | None = None


@dataclass
class Report:
    id: str = field(default_factory=lambda: uuid4().hex)
    project_key: str = ""
    project_profile: ProjectProfile | None = None
    # Correções incompletas são salvas sem substituir o cadastro confirmado.
    registration_draft: dict[str, str] | None = None
    registration_base: str = ""
    address: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    tab_name: str = "Nova obra"
    obra: str = ""
    cliente: str = ""
    responsavel_tecnico: str = ""
    start: str = ""
    end: str = ""
    morning: str = "Não informado"
    afternoon: str = "Não informado"
    holidays: bool = False
    holiday_description: str = ""
    evolution: str = "0"
    employees: list[ResourceRow] = field(
        default_factory=lambda: [ResourceRow(description=role) for role in ROLES]
    )
    contractors: list[ResourceRow] = field(default_factory=list)
    equipment: list[ResourceRow] = field(default_factory=list)
    activities: list[str] = field(default_factory=lambda: [""] * 5)
    materials: str = ""
    notes: str = ""
    photos: list[Photo] = field(default_factory=list)
    engineer: str = ""
    crea: str = ""
    art: str = ""
    permit: str = ""
    template: str = "compact"
    theme: str = "green"
    photo_columns: int = 2

    @classmethod
    def new(cls, name: str, template: str = "compact", *,
            profile: ProjectProfile | None = None) -> Report:
        monday = date.today() - timedelta(days=date.today().weekday())
        report = cls(
            tab_name=profile.name if profile else name, project_profile=profile,
            obra=f"EXECUÇÃO DE EDIFICAÇÃO RESIDENCIAL UNIFAMILIAR - {name.upper()}",
            start=monday.strftime("%d/%m/%Y"),
            end=(monday + timedelta(days=4)).strftime("%d/%m/%Y"), template=template,
        )
        apply_project(report)
        return report

    @property
    def progress(self) -> float:
        try:
            value = Decimal(self.evolution.strip().replace(",", "."))
            if not value.is_finite() or not 0 <= value <= 100:
                raise InvalidOperation
            return float(value)
        except (InvalidOperation, ValueError) as exc:
            raise ValidationError("A evolução da obra deve estar entre 0 e 100%.") from exc

    def totals(self) -> tuple[int, int, int]:
        return tuple(sum(quantity(r.quantity) for r in rows) for rows in
                     (self.employees, self.contractors, self.equipment))

    def week_dates(self) -> list[date]:
        start = parse_date(self.start)
        monday = start - timedelta(days=start.weekday())
        return [monday + timedelta(days=i) for i in range(5)]

    def active_days(self) -> list[int]:
        start, end = parse_date(self.start), parse_date(self.end)
        return [i for i, day in enumerate(self.week_dates()) if start <= day <= end]

    def add_photo(self, photo: Photo, day: int | None = None) -> None:
        if any(p.id == photo.id for p in self.photos):
            raise ValidationError("Esta foto já foi adicionada ao relatório.")
        # 'day' só é preservado para compatibilidade de JSONs antigos, sem efeito no relatório.
        photo.day = day
        self.photos.append(photo)

    def validate_photos(self) -> None:
        if len({p.id for p in self.photos}) != len(self.photos):
            raise ValidationError("Há identificadores de fotos duplicados no relatório.")

    def validate(self) -> None:
        if self.registration_draft is not None:
            raise ValidationError("Marque Fixar Informações para confirmar o cadastro antes de exportar.")
        apply_project(self)
        if not self.obra.strip():
            raise ValidationError("Preencha o nome da obra.")
        start, end = parse_date(self.start), parse_date(self.end)
        if end < start:
            raise ValidationError("A data final deve ser igual ou posterior à inicial.")
        if start.isocalendar()[:2] != end.isocalendar()[:2]:
            raise ValidationError("Um RSO deve abranger uma única semana, de segunda a domingo.")
        for day, text in zip(self.week_dates(), self.activities):
            if text.strip() and not start <= day <= end:
                raise ValidationError(f"Há atividades em {day:%d/%m}, fora do período informado.")
        self.progress
        self.totals()
        if self.morning not in WEATHER or self.afternoon not in WEATHER:
            raise ValidationError("Selecione uma condição de tempo válida.")
        for label, rows in (("Funcionários", self.employees), ("Terceiros", self.contractors),
                            ("Equipamentos", self.equipment)):
            for i, row in enumerate(rows, 1):
                if quantity(row.quantity) and not row.description.strip():
                    raise ValidationError(f"{label}, linha {i}: preencha a descrição/função.")
                if label == "Terceiros" and quantity(row.quantity) and not row.company.strip():
                    raise ValidationError(f"Terceiros, linha {i}: preencha o nome da empresa.")
        self.validate_photos()

    def to_dict(self) -> dict:
        apply_project(self)
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> Report:
        if not isinstance(data, dict):
            raise ValidationError("Rascunho inválido: objeto esperado.")
        allowed = {f.name for f in fields(cls)}
        values = {k: v for k, v in data.items() if k in allowed}
        if values.get("project_profile") is not None:
            values["project_profile"] = ProjectProfile.from_dict(values["project_profile"])
        for key in ("employees", "contractors", "equipment"):
            if key in values:
                values[key] = [ResourceRow(**r) for r in values[key]]
        if "photos" in values:
            values["photos"] = [Photo(**p) for p in values["photos"]]
        report = cls(**values)
        if not isinstance(report.id, str):
            raise ValidationError("Identificador inválido no rascunho.")
        UUID(report.id)
        for f in fields(cls):
            value = getattr(report, f.name)
            if f.name not in {"employees", "contractors", "equipment", "activities", "photos",
                              "holidays", "photo_columns", "project_profile", "registration_draft"} and not isinstance(value, str):
                raise ValidationError(f"Rascunho inválido: campo {f.name}.")
        if report.registration_draft is not None:
            draft = report.registration_draft
            if (not isinstance(draft, dict) or set(draft) != FIXED_FIELDS - {"template"}
                    or not all(isinstance(v, str) and len(v) <= 400 for v in draft.values())):
                raise ValidationError("Rascunho do cadastro inválido.")
        if not isinstance(report.activities, list) or len(report.activities) != 5:
            raise ValidationError("O rascunho deve conter cinco atividades diárias.")
        if not all(isinstance(t, str) for t in report.activities):
            raise ValidationError("Atividades inválidas no rascunho.")
        if (type(report.holidays) is not bool or type(report.photo_columns) is not int
                or report.photo_columns not in (1, 2)):
            raise ValidationError("Configuração inválida no rascunho.")
        if report.template not in ("compact", "wide", "sintra") or report.theme not in ("gray", "green"):
            raise ValidationError("Modelo ou tema inválido no rascunho.")
        for row in report.employees + report.contractors + report.equipment:
            if not all(isinstance(getattr(row, f.name), str) for f in fields(ResourceRow)):
                raise ValidationError("Linha inválida no rascunho.")
        for photo in report.photos:
            if not all(isinstance(getattr(photo, f.name), str) for f in fields(Photo) if f.name != "day"):
                raise ValidationError("Foto inválida no rascunho.")
            if photo.day is not None and (type(photo.day) is not int or photo.day not in range(5)):
                raise ValidationError("Dia da foto inválido no rascunho.")
        apply_project(report)
        return report

