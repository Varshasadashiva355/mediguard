/**
 * MediGuard AI – Authentication and RBAC Manager
 */

const Auth = {
  TOKEN_KEY: "mediguard_token",
  USER_KEY: "mediguard_user",

  getToken() {
    return localStorage.getItem(this.TOKEN_KEY);
  },

  getUser() {
    try {
      const userStr = localStorage.getItem(this.USER_KEY);
      return userStr ? JSON.parse(userStr) : null;
    } catch {
      return null;
    }
  },

  isAuthenticated() {
    return !!this.getToken() && !!this.getUser();
  },

  async login(email, password) {
    try {
      const res = await API.post("/api/auth/login", { email, password });
      if (res.data && res.data.access_token) {
        localStorage.setItem(this.TOKEN_KEY, res.data.access_token);
        localStorage.setItem(this.USER_KEY, JSON.stringify(res.data.user));
        return { success: true, user: res.data.user };
      }
      return { success: false, message: "Invalid login response" };
    } catch (err) {
      return { success: false, message: err.message || "Login failed" };
    }
  },

  async logout() {
    try {
      if (this.isAuthenticated()) {
        await API.post("/api/auth/logout", {});
      }
    } catch (e) {
      console.warn("Logout request failed:", e);
    } finally {
      localStorage.removeItem(this.TOKEN_KEY);
      localStorage.removeItem(this.USER_KEY);
      window.location.href = "index.html";
    }
  },

  async fetchMe() {
    try {
      const res = await API.get("/api/auth/me");
      if (res.data) {
        localStorage.setItem(this.USER_KEY, JSON.stringify(res.data));
        return res.data;
      }
    } catch (e) {
      console.error("Failed to fetch user profile:", e);
      return null;
    }
  },

  hasRole(...roles) {
    const user = this.getUser();
    if (!user) return false;
    return roles.includes(user.role);
  },

  isAdmin() {
    return this.hasRole("admin");
  },

  isCardiologist() {
    return this.hasRole("cardiologist");
  },

  isStaff() {
    return this.hasRole("staff");
  },

  /**
   * Enforce page guard on protected views
   */
  guardRoute(allowedRoles = []) {
    if (!this.isAuthenticated()) {
      window.location.href = "index.html";
      return false;
    }

    if (allowedRoles.length > 0 && !this.hasRole(...allowedRoles)) {
      API.toast(`Access Denied: Your clinical role (${this.getUser()?.role}) is not authorized for this section.`, "error");
      setTimeout(() => {
        window.location.href = "dashboard.html";
      }, 1500);
      return false;
    }

    return true;
  }
};
