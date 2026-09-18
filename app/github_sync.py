from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.github import AvailableRepository
from app.models import (
    GitHubInstallation,
    Project,
    ProjectGitHubConnection,
    ProjectGitHubRepository,
    utcnow,
)


def save_project_repositories(
    session: Session,
    project: Project,
    installation: GitHubInstallation,
    repositories: list[AvailableRepository],
) -> list[ProjectGitHubRepository]:
    binding = session.get(ProjectGitHubConnection, project.id)
    if binding is None:
        binding = ProjectGitHubConnection(
            project_id=project.id,
            installation_id=installation.id,
        )
        session.add(binding)
        try:
            session.flush()
        except IntegrityError:
            session.rollback()
            binding = session.get(ProjectGitHubConnection, project.id)
            if binding is None:
                raise
    else:
        session.refresh(binding)
    if binding.installation_id != installation.id:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Project already uses another GitHub installation",
        )

    now = utcnow()
    existing = {
        row.github_repository_id: row
        for row in session.exec(
            select(ProjectGitHubRepository).where(
                ProjectGitHubRepository.project_id == project.id
            )
        ).all()
    }
    selected = []
    for repository in repositories:
        row = existing.get(repository.id)
        if row is None:
            row = ProjectGitHubRepository(
                project_id=project.id,
                installation_id=installation.id,
                github_repository_id=repository.id,
                full_name=repository.full_name,
                html_url=repository.html_url,
                default_branch=repository.default_branch,
            )
        else:
            row.full_name = repository.full_name
            row.html_url = repository.html_url
            row.default_branch = repository.default_branch
            row.active = True
            row.disconnected_at = None
            row.updated_at = now
        session.add(row)
        selected.append(row)

    selected_ids = {repository.id for repository in repositories}
    for repository_id, row in existing.items():
        if repository_id not in selected_ids:
            row.active = False
            row.disconnected_at = now
            row.updated_at = now
            session.add(row)
    session.commit()
    for row in selected:
        session.refresh(row)
    return selected


def disconnect_project_github(session: Session, project: Project) -> None:
    now = utcnow()
    for row in session.exec(
        select(ProjectGitHubRepository).where(
            ProjectGitHubRepository.project_id == project.id
        )
    ).all():
        row.active = False
        row.disconnected_at = now
        row.updated_at = now
        session.add(row)
    session.commit()
