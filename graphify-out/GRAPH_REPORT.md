# Graph Report - ui-refresh  (2026-09-17)

## Corpus Check
- 79 files · ~81,803 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1026 nodes · 3110 edges · 45 communities (44 shown, 1 thin omitted)
- Extraction: 71% EXTRACTED · 29% INFERRED · 0% AMBIGUOUS · INFERRED: 891 edges (avg confidence: 0.9)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `7d850261`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- Project
- make_csrf_token
- WebhookType
- auth.py
- test_mcp_server.py
- test_authorization_matrix.py
- api_projects.py
- test_project_access.py
- Kanban Flow Slice 1 Implementation Plan
- test_projects.py
- test_web_auth.py
- test_web_project_settings.py
- Notion-Style Sprint Workflow Design
- playwright_ticket_drawer_focus.py
- test_web_ticket_create.py
- Kanban Flow — Slice 1 Design
- 4. Proposed MVP Capabilities for Kanban Flow
- make_project
- test_ticket_api.py
- Ticket
- test_web_final_fixes.py
- test_web_dashboard.py
- Quiet Sprint Workspace UI Refresh
- Kanban Flow — Slice 1
- login_as
- Global Constraints
- 2. Product research and decisions
- test_status.py
- 7. API & Web Route Contract
- Global Constraints
- 6. Domain model
- Global Constraints
- cs482_workflow.md
- 8. AI sprint-report behavior
- test_web_shell.py
- Kanban Flow — Slice 1 follow-ups
- 1. Product vision
- 4. Key user workflows
- Global Constraints
- 10. Initial validation plan & First slice
- kanbanflow
- add_member

## God Nodes (most connected - your core abstractions)
1. `login_as()` - 211 edges
2. `make_project()` - 139 edges
3. `Ticket` - 103 edges
4. `SprintStatus` - 95 edges
5. `Sprint` - 94 edges
6. `Project` - 91 edges
7. `User` - 88 edges
8. `make_csrf_token()` - 69 edges
9. `ProjectMember` - 67 edges
10. `TicketStatus` - 59 edges

## Surprising Connections (you probably didn't know these)
- `test_register_strips_and_validates_name()` --uses--> `User`  [INFERRED]
  tests/test_web_auth.py → app/models.py
- `test_project_reader_dependency_missing_project_raises_404()` --calls--> `project_reader()`  [EXTRACTED]
  tests/test_project_access.py → app/auth.py
- `add_member()` --uses--> `Role`  [INFERRED]
  tests/conftest.py → app/models.py
- `make_project()` --uses--> `Role`  [INFERRED]
  tests/conftest.py → app/models.py
- `test_concurrent_member_add_race_returns_409_not_500()` --uses--> `Role`  [INFERRED]
  tests/test_membership.py → app/models.py

## Import Cycles
- None detected.

## Communities (45 total, 1 thin omitted)

### Community 0 - "Project"
Cohesion: 0.12
Nodes (79): load_project_and_membership(), project_owner(), project_reader(), project_writer(), Session, Project, ProjectMember, Role (+71 more)

### Community 1 - "make_csrf_token"
Cohesion: 0.16
Nodes (26): make_csrf_token(), test_close_preview_shows_totals_destination_and_accessible_dialog(), test_close_rejects_an_unknown_rollover_destination(), test_close_requires_a_planning_destination_without_mutation(), test_close_service_error_is_rendered_without_partial_mutation(), test_duplicate_close_submission_returns_stable_conflict(), test_htmx_close_error_fragment_swaps_on_the_persistent_dialog_host(), test_htmx_close_redirects_to_the_updated_board() (+18 more)

### Community 2 - "WebhookType"
Cohesion: 0.09
Nodes (37): WebhookType, build_payload(), _detail(), dispatch(), format_discord(), format_slack(), format_teams(), _headline() (+29 more)

