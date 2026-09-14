# C04 Product Research & Specification: Kanban Flow

## 1. Product Research & Tool Reviews

To design an effective Engineering Workflow application for CS 482, three relevant project tracking tools were inspected: **Linear**, **Trello**, and **GitHub Projects**.

---

### Tool 1: Linear
* **Inspected Tool / Reference:** [Linear Official Product Documentation](https://linear.app/docs)
* **Core Workflow:**
  * Highly keyboard-driven, minimal-latency issue tracking tailored for fast-paced engineering teams. 
  * Linear organizes execution through continuous development cycles (sprints) that automatically roll over unfinished tasks into the next cycle.
* **Projects & Stories/Tasks Representation:**
  * **Projects:** Time-bound initiatives containing roadmaps, target dates, project leads, and child issues.
  * **Issues/Tasks:** Minimalist single-entity model. Each issue contains an auto-generated project identifier (e.g., `ENG-101`), markdown description, assignee, priority (`Urgent`, `High`, `Medium`, `Low`), and story estimates (points or t-shirt sizes).
* **Sprint, Board, or Status Workflow:**
  * Uses fixed-cadence **Cycles** (equivalent to Sprints) with automated status workflows: `Backlog` → `Todo` → `In Progress` → `In Review` → `Done` → `Canceled`.
  * Issues assigned to a cycle appear on a responsive Kanban board.
* **Reporting & Progress-Tracking Features:**
  * Real-time burn-up charts, team velocity tracking (completed estimates per cycle), and cycle completion percentage progress bars.
* **How Blockers, Decisions, Notes, or Risks Appear:**
  * **Blockers:** First-class issue relations (`blocks` / `blocked by`). A blocked issue visually renders a persistent dependency badge.
  * **Decisions/Notes:** Threaded comments, issue activity audit logs, and project status updates (`On Track`, `At Risk`, `Off Track`).
* **What seems useful for CS 482:**
  * Automatic rollover of uncompleted work into the subsequent cycle.
  * Lightweight keyboard-first interactions and minimal database entity complexity.
  * Explicit tracking of blocked dependencies.
* **What seems unnecessary for the course MVP:**
  * Multi-team workspace hierarchies, enterprise SSO, SLA tracking, and complex multi-project roadmap timelines.

---

### Tool 2: Trello
* **Inspected Tool / Reference:** [Trello Guide & Product Tour](https://trello.com/guide)
* **Core Workflow:**
  * Visual, freeform Kanban workflow based on Boards, Lists (columns), and Cards. Users manually drag and drop cards across columns to represent progress.
* **Projects & Stories/Tasks Representation:**
  * **Projects:** Represented broadly as a single "Board" or grouped under a "Workspace".
  * **Tasks:** "Cards" containing a title, markdown description, color-coded labels, member assignments, checklists, and due dates.
* **Sprint, Board, or Status Workflow:**
  * Trello has no native concept of a "Sprint" or "Cycle" out of the box. Teams emulate sprints by manually creating lists such as `Sprint Backlog`, `Doing`, and `Done`, or by adding third-party Power-Ups.
* **Reporting & Progress-Tracking Features:**
  * Minimal native velocity or burndown reporting. Progress tracking is strictly checklist completion bars (`3/5 completed`) unless external reporting plugins are subscribed to.
* **How Blockers, Decisions, Notes, or Risks Appear:**
  * Unstructured. Teams must use red color labels, card comments, or custom text fields to signal blockers.
* **What seems useful for CS 482:**
  * Clean, universally understood 4-column visual board layout (`Backlog`, `Selected`, `In Progress`, `Done`).
  * Checklists and subtasks inside work items.
* **What seems unnecessary for the course MVP:**
  * Unrestricted freeform list creation (which leads to inconsistent process states).
  * Power-Up ecosystem, custom background themes, and complex card cover designs.

---

### Tool 3: GitHub Projects (Issues & Projects v2)
* **Inspected Tool / Reference:** [GitHub Projects Documentation](https://docs.github.com/en/issues/planning-and-tracking-with-projects)
* **Core Workflow:**
  * Deeply coupled with version control (Git). Development progress is driven by commit messages (e.g., `Closes #42`), pull requests, and code review lifecycles.
* **Projects & Stories/Tasks Representation:**
  * **Projects:** Spreadsheet-style or board-style views grouping issues across repositories.
  * **Stories/Tasks:** "Issues" containing unique sequential IDs (`#12`), markdown bodies, labels, milestones, assignees, and pull request links.
* **Sprint, Board, or Status Workflow:**
  * Milestones and Iteration fields enable sprint tracking. Column statuses move automatically via built-in workflow triggers (e.g., moving to `Done` when a linked PR is merged).
* **Reporting & Progress-Tracking Features:**
  * Milestone progress bars, issue closed vs. open counts, and iteration burn-up charts.
* **How Blockers, Decisions, Notes, or Risks Appear:**
  * Commit references and PR discussion threads record decisions. Issue cross-references (e.g., "duplicate of #5", "blocked by #8") visualize risks.
* **What seems useful for CS 482:**
  * Git commit / PR message linking to close tickets automatically.
  * Direct table and Kanban dual projections.
* **What seems unnecessary for the course MVP:**
  * Complex cross-repository aggregation, enterprise SAML access controls, and custom GraphQL workflow automation rules.

---

## 2. Product Patterns to Adopt and Reject

### Patterns to Adopt
1. **Linear's Cycle Rollover & Aging Mechanism:**
   * Automatically carry unfinished stories forward on sprint closure, **preserving each ticket's `status`** so an in-flight issue stays in flight across the boundary. Linear does this without asking; Jira's equivalent stops to prompt for a destination, and the prompt is a decision a small team makes identically every time.
   * Delay is measured from **`first_sprint_entered_at`**, not `created_at`, so a ticket is not charged for the weeks it sat unscheduled in the backlog, and the value is **frozen at close time** so a historical sprint report reads the same a month later.
2. **Linear & GitHub's Developer-First Interface:**
   * Instead of forcing developers into a web browser, provide an MCP (Model Context Protocol) tool interface for Cursor / Claude Desktop and webhook push notifications to team chat (Teams, Slack, Discord).
3. **GitHub's Git-Driven Status Change:**
   * Adopt the closing-keyword pattern verbatim. A signed inbound webhook parses `push` and `pull_request` payloads for `Closes #<ticket_number>` and advances the matching ticket to `DONE`, so the board follows the repository instead of being maintained beside it.
4. **Trello's Intuitive 4-Column Board Layout — columns fixed, transitions free:**
   * Fix the **column set** to `BACKLOG` → `SELECTED` → `IN_PROGRESS` → `DONE` so every project reads the same way, but impose **no transition rules**: any state may move to any other, in either direction. Trello and GitHub Projects both ship with zero transition constraints and their users are fine; a guard mostly produces a `422` when someone undoes a mis-click.
5. **Single-Table Entity with JSON Extensibility:**
   * Consolidate stories, bugs, and inbound tasks into a single `Ticket` entity with a JSON `meta` column for variable fields (commit hashes, chat message IDs). Named `meta`, not `metadata`, because `metadata` is a reserved attribute on SQLAlchemy / SQLModel declarative classes. The column is capped at 8 KB and 3 levels of nesting so it cannot become a shadow schema.

### Patterns to Reject or Simplify
1. **Manual Drag-and-Drop Front-End Overhead:**
   * Reject heavy client-side drag-and-drop SPA frameworks (React/Next.js). Use server-rendered HTML (FastAPI + Jinja2 + Tailwind) with simple status dropdown buttons.
2. **Unbounded Freeform Columns:**
   * Reject Trello's arbitrary list creation. The four column names are schema, not data, so a board is legible without reading its configuration. This constrains the **column set only** — see Adopt #4 on why transitions stay unconstrained.
3. **Configurable Workflow Engines:**
   * Reject Jira-style transition graphs with conditions, validators, and post-functions, and Linear's per-team workflow customization. Configurability is the reason those tools need an administrator, and a course project has none.
4. **Complex In-App Notification Center:**
   * Eliminate read/unread inbox databases. Route notifications directly to where the team already communicates (Teams/Slack/Discord webhooks). Dispatch runs as a background task with a 5s timeout and three retries, and a failed delivery never reverses the ticket change that triggered it.
5. **Multi-Tenant Enterprise RBAC:**
   * Reject complex permission trees in favor of two project-level roles mapped by user email: `OWNER` for administrative actions (project settings, membership, sprint create/activate/close, report finalize) and `MEMBER` for work actions (ticket CRUD, status changes, report drafting).
6. **Rich Reporting Surfaces:**
   * Reject Linear's burn-up charts and Jira's six report types. Velocity ships as numbers and a table; the retrospective ships as text. A chart is the one artifact that can be delivered to neither of this product's two surfaces — the IDE and the chat channel.

---

## 3. Proposed MVP Capabilities for Kanban Flow

### 1. Projects, Membership & Access
- Minimal user account registration using 3 fields: `name`, `email`, and `password_hash`.
- Project boundaries identified by unique URL slugs (e.g., `/projects/payment-gateway`).
- Direct member mapping via registered email address without multi-step invite links.
- Two roles per project: `OWNER` (project settings, membership, sprint create/activate/close, report finalize) and `MEMBER` (ticket work, report drafting). A non-member receives `404` on read and `403` on write, so project existence is never leaked.

### 2. User Stories & Tickets
- Single relational `Ticket` entity supporting types: `STORY`, `BUG`, `DEMO_REQUEST`, and `TASK`.
- Project-scoped sequential ticket numbers (e.g., `#101`), allocated by an atomic counter increment rather than `MAX(...) + 1`, so concurrent creation cannot collide.
- Priority levels: `LOW`, `MEDIUM`, `HIGH`, `URGENT`.
- Story points estimation field (`story_points: INT`, Fibonacci scale) to support velocity tracking. Optional — an unestimated ticket contributes 0.
- Extensible `meta` (JSON) field for external context (commit hashes, chat message IDs), bounded at 8 KB and 3 levels of nesting.
- Markdown descriptions, rendered through an allow-list sanitizer so a ticket body submitted by a non-technical user cannot inject script into the dashboard.

### 3. Sprint Lifecycle & Kanban Board
- Fixed 4-column board: `BACKLOG`, `SELECTED`, `IN_PROGRESS`, `DONE`, with **free transitions** between any two states in either direction.
- `status` and sprint membership are **independent axes**: a ticket in an active sprint may sit in `BACKLOG`, and unplanned work may be `IN_PROGRESS` with no sprint at all.
- Projects enforce a maximum of **one active sprint** at any time.
- **Sprint Closure & Automated Rollover:** Closing a sprint moves every unfinished item (`status != 'DONE'`) into the next sprint — **auto-creating that sprint if none exists** — while **preserving each ticket's `status`**, incrementing `rollover_count`, and freezing `delayed_days`. The whole move runs in one transaction.
- Warning tags (`STALE_BLOCKER`) visually triggered on cards with `rollover_count >= 2` **or** `delayed_days >= 14`.

### 4. Progress & Velocity Tracking
- Sprint-level velocity following Linear's and Jira's shared definition: `committed_points` frozen at sprint activation vs. `completed_points` frozen at sprint closure.
- A `SprintTicketHistory` snapshot row is written per ticket at close, recording `status_at_close` and `story_points_at_close`. This exists because rollover overwrites a ticket's `sprint_id` — without the snapshot, "what did Sprint 3 actually contain" becomes unanswerable and historical velocity would silently rewrite itself.

### 5. Git-Driven Ticket Closure (GitHub Inbound Webhook)
- A single signed endpoint accepts GitHub `push` and `pull_request` events, verifying `X-Hub-Signature-256` against a per-project secret.
- Commit messages containing `Closes #<ticket_number>` advance the matching ticket to `DONE` and queue a chat notification, closing the gap between repository state and board state without any human board interaction.
- Ticket numbers are project-scoped, so resolution is constrained to the project bound to that webhook secret.

### 6. Multi-Interface Accessibility (IDE MCP + Web Dashboard)
- **Developer Interface (MCP):** Stdio MCP Server allowing developers to query assigned tickets and update statuses from Cursor / Claude Desktop without opening a browser. The server runs on the developer's machine and reaches the backend over HTTPS, authenticating with a revocable personal access token.
- **Revocable tokens:** a dedicated `ApiToken` record per token, stored as a SHA-256 hash with only a display prefix retained. Plaintext is shown exactly once at issue time; revoking a developer's IDE access does not log them out of the dashboard.
- **Stakeholder / Non-Technical Interface (Web UI):** Server-rendered dashboard (FastAPI + Jinja2) displaying the visual Kanban board, the velocity table, and an instant `[+ New Ticket]` submission modal.

### 7. AI Sprint Retrospective Draft
- On sprint close, a structured Markdown draft is generated covering the sprint goal, completed work grouped by ticket type, velocity (committed vs. completed), rollover blockers, and a reviewer notes section.
- **Two generation paths.** Server-side by default when an API key is configured; otherwise the draft is left pending and a developer can produce it through an MCP tool using their own IDE LLM session. A team with no key still gets reports; a team with one needs no developer in the loop.
- The draft is always hand-editable. Any member may save it; only an `OWNER` may finalize, after which it becomes read-only.
- Generation runs **after** the close transaction commits, so a model outage can never leave a sprint half-closed.

---

## 4. Deliberately Excluded Capabilities

The following features are intentionally excluded to protect project velocity and prioritize course requirements:

1. **Complex Authentication & Recovery Flows:**
   * Excluded: OAuth2 social logins, magic links, email verification loops, and password recovery workflows.
   * Reason: 3-field authentication is sufficient for course evaluation and internal team use.
2. **Email / Gmail Inbound Triage:**
   * Excluded: mailbox polling or push ingestion that converts inbound customer email into tickets.
   * Reason: GitHub inbound parsing is one signed endpoint and one regular expression; email intake needs OAuth, delivery infrastructure, and an address-to-project mapping model — effectively a second product. Non-technical intake runs entirely through the web modal in v1.
3. **Reporting Charts:**
   * Excluded: burndown charts, burn-up charts, cumulative flow diagrams, and control charts — the reporting surfaces Linear and Jira lead with.
   * Reason: this product's two delivery surfaces are the IDE and the chat channel, and a chart renders in neither. Velocity is delivered as numbers; the retrospective as text.
4. **Configurable Workflow & Transition Rules:**
   * Excluded: per-project status configuration, transition guards, conditions, validators, and post-functions.
   * Reason: two of the three tools reviewed impose no transition rules at all. The engineering effort belongs in the sprint-close transaction instead.
5. **Board Card Ordering & WIP Limits:**
   * Excluded: within-column ranking, manual card ordering, and work-in-progress caps.
   * Reason: ranking requires a rank field and a reordering interaction, which is exactly the drag-and-drop machinery excluded below.
6. **In-App Notification Bell System:**
   * Excluded: In-app notification centers, read/unread states, and badge counters.
   * Reason: Replaced entirely by push webhooks to team chat channels.
7. **Direct File Storage & Attachment Management:**
   * Excluded: S3 integration, binary chunking, and file previewers.
   * Reason: Team members can link external URLs, PRs, or logs directly in markdown descriptions.
8. **Drag-and-Drop SPA Frontend:**
   * Excluded: React/Vue drag-and-drop state synchronizers.
   * Reason: Replaced by lightweight server-side rendered HTML with click-to-move status dropdowns.
9. **Server-Side LLM Calls for Routine Interactive Work:**
   * Excluded: server-side model calls for natural-language parsing, triage, or any per-interaction task.
   * Reason: interactive parsing — turning *"mark #42 done, resolved in abc1234"* into a structured tool call — happens in the developer's existing Cursor / Claude session at no cost to the server. The one server-side model call in the product is the sprint retrospective, which fires **once per sprint close**, so its cost scales with sprint count rather than with user activity.

---

## 5. Short List of MVP Implications for Kanban Flow

1. **A sprint must be a real object, not a date range.**
   * GitHub Projects tracks iterations as a *field* on an item, which cannot answer "what did Sprint 3 contain" once items move — and that is precisely the question velocity depends on. Linear's Cycle is a real container, and this app follows it: a `Sprint` entity plus a `SprintTicketHistory` snapshot written at close.
2. **Sprint close is the product's most important moment, and it should not ask.**
   * Jira gets the timing right and the ergonomics wrong. Adopt Linear's automatic behavior and go one step further: if no next sprint exists, create it rather than failing or dumping work back to the backlog.
3. **Velocity Metric Grounding:**
   * Requires a `story_points` integer field on each ticket so sprint closure can output credible numeric velocity, and requires the close-time snapshot so those numbers never change retroactively.
4. **Git is the status input that matters.**
   * GitHub's closing keywords eliminate the most common source of board drift for the cost of one signed endpoint and one regular expression. This is the highest value-to-effort ratio item in the MVP.
5. **Do not build a transition state machine.**
   * Two of the three tools reviewed impose no transition rules whatsoever. Validate that the status is a member of the enum, allow any move, and spend the saved effort on making sprint close transactionally correct.
6. **Two-Tier Output Projection for MCP:**
   * To prevent high token consumption in Cursor / Claude contexts, `list_my_tickets` returns compact summaries (`number`, `title`, `status`, `priority`, `points`) with a default limit of 20, leaving full descriptions to explicit `get_ticket` requests. The under-500-token claim is asserted in CI against a real tokenizer, not assumed.
7. **Notifications must never be able to damage data.**
   * Chat delivery runs as a background task with a timeout and bounded retries. A Slack outage degrades visibility, never correctness — the ticket change stands regardless.
8. **Technical Stack Selection:**
   * **Backend:** Python (FastAPI) for native async I/O, Pydantic validation, and seamless MCP integration. Run with a single worker, since SQLite permits one writer.
   * **Database:** Embedded **SQLite with WAL mode** (`PRAGMA journal_mode=WAL; PRAGMA foreign_keys=ON`), giving zero-install, zero-cost persistence with no network round-trip on reads. WAL provides concurrent *readers*, not concurrent writers — acceptable at team scale. Read-latency figures will be measured during validation rather than assumed.
   * **Hosting:** Single $5/month **AWS Lightsail** Ubuntu instance running via `docker-compose`.
9. **Non-Technical Usability:**
   * A web view and ticket-creation modal ensure faculty evaluators, PMs, and non-technical stakeholders can inspect work and file requests without an IDE or terminal — the audience none of the three reviewed tools' developer-facing strengths serve.
