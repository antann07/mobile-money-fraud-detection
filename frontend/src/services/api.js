// ============================================================
// api.js — Central API helper for the frontend
// ============================================================
//
// Production-hardened with:
//   - Automatic 401/403 handling (expired or invalid token)
//   - Token presence check before authenticated requests
//   - Clean redirect to /login when session is invalid
//   - No console.log in production (only in dev)
//
// Backend routes used by the frontend:
//   PUBLIC (no token):
//     POST /api/auth/register
//     POST /api/auth/login
//     GET  /api/health
//
//   PROTECTED (requires JWT in Authorization header):
//     POST /api/wallet/add
//     GET  /api/wallet
//     POST /api/transactions/add
//     GET  /api/transactions
//     GET  /api/predictions
// ============================================================

// VITE_API_BASE controls where the frontend sends API requests.
//   Development (npm run dev):  "http://127.0.0.1:5001"  (set in .env)
//   Docker / production:        ""  (empty → same-origin, Nginx proxies /api)
// NOTE: We must NOT use || here — empty string is intentional for Docker mode.
const API_BASE =
  import.meta.env.VITE_API_BASE !== undefined &&
  import.meta.env.VITE_API_BASE !== null
    ? import.meta.env.VITE_API_BASE
    : "http://127.0.0.1:5001";
const IS_DEV = import.meta.env.DEV;

// ── Helpers ────────────────────────────────────────────────
function _log(...args) {
  if (IS_DEV) console.log("[api]", ...args);
}

// ============================================================
// GET response cache + in-flight deduplication
// ============================================================
// Problems this solves:
//   1. React StrictMode double-invokes useEffect in development,
//      causing every page to fire the same request twice on mount.
//   2. Dashboard and MessageHistory both fetch /api/message-checks/history
//      on mount. Without a cache they hit the same endpoint twice in
//      rapid succession, which can trigger the 20-requests/min limit.
//   3. If two components request the same URL at the exact same moment,
//      the dedup map returns the shared in-flight promise instead of
//      launching a second network call.
//
// TTL is kept short (20 s) so that navigating back to a page returns
// fresh data while protecting against burst-on-mount patterns.
// ============================================================

const _inFlight = new Map(); // path → Promise<result>  (while request is running)
const _cache    = new Map(); // path → { result, ts }    (after request completes)
const CACHE_TTL = 20_000;   // 20 seconds

function _cacheGet(path) {
  const entry = _cache.get(path);
  if (!entry) return null;
  if (Date.now() - entry.ts > CACHE_TTL) { _cache.delete(path); return null; }
  return entry.result;
}

function _cacheSet(path, result) {
  _cache.set(path, { result, ts: Date.now() });
}

/**
 * Bust cached GET results whose key starts with `prefix`.
 * Call this from POST/PATCH/DELETE handlers after a write that would
 * make a cached list stale (e.g. after submitting a new message check,
 * call bustCache("/api/message-checks") to force a fresh history load).
 *
 * @param {string} prefix  URL prefix to match (e.g. "/api/wallet")
 */
function bustCache(prefix) {
  for (const key of _cache.keys()) {
    if (key.startsWith(prefix)) _cache.delete(key);
  }
}

/**
 * Clear auth state and redirect to login.
 * Called when the backend returns 401 (expired/invalid token).
 */
function handleUnauthorized() {
  localStorage.removeItem("token");
  localStorage.removeItem("user"); // FIX: also clear stored user on logout/expiry
  // Only redirect if not already on login/register page
  const path = window.location.pathname;
  if (path !== "/login" && path !== "/register") {
    window.location.href = "/login";
  }
}

