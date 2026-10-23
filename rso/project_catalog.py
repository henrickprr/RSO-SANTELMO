"""Catálogo reconstruível dos relatórios locais, recuperados do Firebase ou ZIP.

Cadastrar uma obra grava seu primeiro relatório. O cadastro acompanha todas as
semanas seguintes; não exige uma segunda coleção nem novas regras no Firebase.
"""

from .models import Report, ValidationError
from .projects import PROJECTS, ProjectProfile, normalized_name
from .storage import DraftRepository


class ProjectCatalog:
    def __init__(self, repository: DraftRepository):
        self.repository = repository

    def _profiles(self) -> dict[str, ProjectProfile]:
        result = {}
        # Chamador mantém o RLock. Não consultar Firestore a cada abertura do menu.
        for path in sorted(self.repository.drafts.glob("*.json")):
            try:
                report = self.repository.read(path)
            except (OSError, ValueError, TypeError, KeyError):
                # load_all já apresenta os avisos de recuperação ao abrir o app.
                continue
            profile = report.project_profile
            if profile is None:
                continue
            if profile.key in result and result[profile.key] != profile:
                raise ValidationError("Há cadastros diferentes para a mesma obra no backup.")
            result[profile.key] = profile
        return result

    def choices(self) -> dict[str, str]:
        with self.repository.lock:
            return {**{key: value["name"] for key, value in PROJECTS.items()},
                    **{key: value.name for key, value in self._profiles().items()}}

    def register(self, profile: ProjectProfile) -> Report:
        with self.repository.lock:
            choices = self.choices()
            if profile.key in choices or normalized_name(profile.name) in {
                    normalized_name(name) for name in choices.values()}:
                raise ValidationError("Esta obra já está cadastrada. Use Novo relatório para outra semana.")
            report = Report.new(profile.name, profile=profile)
            self.repository.save(report)
            return report

    def new_report(self, project_key: str) -> Report:
        with self.repository.lock:
            if project_key in PROJECTS:
                project = PROJECTS[project_key]
                report = Report.new(project["name"], project["template"])
            else:
                profile = self._profiles().get(project_key)
                if profile is None:
                    raise ValidationError("Obra não encontrada. Reabra o aplicativo e tente novamente.")
                # Novo objeto: atividades, recursos e fotos não são copiados da semana anterior.
                report = Report.new(profile.name, profile=profile)
            self.repository.save(report)
            return report
