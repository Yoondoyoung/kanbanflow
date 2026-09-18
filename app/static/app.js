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
