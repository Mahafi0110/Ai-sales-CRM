// Any <select data-autosubmit> sends its form as soon as the choice changes (used on the pipeline board).
document.addEventListener("change", function (event) {
  const el = event.target;
  if (el.matches("select[data-autosubmit]")) {
    el.form.submit();
  }
});

// <button data-copy-target="someTextareaId"> copies that box's text.
document.addEventListener("click", function (event) {
  const button = event.target.closest("[data-copy-target]");
  if (!button) return;
  const box = document.getElementById(button.dataset.copyTarget);
  navigator.clipboard.writeText(box.value).then(function () {
    const old = button.innerHTML;
    button.textContent = "Copied";
    setTimeout(function () { button.innerHTML = old; }, 1500);
  });
});

// <button data-fill-target="boxId" data-fill-text="..."> puts example text into a text box.
document.addEventListener("click", function (event) {
  const button = event.target.closest("[data-fill-target]");
  if (!button) return;
  const box = document.getElementById(button.dataset.fillTarget);
  box.value = button.dataset.fillText;
  box.focus();
});

// Show that the assistant is working (a request can take a while on the free AI tier).
document.addEventListener("submit", function (event) {
  if (event.target.id !== "assistantForm") return;
  const button = document.getElementById("assistantSubmit");
  button.disabled = true;
  button.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Working...';
});

// Show how many approvals are waiting next to "Approvals" in the menu.
document.addEventListener("DOMContentLoaded", function () {
  const badge = document.getElementById("approvalBadge");
  if (badge) {
    fetch("/api/approvals/count", { credentials: "same-origin" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        if (data && data.pending > 0) {
          badge.textContent = data.pending;
          badge.classList.remove("d-none");
        }
      })
      .catch(function () {});
  }

  const shell = document.querySelector(".app-shell");
  const toggle = document.querySelector("[data-sidebar-toggle]");
  const close = document.querySelector("[data-sidebar-close]");
  if (!shell || !toggle) return;

  function setSidebarOpen(open) {
    shell.classList.toggle("sidebar-open", open);
    toggle.setAttribute("aria-expanded", String(open));
  }

  toggle.addEventListener("click", function () {
    setSidebarOpen(!shell.classList.contains("sidebar-open"));
  });
  if (close) close.addEventListener("click", function () { setSidebarOpen(false); });
  shell.querySelectorAll(".sidebar .nav-link").forEach(function (link) {
    link.addEventListener("click", function () { setSidebarOpen(false); });
  });
  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") setSidebarOpen(false);
  });
});
