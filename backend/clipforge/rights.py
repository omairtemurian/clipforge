"""The copyright guard (SPEC-v2 1.6): publishing needs the owner to say why
they may use a project's source video."""

from clipforge.models import Project


def rights_ok(project: Project) -> bool:
    """Return whether project's source rights are set; False when unset
    (every v1 project until the owner chooses). Publishing checks this."""
    return project.source_rights is not None
