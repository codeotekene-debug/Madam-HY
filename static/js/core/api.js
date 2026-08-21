/**
 * MADAM HY - Core API utilities.
 *
 * Provides:
 * - CSRF token retrieval
 * - Request helper with automatic CSRF and Content-Type handling
 * - Consistent error handling
 * - Authentication/role helpers
 *
 * All POST/PATCH/DELETE requests automatically include CSRF token.
 * FormData requests omit manual Content-Type so browser can set multipart/form-data boundary.
 */

// ============================================================================
// CSRF TOKEN RETRIEVAL
// ============================================================================

/**
 * Extract CSRF token from Django's csrftoken cookie.
 * @returns {string} CSRF token or empty string if not found.
 */
function getCsrfToken() {
    const cookieValue = document.cookie
        .split('; ')
        .find(row => row.startsWith('csrftoken='))
        ?.split('=')[1];
    return cookieValue || '';
}

// ============================================================================
// API REQUEST HELPER
// ============================================================================

/**
 * Make an API request with automatic CSRF and Content-Type handling.
 *
 * @param {string} url - Request URL (relative or absolute).
 * @param {Object} options - Request options.
 * @param {string} [options.method='GET'] - HTTP method.
 * @param {Object|FormData} [options.body] - Request body (plain object for JSON, FormData for multipart).
 * @param {Object} [options.headers={}] - Additional headers.
 * @returns {Promise<{success: boolean, status: number, data: any, message: string, errors: Object}>}
 */
async function apiRequest(url, options = {}) {
    const method = (options.method || 'GET').toUpperCase();
    const headers = { ...options.headers };
    let body = options.body;

    // Add CSRF token for non-GET requests
    if (method !== 'GET') {
        const csrfToken = getCsrfToken();
        if (csrfToken) {
            headers['X-CSRFToken'] = csrfToken;
        }
    }

    // Prepare request body and set Content-Type (unless FormData)
    if (body) {
        if (body instanceof FormData) {
            // Browser will auto-set Content-Type with multipart/form-data boundary
            // Do NOT manually set Content-Type
        } else if (typeof body === 'object') {
            // Convert plain object to JSON
            headers['Content-Type'] = 'application/json';
            body = JSON.stringify(body);
        }
    }

    // Make the request
    let response;
    try {
        response = await fetch(url, {
            method,
            headers,
            body,
        });
    } catch (error) {
        return {
            success: false,
            status: 0,
            data: null,
            message: `Network error: ${error.message}`,
            errors: null,
        };
    }

    // Parse response
    let responseData;
    try {
        const contentType = response.headers.get('content-type');
        if (contentType && contentType.includes('application/json')) {
            responseData = await response.json();
        } else {
            // Non-JSON response (unlikely for our backend, but handle gracefully)
            const text = await response.text();
            responseData = {
                success: response.ok,
                message: response.statusText,
                data: text,
            };
        }
    } catch (error) {
        return {
            success: false,
            status: response.status,
            data: null,
            message: 'Failed to parse response',
            errors: { detail: error.message },
        };
    }

    // Return consistent response structure
    return {
        success: responseData.success !== undefined ? responseData.success : response.ok,
        status: response.status,
        data: responseData.data || null,
        message: responseData.message || (response.ok ? 'Success' : response.statusText),
        errors: responseData.errors || null,
    };
}

// ============================================================================
// AUTHENTICATION & ROLE HELPERS
// ============================================================================

/**
 * Get authentication context from page DOM.
 * Expects base.html to expose data attributes on #app-context element.
 * @returns {Object} {authenticated: boolean, userId: number|null, userRole: string}
 */
function getAuthContext() {
    const appContext = document.getElementById('app-context');
    if (!appContext) {
        return {
            authenticated: false,
            userId: null,
            userRole: '',
        };
    }

    return {
        authenticated: appContext.dataset.authenticated === 'true',
        userId: appContext.dataset.userId ? parseInt(appContext.dataset.userId, 10) : null,
        userRole: appContext.dataset.userRole || '',
    };
}

/**
 * Check if current user is authenticated.
 * @returns {boolean}
 */
function isAuthenticated() {
    return getAuthContext().authenticated;
}

/**
 * Get current user's role.
 * @returns {string} Role name ('OWNER', 'MANAGER', 'CASHIER', 'STAFF', 'CUSTOMER', or empty string).
 */
function getCurrentUserRole() {
    return getAuthContext().userRole;
}

/**
 * Check if current user can manage products.
 * Management roles: OWNER, MANAGER
 * Note: This is UI-only. Backend authorization is always authoritative.
 * @returns {boolean}
 */
function canManageProducts() {
    const role = getCurrentUserRole();
    return role === 'OWNER' || role === 'MANAGER';
}

/**
 * Check if current user can manage product images.
 * Management roles: OWNER, MANAGER
 * Note: This is UI-only. Backend authorization is always authoritative.
 * @returns {boolean}
 */
function canManageImages() {
    const role = getCurrentUserRole();
    return role === 'OWNER' || role === 'MANAGER';
}

/**
 * Check if current user can manage categories.
 * Management roles: OWNER, MANAGER
 * Note: This is UI-only. Backend authorization is always authoritative.
 * @returns {boolean}
 */
function canManageCategories() {
    const role = getCurrentUserRole();
    return role === 'OWNER' || role === 'MANAGER';
}

// ============================================================================
// EXPORTS (for use in other modules)
// ============================================================================

// Note: These are globally available via script tags.
// For ES6 modules, uncomment:
// export { getCsrfToken, apiRequest, isAuthenticated, getCurrentUserRole, canManageProducts, canManageImages, canManageCategories };
