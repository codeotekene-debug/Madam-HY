/**
 * MADAM HY — Accessible Modal Management (WCAG 2.1 Compliant)
 * Handles focus trapping, keyboard navigation (Escape), and ARIA states.
 */

let activeModal = null;
let lastFocusedElement = null;

/**
 * Open a modal dialog by its element ID.
 * @param {string} modalId - The ID of the modal-overlay container.
 * @param {HTMLElement} [triggerElement] - The element that triggered the modal.
 */
function openModal(modalId, triggerElement = null) {
    const modalOverlay = document.getElementById(modalId);
    if (!modalOverlay) return;

    lastFocusedElement = triggerElement || document.activeElement;
    activeModal = modalOverlay;

    modalOverlay.classList.add('active');
    modalOverlay.setAttribute('aria-hidden', 'false');

    // Prevent body background scroll while modal is open
    document.body.style.overflow = 'hidden';

    // Focus first focusable element inside the modal
    const focusableElements = getFocusableElements(modalOverlay);
    if (focusableElements.length > 0) {
        focusableElements[0].focus();
    }
}

/**
 * Close a modal dialog by its element ID or currently active modal.
 * @param {string} [modalId] - Optional modal-overlay ID.
 */
function closeModal(modalId = null) {
    const modalOverlay = modalId ? document.getElementById(modalId) : activeModal;
    if (!modalOverlay) return;

    modalOverlay.classList.remove('active');
    modalOverlay.setAttribute('aria-hidden', 'true');

    document.body.style.overflow = '';
    activeModal = null;

    // Restore focus to trigger element
    if (lastFocusedElement && typeof lastFocusedElement.focus === 'function') {
        lastFocusedElement.focus();
        lastFocusedElement = null;
    }
}

/**
 * Get all focusable elements inside a container.
 * @param {HTMLElement} container
 * @returns {NodeList}
 */
function getFocusableElements(container) {
    return container.querySelectorAll(
        'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
    );
}

// Trap focus inside active modal dialog
document.addEventListener('keydown', (event) => {
    if (!activeModal) return;

    // Close on Escape key
    if (event.key === 'Escape' || event.key === 'Esc') {
        closeModal();
        return;
    }

    // Tab key focus trap
    if (event.key === 'Tab') {
        const focusable = getFocusableElements(activeModal);
        if (focusable.length === 0) {
            event.preventDefault();
            return;
        }

        const first = focusable[0];
        const last = focusable[focusable.length - 1];

        if (event.shiftKey) {
            if (document.activeElement === first) {
                event.preventDefault();
                last.focus();
            }
        } else {
            if (document.activeElement === last) {
                event.preventDefault();
                first.focus();
            }
        }
    }
});

// Click outside overlay backdrop to close
document.addEventListener('click', (event) => {
    if (!activeModal) return;

    // If clicking directly on the overlay backdrop
    if (event.target === activeModal) {
        closeModal();
        return;
    }

    // If clicking an element with data-modal-close or .modal-close
    if (event.target.closest('.modal-close') || event.target.closest('[data-modal-close]')) {
        closeModal();
    }
});

// Expose globally
window.openModal = openModal;
window.closeModal = closeModal;
