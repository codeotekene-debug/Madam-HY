/**
 * MADAM HY — Accessible Navigation & Mobile Drawer Module (WCAG 2.1 Compliant)
 * Manages responsive sidebar drawer toggling, ARIA attributes, active link detection,
 * and user profile dropdowns.
 */

const mobileMenuButton = document.getElementById("mobileMenuButton");
const sidebarToggle = document.getElementById("sidebarToggle");
const sidebar = document.getElementById("sidebar");
const sidebarOverlay = document.getElementById("sidebarOverlay");
const sidebarClose = document.getElementById("sidebarClose");
let sidebarPreviousOverflow = "";

function initNavigation() {
    if (!sidebar) return;

    // Set initial ARIA attributes based on screen width
    const isMobile = window.innerWidth <= 900;
    sidebar.setAttribute("aria-hidden", isMobile ? "true" : "false");
    sidebar.setAttribute("role", "navigation");
    if (isMobile) sidebar.setAttribute("inert", "");
    else sidebar.removeAttribute("inert");

    [mobileMenuButton, sidebarToggle].forEach((btn) => {
        if (btn) {
            btn.setAttribute("aria-expanded", "false");
            btn.setAttribute("aria-controls", "sidebar");
            if (!btn.getAttribute("aria-label")) {
                btn.setAttribute("aria-label", "Open navigation menu");
            }
        }
    });

    if (sidebarClose) {
        sidebarClose.setAttribute("aria-label", "Close navigation menu");
    }

    // Auto-detect and highlight current active nav item
    highlightActiveNav();

    // Initialize user profile dropdown & interactive dropdown menus
    initDropdowns();
}

function highlightActiveNav() {
    const currentPath = window.location.pathname;
    if (!currentPath) return;

    const navLinks = document.querySelectorAll(".sidebar-navigation .nav-item");
    let exactMatch = null;
    let prefixMatch = null;

    navLinks.forEach((link) => {
        const href = link.getAttribute("href");
        if (!href || href === "#") return;

        link.classList.remove("active");
        link.removeAttribute("aria-current");

        if (href === currentPath) {
            exactMatch = link;
        } else if (href !== "/" && href !== "/dashboard/" && href !== "/customer/" && currentPath.startsWith(href)) {
            if (!prefixMatch || href.length > prefixMatch.getAttribute("href").length) {
                prefixMatch = link;
            }
        }
    });

    const activeLink = exactMatch || prefixMatch;
    if (activeLink) {
        activeLink.classList.add("active");
        activeLink.setAttribute("aria-current", "page");
    }
}

function openSidebar() {
    if (!sidebar) return;

    sidebar.classList.add("open");
    sidebar.setAttribute("aria-hidden", "false");
    sidebar.removeAttribute("inert");
    sidebarOverlay?.classList.add("active");
    sidebarPreviousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    [mobileMenuButton, sidebarToggle].forEach((btn) => {
        if (btn) {
            btn.setAttribute("aria-expanded", "true");
            btn.setAttribute("aria-label", "Close navigation menu");
        }
    });

    // Move keyboard focus to close button inside drawer for accessibility
    setTimeout(() => {
        sidebarClose?.focus();
    }, 50);
}

function closeSidebar() {
    if (!sidebar) return;

    sidebar.classList.remove("open");
    sidebarOverlay?.classList.remove("active");

    const isMobile = window.innerWidth <= 900;
    sidebar.setAttribute("aria-hidden", isMobile ? "true" : "false");
    if (isMobile) sidebar.setAttribute("inert", "");
    document.body.style.overflow = sidebarPreviousOverflow;

    [mobileMenuButton, sidebarToggle].forEach((btn) => {
        if (btn) {
            btn.setAttribute("aria-expanded", "false");
            btn.setAttribute("aria-label", "Open navigation menu");
        }
    });

    if (mobileMenuButton) {
        mobileMenuButton.focus();
    } else if (sidebarToggle) {
        sidebarToggle.focus();
    }
}

function initDropdowns() {
    const dropdownContainers = document.querySelectorAll(".dropdown, #userMenuDropdown");

    dropdownContainers.forEach((dropdown) => {
        const trigger = dropdown.querySelector(".dropdown-trigger, [data-toggle='dropdown'], #userMenuButton, .user-menu-trigger");
        if (!trigger) return;

        trigger.addEventListener("click", (e) => {
            e.stopPropagation();
            const wasActive = dropdown.classList.contains("active");

            // Close all other open dropdowns
            dropdownContainers.forEach((other) => {
                if (other !== dropdown) {
                    other.classList.remove("active");
                    const otherBtn = other.querySelector("[aria-expanded]");
                    if (otherBtn) otherBtn.setAttribute("aria-expanded", "false");
                }
            });

            dropdown.classList.toggle("active", !wasActive);
            trigger.setAttribute("aria-expanded", !wasActive ? "true" : "false");
        });
    });

    // Close dropdowns when clicking outside
    document.addEventListener("click", (e) => {
        if (!e.target.closest(".dropdown")) {
            dropdownContainers.forEach((dropdown) => {
                dropdown.classList.remove("active");
                const btn = dropdown.querySelector("[aria-expanded]");
                if (btn) btn.setAttribute("aria-expanded", "false");
            });
        }
    });

    // Close dropdowns on Escape key
    document.addEventListener("keydown", (e) => {
        if (e.key === "Escape" || e.key === "Esc") {
            dropdownContainers.forEach((dropdown) => {
                if (dropdown.classList.contains("active")) {
                    dropdown.classList.remove("active");
                    const btn = dropdown.querySelector("[aria-expanded]");
                    if (btn) {
                        btn.setAttribute("aria-expanded", "false");
                        btn.focus();
                    }
                }
            });
        }
    });
}

