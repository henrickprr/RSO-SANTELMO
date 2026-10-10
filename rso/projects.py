"""Cadastro fixo por obra, transcrito dos PDFs fornecidos pelo usuário.

Edite somente este arquivo para corrigir dados cadastrais. Endereços das obras
não constam nos anexos; o endereço do cabeçalho pertence à Santelmo.
O PDF Átrio contém 'Casa Bella Vista' por engano e deixa o cliente em branco.
Não copiar o cliente ou os números de outra obra para preencher essas lacunas.
"""

import unicodedata

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
    if name in ("address", "cliente"):
        # O usuário autorizou preencher as lacunas dos modelos na interface.
        return bool(PROJECTS.get(report.project_key, {}).get(name))
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
    key = report.project_key or identify_project(report.tab_name)
    if not key:
        return  # Rascunhos legados de obras desconhecidas continuam legíveis.
    if key not in PROJECTS:
        raise ValueError("Cadastro de obra não encontrado no código.")
    report.project_key = key
    project = PROJECTS[key]
    for field, value in COMMON.items():
        setattr(report, field, value)
    for field in ("cliente", "art", "permit", "template", "address"):
        if field in ("cliente", "address") and not project[field]:
            continue
        setattr(report, field, project[field])
    report.obra = "EXECUÇÃO DE EDIFICAÇÃO RESIDENCIAL UNIFAMILIAR - " + project["name"].upper()
