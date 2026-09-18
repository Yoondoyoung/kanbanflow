import re
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from urllib.parse import urlparse

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.config import Settings, settings
from app.github import AvailableRepository
from app.models import (
    GitHubArtifact,
    GitHubArtifactKind,
    GitHubArtifactState,
    GitHubCIState,
    GitHubInstallation,
    GitHubReviewState,
    Project,
    ProjectGitHubConnection,
    ProjectGitHubRepository,
    Ticket,
    TicketGitLink,
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


def extract_ticket_numbers(
    project_key: str, texts: Iterable[str | None]
) -> set[int]:
    if not project_key:
        return set()
    pattern = re.compile(
        rf"(?<![A-Z0-9]){re.escape(project_key)}-([1-9][0-9]*)(?![A-Z0-9])",
        re.IGNORECASE,
    )
    return {
        int(match.group(1))
        for text in texts
        if isinstance(text, str)
        for match in pattern.finditer(text)
    }


def parse_github_datetime(value: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError("invalid GitHub datetime")
    parsed = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
    if parsed.tzinfo is None:
        raise ValueError("GitHub datetime must include a timezone")
    return parsed.astimezone(UTC)


def aggregate_review_state(reviews: Sequence[dict]) -> GitHubReviewState:
    ordered = []
    for index, review in enumerate(reviews):
        if not isinstance(review, dict):
            continue
        try:
            submitted_at = parse_github_datetime(review.get("submitted_at"))
        except (TypeError, ValueError):
            continue
        ordered.append((submitted_at, index, review))

    effective: dict[str, str] = {}
    for _, _, review in sorted(ordered):
        user = review.get("user")
        login = user.get("login") if isinstance(user, dict) else None
        state = review.get("state")
        if not isinstance(login, str) or not login or not isinstance(state, str):
            continue
        login = login.casefold()
        if state == "DISMISSED":
            effective.pop(login, None)
        elif state in {"APPROVED", "CHANGES_REQUESTED"}:
            effective[login] = state

    if "CHANGES_REQUESTED" in effective.values():
        return GitHubReviewState.CHANGES_REQUESTED
    if "APPROVED" in effective.values():
        return GitHubReviewState.APPROVED
    return GitHubReviewState.REVIEW_REQUIRED


def aggregate_ci_state(check_runs: Sequence[dict]) -> GitHubCIState:
    pending_statuses = {"queued", "in_progress", "waiting", "requested", "pending"}
    failed_conclusions = {
        "failure",
        "cancelled",
        "timed_out",
        "action_required",
        "startup_failure",
        "stale",
    }
    successful_conclusions = {"success", "neutral", "skipped"}
    checks = [
        check
        for check in check_runs
        if isinstance(check, dict)
        and (
            isinstance(check.get("status"), str)
            or isinstance(check.get("conclusion"), str)
        )
    ]
    if not checks:
        return GitHubCIState.NONE
    if any(check.get("conclusion") in failed_conclusions for check in checks):
        return GitHubCIState.FAILED
    if any(check.get("status") in pending_statuses for check in checks):
        return GitHubCIState.PENDING
    if all(
        check.get("status") == "completed"
        and check.get("conclusion") in successful_conclusions
        for check in checks
    ):
        return GitHubCIState.PASSED
    return GitHubCIState.NONE


def _validated_github_url(value: object, config: Settings) -> str:
    if not isinstance(value, str):
        raise ValueError("invalid GitHub URL")
    try:
        parsed = urlparse(value)
        configured = urlparse(config.github_web_url)
        valid = (
            parsed.scheme == configured.scheme == "https"
            and parsed.hostname is not None
            and parsed.hostname == configured.hostname
            and (parsed.port or 443) == (configured.port or 443)
            and parsed.username is None
            and parsed.password is None
            and configured.username is None
            and configured.password is None
        )
    except ValueError:
        valid = False
    if not valid:
        raise ValueError("GitHub URL must use the configured HTTPS web origin")
    return value


def _matching_tickets(
    session: Session,
    connection: ProjectGitHubRepository,
    texts: Iterable[str | None],
) -> list[Ticket]:
    project = session.get(Project, connection.project_id)
    if project is None:
        return []
    numbers = extract_ticket_numbers(project.key, texts)
    if not numbers:
        return []
    return list(
        session.exec(
            select(Ticket).where(
                Ticket.project_id == connection.project_id,
                Ticket.ticket_number.in_(numbers),
            )
        ).all()
    )


def upsert_pull_request(
    session: Session,
    connection: ProjectGitHubRepository,
    pull: dict,
    config: Settings = settings,
) -> GitHubArtifact:
    if not isinstance(pull, dict):
        raise ValueError("invalid pull request payload")
    external_id = pull.get("node_id") or pull.get("id")
    number = pull.get("number")
    title = pull.get("title")
    user = pull.get("user")
    head = pull.get("head")
    author_login = user.get("login") if isinstance(user, dict) else None
    head_sha = head.get("sha") if isinstance(head, dict) else None
    if (
        not isinstance(external_id, (str, int))
        or isinstance(external_id, bool)
        or not external_id
        or len(str(external_id)) > 255
        or not isinstance(number, int)
        or isinstance(number, bool)
        or number <= 0
        or not isinstance(title, str)
        or not isinstance(author_login, str)
        or not isinstance(head_sha, str)
        or len(head_sha) > 64
    ):
        raise ValueError("invalid pull request payload")

    external_id = str(external_id)
    html_url = _validated_github_url(pull.get("html_url"), config)
    occurred_at = parse_github_datetime(pull.get("updated_at"))
    state = (
        GitHubArtifactState.DRAFT
        if pull.get("draft")
        else GitHubArtifactState.MERGED
        if pull.get("merged_at")
        else GitHubArtifactState.CLOSED
        if pull.get("state") == "closed"
        else GitHubArtifactState.OPEN
    )
    artifact = session.exec(
        select(GitHubArtifact).where(
            GitHubArtifact.repository_connection_id == connection.id,
            GitHubArtifact.kind == GitHubArtifactKind.PULL_REQUEST,
            GitHubArtifact.external_id == external_id,
        )
    ).first()
    if artifact is None:
        artifact = GitHubArtifact(
            repository_connection_id=connection.id,
            kind=GitHubArtifactKind.PULL_REQUEST,
            external_id=external_id,
            number=number,
            title=title[:500],
            html_url=html_url,
            author_login=author_login[:255],
            state=state,
            review_state=GitHubReviewState.REVIEW_REQUIRED,
            head_sha=head_sha,
            occurred_at=occurred_at,
        )
    else:
        artifact.number = number
        artifact.title = title[:500]
        artifact.html_url = html_url
        artifact.author_login = author_login[:255]
        artifact.state = state
        artifact.head_sha = head_sha
        artifact.occurred_at = occurred_at
        artifact.updated_at = utcnow()
    session.add(artifact)
    session.flush()
    return artifact


def reconcile_pull_request_links(
    session: Session,
    connection: ProjectGitHubRepository,
    artifact: GitHubArtifact,
    texts: Iterable[str | None],
) -> None:
    if artifact.repository_connection_id != connection.id:
        raise ValueError("artifact does not belong to repository connection")
    ticket_ids = {ticket.id for ticket in _matching_tickets(session, connection, texts)}
    existing = {
        link.ticket_id: link
        for link in session.exec(
            select(TicketGitLink).where(TicketGitLink.artifact_id == artifact.id)
        ).all()
    }
    for ticket_id, link in existing.items():
        if ticket_id not in ticket_ids:
            session.delete(link)
    for ticket_id in ticket_ids - existing.keys():
        session.add(TicketGitLink(ticket_id=ticket_id, artifact_id=artifact.id))


def insert_linked_commit(
    session: Session,
    connection: ProjectGitHubRepository,
    commit: dict,
    config: Settings = settings,
) -> GitHubArtifact | None:
    if not isinstance(commit, dict):
        return None
    sha = commit.get("id", "")
    if not isinstance(sha, str) or re.fullmatch(r"[0-9a-fA-F]{40}", sha) is None:
        return None
    sha = sha.lower()
    existing = session.exec(
        select(GitHubArtifact).where(
            GitHubArtifact.repository_connection_id == connection.id,
            GitHubArtifact.kind == GitHubArtifactKind.COMMIT,
            GitHubArtifact.external_id == sha,
        )
    ).first()
    if existing is not None:
        return existing

    message = commit.get("message")
    if not isinstance(message, str):
        return None
    tickets = _matching_tickets(session, connection, [message])
    if not tickets:
        return None
    html_url = f"{_validated_github_url(connection.html_url, config).rstrip('/')}/commit/{sha}"
    try:
        occurred_at = parse_github_datetime(commit.get("timestamp"))
    except (TypeError, ValueError):
        return None
    author = commit.get("author")
    committer = commit.get("committer")
    author = author if isinstance(author, dict) else {}
    committer = committer if isinstance(committer, dict) else {}
    author_login = (
        author.get("username")
        or author.get("name")
        or committer.get("username")
        or committer.get("name")
        or ""
    )
    if not isinstance(author_login, str):
        author_login = ""
    artifact = GitHubArtifact(
        repository_connection_id=connection.id,
        kind=GitHubArtifactKind.COMMIT,
        external_id=sha,
        title=message.splitlines()[0][:500],
        html_url=html_url,
        author_login=author_login[:255],
        occurred_at=occurred_at,
    )
    session.add(artifact)
    session.flush()
    for ticket in tickets:
        session.add(TicketGitLink(ticket_id=ticket.id, artifact_id=artifact.id))
    return artifact