// Event listeners for mobile sidebar toggles
[mobileMenuButton, sidebarToggle].forEach((btn) => {
    btn?.addEventListener("click", () => {
        const isOpen = sidebar?.classList.contains("open");
        if (isOpen) {
            closeSidebar();
        } else {
            openSidebar();
        }
    });
});

sidebarOverlay?.addEventListener("click", closeSidebar);
sidebarClose?.addEventListener("click", closeSidebar);

// Close sidebar on Escape key if open
document.addEventListener("keydown", (event) => {
    if (!sidebar?.classList.contains("open")) return;
    if (event.key === "Escape" || event.key === "Esc") {
        closeSidebar();
        return;
    }
    if (event.key === "Tab") {
        const focusable = getFocusableElements(sidebar);
        if (!focusable.length) {
            event.preventDefault();
            sidebarClose?.focus();
            return;
        }
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (event.shiftKey && (document.activeElement === first || !sidebar.contains(document.activeElement))) {
            event.preventDefault();
            last.focus();
        } else if (!event.shiftKey && (document.activeElement === last || !sidebar.contains(document.activeElement))) {
            event.preventDefault();
            first.focus();
        }
    }
});

// Reset states on viewport resize
window.addEventListener("resize", () => {
    if (window.innerWidth > 900) {
        if (sidebar?.classList.contains("open")) {
            sidebar.classList.remove("open");
            sidebarOverlay?.classList.remove("active");
        }
        sidebar?.setAttribute("aria-hidden", "false");
            sidebar?.removeAttribute("inert");
            document.body.style.overflow = sidebarPreviousOverflow;
        [mobileMenuButton, sidebarToggle].forEach((btn) => {
            btn?.setAttribute("aria-expanded", "false");
        });
    } else {
        if (!sidebar?.classList.contains("open")) {
            sidebar?.setAttribute("aria-hidden", "true");
            sidebar?.setAttribute("inert", "");
        }
    }
});

function getFocusableElements(container) {
    return Array.from(container.querySelectorAll(
        'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
    )).filter(element => !element.hidden && element.getAttribute('aria-hidden') !== 'true');
}

function setupGlobalSearch() {
    const trigger = document.getElementById('globalSearchToggle');
    const dialog = document.getElementById('globalSearchDialog');
    const backdrop = document.getElementById('globalSearchBackdrop');
    const closeButton = document.getElementById('globalSearchClose');
    const form = document.getElementById('globalSearchForm');
    const scope = document.getElementById('globalSearchScope');
    const input = document.getElementById('globalSearchInput');
    if (!trigger || !dialog || !backdrop || !form || !scope || !input) return;

    let previousOverflow = '';
    const open = () => {
        previousOverflow = document.body.style.overflow;
        document.body.style.overflow = 'hidden';
        backdrop.hidden = false;
        dialog.hidden = false;
        trigger.setAttribute('aria-expanded', 'true');
        requestAnimationFrame(() => input.focus());
    };
    const close = () => {
        dialog.hidden = true;
        backdrop.hidden = true;
        document.body.style.overflow = previousOverflow;
        trigger.setAttribute('aria-expanded', 'false');
        trigger.focus();
    };

    trigger.setAttribute('aria-expanded', 'false');
    trigger.addEventListener('click', open);
    closeButton?.addEventListener('click', close);
    backdrop.addEventListener('click', close);
    form.addEventListener('submit', () => {
        form.action = scope.value === '/orders/' ? '/orders/' : '/products/';
    });
    document.addEventListener('keydown', event => {
        if (dialog.hidden) return;
        if (event.key === 'Escape') {
            event.preventDefault();
            close();
            return;
        }
        if (event.key !== 'Tab') return;
        const focusable = getFocusableElements(dialog);
        if (!focusable.length) {
            event.preventDefault();
            closeButton?.focus();
            return;
        }
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (event.shiftKey && (document.activeElement === first || !dialog.contains(document.activeElement))) {
            event.preventDefault();
            last.focus();
        } else if (!event.shiftKey && (document.activeElement === last || !dialog.contains(document.activeElement))) {
            event.preventDefault();
            first.focus();
        }
    });
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', setupGlobalSearch);
} else {
    setupGlobalSearch();
}

// Run initialization on DOM load
if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initNavigation);
} else {
    initNavigation();
}

// Export for module/global usage
if (typeof module !== "undefined" && module.exports) {
    module.exports = { openSidebar, closeSidebar, initNavigation, highlightActiveNav };
} else {
    window.openSidebar = openSidebar;
    window.closeSidebar = closeSidebar;
    window.initNavigation = initNavigation;
    window.highlightActiveNav = highlightActiveNav;
}
