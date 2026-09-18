(() => {
  const inputSelector = "[data-mention-input]";

  function menuFor(input) {
    return document.getElementById(input.getAttribute("aria-controls"));
  }

  function mentionAtCursor(input) {
    const before = input.value.slice(0, input.selectionStart);
    const match = before.match(/(?:^|\s)@([^@\n]*)$/);
    if (!match) return null;
    return { query: match[1].trim().toLowerCase(), start: before.lastIndexOf("@") };
  }

  function closeMenu(input) {
    const menu = menuFor(input);
    if (!menu) return;
    menu.hidden = true;
    input.setAttribute("aria-expanded", "false");
  }

  function syncSelected(input) {
    const holder = input.closest("form").querySelector("[data-selected-mentions]");
    holder.querySelectorAll("input").forEach((hidden) => {
      const name = hidden.dataset.mentionName.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      const token = new RegExp(`(^|\\s)@${name}(?=\\s|$|[.,!?;:])`);
      if (!token.test(input.value)) hidden.remove();
    });
  }

  function showMatches(input) {
    syncSelected(input);
    const mention = mentionAtCursor(input);
    const menu = menuFor(input);
    if (!mention || !menu) return closeMenu(input);
    let visible = 0;
    menu.querySelectorAll("[data-mention-id]").forEach((option) => {
      option.hidden = !option.dataset.mentionSearch.includes(mention.query);
      option.setAttribute("aria-selected", visible === 0 && !option.hidden ? "true" : "false");
      if (!option.hidden) visible += 1;
    });
    menu.hidden = visible === 0;
    input.setAttribute("aria-expanded", String(visible > 0));
  }

  function selectMention(input, option) {
    const mention = mentionAtCursor(input);
    if (!mention) return;
    const name = option.dataset.mentionName;
    const insertion = `@${name} `;
    input.setRangeText(insertion, mention.start, input.selectionStart, "end");
    const holder = input.closest("form").querySelector("[data-selected-mentions]");
    if (![...holder.children].some((item) => item.value === option.dataset.mentionId)) {
      const hidden = document.createElement("input");
      hidden.type = "hidden";
      hidden.name = "mention_ids";
      hidden.value = option.dataset.mentionId;
      hidden.dataset.mentionName = name;
      holder.append(hidden);
    }
    closeMenu(input);
    input.focus();
  }

  function visibleOptions(input) {
    const menu = menuFor(input);
    return menu ? [...menu.querySelectorAll("[data-mention-id]:not([hidden])")] : [];
  }

  function localizeTimes(root = document) {
    root.querySelectorAll("[data-local-time]").forEach((time) => {
      const value = new Date(time.dateTime);
      if (!Number.isNaN(value.getTime())) {
        time.textContent = new Intl.DateTimeFormat([], {
          dateStyle: "medium",
          timeStyle: "short",
        }).format(value);
      }
    });
  }

  document.addEventListener("DOMContentLoaded", () => localizeTimes());
  document.addEventListener("htmx:afterSwap", (event) => localizeTimes(event.target));

  document.addEventListener("input", (event) => {
    if (event.target.matches(inputSelector)) showMatches(event.target);
  });

  document.addEventListener("keydown", (event) => {
    const input = event.target;
    if (!input.matches(inputSelector) || input.getAttribute("aria-expanded") !== "true") return;
    const options = visibleOptions(input);
    let index = options.findIndex((option) => option.getAttribute("aria-selected") === "true");
    if (event.key === "Escape") return closeMenu(input);
    if (event.key === "Enter" && options[index]) {
      event.preventDefault();
      return selectMention(input, options[index]);
    }
    if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
    event.preventDefault();
    options[index]?.setAttribute("aria-selected", "false");
    index = (index + (event.key === "ArrowDown" ? 1 : -1) + options.length) % options.length;
    options[index].setAttribute("aria-selected", "true");
    options[index].scrollIntoView({ block: "nearest" });
  });

  document.addEventListener("click", (event) => {
    const editDescription = event.target.closest("[data-description-edit]");
    if (editDescription) {
      const editor = editDescription.closest("[data-description-editor]");
      editDescription.hidden = true;
      editor.querySelector("[data-description-view]").hidden = true;
      editor.querySelector("[data-description-fields]").hidden = false;
      editor.querySelector("textarea").focus();
      return;
    }
    const cancelDescription = event.target.closest("[data-description-cancel]");
    if (cancelDescription) {
      const editor = cancelDescription.closest("[data-description-editor]");
      const textarea = editor.querySelector("textarea");
      textarea.value = textarea.defaultValue;
      editor.querySelector("[data-description-fields]").hidden = true;
      editor.querySelector("[data-description-view]").hidden = false;
      const editButton = editor.querySelector("[data-description-edit]");
      editButton.hidden = false;
      editButton.focus();
      return;
    }
    const copyButton = event.target.closest("[data-copy-text]");
    if (copyButton) {
      const status = copyButton.nextElementSibling;
      navigator.clipboard.writeText(copyButton.dataset.copyText).then(
        () => { status.textContent = "Copied"; },
        () => { status.textContent = "Copy failed"; },
      );
      return;
    }
    const option = event.target.closest("[data-mention-id]");
    if (option) return selectMention(option.closest("form").querySelector(inputSelector), option);
    document.querySelectorAll(inputSelector).forEach(closeMenu);
  });

  document.addEventListener("submit", (event) => {
    const input = event.target.querySelector(inputSelector);
    if (input) syncSelected(input);
  }, true);
})();

