"""Correções canônicas e marcadores de exclusão, separados dos dados semanais."""

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from uuid import UUID

from .projects import PROJECTS, ProjectProfile


class ProjectDeleted(OSError):
    def __init__(self):
        super().__init__("Esta obra foi excluída. Reabra o aplicativo para atualizar as abas.")


class ProjectChanged(OSError):
    def __init__(self):
        super().__init__("O cadastro mudou em outra sessão. Reabra o aplicativo para revisar os dados atuais.")


def project_key(report) -> str:
    return report.project_key or "custom_" + report.id


@dataclass(frozen=True)
class ProjectState:
    key: str
    profile: ProjectProfile | None = None
    deleted: bool = False

    def __post_init__(self):
        if not isinstance(self.key, str) or (self.key not in PROJECTS and
                (not self.key.startswith("custom_") or UUID(self.key[7:]).hex != self.key[7:])):
            raise ValueError("Identificador de obra inválido.")
        if type(self.deleted) is not bool or (self.profile is None) != self.deleted:
            raise ValueError("Estado da obra inválido.")
        if self.profile is not None and self.profile.key != self.key:
            raise ValueError("Cadastro de outra obra.")

    @property
    def revision(self) -> str:
        return sha256(json.dumps(asdict(self), sort_keys=True, ensure_ascii=False).encode()).hexdigest()

    def to_dict(self) -> dict:
        return {**asdict(self), "revision": self.revision}

    @classmethod
    def from_dict(cls, value):
        state = cls(key=value["key"], deleted=value["deleted"],
                    profile=ProjectProfile.from_dict(value["profile"]) if value["profile"] else None)
        if state.revision != value["revision"]:
            raise ValueError("Cadastro persistido inconsistente.")
        return state
