"""Cadastros dos modelos e das obras adicionadas pela interface.

Os quatro cadastros iniciais foram transcritos dos PDFs. Endereços das obras
não constam nos anexos; o endereço do cabeçalho pertence à Santelmo.
O PDF Átrio contém 'Casa Bella Vista' por engano e deixa o cliente em branco.
Não copiar o cliente ou os números de outra obra para preencher essas lacunas.
"""

from dataclasses import dataclass, field, fields
import unicodedata
from uuid import UUID, uuid4


def normalized_name(name: str) -> str:
    return " ".join(unicodedata.normalize("NFKD", name).encode("ascii", "ignore")
                    .decode().casefold().split())


@dataclass(frozen=True)
class ProjectProfile:
    """Cadastro imutável, incluído em cada semana para sobreviver a backup/nuvem.

    O identificador pertence à obra; Report.id pertence somente àquela semana.
    Não armazenamos o cadastro apenas no disco temporário do Render.
    """

    name: str
    obra: str
    address: str
    cliente: str
    responsavel_tecnico: str
    engineer: str
    crea: str
    art: str
    permit: str
    template: str = "compact"
    key: str = field(default_factory=lambda: "custom_" + uuid4().hex)

    def __post_init__(self):
        for item in fields(self):
            value = getattr(self, item.name)
            if (not isinstance(value, str) or len(value) > 400
                    or (not value.strip() and item.name not in {"address", "cliente"})):
                raise ValueError(f"Preencha um valor válido para {item.name} (até 400 caracteres).")
            object.__setattr__(self, item.name, value.strip())
        if len(self.name) > 80 or not normalized_name(self.name):
            raise ValueError("Informe um nome de obra com até 80 caracteres.")
        if self.key not in PROJECTS and (not self.key.startswith("custom_")
                                        or UUID(self.key[7:]).hex != self.key[7:]):
            raise ValueError("Identificador inválido no cadastro da obra.")
        if self.template not in ("compact", "wide", "sintra"):
            raise ValueError("Modelo inválido no cadastro da obra.")

    @classmethod
    def from_dict(cls, value):
        if not isinstance(value, dict):
            raise ValueError("Cadastro de obra inválido no rascunho.")
        return cls(**value)

COMMON = {
    "responsavel_tecnico": "ENGº DANILO JOSÉ FONSECA LIMA",
    "engineer": "DANILO FONSECA",
    "crea": "1915794803",
}

PROJECTS = {
    "bella_vista": {"name": "Casa Bella Vista", "cliente": "FRANCISCO E JAMILLE",
                   "art": "CE20251725141", "permit": "227/2025", "template": "wide", "address": ""},
    "bosque": {"name": "Casa Bosque", "cliente": "DANILO FONSECA",
               "art": "CE20261946083", "permit": "216/2026", "template": "compact", "address": ""},
    "sintra": {"name": "Casa Sintra", "cliente": "JUDSON E LAURA",
               "art": "CE20251740545", "permit": "245/2025", "template": "sintra", "address": ""},
    "atrio": {"name": "Casa Átrio", "cliente": "",
              "art": "CE20261896040", "permit": "139/2026", "template": "compact", "address": ""},
}

FIXED_FIELDS = frozenset({"tab_name", "obra", "address", "cliente", "responsavel_tecnico",
                          "engineer", "crea", "art", "permit", "template"})


def is_fixed_field(report, name: str) -> bool:
    if report.registration_draft is not None and name != "template":
        return False
    return name in FIXED_FIELDS


def identify_project(name: str) -> str:
    normalized = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower().strip()
    while normalized.endswith(" (restaurada)"):
        normalized = normalized.removesuffix(" (restaurada)")
    normalized = normalized.removeprefix("demonstracao ")
    for key, project in PROJECTS.items():
        known = unicodedata.normalize("NFKD", project["name"]).encode("ascii", "ignore").decode().lower()
        if normalized == known:
            return key
    return ""


def apply_project(report) -> None:
    # Identificador estável: mudar rótulo, restaurar backup ou abrir outra aba
    # não permite transportar cliente/ART/alvará de uma obra para outra.
    if report.project_profile is not None:
        profile = report.project_profile
        if not isinstance(profile, ProjectProfile) or report.project_key not in ("", profile.key):
            raise ValueError("O cadastro pertence a outra obra.")
        report.project_key = profile.key
        for name in FIXED_FIELDS - {"tab_name"}:
            setattr(report, name, getattr(profile, name))
        return
    key = report.project_key or identify_project(report.tab_name)
    if not key:
        return  # Rascunhos legados de obras desconhecidas continuam legíveis.
    if key not in PROJECTS:
        raise ValueError("Cadastro de obra não encontrado no código.")
    report.project_key = key
    project = PROJECTS[key]
    for name, value in COMMON.items():
        setattr(report, name, value)
    for name in ("cliente", "art", "permit", "template", "address"):
        if name in ("cliente", "address") and not project[name]:
            continue
        setattr(report, name, project[name])
    report.obra = "EXECUÇÃO DE EDIFICAÇÃO RESIDENCIAL UNIFAMILIAR - " + project["name"].upper()