// ============================================================
// authFetch — reusable helper for authenticated API requests
// ============================================================
// GET requests are served from the 20-second cache when a fresh
// entry exists, or deduplicated if the same request is in-flight.
// POST / PATCH / DELETE requests always go to the network.
// ============================================================
async function authFetch(path, method = "GET", body = null) {
  const token = localStorage.getItem("token");

  // If there's no token at all, redirect immediately
  if (!token) {
    handleUnauthorized();
    return {
      data: { success: false, errors: ["No authentication token. Please login."] },
      response: { ok: false, status: 401 },
    };
  }

  // ── GET cache check ────────────────────────────────────
  if (method === "GET" && !body) {
    const cached = _cacheGet(path);
    if (cached) {
      _log(`Cache hit: ${path}`);
      return cached;
    }

    // ── In-flight deduplication ────────────────────────
    // If an identical GET is already pending, share the promise rather
    // than sending a second network request for the same data.
    if (_inFlight.has(path)) {
      _log(`In-flight dedup: ${path}`);
      return _inFlight.get(path);
    }
  }

  const url = `${API_BASE}${path}`;
  _log(`${method} ${url}`);

  const options = {
    method,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
  };

  if (body) {
    options.body = JSON.stringify(body);
  }

  // Wrap the fetch in an async IIFE so we can register it in _inFlight
  // before the first await, then clean up in .finally().
  const fetchPromise = (async () => {
    const response = await fetch(url, options);

    // 401 = token expired or invalid → clear token and redirect to login
    // 403 = forbidden (e.g. "wallet not yours") → do NOT redirect, let caller handle
    if (response.status === 401) {
      _log("401 Unauthorized — token expired or invalid, redirecting to login");
      handleUnauthorized();
      const data = await response.json().catch(() => ({
        success: false,
        errors: ["Session expired. Please login again."],
      }));
      return { data, response: { ok: false, status: 401 } };
    }

    const data = await response.json().catch(() => ({
      success: false,
      errors: ["Invalid server response."],
    }));
    _log(`Status: ${response.status}`);

    // Cache successful GET responses using a plain response-like object
    // (the real Response body stream is already consumed by .json() above)
    const result = { data, response: { ok: response.ok, status: response.status } };
    if (method === "GET" && response.ok) {
      _cacheSet(path, result);
    }

    return result;
  })().finally(() => {
    _inFlight.delete(path);
  });

  // Register in the dedup map only for GET requests
  if (method === "GET" && !body) {
    _inFlight.set(path, fetchPromise);
  }

  return fetchPromise;
}

// ============================================================
// publicFetch — for endpoints that don't need a token
// ============================================================
async function publicFetch(path) {
  const url = `${API_BASE}${path}`;
  const response = await fetch(url);
  const data = await response.json().catch(() => ({ success: false, errors: ["Invalid server response."] }));
  return { data, response };
}

// ============================================================
// authFetchMultipart — for file uploads (no Content-Type header)
// ============================================================
async function authFetchMultipart(path, formData) {
  const token = localStorage.getItem("token");

  if (!token) {
    handleUnauthorized();
    return {
      data: { success: false, errors: ["No authentication token. Please login."] },
      response: { ok: false, status: 401 },
    };
  }

  const url = `${API_BASE}${path}`;
  _log(`POST (multipart) ${url}`);

  const response = await fetch(url, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: formData,
  });

  if (response.status === 401) {
    _log("401 Unauthorized — token expired or invalid, redirecting to login");
    handleUnauthorized();
    const data = await response.json().catch(() => ({ success: false, errors: ["Session expired. Please login again."] }));
    return { data, response };
  }

  const data = await response.json().catch(() => ({ success: false, errors: ["Invalid server response."] }));
  _log(`Status: ${response.status}`);

  return { data, response };
}

// ============================================================
// refreshToken — re-issues a JWT with the user's current DB role
// ============================================================
// Call this when the user is getting 403 but should be admin,
// e.g. after a role promotion in the DB.
async function refreshToken() {
  const token = localStorage.getItem("token");
  if (!token) return false;

  const url = `${API_BASE}/api/auth/refresh`;
  _log("Refreshing token...");

  try {
    const response = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
    });

    if (response.ok) {
      const data = await response.json();
      if (data.token) {
        localStorage.setItem("token", data.token);
        if (data.user) {
          localStorage.setItem("user", JSON.stringify(data.user));
        }
        _log("Token refreshed successfully, new role:", data.user?.role);
        return true;
      }
    }
  } catch (err) {
    _log("Token refresh failed:", err);
  }
  return false;
}

export { API_BASE, authFetch, authFetchMultipart, publicFetch, refreshToken, bustCache };
