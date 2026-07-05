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

  function extractIntentLocally(message) {
    const roleName = config.supportedRoles.find((role) =>
      message.toLowerCase().includes(role.toLowerCase())
    );

    const durationMatch = message.match(/(\d+)\s*(?:hour|hours|hr|hrs)\b/i);
    const ticketMatch = message.match(/\bTicket[\w-]+\b/i);

    const missing = [];
    if (!roleName) missing.push("roleName");
    if (!durationMatch) missing.push("durationHours");
    if (!ticketMatch) missing.push("ticketNumber");

    if (missing.length > 0) {
      throw new Error(`Missing required information: ${missing.join(", ")}`);
    }

    const durationHours = Number.parseInt(durationMatch[1], 10);
    const ticketNumber = ticketMatch[0];

    return {
      roleName,
      durationHours,
      ticketNumber,
      justification: ticketNumber
    };
  }

  function extractIntent() {
    try {
      currentPayload = extractIntentLocally(elements.promptInput.value);
      elements.payloadOutput.textContent = JSON.stringify(currentPayload, null, 2);
      elements.resultOutput.textContent = "Payload ready. Review it, then activate PIM.";
    } catch (error) {
      currentPayload = null;
      elements.payloadOutput.textContent = "{}";
      elements.resultOutput.textContent = error.message;
    }

    renderAuthState();
  }

  async function activatePim() {
    if (!currentPayload) {
      extractIntent();
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

      elements.resultOutput.textContent = JSON.stringify(
        {
          status: response.status,
          body: responseBody
        },
        null,
        2
      );
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
  elements.extractButton.addEventListener("click", extractIntent);
  elements.activateButton.addEventListener("click", activatePim);

  initialize();
})();
