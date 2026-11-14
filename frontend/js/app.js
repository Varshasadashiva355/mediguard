/**
 * MediGuard AI – Application Shell & UI Interactions Controller
 */

document.addEventListener("DOMContentLoaded", () => {
  // 1. Initialise Authenticated User Profile in Topbar & Sidebar
  initUserProfile();

  // 2. Setup Emergency Protocol Modal
  initEmergencyModal();

  // 3. Setup Responsive Sidebar Toggle
  initSidebarToggle();

  // 4. Highlight Active Navigation Item
  initNavigation();
});

function initUserProfile() {
  const user = Auth.getUser();
  if (!user) return;

  const userNameEl = document.getElementById("topbar-user-name");
  const userRoleEl = document.getElementById("topbar-user-role");
  const userDeptEl = document.getElementById("sidebar-user-dept");

  if (userNameEl) userNameEl.textContent = user.full_name || user.email;
  if (userRoleEl) {
    userRoleEl.textContent = user.role.toUpperCase();
    userRoleEl.className = `badge badge-role-${user.role}`;
  }
  if (userDeptEl) userDeptEl.textContent = user.department || "Cardiology";

  // Hide or restrict links based on clinical role
  applyRoleVisibility(user.role);
}

function applyRoleVisibility(role) {
  // Reviews section: only cardiologist and admin
  const reviewLinks = document.querySelectorAll(".nav-role-cardiologist");
  reviewLinks.forEach(el => {
    if (role !== "cardiologist" && role !== "admin") {
      el.classList.add("disabled");
      el.title = "Restricted to Cardiologists & Admin only (Clinical Decision Support Review)";
    }
  });

  // Audit logs & Settings: only admin
  const adminLinks = document.querySelectorAll(".nav-role-admin");
  adminLinks.forEach(el => {
    if (role !== "admin") {
      el.classList.add("disabled");
      el.title = "Restricted to Hospital Administrators";
    }
  });
}

function initEmergencyModal() {
  const triggerBtn = document.getElementById("btn-emergency-protocol");
  const modalBackdrop = document.getElementById("modal-emergency-protocol");
  const closeBtns = document.querySelectorAll(".btn-close-emergency-modal");

  if (!triggerBtn || !modalBackdrop) return;

  triggerBtn.addEventListener("click", () => {
    modalBackdrop.classList.add("show");
  });

  closeBtns.forEach(btn => {
    btn.addEventListener("click", () => {
      modalBackdrop.classList.remove("show");
    });
  });

  modalBackdrop.addEventListener("click", (e) => {
    if (e.target === modalBackdrop) {
      modalBackdrop.classList.remove("show");
    }
  });
}

function initSidebarToggle() {
  const toggleBtn = document.getElementById("sidebar-toggle-btn");
  const sidebar = document.getElementById("sidebar");

  if (toggleBtn && sidebar) {
    toggleBtn.addEventListener("click", () => {
      sidebar.classList.toggle("open");
    });

    // Close when clicking outside on mobile
    document.addEventListener("click", (e) => {
      if (sidebar.classList.contains("open") && !sidebar.contains(e.target) && !toggleBtn.contains(e.target)) {
        sidebar.classList.remove("open");
      }
    });
  }
}

function initNavigation() {
  const currentPath = window.location.pathname.split("/").pop() || "dashboard.html";
  const navLinks = document.querySelectorAll(".nav-link");

  navLinks.forEach(link => {
    const href = link.getAttribute("href");
    if (href === currentPath) {
      link.classList.add("active");
    } else {
      link.classList.remove("active");
    }
  });
}
