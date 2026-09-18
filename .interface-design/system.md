# Kanban Flow Interface System

## Direction

- Calm, practical work-management UI for both technical and non-technical teams.
- Keep information dense but readable; use plain department-neutral language.
- Prefer native HTML, semantic CSS, and restrained interaction over decorative UI.

## Foundations

- Depth: bordered white surfaces on a warm gray canvas; shadows only for modal elevation.
- Spacing: 4px base unit using the existing `--space-1` through `--space-6` tokens.
- Corners: 4px controls, 8px surfaces and dialogs.
- Typography: system sans-serif, 14px body, 18px section headings, 12px supporting metadata.
- Controls: 40px minimum height with a visible `:focus-visible` outline.

## Hierarchy

- Lead with the work item title and editable details.
- Keep metadata compact in paired fields on desktop and a single column on mobile.
- Treat conversation as a primary workflow, not a footer.
- Use borders and spacing—not extra cards or color—to separate regions.

## Component Patterns

### Ticket detail modal

- Centered native `<dialog>` with a maximum width of 1120px and 16px viewport gutters.
- Desktop layout: ticket details 60% / comments 40%, with a 20px gap.
- Separate comments with a 1px left border and 20px left padding.
- At widths below 768px, use a full-screen dialog and stack comments below details with a top border.
- On open, focus the modal heading; on close, return focus to the originating ticket.

### Ticket comments

- Keep comment history, edit/delete actions, mention controls, and composer in the right panel.
- Use an inset surface for each comment and muted 12px timestamps.
- Place Edit and Delete at the card's top right; return Edit to normal flow while its form is open.
- Typing `@` in the composer opens a keyboard-accessible project-member picker below the textarea.
- Store comment timestamps as UTC and render them in the browser's locale and time zone.
- Preserve native form submission as a fallback; HTMX may replace only the comments region.

### Ticket development activity

- Keep ticket reference and branch-command copy controls in the left detail pane, using
  native buttons with visible polite status text.
- Render linked GitHub work as border-separated rows below the editable fields; repository
  and timestamp are muted metadata, while the PR or commit title carries the row hierarchy.
- Use compact neutral pills for PR and CI summaries near the header. Keep comments in the
  existing right pane and stack both panes only at the 767px mobile breakpoint.
- Show external text as escaped text. Only configured GitHub HTTPS-origin URLs become links,
  and those links open in a new tab with `noopener noreferrer`.
