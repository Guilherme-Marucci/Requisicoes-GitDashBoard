/* Carregamento dos fragmentos locais e comportamentos compartilhados do painel. */
(async () => {
  // Centraliza Lucide também para templates e cartões inseridos após filtros.
  // SVGs já convertidos não disparam outra conversão sem novos placeholders.
  function renderIcons() {
    if (!document.querySelector("i[data-lucide]")) return;
    window.lucide?.createIcons({ attrs: { "aria-hidden": "true", focusable: "false" } });
  }
  new MutationObserver((changes) => {
    const hasNewIcons = changes.some((change) => [...change.addedNodes].some((node) =>
      node.nodeType === Node.ELEMENT_NODE &&
      (node.matches("i[data-lucide]") || node.querySelector("i[data-lucide]"))));
    if (hasNewIcons) renderIcons();
  }).observe(document.body, { childList: true, subtree: true });
  renderIcons();
  // A página recebe as URLs do Flask; a localização física dos componentes fica no backend.
  const templates = new Map([
    ["sidebar", "aside#sidebar"],
    ["topbar", "header.topbar"],
    ["footer", "footer.footer"],
  ]);
  let savedTheme = "dark";
  try { savedTheme = localStorage.getItem("requisicoes-preview-theme") || "dark"; } catch { /* Preferência opcional. */ }
  document.documentElement.dataset.theme = savedTheme === "light" ? "light" : "dark";

  // Cada lista mantém colunas fixas por posição: abrir à direita não desloca a pilha esquerda.
  // A ordem do DOM é preservada para teclado, leitura e passagem para uma coluna no celular.
  let pendingCardLayout = false;
  function scheduleCardLayout() {
    if (pendingCardLayout) return;
    pendingCardLayout = true;
    requestAnimationFrame(() => {
      pendingCardLayout = false;
      document.querySelectorAll("[data-card-stack]").forEach((stack) => {
        if (stack.closest("details:not([open])") || !stack.getBoundingClientRect().width) return;
        const css = getComputedStyle(stack);
        const columns = Number(css.getPropertyValue("--card-columns")) || 1;
        const gap = parseFloat(css.getPropertyValue("--card-gap")) || 0;
        const cards = [...stack.children].filter((card) => !card.hidden);
        const heights = cards.map((card) => Math.ceil(card.getBoundingClientRect().height));
        const nextRow = Array(columns).fill(1);
        stack.classList.add("is-measured");
        cards.forEach((card, index) => {
          const column = index % columns;
          const height = Math.max(1, heights[index]);
          card.style.gridColumn = String(column + 1);
          card.style.gridRow = `${nextRow[column]} / span ${height}`;
          nextRow[column] += height + gap;
        });
      });
    });
  }

  // Observa também listas inseridas pelos filtros/iterações e libera os nós removidos.
  const observedCards = new Set();
  const cardResize = new ResizeObserver(scheduleCardLayout);
  function observeCardStacks() {
    const current = new Set(document.querySelectorAll("[data-card-stack], [data-card-stack] > *"));
    observedCards.forEach((node) => {
      if (!current.has(node)) {
        cardResize.unobserve(node);
        observedCards.delete(node);
      }
    });
    current.forEach((node) => {
      if (!observedCards.has(node)) {
        observedCards.add(node);
        cardResize.observe(node);
      }
    });
    scheduleCardLayout();
  }
  const mainContent = document.querySelector("#conteudo");
  if (mainContent) {
    new MutationObserver(observeCardStacks).observe(mainContent, {
      childList: true,
      subtree: true,
    });
  }
  document.addEventListener("toggle", scheduleCardLayout, true);
  window.addEventListener("resize", scheduleCardLayout);
  observeCardStacks();

  // Os cartões não dependem do carregamento dos menus; continuam funcionando se um fragmento falhar.
  const loaded = await Promise.all([...document.querySelectorAll("[data-layout]")].map(async (slot) => {
    try {
      const source = templates.get(slot.dataset.layout);
      if (!source) throw new Error("Template desconhecido");
      if (!/^https?:$/.test(location.protocol)) throw new Error("Servidor HTTP necessário");
      if (!slot.dataset.componentUrl) throw new Error("URL do componente ausente");
      const url = new URL(slot.dataset.componentUrl, location.href);
      if (url.origin !== location.origin) throw new Error("Componente fora da aplicação");
      const response = await fetch(url, { cache: "no-cache" });
      if (response.status === 401) {
        window.location.assign("/login?next=" + encodeURIComponent(location.pathname));
        return false;
      }
      if (!response.ok) throw new Error("Template indisponível");
      const template = document.createElement("template");
      template.innerHTML = await response.text();
      if (!template.content.querySelector(source)) throw new Error("Template inválido");
      // Substituir o ponto inteiro mantém a topbar como filha direta de app-main: sticky não fica preso a um wrapper.
      slot.replaceWith(template.content.cloneNode(true));
      return true;
    } catch {
      slot.className = "layout-error";
      slot.setAttribute("role", "alert");
      const message = document.createElement("p");
      message.textContent = location.protocol === "file:"
        ? "Abra o painel por um servidor HTTP local para carregar os menus."
        : "Não foi possível carregar parte da navegação. Tente recarregar o painel.";
      const retry = document.createElement("button");
      retry.type = "button";
      retry.className = "clear-button";
      retry.textContent = "Recarregar";
      retry.addEventListener("click", () => location.reload());
      slot.replaceChildren(message, retry);
      return false;
    }
  }));
  if (loaded.includes(false)) return;

  // No próprio painel, âncoras preservam filtros e cartões abertos sem recarregar.
  document.querySelectorAll(".sidebar a[href]").forEach((link) => {
    if (document.body.dataset.page === "dashboard" && link.hash && document.getElementById(link.hash.slice(1))) {
      link.setAttribute("href", link.hash);
    }
  });
  const activePage = document.body.dataset.page;
  if (activePage && document.querySelector(`.main-nav__link[data-page-link="${activePage}"]`)) {
    document.querySelectorAll(".main-nav__link").forEach((link) => {
      const active = link.dataset.pageLink === activePage;
      link.classList.toggle("is-active", active);
      if (active) link.setAttribute("aria-current", "page");
      else link.removeAttribute("aria-current");
    });
  }
  const pageTitle = document.body.dataset.pageTitle;
  const breadcrumbTitle = document.querySelector(".breadcrumb strong");
  if (pageTitle && breadcrumbTitle) breadcrumbTitle.textContent = pageTitle;

  function applyTheme(theme) {
    document.documentElement.dataset.theme = theme;
    const button = document.querySelector("#theme-toggle");
    // Acesso mantém o tema aplicado, mas não oferece alternância na própria tela.
    if (!button) return;
    button.innerHTML = theme === "dark"
      ? '<i data-lucide="sun"></i><span>Tema claro</span>'
      : '<i data-lucide="moon"></i><span>Tema escuro</span>';
    button.setAttribute("aria-label", theme === "dark" ? "Ativar tema claro" : "Ativar tema escuro");
  }

  function setMenuOpen(open) {
    if (!document.querySelector("#menu-toggle")) return;
    document.querySelector("#sidebar").classList.toggle("is-open", open);
    document.querySelector("#sidebar-backdrop").hidden = !open;
    const button = document.querySelector("#menu-toggle");
    button.setAttribute("aria-expanded", String(open));
    button.setAttribute("aria-label", open ? "Fechar menu" : "Abrir menu");
  }

  const menuButton = document.querySelector("#menu-toggle");
  // A página de acesso reutiliza o tema e o rodapé sem carregar a navegação do painel.
  menuButton?.addEventListener("click", () => setMenuOpen(menuButton.getAttribute("aria-expanded") !== "true"));
  document.querySelector("#sidebar-backdrop")?.addEventListener("click", () => setMenuOpen(false));
  document.querySelectorAll(".main-nav__link").forEach((link) => link.addEventListener("click", () => {
    document.querySelectorAll(".main-nav__link").forEach((item) => item.classList.remove("is-active"));
    link.classList.add("is-active");
    setMenuOpen(false);
  }));
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && menuButton?.getAttribute("aria-expanded") === "true") {
      setMenuOpen(false);
      menuButton.focus();
    }
  });

  applyTheme(document.documentElement.dataset.theme);
  document.querySelector("#theme-toggle")?.addEventListener("click", () => {
    const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    applyTheme(next);
    try { localStorage.setItem("requisicoes-preview-theme", next); } catch { /* O tema continua ativo nesta página. */ }
  });

  // Ao voltar ao desktop, o painel móvel não deve manter o fundo bloqueado.
  const mobile = window.matchMedia("(max-width: 920px)");
  mobile.addEventListener("change", () => setMenuOpen(false));

  // Preferências visuais locais: nunca alteram permissões do backend.
  const profileDialog = document.querySelector("#profile-dialog");
  if (!profileDialog) return;
  const profileButton = document.querySelector("#profile-toggle");
  const profileName = document.querySelector("#profile-name");
  const profileTheme = document.querySelector("#profile-theme");
  const feedback = document.querySelector("#profile-feedback");
  let displayName = document.body.dataset.userName?.trim() || "Equipe de compras";
  try {
    const stored = localStorage.getItem("requisicoes-preview-profile");
    if (stored && stored.trim() && stored.length <= 60) displayName = stored.trim();
  } catch { /* O perfil continua disponível sem persistência local. */ }

  function updateProfile() {
    profileButton.title = `Ajustar perfil de ${displayName}`;
    profileButton.setAttribute("aria-label", `Ajustar perfil de ${displayName}`);
  }
  updateProfile();

  profileButton.addEventListener("click", () => {
    setMenuOpen(false);
    feedback.hidden = true;
    profileName.value = displayName;
    profileName.setCustomValidity("");
    profileTheme.value = document.documentElement.dataset.theme;
    profileDialog.showModal();
    profileName.focus();
  });
  document.querySelector("#profile-close").addEventListener("click", () => profileDialog.close());
  document.querySelector("#profile-cancel").addEventListener("click", () => profileDialog.close());
  profileDialog.addEventListener("close", () => profileButton.focus());
  profileName.addEventListener("input", () => profileName.setCustomValidity(""));
  document.querySelector("#profile-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const name = profileName.value.trim();
    if (!name) {
      profileName.setCustomValidity("Informe o nome de exibição.");
      profileName.reportValidity();
      return;
    }
    displayName = name;
    const theme = profileTheme.value === "light" ? "light" : "dark";
    applyTheme(theme);
    updateProfile();
    let persisted = true;
    try {
      localStorage.setItem("requisicoes-preview-profile", displayName);
      localStorage.setItem("requisicoes-preview-theme", theme);
    } catch { persisted = false; }
    profileDialog.close();
    feedback.textContent = persisted ? "Preferências salvas neste navegador."
      : "Preferências aplicadas nesta aba. O navegador não permitiu salvá-las.";
    feedback.hidden = false;
  });
})();
