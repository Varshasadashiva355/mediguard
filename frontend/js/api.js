/**
 * MediGuard AI – API Client & Fetch Wrapper
 * Handles JWT bearer tokens, automatic 401 redirection, and toast notifications.
 */

const API = {
  baseUrl: window.location.origin.includes(":5000") 
    ? window.location.origin 
    : "http://127.0.0.1:5000",

  /**
   * Core request dispatcher with authorization headers and JSON parsing.
   */
  async request(endpoint, options = {}) {
    const url = endpoint.startsWith("http") ? endpoint : `${this.baseUrl}${endpoint}`;
    const token = localStorage.getItem("mediguard_token");

    const headers = {
      "Content-Type": "application/json",
      ...(token ? { "Authorization": `Bearer ${token}` } : {}),
      ...(options.headers || {})
    };

    try {
      const response = await fetch(url, {
        ...options,
        headers
      });

      // Handle 401 Unauthorized
      if (response.status === 401) {
        localStorage.removeItem("mediguard_token");
        localStorage.removeItem("mediguard_user");
        this.setAuthBanner(true, "Your clinical session has expired or authorization token is missing.");
        if (!window.location.pathname.endsWith("index.html") && window.location.pathname !== "/") {
          this.toast("Session expired. Redirecting to clinical login...", "warning");
          setTimeout(() => { window.location.href = "index.html"; }, 1500);
        }
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.message || "Unauthorized access");
      }

      this.setAuthBanner(false);

      // Handle 503 / Database unavailable
      if (response.status === 503 || response.status === 500) {
        const errJson = await response.clone().json().catch(() => ({}));
        if (errJson.error === "Database Unavailable" || (errJson.message && errJson.message.toLowerCase().includes("database"))) {
          this.setDbUnavailable(true, errJson.message);
        }
      } else {
        this.setDbUnavailable(false);
      }

      const data = await response.json().catch(() => ({}));

      if (!response.ok) {
        const errorMsg = data.message || `Request failed with status ${response.status}`;
        throw new Error(errorMsg);
      }

      return data;
    } catch (err) {
      if (err.name === "TypeError" || (err.message && (err.message.includes("fetch") || err.message.includes("NetworkError") || err.message.includes("Failed to fetch")))) {
        this.setDbUnavailable(true, "Backend or database service is unreachable. Operating in offline/fallback mode.");
      }
      console.error(`API Error on [${options.method || "GET"} ${endpoint}]:`, err);
      throw err;
    }
  },

  setAuthBanner(isAuthError, message = "Session expired or unauthorized. Please sign in to view clinical data.") {
    let banner = document.getElementById("auth-unauthorized-banner");
    if (!banner && document.body) {
      banner = document.createElement("div");
      banner.id = "auth-unauthorized-banner";
      banner.style.cssText = "display:none; background:#FEF2F2; border-bottom:2px solid #DC2626; color:#991B1B; padding:0.75rem 1.5rem; text-align:center; font-weight:600; font-size:0.875rem; position:sticky; top:0; z-index:99999; box-shadow:0 2px 8px rgba(0,0,0,0.1);";
      document.body.prepend(banner);
    }
    if (banner) {
      if (isAuthError) {
        banner.innerHTML = `🔒 <span>${message}</span> &nbsp;&bull;&nbsp; <a href="index.html" style="color:#DC2626; text-decoration:underline; font-weight:700;">Click Here to Sign In</a>`;
        banner.style.display = "block";
      } else {
        banner.style.display = "none";
      }
    }
  },

  setDbUnavailable(isUnavailable, message = "Database Unavailable – live queries paused.") {
    let banner = document.getElementById("db-unavailable-banner");
    if (!banner && document.body) {
      banner = document.createElement("div");
      banner.id = "db-unavailable-banner";
      banner.style.cssText = "display:none; background:#FEF2F2; border-bottom:2px solid #EF4444; color:#991B1B; padding:0.65rem 1.5rem; text-align:center; font-weight:600; font-size:0.875rem; position:sticky; top:0; z-index:9999; box-shadow:0 2px 8px rgba(0,0,0,0.08);";
      document.body.prepend(banner);
    }
    if (banner) {
      if (isUnavailable) {
        banner.innerHTML = `⚠️ <span>${message}</span>`;
        banner.style.display = "block";
      } else {
        banner.style.display = "none";
      }
    }
  },

  get(endpoint, headers = {}) {
    return this.request(endpoint, { method: "GET", headers });
  },

  post(endpoint, body = {}, headers = {}) {
    return this.request(endpoint, {
      method: "POST",
      body: JSON.stringify(body),
      headers
    });
  },

  put(endpoint, body = {}, headers = {}) {
    return this.request(endpoint, {
      method: "PUT",
      body: JSON.stringify(body),
      headers
    });
  },

  delete(endpoint, headers = {}) {
    return this.request(endpoint, { method: "DELETE", headers });
  },

  /**
   * Display toast alert message
   */
  toast(message, type = "info") {
    let container = document.getElementById("toast-container");
    if (!container) {
      container = document.createElement("div");
      container.id = "toast-container";
      container.className = "toast-container";
      document.body.appendChild(container);
    }

    const toast = document.createElement("div");
    toast.className = `toast toast-${type}`;
    
    let icon = "ℹ️";
    if (type === "success") icon = "✅";
    if (type === "error") icon = "❌";
    if (type === "warning") icon = "⚠️";

    toast.innerHTML = `<span>${icon}</span><div style="flex:1;">${message}</div>`;
    container.appendChild(toast);

    setTimeout(() => {
      toast.style.opacity = "0";
      toast.style.transform = "translateX(100%)";
      toast.style.transition = "all 0.3s ease";
      setTimeout(() => toast.remove(), 300);
    }, 4000);
  }
};
