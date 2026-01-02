(function () {
    const TOKEN_KEY = "ghost_admin_token";

    const getToken = () => localStorage.getItem(TOKEN_KEY);
    const setToken = (token) => localStorage.setItem(TOKEN_KEY, token);
    const clearToken = () => localStorage.removeItem(TOKEN_KEY);

    const setUserInfo = (principal) => {
        const el = document.querySelector("[data-user-info]");
        if (!el) return;
        if (!principal) {
            el.textContent = "未登录";
            return;
        }
        const scope = principal.scope_team_id ? ` / Team ${principal.scope_team_id}` : "";
        el.textContent = `${principal.display_name} (${principal.role}${scope})`;
    };

    async function apiFetch(path, options = {}) {
        const headers = new Headers(options.headers || {});
        const token = options.token || getToken();
        if (token) {
            headers.set("Authorization", `Bearer ${token}`);
        }
        if (options.body && !(options.body instanceof FormData) && !headers.has("Content-Type")) {
            headers.set("Content-Type", "application/json");
        }
        const response = await fetch(path, { ...options, headers });
        const contentType = response.headers.get("content-type") || "";
        let data = null;
        if (response.status !== 204) {
            if (contentType.includes("application/json")) {
                data = await response.json();
            } else {
                data = await response.text();
            }
        }
        if (response.status === 401 && !options.skipAuthRedirect) {
            clearToken();
            window.location.assign("/admin/login");
            throw { status: response.status, data };
        }
        if (!response.ok) {
            const detail = typeof data === "string" ? data : data?.detail || "请求失败";
            throw { status: response.status, data: detail };
        }
        return data;
    }

    async function verifySession(opts = {}) {
        const token = opts.token || getToken();
        if (!token) {
            if (!opts.skipAuthRedirect) {
                window.location.assign("/admin/login");
            }
            setUserInfo(null);
            return null;
        }
        try {
            const principal = await apiFetch("/api/session/verify", {
                method: "POST",
                token,
                skipAuthRedirect: opts.skipAuthRedirect ?? true,
            });
            setUserInfo(principal);
            window.currentPrincipal = principal;
            return principal;
        } catch (err) {
            clearToken();
            if (!opts.skipAuthRedirect) {
                window.location.assign("/admin/login");
            }
            return null;
        }
    }

    async function requireAuth() {
        return verifySession({ skipAuthRedirect: false });
    }

    function normalizeDateInput(value) {
        if (typeof value !== "string") return value;
        const raw = value.trim();
        if (!raw) return raw;

        // If backend returns a naive datetime (no timezone), treat it as UTC.
        // Common cases: "YYYY-MM-DDTHH:mm:ss(.sss)" or "YYYY-MM-DD HH:mm:ss(.sss)".
        const hasTz = /([zZ]|[+-]\d{2}:\d{2})$/.test(raw);
        if (hasTz) return raw;

        const isoLike = /^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(\.\d+)?$/.test(raw);
        if (isoLike) return raw.replace(" ", "T") + "Z";
        return raw;
    }

    function formatDate(value) {
        if (!value) return "—";
        const d = new Date(normalizeDateInput(value));
        if (Number.isNaN(d.getTime())) return value;
        return d.toLocaleString();
    }

    function showStatus(el, message, type = "info") {
        if (!el) return;
        el.textContent = message || "";
        el.dataset.type = type;
        el.hidden = !message;
    }

    function setupLogout() {
        const btn = document.getElementById("logout-btn");
        if (!btn) return;
        btn.addEventListener("click", () => {
            clearToken();
            window.location.assign("/admin/login");
        });
    }

    document.addEventListener("DOMContentLoaded", () => {
        setupLogout();
        const page = document.body.dataset.page;
        if (page && page !== "login") {
            verifySession({ skipAuthRedirect: false });
        }
    });

    window.GhostAdmin = {
        apiFetch,
        getToken,
        setToken,
        clearToken,
        verifySession,
        requireAuth,
        formatDate,
        showStatus,
        setUserInfo,
    };
})();
