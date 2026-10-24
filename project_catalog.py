"""Catálogo de obras com rascunhos de correção e exclusão por identidade estável.

O cadastro acompanha cada relatório e o backup. Correções confirmadas e marcadores
de exclusão têm precedência sobre essas cópias, inclusive após recuperar a nuvem.
"""

from .models import Report, ValidationError
from .projects import FIXED_FIELDS, PROJECTS, ProjectProfile, normalized_name
from .project_state import ProjectState, project_key
from .storage import DraftRepository


class ProjectCatalog:
    def __init__(self, repository: DraftRepository):
        self.repository = repository

    def _profiles(self) -> dict[str, ProjectProfile]:
        result = {}
        # Chamador mantém o RLock. Não consultar Firestore a cada abertura do menu.
        for path in sorted(self.repository.drafts.glob("*.json")):
            try:
                report = self.repository.read_current(path)
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
            choices = {**{key: value["name"] for key, value in PROJECTS.items()},
                       **{key: value.name for key, value in self._profiles().items()}}
            for key, state in self.repository.project_states.items():
                if state.deleted:
                    choices.pop(key, None)
                else:
                    choices[key] = state.profile.name
            return choices

    def begin_edit(self, report: Report) -> None:
        with self.repository.lock:
            self.repository.apply_registration(report)
            if report.registration_draft is not None:
                return
            state = self.repository.project_states.get(project_key(report))
            report.registration_base = state.revision if state else ""
            report.registration_draft = {name: getattr(report, name)
                for name in FIXED_FIELDS - {"template"}}
            self.repository.save(report)

    def confirm_edit(self, report: Report) -> None:
        if report.registration_draft is None:
            return
        values = dict(report.registration_draft)
        values["name"] = values.pop("tab_name")
        profile = ProjectProfile(**values, key=project_key(report), template=report.template)
        with self.repository.lock:
            for key, name in self.choices().items():
                if key != profile.key and normalized_name(name) == normalized_name(profile.name):
                    raise ValidationError("Já existe outra obra com este nome.")
        # Não manter o lock local enquanto o backend aguarda uma transação de rede.
        self.repository.set_project_state(ProjectState(profile.key, profile),
                                           report.registration_base or None)
        with self.repository.lock:
            previous, previous_base = report.registration_draft, report.registration_base
            report.registration_draft = None
            report.registration_base = ""
            try:
                self.repository.save(report)
            except OSError:
                # Cadastro confirmado e diário têm persistências independentes.
                # Preservar o texto editado se a gravação do diário precisar de retry.
                report.registration_draft, report.registration_base = previous, previous_base
                raise

    def reports_for(self, key: str) -> list[Report]:
        with self.repository.lock:
            reports = [self.repository.read_current(p) for p in self.repository.drafts.glob("*.json")]
            return [r for r in reports if project_key(r) == key]

    def delete(self, key: str, expected: str | None) -> None:
        self.repository.set_project_state(ProjectState(key, deleted=True), expected)

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
            if project_key not in self.choices():
                raise ValidationError("Obra não encontrada ou excluída. Reabra o aplicativo.")
            state = self.repository.project_states.get(project_key)
            profile = state.profile if state else self._profiles().get(project_key)
            if profile:
                report = Report.new(profile.name, profile=profile)
            elif project_key in PROJECTS:
                project = PROJECTS[project_key]
                report = Report.new(project["name"], project["template"])
            else:
                raise ValidationError("Obra não encontrada. Reabra o aplicativo e tente novamente.")
            self.repository.save(report)
            return report
