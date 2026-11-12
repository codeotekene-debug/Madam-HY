/**
 * MADAM HY — Progressive Client-Side Partial Navigation Router (HTMX Boost / Turbo Drive)
 *
 * Provides instant, smooth SPA-like navigation without full-page white flashes:
 * - Intercepts boosted links and GET filter forms across sidebar, topbar subnav, and pagination.
 * - Selectively swaps #topbarNav and .page-content while keeping master shell, sidebar, and CSS in memory.
 * - Reconciles <head> stylesheets and external bundles between incoming pages.
 * - Automated script re-creation and unified lifecycle execution (DOMContentLoaded & page:load).
 * - Synchronizes active sidebar navigation links without requiring page refreshes.
 * - Updates document.title and browser history via pushState.
 * - Manages component script lifecycles and timer cleanup (prevents memory leaks).
 * - Displays a topbar micro-progress indicator for requests exceeding 80ms.
 */

(function () {
    'use strict';

    // =========================================================================
    // PAGE LIFECYCLE & CLEANUP MANAGER
    // =========================================================================

    const PageLifecycle = {
        intervals: new Set(),
        timeouts: new Set(),
        unmountCallbacks: new Set(),

        registerInterval(id) {
            this.intervals.add(id);
            return id;
        },

        registerTimeout(id) {
            this.timeouts.add(id);
            return id;
        },

        onUnmount(callback) {
            if (typeof callback === 'function') {
                this.unmountCallbacks.add(callback);
            }
        },

        clearAll() {
            // Execute custom unmount callbacks
            this.unmountCallbacks.forEach(cb => {
                try {
                    cb();
                } catch (e) {
                    console.error('[PageLifecycle] Error during cleanup:', e);
                }
            });
            this.unmountCallbacks.clear();

            // Clear all registered intervals
            this.intervals.forEach(id => clearInterval(id));
            this.intervals.clear();

            // Clear all registered timeouts
            this.timeouts.forEach(id => clearTimeout(id));
            this.timeouts.clear();

            // Dispatch global unmount event
            document.dispatchEvent(new CustomEvent('page:beforeUnmount'));
            document.dispatchEvent(new CustomEvent('turbo:before-render'));
        }
    };

    // Expose lifecycle globally
    window.PageLifecycle = PageLifecycle;
    window.registerPageInterval = (id) => PageLifecycle.registerInterval(id);
    window.registerPageTimeout = (id) => PageLifecycle.registerTimeout(id);

    // =========================================================================
    // TOPBAR MICRO-PROGRESS INDICATOR
    // =========================================================================

    const ProgressBar = {
        element: null,
        timer: null,
        active: false,

        init() {
            this.element = document.getElementById('topbarProgress');
            if (!this.element) {
                this.element = document.createElement('div');
                this.element.id = 'topbarProgress';
                this.element.className = 'topbar-progress';
                this.element.setAttribute('aria-hidden', 'true');
                const topbar = document.getElementById('main-navbar') || document.body;
                topbar.prepend(this.element);
            }
        },

        start() {
            this.init();
            if (this.timer) clearTimeout(this.timer);
            this.active = true;

            // Only show progress indicator if request exceeds 80ms
            this.timer = setTimeout(() => {
                if (!this.active) return;
                this.element.style.width = '20%';
                this.element.classList.add('active');

                this.timer = setTimeout(() => {
                    if (!this.active) return;
                    this.element.style.width = '65%';

                    this.timer = setTimeout(() => {
                        if (!this.active) return;
                        this.element.style.width = '85%';
                    }, 200);
                }, 150);
            }, 80);
        },

        finish() {
            this.active = false;
            if (this.timer) clearTimeout(this.timer);
            if (!this.element) return;

            this.element.style.width = '100%';
            setTimeout(() => {
                this.element.classList.remove('active');
                setTimeout(() => {
                    this.element.style.width = '0%';
                }, 250);
            }, 120);
        }
    };

    // =========================================================================
    // PARTIAL SPA NAVIGATION ROUTER
    // =========================================================================

    const Router = {
        isNavigating: false,
        currentController: null,

        init() {
            ProgressBar.init();

            // Global link click delegation
            document.addEventListener('click', this.handleLinkClick.bind(this));

            // Global GET form submission delegation
            document.addEventListener('submit', this.handleFormSubmit.bind(this));

            // Popstate handling for browser back/forward buttons
            window.addEventListener('popstate', (e) => {
                this.navigate(window.location.href, { pushHistory: false });
            });
        },

        isBoosted(element) {
            if (!element) return false;
            // Explicit opt-out has highest priority
            if (element.closest('[hx-boost="false"], [data-turbo="false"]')) {
                return false;
            }
            // Explicit boost
            if (element.closest('[hx-boost="true"], [data-turbo="true"]')) {
                return true;
            }
            // Default boost for sidebar, subnav, and main content
            return Boolean(element.closest('#sidebar, #topbarNav, #main-content, .subnav-pill, .pagination, .page-actions'));
        },

        shouldInterceptLink(link, event) {
            // Ignore non-HTML, modified clicks or prevented events
            if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
                return false;
            }

            if (!link || !link.href) return false;

            // Check opt-outs
            if (link.getAttribute('hx-boost') === 'false' || link.getAttribute('data-turbo') === 'false') return false;
            if (link.hasAttribute('download') || link.getAttribute('target') === '_blank') return false;
            if (link.getAttribute('rel') === 'external') return false;

            const href = link.getAttribute('href') || '';
            if (href.startsWith('#') || href.startsWith('javascript:') || href.startsWith('mailto:') || href.startsWith('tel:')) {
                return false;
            }

            // Must be internal origin
            const url = new URL(link.href, window.location.origin);
            if (url.origin !== window.location.origin) return false;

            // Don't intercept logout or admin paths
            if (url.pathname.includes('/logout') || url.pathname.startsWith('/admin/')) {
                return false;
            }

            return this.isBoosted(link);
        },

        handleLinkClick(event) {
            const link = event.target.closest('a');
            if (!link) return;

            if (this.shouldInterceptLink(link, event)) {
                event.preventDefault();
                const url = link.href;

                // Add active visual state to link/pill
                link.classList.add('is-navigating');
                this.navigate(url, {
                    pushHistory: true,
                    onComplete: () => link.classList.remove('is-navigating')
                });
            }
        },

        handleFormSubmit(event) {
            const form = event.target;
            if (!form || form.tagName !== 'FORM') return;

            const method = (form.getAttribute('method') || 'GET').toUpperCase();
            if (method !== 'GET') return; // Only boost GET filter/search forms

            if (!this.isBoosted(form)) return;
            if (form.getAttribute('hx-boost') === 'false' || form.getAttribute('data-turbo') === 'false') return;

            event.preventDefault();

            const action = form.getAttribute('action') || window.location.pathname;
            const formData = new FormData(form);
            const params = new URLSearchParams();

            for (const [key, value] of formData.entries()) {
                if (value !== '') {
                    params.append(key, value);
                }
            }

            const queryString = params.toString();
            const targetUrl = queryString ? `${action.split('?')[0]}?${queryString}` : action.split('?')[0];

            this.navigate(targetUrl, { pushHistory: true });
        },

        async navigate(url, options = {}) {
            const { pushHistory = true, onComplete = null } = options;

            // Cancel any in-flight navigation
            if (this.currentController) {
                this.currentController.abort();
            }
            this.currentController = new AbortController();
            this.isNavigating = true;

            const mainContent = document.getElementById('main-content');
            ProgressBar.start();
            if (mainContent) {
                mainContent.classList.add('turbo-loading', 'htmx-swapping');
            }

            try {
                const response = await fetch(url, {
                    signal: this.currentController.signal,
                    headers: {
                        'Accept': 'text/html,application/xhtml+xml',
                        'X-HX-Request': 'true',
                        'X-Turbo-Request': 'true',
                    },
                });

                // If redirected to login (session timeout)
                if (response.redirected && response.url.includes('/login')) {
                    window.location.href = response.url;
                    return;
                }

                if (response.status === 401) {
                    window.location.href = `/accounts/login/?next=${encodeURIComponent(window.location.pathname)}`;
                    return;
                }

                // If response is JSON instead of HTML, fallback to standard navigation
                const contentType = response.headers.get('content-type') || '';
                if (contentType.includes('application/json')) {
                    console.warn('[Router] Received JSON response, falling back to standard navigation for:', url);
                    window.location.href = url;
                    return;
                }

                const htmlText = await response.text();
                const parser = new DOMParser();
                const newDoc = parser.parseFromString(htmlText, 'text/html');

                // 1. Cleanup timers & callbacks from previous page
                PageLifecycle.clearAll();

                // 2. Reconcile <head> assets (stylesheets and scripts)
                this.reconcileHeadAssets(newDoc);

                // 3. Update document title
                const newTitle = newDoc.querySelector('title');
                if (newTitle) {
                    document.title = newTitle.textContent;
                }

                // 4. Swap #topbarNav (contextual module subnav pills)
                const currentNav = document.getElementById('topbarNav');
                const newNav = newDoc.getElementById('topbarNav');
                if (currentNav && newNav) {
                    currentNav.innerHTML = newNav.innerHTML;
                }

                // 5. Update page title in navbar
                const currentH1 = document.querySelector('.topbar-title h1');
                const newH1 = newDoc.querySelector('.topbar-title h1');
                if (currentH1 && newH1) {
                    currentH1.innerHTML = newH1.innerHTML;
                }

                // 6. Content-swapping routine: Swap .page-content or #main-content
                const currentPageContent = document.querySelector('.page-content');
                const newPageContent = newDoc.querySelector('.page-content');

                if (currentPageContent && newPageContent) {
                    // Include any page-specific scripts from incoming newDoc body into the container
                    const incomingPageScripts = Array.from(newDoc.querySelectorAll('body > script:not([src*="core/"])'));
                    incomingPageScripts.forEach(script => {
                        if (!newPageContent.contains(script)) {
                            newPageContent.appendChild(script.cloneNode(true));
                        }
                    });

                    currentPageContent.innerHTML = newPageContent.innerHTML;
                } else if (mainContent) {
                    const newMain = newDoc.getElementById('main-content');
                    if (newMain) {
                        const incomingPageScripts = Array.from(newDoc.querySelectorAll('body > script:not([src*="core/"])'));
                        incomingPageScripts.forEach(script => {
                            if (!newMain.contains(script)) {
                                newMain.appendChild(script.cloneNode(true));
                            }
                        });
                        mainContent.innerHTML = newMain.innerHTML;
                    }
                }

                // 7. Update browser history
                const finalUrl = response.redirected ? response.url : url;
                const targetUrl = finalUrl;
                if (pushHistory) {
                    window.history.pushState({ url: finalUrl }, '', finalUrl);
                }

                // 8. Synchronize sidebar active link
                this.updateSidebarActiveLink(finalUrl);

                // 9. Reconcile JSON data blocks in body (e.g. owner-dashboard-data, requests-data)
                this.reconcileJsonDataBlocks(newDoc);

                // 10. Re-execute scripts embedded inside the swapped page content container
                const targetContainer = document.querySelector('.page-content') || mainContent;
                if (targetContainer) {
                    this.reexecuteScripts(targetContainer);
                }

                // 11. Immediately after re-executing scripts, dispatch required lifecycle events:
                document.dispatchEvent(new Event('DOMContentLoaded', { bubbles: true, cancelable: true }));
                window.dispatchEvent(new CustomEvent('page:load', { detail: { url: targetUrl } }));

                // Compatibility events for Turbo/HTMX/component listeners
                document.dispatchEvent(new CustomEvent('page:load', { detail: { url: targetUrl } }));
                document.dispatchEvent(new CustomEvent('turbo:load', { detail: { url: targetUrl } }));
                document.dispatchEvent(new CustomEvent('htmx:afterSwap', { detail: { target: targetContainer } }));
                document.dispatchEvent(new CustomEvent('htmx:load', { detail: { elt: targetContainer } }));

                // 12. Scroll to top
                window.scrollTo({ top: 0, behavior: 'instant' });

            } catch (error) {
                if (error.name === 'AbortError') {
                    // Navigation was superseded by another click
                    return;
                }
                console.warn('[Router] Script execution or navigation error, falling back to standard navigation:', error);
                const targetUrl = url;
                window.dispatchEvent(new CustomEvent('router:error', { detail: { url: targetUrl, error } }));
                const sidebar = document.getElementById('sidebar');
                if (sidebar) {
                    sidebar.dispatchEvent(new CustomEvent('router:error', { detail: { url: targetUrl, error } }));
                }
                window.location.href = targetUrl;
            } finally {
                this.isNavigating = false;
                ProgressBar.finish();
                if (mainContent) {
                    mainContent.classList.remove('turbo-loading', 'htmx-swapping');
                }
                if (typeof onComplete === 'function') {
                    onComplete();
                }
            }
        },

        /**
         * Reconcile stylesheets and head scripts from incoming page into document.head.
         */
        reconcileHeadAssets(newDoc) {
            // Reconcile stylesheets
            const incomingStyles = newDoc.querySelectorAll('head link[rel="stylesheet"]');
            incomingStyles.forEach(link => {
                const href = link.getAttribute('href');
                if (!href) return;
                const existing = document.head.querySelector(`link[href="${href}"]`);
                if (!existing) {
                    const newLink = document.createElement('link');
                    Array.from(link.attributes).forEach(attr => newLink.setAttribute(attr.name, attr.value));
                    document.head.appendChild(newLink);
                }
            });

            // Reconcile head scripts
            const incomingHeadScripts = newDoc.querySelectorAll('head script');
            incomingHeadScripts.forEach(script => {
                const src = script.getAttribute('src');
                if (src && !document.head.querySelector(`script[src="${src}"]`)) {
                    const newScript = document.createElement('script');
                    Array.from(script.attributes).forEach(attr => newScript.setAttribute(attr.name, attr.value));
                    document.head.appendChild(newScript);
                }
            });
        },

        /**
         * Reconcile application/json data script blocks into document.body.
         */
        reconcileJsonDataBlocks(newDoc) {
            const jsonScripts = newDoc.querySelectorAll('script[type="application/json"]');
            jsonScripts.forEach(script => {
                if (!script.id) return;
                let existing = document.getElementById(script.id);
                if (existing) {
                    existing.textContent = script.textContent;
                } else {
                    const clone = document.createElement('script');
                    clone.type = 'application/json';
                    clone.id = script.id;
                    clone.textContent = script.textContent;
                    document.body.appendChild(clone);
                }
            });
        },

        /**
         * Script re-creation routine (reexecuteScripts(container)).
         * Iterates through all <script> tags in the incoming container,
         * instantiates new document.createElement('script') nodes with matching
         * attributes and inline source, and replaces them to force immediate browser execution.
         */
        reexecuteScripts(container) {
            if (!container) return;
            const scripts = Array.from(container.querySelectorAll('script'));
            scripts.forEach(oldScript => {
                // Skip JSON data templates or config blocks
                if (oldScript.type && oldScript.type === 'application/json') {
                    return;
                }

                const newScript = document.createElement('script');
                Array.from(oldScript.attributes).forEach(attr => {
                    newScript.setAttribute(attr.name, attr.value);
                });

                // Sequential execution for external scripts with error fallback
                if (newScript.src) {
                    newScript.async = false;
                    newScript.addEventListener('load', () => {
                        document.dispatchEvent(new Event('DOMContentLoaded', { bubbles: true, cancelable: true }));
                        window.dispatchEvent(new CustomEvent('page:load', { detail: { url: window.location.href } }));
                    });
                    newScript.addEventListener('error', (err) => {
                        console.warn('[Router] Script failed to load: ' + newScript.src + ', triggering fallback standard navigation');
                        const targetUrl = window.location.href;
                        window.dispatchEvent(new CustomEvent('router:error', { detail: { url: targetUrl, error: err } }));
                        window.location.href = targetUrl;
                    });
                }

                if (oldScript.textContent) {
                    newScript.textContent = oldScript.textContent;
                }

                if (oldScript.parentNode) {
                    oldScript.parentNode.replaceChild(newScript, oldScript);
                }
            });
        },

        /**
         * Alias for backward compatibility with existing tests.
         */
        reexecutePageScripts(container) {
            return this.reexecuteScripts(container);
        },

        /**
         * Synchronizes active state on sidebar links matching current path.
         */
        updateSidebarActiveLink(url) {
            try {
                const pathname = new URL(url, window.location.origin).pathname;
                const navLinks = document.querySelectorAll('.sidebar-navigation a.nav-item, #sidebar a.nav-item');
                let exactMatch = null;
                let prefixMatch = null;

                navLinks.forEach(link => {
                    const href = link.getAttribute('href');
                    if (!href || href === '#' || href.startsWith('javascript:')) return;

                    link.classList.remove('active');
                    link.removeAttribute('aria-current');

                    if (href === pathname) {
                        exactMatch = link;
                    } else if (href !== '/' && href !== '/dashboard/' && href !== '/customer/' && pathname.startsWith(href)) {
                        if (!prefixMatch || href.length > prefixMatch.getAttribute('href').length) {
                            prefixMatch = link;
                        }
                    }
                });

                const activeLink = exactMatch || prefixMatch;
                if (activeLink) {
                    activeLink.classList.add('active');
                    activeLink.setAttribute('aria-current', 'page');
                }

                if (typeof window.highlightActiveNav === 'function') {
                    window.highlightActiveNav();
                }

                // Close mobile drawer if open
                if (window.innerWidth <= 900 && typeof window.closeSidebar === 'function') {
                    window.closeSidebar();
                }
            } catch (e) {
                console.error('[Router] Error updating active sidebar link:', e);
            }
        },

        /**
         * Dispatches unified lifecycle events to re-initialize components and tables.
         */
        dispatchLifecycleEvents(url) {
            const target = document.querySelector('.page-content') || document.getElementById('main-content') || document.body;

            // 1. Standard DOMContentLoaded so all existing vanilla listeners re-bind
            document.dispatchEvent(new Event('DOMContentLoaded', { bubbles: true, cancelable: true }));

            // 2. Unified MADAM HY page:load event
            window.dispatchEvent(new CustomEvent('page:load', { detail: { url } }));
            document.dispatchEvent(new CustomEvent('page:load', { detail: { url } }));

            // 3. Turbo Drive & HTMX compatibility events
            document.dispatchEvent(new CustomEvent('turbo:load', { detail: { url } }));
            document.dispatchEvent(new CustomEvent('htmx:afterSwap', { detail: { target } }));
            document.dispatchEvent(new CustomEvent('htmx:load', { detail: { elt: target } }));
        }
    };

    window.Router = Router;

    // Initialize on DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => Router.init());
    } else {
        Router.init();
    }
})();