### Community 3 - "auth.py"
Cohesion: 0.05
Nodes (63): assert_csrf_matches(), _bearer_token(), current_user(), hash_password(), _is_older_than_an_hour(), make_session_cookie(), optional_user(), Request (+55 more)

### Community 4 - "test_mcp_server.py"
Cohesion: 0.13
Nodes (33): anyio, _api_path(), api_request(), close_sprint(), create_sprint(), list_sprints(), MCPSettings, _path_segment() (+25 more)

### Community 5 - "test_authorization_matrix.py"
Cohesion: 0.20
Nodes (15): call(), endpoint_project_slug(), endpoints(), V-8: every mutating endpoint enforces the permission matrix for every caller…, Full state of everything a row in `endpoints()` could write to. One composite…, Issue the request. FORM (HTML) writes get a valid CSRF token for `actor` so the…, (kind, transport, method, url, kwargs) for every mutating route in the app.…, Ruling: cover the HTML mutating routes too, not only /api/v1/*. Both reach… (+7 more)

### Community 6 - "api_projects.py"
Cohesion: 0.06
Nodes (56): issue_api_token(), add_member(), delete_project(), get_project(), list_members(), list_projects(), _members(), _out() (+48 more)

### Community 7 - "test_project_access.py"
Cohesion: 0.14
Nodes (14): parametrize, test_delete_rejects_a_mismatched_confirmation_value(), test_delete_requires_confirmation(), test_explicit_null_project_update_fields_are_ignored(), test_missing_project_is_404_even_for_writes(), test_missing_project_is_404_on_read(), test_non_member_reads_404_and_writes_403(), test_owner_can_edit_name_but_slug_never_changes() (+6 more)

### Community 8 - "Kanban Flow Slice 1 Implementation Plan"
Cohesion: 0.06
Nodes (31): Coverage Check, File Structure, Global Constraints, Kanban Flow Slice 1 Implementation Plan, Task 10: Membership management, Task 11: `meta` validation, atomic ticket numbers, and ticket creation, Task 12: Prove the ticket-number allocation under concurrency (V-1), Task 13: Ticket read, list, update, and delete (+23 more)

### Community 9 - "test_projects.py"
Cohesion: 0.20
Nodes (8): parametrize, test_concurrent_project_creation_race_returns_409_not_500(), test_create_project_makes_the_creator_an_owner(), test_duplicate_slug_returns_409(), test_non_member_gets_404_on_project_detail(), test_project_list_shows_only_projects_you_belong_to(), test_slugify(), test_unslugifiable_name_returns_422()

### Community 10 - "test_web_auth.py"
Cohesion: 0.07
Nodes (22): block_foreign_origin_cookie_writes(), health(), get, Request, render_markdown(), middleware, test_basic_markdown_renders(), test_img_onerror_in_source_is_neutralized() (+14 more)

### Community 11 - "test_web_project_settings.py"
Cohesion: 0.19
Nodes (14): _csrf(), fixture, Removing a member name or danger styling must make this fail., settings_world(), test_member_api_redacts_webhook_but_owner_can_read_it(), test_member_reads_settings_without_mutation_controls_or_webhook_secret(), test_owner_adds_changes_and_removes_members(), test_owner_renames_project_without_changing_its_slug() (+6 more)

### Community 12 - "Notion-Style Sprint Workflow Design"
Cohesion: 0.07
Nodes (26): 10. Deferred Work, 1. Goal, 2. Design Direction, 3. Users and Permissions, 4. Information Architecture and Click Targets, 5. Screens, 6. Sprint Lifecycle, 7. Shared API and MCP Design (+18 more)

### Community 13 - "playwright_ticket_drawer_focus.py"
Cohesion: 0.60
Nodes (4): main(), _port(), Run with: /opt/homebrew/opt/python@3.11/bin/python3.11…, _wait()

### Community 14 - "test_web_ticket_create.py"
Cohesion: 0.14
Nodes (13): parametrize, Open modal, title, type, description, submit — the form must ask for nothing…, test_empty_title_is_422(), test_five_interactions_or_fewer(), test_missing_csrf_is_403_and_creates_nothing(), test_modal_redirects_after_a_successful_htmx_submission(), test_non_htmx_ticket_submission_redirects_to_the_project(), test_non_member_submission_creates_nothing() (+5 more)

### Community 15 - "Kanban Flow — Slice 1 Design"
Cohesion: 0.09
Nodes (21): 10. Validation, 11. Deferred, with the trigger for revisiting, 1. Decisions confirmed, 2. Slice 1 scope, 3. Module layout, 4. Schema, 5. Route contract, 6. Authentication, CSRF, authorization (+13 more)

### Community 16 - "4. Proposed MVP Capabilities for Kanban Flow"
Cohesion: 0.09
Nodes (21): 1. Intended Users & Stakeholders, 1. Projects, Membership & Access, 2. Product Research & Tool Reviews, 2. User Stories & Tickets, 3. Product Patterns to Adopt and Reject, 3. Sprint Lifecycle & Kanban Board, 4. Progress & Velocity Tracking, 4. Proposed MVP Capabilities for Kanban Flow (+13 more)

### Community 17 - "make_project"
Cohesion: 0.06
Nodes (102): Sprint, SprintStatus, SprintTicketHistory, get_sprint(), get_sprint_history(), list_sprints(), patch_sprint(), post_close_sprint() (+94 more)

### Community 22 - "test_ticket_api.py"
Cohesion: 0.11
Nodes (6): fixture, parametrize, seeded(), test_non_member_gets_404_on_ticket_read(), test_only_owner_deletes(), test_patch_rejects_explicit_null_on_non_nullable_field()

### Community 23 - "Ticket"
Cohesion: 0.06
Nodes (67): Run migrations in 'offline' mode. This configures the context with just a URL…, Run migrations in 'online' mode. In this scenario we need to create an Engine…, run_migrations_offline(), run_migrations_online(), The one place a missing membership becomes 403 on a write path. Every write-…, require_member(), ApiToken, Priority (+59 more)

### Community 24 - "test_web_final_fixes.py"
Cohesion: 0.18
Nodes (15): _detail_data(), parametrize, test_allowed_owner_self_removal_redirects_to_dashboard(), test_detail_422_html_swaps_but_csrf_403_does_not(), test_detail_missing_or_blank_title_returns_an_html_form_with_attempted_values(), test_detail_move_requests_a_board_refresh(), test_detail_typed_validation_keeps_every_attempted_field(), test_history_summary_counts_completed_tickets_from_close_snapshot() (+7 more)

### Community 25 - "test_web_dashboard.py"
Cohesion: 0.18
Nodes (14): csrf_for(), test_create_project_from_the_form(), test_create_project_with_another_users_csrf_is_403(), test_create_project_without_csrf_is_403(), test_dashboard_has_accessible_project_creation_dialog(), test_dashboard_lists_projects(), test_invalid_project_name_is_escaped_and_preserved_in_the_reopened_dialog(), test_missing_csrf_token_does_not_create_the_project() (+6 more)

### Community 27 - "Quiet Sprint Workspace UI Refresh"
Cohesion: 0.14
Nodes (13): Backlog, Board, Dashboard, Domain exploration, History, Information architecture, Intent, Interaction and accessibility (+5 more)

### Community 28 - "Kanban Flow — Slice 1"
Cohesion: 0.14
Nodes (13): Chat notifications, Design documents, Develop (without Docker), Generate a real `SESSION_SECRET`, Kanban Flow — Slice 1, MCP sprint tools, Out of scope for this slice, Prerequisites (+5 more)

### Community 29 - "login_as"
Cohesion: 0.07
Nodes (40): login_as(), test_foreign_origin_write_creates_no_ticket(), test_foreign_origin_write_is_rejected(), test_missing_cookie_write_is_not_blocked_by_origin(), test_missing_origin_is_allowed(), test_non_api_path_write_is_not_blocked_by_origin(), test_reads_are_not_blocked_by_origin(), test_same_origin_write_is_allowed() (+32 more)

### Community 31 - "Global Constraints"
Cohesion: 0.17
Nodes (11): Global Constraints, Notion-Style Sprint Web Implementation Plan, Task 1: Add the visual foundation and application shell, Task 2: Redesign the project dashboard, Task 3: Make the project entry sprint-aware, Task 4: Add Backlog and planning UI, Task 5: Add sprint start and close workflows, Task 6: Add closed-sprint history (+3 more)

### Community 34 - "2. Product research and decisions"
Cohesion: 0.18
Nodes (11): 2. Product research and decisions, Adjacent systems inspected (not project-management tools), Cross-tool pattern summary, How these tools were inspected, MVP implications, Patterns to adopt, Patterns to reject or simplify, Product decisions (+3 more)

### Community 35 - "test_status.py"
Cohesion: 0.18
Nodes (4): fixture, test_non_member_cannot_transition(), test_plain_member_can_transition(), ticket_id()

### Community 36 - "7. API & Web Route Contract"
Cohesion: 0.20
Nodes (10): 0) Conventions, 1) Web UI Routes (HTML Serving), 2) Auth & Tokens, 3) Projects & Membership, 4) Sprints, 5) Tickets & Board, 6) Reports & Velocity, 7. API & Web Route Contract (+2 more)

### Community 37 - "Global Constraints"
Cohesion: 0.20
Nodes (9): Global Constraints, Sprint Core Implementation Plan, Task 1: Persist sprint state and history, Task 2: Define sprint request and response schemas, Task 3: Implement sprint creation and activation services, Task 4: Implement atomic close and rollover, Task 5: Expose sprint JSON APIs, Task 6: Add sprint assignment to tickets (+1 more)

### Community 38 - "6. Domain model"
Cohesion: 0.22
Nodes (9): 6. Domain model, Entity: ApiToken, Entity: Project, Entity: ProjectMember, Entity: Sprint, Entity: SprintReport, Entity: SprintTicketHistory, Entity: Ticket (+1 more)

### Community 40 - "Global Constraints"
Cohesion: 0.25
Nodes (7): Global Constraints, Sprint MCP Implementation Plan, Task 1: Add revocable API tokens, Task 2: Issue, list, revoke, and authenticate tokens, Task 3: Build the minimal MCP HTTP client, Task 4: Expose sprint MCP tools, Task 5: Document and verify MCP setup

### Community 41 - "cs482_workflow.md"
Cohesion: 0.29
Nodes (6): 11. Decision log, 3. MVP scope, 5. Functional requirements, 9. Non-functional and platform requirements, Explicitly out of scope, In scope

### Community 42 - "8. AI sprint-report behavior"
Cohesion: 0.29
Nodes (7): 8. AI sprint-report behavior, Failure behavior, How quality is checked, Human review, Inputs provided to the model, Output sections, Where generation runs

### Community 43 - "test_web_shell.py"
Cohesion: 0.18
Nodes (5): Removing focus entry, containment, return, or background inerting must fail., test_backdrop_hides_and_drawer_closes_when_resized_to_desktop(), test_mobile_drawer_has_a_complete_focus_lifecycle(), test_mobile_drawer_is_inert_only_while_closed(), test_signed_in_shell_has_project_sidebar()

### Community 44 - "Kanban Flow — Slice 1 follow-ups"
Cohesion: 0.33
Nodes (5): Fixed already, Kanban Flow — Slice 1 follow-ups, Must be verified on a machine with Docker, Remaining — Important, Remaining — worth doing cheaply

### Community 45 - "1. Product vision"
Cohesion: 0.33
Nodes (6): 1. Product vision, Intended users and stakeholders, Problem statement, Product name, Product vision, Success criteria

### Community 46 - "4. Key user workflows"
Cohesion: 0.33
Nodes (6): 4. Key user workflows, Workflow 0: Sprint Planning (backlog → sprint), Workflow 1: Developer Task Resolution via IDE MCP, Workflow 2: Non-Technical User Web Dashboard Triage & Ticket Submission, Workflow 2b: GitHub Commit Closes a Ticket, Workflow 3: Sprint Closure, Story Rollover, and Retrospective Draft

### Community 47 - "Global Constraints"
Cohesion: 0.33
Nodes (5): Global Constraints, Quiet Sprint Workspace UI Refresh Implementation Plan, Task 1: Application shell and shared design system, Task 2: Board and backlog workspaces, Task 3: History, settings, authentication, and responsive polish

### Community 48 - "10. Initial validation plan & First slice"
Cohesion: 0.50
Nodes (4): 10. Initial validation plan & First slice, First implementation slice, Known open risks, Validation plan

### Community 57 - "add_member"
Cohesion: 0.12
Nodes (19): add_member(), test_adding_unknown_email_is_404_and_duplicate_is_409(), test_concurrent_member_add_race_returns_409_not_500(), test_last_owner_cannot_be_demoted_or_removed(), test_list_members_returns_every_member_not_just_caller(), test_member_cannot_manage_membership(), test_non_owner_gets_403_on_patch_and_delete(), test_owner_adds_member_by_email() (+11 more)

## Knowledge Gaps
- **186 isolated node(s):** `kanbanflow`, `Prerequisites`, `Run locally (Docker)`, `Generate a real `SESSION_SECRET``, `Single worker, on purpose` (+181 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **1 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `login_as()` connect `login_as` to `make_csrf_token`, `WebhookType`, `auth.py`, `test_status.py`, `test_authorization_matrix.py`, `test_project_access.py`, `test_projects.py`, `test_web_auth.py`, `test_web_project_settings.py`, `test_web_shell.py`, `test_web_ticket_create.py`, `make_project`, `test_ticket_api.py`, `Ticket`, `test_web_final_fixes.py`, `add_member`, `test_web_dashboard.py`?**
  _High betweenness centrality (0.098) - this node is a cross-community bridge._
- **Why does `make_project()` connect `make_project` to `Project`, `make_csrf_token`, `WebhookType`, `auth.py`, `test_status.py`, `test_project_access.py`, `test_web_project_settings.py`, `test_web_shell.py`, `test_web_ticket_create.py`, `test_ticket_api.py`, `Ticket`, `add_member`, `login_as`, `test_web_dashboard.py`?**
  _High betweenness centrality (0.044) - this node is a cross-community bridge._
- **Why does `Ticket` connect `Ticket` to `Project`, `make_csrf_token`, `WebhookType`, `auth.py`, `test_authorization_matrix.py`, `test_projects.py`, `test_web_ticket_create.py`, `make_project`, `test_ticket_api.py`, `test_web_final_fixes.py`, `add_member`, `login_as`?**
  _High betweenness centrality (0.038) - this node is a cross-community bridge._
- **Are the 209 inferred relationships involving `login_as()` (e.g. with `issue_token()` and `test_invalid_bearer_does_not_fall_back_to_a_valid_cookie()`) actually correct?**
  _`login_as()` has 209 INFERRED edges - model-reasoned connections that need verification._
- **Are the 137 inferred relationships involving `make_project()` (e.g. with `Project` and `ProjectMember`) actually correct?**
  _`make_project()` has 137 INFERRED edges - model-reasoned connections that need verification._
- **Are the 47 inferred relationships involving `Ticket` (e.g. with `build_payload()` and `schedule()`) actually correct?**
  _`Ticket` has 47 INFERRED edges - model-reasoned connections that need verification._
- **Are the 71 inferred relationships involving `SprintStatus` (e.g. with `board()` and `render()`) actually correct?**
  _`SprintStatus` has 71 INFERRED edges - model-reasoned connections that need verification._