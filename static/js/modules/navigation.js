/**
 * MADAM HY — Accessible Mobile Drawer & Navigation Module (ES Module / Bundler Compatible)
 * Manages responsive sidebar drawer toggling, ARIA attributes, and keyboard focus.
 */

export function initNavigation() {
    const mobileMenuButton = document.getElementById("mobileMenuButton");
    const sidebar = document.getElementById("sidebar");
    const sidebarOverlay = document.getElementById("sidebarOverlay");
    const sidebarClose = document.getElementById("sidebarClose");

    if (!sidebar) return;

    const isMobile = window.innerWidth <= 900;
    sidebar.setAttribute("aria-hidden", isMobile ? "true" : "false");
    sidebar.setAttribute("role", "navigation");

    if (mobileMenuButton) {
        mobileMenuButton.setAttribute("aria-expanded", "false");
        mobileMenuButton.setAttribute("aria-controls", "sidebar");
        mobileMenuButton.setAttribute("aria-label", "Open navigation menu");
    }

    if (sidebarClose) {
        sidebarClose.setAttribute("aria-label", "Close navigation menu");
    }
}

export function openSidebar() {
    const sidebar = document.getElementById("sidebar");
    const sidebarOverlay = document.getElementById("sidebarOverlay");
    const mobileMenuButton = document.getElementById("mobileMenuButton");
    const sidebarClose = document.getElementById("sidebarClose");

    if (!sidebar) return;

    sidebar.classList.add("open");
    sidebar.setAttribute("aria-hidden", "false");
    sidebarOverlay?.classList.add("active");

    if (mobileMenuButton) {
        mobileMenuButton.setAttribute("aria-expanded", "true");
        mobileMenuButton.setAttribute("aria-label", "Close navigation menu");
    }

    setTimeout(() => {
        sidebarClose?.focus();
    }, 50);
}

export function closeSidebar() {
    const sidebar = document.getElementById("sidebar");
    const sidebarOverlay = document.getElementById("sidebarOverlay");
    const mobileMenuButton = document.getElementById("mobileMenuButton");

    if (!sidebar) return;

    sidebar.classList.remove("open");
    sidebarOverlay?.classList.remove("active");

    const isMobile = window.innerWidth <= 900;
    sidebar.setAttribute("aria-hidden", isMobile ? "true" : "false");

    if (mobileMenuButton) {
        mobileMenuButton.setAttribute("aria-expanded", "false");
        mobileMenuButton.setAttribute("aria-label", "Open navigation menu");
        mobileMenuButton.focus();
    }
}

// Auto-bind on load if in browser environment
if (typeof window !== "undefined") {
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initNavigation);
    } else {
        initNavigation();
    }
}
