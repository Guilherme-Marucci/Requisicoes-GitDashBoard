/* Integração do login, cadastro corporativo e recuperação de senha com os endpoints Flask (/api/auth/*). */
(() => {
  const form = document.querySelector("#login-form");
  const userField = document.querySelector("#login-user");
  const passwordField = document.querySelector("#login-password");
  const toggle = document.querySelector("#password-toggle");
  const alertBox = document.querySelector("#login-alert");
  const infoBox = document.querySelector("#login-info");
  const submitButton = document.querySelector("#login-submit");

  const registerDialog = document.querySelector("#register-dialog");
  const registerForm = document.querySelector("#register-form");
  const registerAlert = document.querySelector("#register-alert");
  const registerButton = document.querySelector("#register-toggle");

  const recoveryDialog = document.querySelector("#recovery-dialog");
  const recoveryForm = document.querySelector("#recovery-form");
  const recoveryAlert = document.querySelector("#recovery-alert");
  const recoveryButton = document.querySelector("#recovery-toggle");

  const resetDialog = document.querySelector("#reset-dialog");
  const resetForm = document.querySelector("#reset-form");
  const resetAlert = document.querySelector("#reset-alert");
  const resetTokenInput = document.querySelector("#reset-token");

  if (!form || !userField || !passwordField) return;

  function clearErrors() {
    if (alertBox) {
      alertBox.hidden = true;
      alertBox.textContent = "";
    }
    [userField, passwordField].forEach((field) => {
      field.removeAttribute("aria-invalid");
      field.removeAttribute("aria-describedby");
    });
  }

  function showError(message, targetField) {
    if (infoBox) infoBox.hidden = true;
    if (alertBox) {
      alertBox.textContent = message;
      alertBox.hidden = false;
    }
    if (targetField) {
      targetField.setAttribute("aria-invalid", "true");
      if (alertBox) targetField.setAttribute("aria-describedby", "login-alert");
      targetField.focus();
    }
  }

  function showInfo(message) {
    clearErrors();
    if (infoBox) {
      infoBox.textContent = message;
      infoBox.hidden = false;
    }
  }

  function resetPasswordVisibility() {
    passwordField.type = "password";
    if (!toggle) return;
    toggle.innerHTML = '<i data-lucide="eye" aria-hidden="true"></i><span>Mostrar</span>';
    toggle.setAttribute("aria-pressed", "false");
  }

  if (toggle) {
    toggle.hidden = false;
    toggle.addEventListener("click", () => {
      const visible = passwordField.type === "password";
      passwordField.type = visible ? "text" : "password";
      toggle.innerHTML = visible
        ? '<i data-lucide="eye-off" aria-hidden="true"></i><span>Ocultar</span>'
        : '<i data-lucide="eye" aria-hidden="true"></i><span>Mostrar</span>';
      toggle.setAttribute("aria-pressed", String(visible));
    });
  }

  userField.addEventListener("input", clearErrors);
  passwordField.addEventListener("input", clearErrors);

  form.addEventListener("submit", (event) => {
    const userValue = userField.value.trim();
    const passwordValue = passwordField.value;

    if (!userValue) {
      event.preventDefault();
      showError("Informe seu e-mail corporativo.", userField);
      return;
    }
    if (!passwordValue) {
      event.preventDefault();
      showError("Informe sua senha.", passwordField);
      return;
    }

    resetPasswordVisibility();
    if (submitButton) submitButton.disabled = true;
  });

  // Cadastro corporativo -> POST /api/auth/registrar
  if (registerDialog && registerForm && registerButton) {
    registerButton.addEventListener("click", () => {
      registerForm.reset();
      registerAlert.hidden = true;
      registerDialog.showModal();
    });
    document.querySelector("#register-close")?.addEventListener("click", () => registerDialog.close());
    document.querySelector("#register-cancel")?.addEventListener("click", () => registerDialog.close());

    registerForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      registerAlert.hidden = true;
      const nome = document.querySelector("#register-name")?.value.trim() || "";
      const email = document.querySelector("#register-email")?.value.trim().toLowerCase() || "";
      const telefone = document.querySelector("#register-tel")?.value.trim() || "";
      const senha = document.querySelector("#register-password")?.value || "";
      const confirmacao = document.querySelector("#register-password-confirm")?.value || "";

      if (!email.endsWith("@ssonic.com.br")) {
        registerAlert.textContent = "Domínio corporativo não autorizado. Utilize seu e-mail @ssonic.com.br.";
        registerAlert.hidden = false;
        return;
      }
      if (senha.length < 8) {
        registerAlert.textContent = "A senha deve conter no mínimo 8 caracteres.";
        registerAlert.hidden = false;
        return;
      }
      if (senha !== confirmacao) {
        registerAlert.textContent = "As senhas não coincidem.";
        registerAlert.hidden = false;
        return;
      }

      try {
        const res = await fetch("/api/auth/registrar", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ nome, email, telefone, senha }),
        });
        const data = await res.json();
        if (!res.ok) {
          registerAlert.textContent = data.erro || "Não foi possível concluir o cadastro.";
          registerAlert.hidden = false;
          return;
        }
        registerDialog.close();
        userField.value = email;
        showInfo(data.mensagem || "Cadastro realizado. Verifique seu e-mail corporativo para ativar a conta.");
      } catch {
        registerAlert.textContent = "Falha de comunicação com o servidor.";
        registerAlert.hidden = false;
      }
    });
  }

  // Esqueci a senha -> POST /api/auth/esqueci-senha
  if (recoveryDialog && recoveryForm && recoveryButton) {
    recoveryButton.addEventListener("click", () => {
      recoveryForm.reset();
      recoveryAlert.hidden = true;
      recoveryDialog.showModal();
    });
    document.querySelector("#recovery-close")?.addEventListener("click", () => recoveryDialog.close());
    document.querySelector("#recovery-cancel")?.addEventListener("click", () => recoveryDialog.close());

    recoveryForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      recoveryAlert.hidden = true;
      const email = document.querySelector("#recovery-email")?.value.trim().toLowerCase() || "";
      if (!email.endsWith("@ssonic.com.br")) {
        recoveryAlert.textContent = "Domínio corporativo não autorizado.";
        recoveryAlert.hidden = false;
        return;
      }
      try {
        const res = await fetch("/api/auth/esqueci-senha", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email }),
        });
        const data = await res.json();
        if (!res.ok) {
          recoveryAlert.textContent = data.erro || "Não foi possível processar a solicitação.";
          recoveryAlert.hidden = false;
          return;
        }
        recoveryDialog.close();
        showInfo(data.mensagem);
      } catch {
        recoveryAlert.textContent = "Falha de comunicação com o servidor.";
        recoveryAlert.hidden = false;
      }
    });
  }

  // Redefinir senha via link (?reset_token=...) -> POST /api/auth/redefinir-senha
  const params = new URLSearchParams(window.location.search);
  const urlResetToken = params.get("reset_token");
  if (urlResetToken && resetDialog && resetForm && resetTokenInput) {
    resetTokenInput.value = urlResetToken;
    resetDialog.showModal();
    document.querySelector("#reset-close")?.addEventListener("click", () => resetDialog.close());

    resetForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      resetAlert.hidden = true;
      const nova_senha = document.querySelector("#reset-password")?.value || "";
      const confirmacao = document.querySelector("#reset-password-confirm")?.value || "";
      if (nova_senha.length < 8) {
        resetAlert.textContent = "A nova senha deve conter no mínimo 8 caracteres.";
        resetAlert.hidden = false;
        return;
      }
      if (nova_senha !== confirmacao) {
        resetAlert.textContent = "As senhas não coincidem.";
        resetAlert.hidden = false;
        return;
      }
      try {
        const res = await fetch("/api/auth/redefinir-senha", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ token: resetTokenInput.value, nova_senha }),
        });
        const data = await res.json();
        if (!res.ok) {
          resetAlert.textContent = data.erro || "Token inválido ou expirado.";
          resetAlert.hidden = false;
          return;
        }
        resetDialog.close();
        window.history.replaceState({}, document.title, window.location.pathname);
        showInfo(data.mensagem || "Senha redefinida com sucesso. Você já pode entrar.");
      } catch {
        resetAlert.textContent = "Falha de comunicação com o servidor.";
        resetAlert.hidden = false;
      }
    });
  }

  window.addEventListener("pageshow", (event) => {
    resetPasswordVisibility();
    if (submitButton) submitButton.disabled = false;
    if (event.persisted) {
      passwordField.value = "";
    }
  });
})();
