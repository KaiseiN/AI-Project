(function () {
  const config = window.PIM_ORCHESTRATOR_CONFIG;
  const redirectUri = config.redirectUri || `${window.location.origin}/orchestrator/`;
  const authorizeEndpoint = `https://login.microsoftonline.com/${config.tenantId}/oauth2/v2.0/authorize`;
  const tokenEndpoint = `https://login.microsoftonline.com/${config.tenantId}/oauth2/v2.0/token`;
  const scopes = ["openid", "profile", config.apiScope].join(" ");

  const elements = {
    accountState: document.getElementById("accountState"),
    signInButton: document.getElementById("signInButton"),
    signOutButton: document.getElementById("signOutButton"),
    promptInput: document.getElementById("promptInput"),
    extractButton: document.getElementById("extractButton"),
    activateButton: document.getElementById("activateButton"),
    confirmationPanel: document.getElementById("confirmationPanel"),
    confirmationText: document.getElementById("confirmationText"),
    payloadOutput: document.getElementById("payloadOutput"),
    resultOutput: document.getElementById("resultOutput")
  };

  let currentPayload = null;
  let tokenRecord = loadTokenRecord();

  async function initialize() {
    try {
      await completeRedirectIfNeeded();
    } catch (error) {
      elements.resultOutput.textContent = error.message;
    }

    tokenRecord = loadTokenRecord();
    renderAuthState();
  }

  function renderAuthState() {
    const signedIn = Boolean(getValidAccessToken());
    const claims = signedIn ? decodeJwtClaims(tokenRecord.accessToken) : null;
    elements.accountState.textContent = signedIn
      ? `Signed in as ${claims.upn || claims.unique_name || claims.name || "user"}`
      : "Signed out";
    elements.signInButton.hidden = signedIn;
    elements.signOutButton.hidden = !signedIn;
    elements.extractButton.disabled = !signedIn;
    elements.activateButton.disabled = !signedIn || !currentPayload;
  }

  async function signIn() {
    const state = crypto.randomUUID();
    const codeVerifier = base64UrlEncode(crypto.getRandomValues(new Uint8Array(32)));
    const codeChallenge = await sha256Base64Url(codeVerifier);

    sessionStorage.setItem("pim_auth_state", state);
    sessionStorage.setItem("pim_code_verifier", codeVerifier);

    const params = new URLSearchParams({
      client_id: config.clientId,
      response_type: "code",
      redirect_uri: redirectUri,
      response_mode: "query",
      scope: scopes,
      state,
      code_challenge: codeChallenge,
      code_challenge_method: "S256"
    });

    window.location.assign(`${authorizeEndpoint}?${params.toString()}`);
  }

  function signOut() {
    sessionStorage.removeItem("pim_token_record");
    tokenRecord = null;
    currentPayload = null;
    elements.payloadOutput.textContent = "{}";
    elements.resultOutput.textContent = "Signed out.";
    renderConfirmation();
    renderAuthState();
  }

  async function completeRedirectIfNeeded() {
    const params = new URLSearchParams(window.location.search);
    const error = params.get("error");
    if (error) {
      throw new Error(`${error}: ${params.get("error_description") || "Sign-in failed."}`);
    }

    const code = params.get("code");
    if (!code) {
      return;
    }

    const actualState = params.get("state");
    const expectedState = sessionStorage.getItem("pim_auth_state");
    const codeVerifier = sessionStorage.getItem("pim_code_verifier");

    if (!expectedState || actualState !== expectedState) {
      throw new Error("Sign-in state validation failed.");
    }

    if (!codeVerifier) {
      throw new Error("Missing PKCE code verifier.");
    }

    const tokenResponse = await fetch(tokenEndpoint, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({
        client_id: config.clientId,
        grant_type: "authorization_code",
        code,
        redirect_uri: redirectUri,
        code_verifier: codeVerifier,
        scope: scopes
      })
    });

    const tokenBody = await tokenResponse.json();
    if (!tokenResponse.ok) {
      throw new Error(tokenBody.error_description || tokenBody.error || "Token exchange failed.");
    }

    tokenRecord = {
      accessToken: tokenBody.access_token,
      expiresAt: Date.now() + tokenBody.expires_in * 1000
    };
    sessionStorage.setItem("pim_token_record", JSON.stringify(tokenRecord));
    sessionStorage.removeItem("pim_auth_state");
    sessionStorage.removeItem("pim_code_verifier");

    window.history.replaceState({}, document.title, window.location.pathname);
  }

  function loadTokenRecord() {
    const rawRecord = sessionStorage.getItem("pim_token_record");
    if (!rawRecord) {
      return null;
    }

    try {
      return JSON.parse(rawRecord);
    } catch {
      sessionStorage.removeItem("pim_token_record");
      return null;
    }
  }

  function getValidAccessToken() {
    if (!tokenRecord || !tokenRecord.accessToken || !tokenRecord.expiresAt) {
      return null;
    }

    if (Date.now() > tokenRecord.expiresAt - 60_000) {
      sessionStorage.removeItem("pim_token_record");
      tokenRecord = null;
      return null;
    }

    return tokenRecord.accessToken;
  }

  async function extractIntentWithBackend(message) {
    const accessToken = getValidAccessToken();
    if (!accessToken) {
      throw new Error("Please sign in again.");
    }

    const response = await fetch(config.intentUrl, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${accessToken}`,
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ message })
    });

    const responseBody = await parseResponseBody(response);
    if (!response.ok) {
      throw new Error(
        formatErrorValue(responseBody.details || responseBody.error || responseBody) ||
          "Intent extraction failed."
      );
    }

    return responseBody;
  }

  async function extractIntent() {
    try {
      elements.extractButton.disabled = true;
      elements.resultOutput.textContent = "Extracting intent...";
      const intentResult = await extractIntentWithBackend(elements.promptInput.value);
      if (intentResult.status === "needs_input") {
        currentPayload = null;
        elements.payloadOutput.textContent = JSON.stringify(intentResult.partialPayload || {}, null, 2);
        elements.resultOutput.textContent = intentResult.message;
        return;
      }

      currentPayload = intentResult;
      elements.payloadOutput.textContent = JSON.stringify(currentPayload, null, 2);
      elements.resultOutput.textContent = "Review the activation details, then activate PIM.";
    } catch (error) {
      currentPayload = null;
      elements.payloadOutput.textContent = "{}";
      elements.resultOutput.textContent = error.message;
    }

    renderConfirmation();
    renderAuthState();
  }

  async function activatePim() {
    if (!currentPayload) {
      await extractIntent();
    }

    if (!currentPayload) {
      return;
    }

    const accessToken = getValidAccessToken();
    if (!accessToken) {
      elements.resultOutput.textContent = "Please sign in again.";
      renderAuthState();
      return;
    }

    elements.activateButton.disabled = true;
    elements.resultOutput.textContent = "Calling Azure Function...";

    try {
      const response = await fetch(config.functionUrl, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${accessToken}`,
          "Content-Type": "application/json"
        },
        body: JSON.stringify(currentPayload)
      });

      const contentType = response.headers.get("content-type") || "";
      const responseBody = contentType.includes("application/json")
        ? await response.json()
        : await response.text();

      elements.resultOutput.textContent = formatActivationResult(response.status, responseBody);
    } catch (error) {
      elements.resultOutput.textContent = buildFetchErrorMessage(error);
    } finally {
      renderAuthState();
    }
  }

  function buildFetchErrorMessage(error) {
    if (error instanceof TypeError && error.message === "Failed to fetch") {
      return [
        "Failed to fetch.",
        "",
        "Most likely cause: the browser blocked the request because the Azure Function App CORS settings do not allow this origin.",
        "",
        "Add this allowed origin in the Function App CORS settings:",
        window.location.origin,
        "",
        "Then restart the Function App and try again."
      ].join("\n");
    }

    return error.message;
  }

  async function parseResponseBody(response) {
    const contentType = response.headers.get("content-type") || "";
    if (contentType.includes("application/json")) {
      return response.json();
    }

    const text = await response.text();
    if (!text) {
      return "";
    }

    try {
      return JSON.parse(text);
    } catch {
      return text;
    }
  }

  function formatErrorValue(value) {
    if (!value) {
      return "";
    }

    if (typeof value === "string") {
      return value;
    }

    return JSON.stringify(value, null, 2);
  }

  function renderConfirmation() {
    if (!currentPayload) {
      elements.confirmationPanel.hidden = true;
      elements.confirmationText.textContent = "";
      return;
    }

    elements.confirmationPanel.hidden = false;
    elements.confirmationText.textContent =
      `${currentPayload.roleName} will be activated for ${currentPayload.durationHours} ` +
      `${currentPayload.durationHours === 1 ? "hour" : "hours"} using ${currentPayload.ticketNumber}.`;
  }

  function formatActivationResult(status, body) {
    if (status === 200 && body && body.message === "pim is already activated") {
      return `${currentPayload.roleName} is already active.`;
    }

    if (body && body.message) {
      return body.message;
    }

    if (status === 201 && body && body.status === "Provisioned") {
      return [
        `${currentPayload.roleName} is active for ${currentPayload.durationHours} ` +
          `${currentPayload.durationHours === 1 ? "hour" : "hours"} using ${currentPayload.ticketNumber}.`,
        "",
        `Request ID: ${body.id}`,
        `PIM status: ${body.status}`
      ].join("\n");
    }

    return JSON.stringify({ status, body }, null, 2);
  }

  async function sha256Base64Url(value) {
    const data = new TextEncoder().encode(value);
    const hash = await crypto.subtle.digest("SHA-256", data);
    return base64UrlEncode(new Uint8Array(hash));
  }

  function base64UrlEncode(bytes) {
    let binary = "";
    bytes.forEach((byte) => {
      binary += String.fromCharCode(byte);
    });

    return btoa(binary)
      .replace(/\+/g, "-")
      .replace(/\//g, "_")
      .replace(/=+$/g, "");
  }

  function decodeJwtClaims(token) {
    const payload = token.split(".")[1];
    const paddedPayload = payload + "=".repeat((4 - (payload.length % 4)) % 4);
    return JSON.parse(atob(paddedPayload.replace(/-/g, "+").replace(/_/g, "/")));
  }

  elements.signInButton.addEventListener("click", signIn);
  elements.signOutButton.addEventListener("click", signOut);
  elements.extractButton.addEventListener("click", () => {
    extractIntent();
  });
  elements.activateButton.addEventListener("click", activatePim);

  initialize();
})();
