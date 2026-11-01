/* Aplica o tema salvo antes da pintura (evita flash). Sem sessão, usa o localStorage. */
(function () {
  var TEMAS = ["dark", "dark-pink", "dark-green", "dark-blue", "dark-red", "dark-purple"];
  var root = document.documentElement;
  if (root.hasAttribute("data-theme-local")) {
    try {
      var salvo = localStorage.getItem("painel-tema");
      if (TEMAS.indexOf(salvo) !== -1) root.setAttribute("data-theme", salvo);
    } catch (e) { /* preferência opcional */ }
  }
})();