(() => {
  let draggedCard = null;

  function setDragStatus(board, message) {
    const status = board.querySelector("[data-board-drag-status]");
    status.hidden = false;
    status.textContent = message;
  }

  function refreshLane(lane) {
    const cards = lane.querySelectorAll(":scope > .ticket-card");
    let empty = lane.querySelector(":scope > .board-empty-state");
    if (cards.length) empty?.remove();
    else if (!empty) {
      empty = document.createElement("p");
      empty.className = "board-empty-state";
      empty.textContent = "No tickets here.";
      lane.append(empty);
    }

    const count = lane.closest(".board-column").querySelector("[data-testid^='column-count-']");
    if (!count.textContent.trim().endsWith("+")) count.textContent = String(cards.length);
  }

  document.addEventListener("dragstart", (event) => {
    const card = event.target.closest(".ticket-card[draggable='true']");
    if (!card) return;
    draggedCard = card;
    card.classList.add("is-dragging");
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", card.id);
  });

  document.addEventListener("dragend", () => {
    draggedCard?.classList.remove("is-dragging");
    document.querySelectorAll("[data-drop-status].is-drag-over").forEach((lane) => lane.classList.remove("is-drag-over"));
    draggedCard = null;
  });

  document.addEventListener("dragover", (event) => {
    const lane = event.target.closest("[data-drop-status]");
    if (!lane || !draggedCard) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = "move";
    document.querySelectorAll("[data-drop-status].is-drag-over").forEach((other) => other.classList.toggle("is-drag-over", other === lane));
  });

  document.addEventListener("dragleave", (event) => {
    const lane = event.target.closest("[data-drop-status]");
    if (lane && !lane.contains(event.relatedTarget)) lane.classList.remove("is-drag-over");
  });

  document.addEventListener("drop", async (event) => {
    const lane = event.target.closest("[data-drop-status]");
    const card = draggedCard;
    if (!lane || !card) return;
    event.preventDefault();
    lane.classList.remove("is-drag-over");

    const source = card.closest("[data-drop-status]");
    if (source === lane) return;
    const board = lane.closest(".project-board");
    const body = new FormData();
    body.append("status", lane.dataset.dropStatus);
    body.append("_csrf", board.dataset.boardCsrf);

    card.setAttribute("aria-busy", "true");
    try {
      const response = await fetch(card.dataset.ticketStatusUrl, {
        method: "POST",
        body,
        credentials: "same-origin",
        headers: { "HX-Request": "true" },
      });
      if (!response.ok) throw new Error();
      lane.append(card);
      refreshLane(source);
      refreshLane(lane);
      setDragStatus(board, `Moved ticket to ${lane.dataset.dropStatus.replaceAll("_", " ").toLowerCase()}.`);
    } catch {
      setDragStatus(board, "Could not move ticket. Try again.");
    } finally {
      card.removeAttribute("aria-busy");
    }
  });
})();
