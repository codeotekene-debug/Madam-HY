/**
 * MADAM HY - Notifications Center Page Scripts.
 * Enhances notifications list with asynchronous mark-as-read actions
 * and live counter updates.
 */

document.addEventListener('DOMContentLoaded', () => {
    const rawDataElem = document.getElementById('notifications-data');
    let notificationsData = [];
    if (rawDataElem) {
        try {
            notificationsData = JSON.parse(rawDataElem.textContent);
        } catch (e) {
            console.warn('Failed to parse notifications data:', e);
        }
    }
    window.__NOTIFICATIONS_DATA__ = notificationsData;

    // Attach AJAX handlers to mark-read forms for smoother UX
    const listContainer = document.getElementById('notificationsContainer');
    if (!listContainer) return;

    listContainer.addEventListener('click', async (event) => {
        const toggleBtn = event.target.closest('.btn-toggle-read');
        if (!toggleBtn) return;

        const notifId = toggleBtn.getAttribute('data-id');
        const action = toggleBtn.getAttribute('data-action');
        if (!notifId || !action) return;

        event.preventDefault();
        const form = toggleBtn.closest('form');
        const url = form ? form.getAttribute('action') : `/notifications/${notifId}/${action}/`;

        try {
            toggleBtn.disabled = true;
            toggleBtn.style.opacity = '0.5';

            let response;
            if (typeof window.apiRequest === 'function') {
                response = await window.apiRequest(url, { method: 'POST' });
            } else {
                const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value || '';
                const fetchRes = await fetch(url, {
                    method: 'POST',
                    headers: {
                        'X-CSRFToken': csrfToken,
                        'Accept': 'application/json',
                        'Content-Type': 'application/json',
                    },
                });
                response = {
                    success: fetchRes.ok,
                    status: fetchRes.status,
                    data: await fetchRes.json().catch(() => ({})),
                };
            }

            if (response && response.success) {
                const card = document.getElementById(`notification-card-${notifId}`);
                if (card) {
                    if (action === 'read') {
                        card.classList.remove('unread');
                        card.setAttribute('data-read', 'true');
                        toggleBtn.setAttribute('data-action', 'unread');
                        toggleBtn.innerHTML = '↺ Mark as unread';
                        if (form) form.setAttribute('action', `/notifications/${notifId}/unread/`);
                    } else {
                        card.classList.add('unread');
                        card.setAttribute('data-read', 'false');
                        toggleBtn.setAttribute('data-action', 'read');
                        toggleBtn.innerHTML = '✓ Mark as read';
                        if (form) form.setAttribute('action', `/notifications/${notifId}/read/`);
                    }
                }

                // Update unread badges
                if (window.Notifications && typeof window.Notifications.fetchUnreadCount === 'function') {
                    window.Notifications.fetchUnreadCount();
                } else if (response.data && typeof response.data.unread_count === 'number') {
                    const badge = document.getElementById('notificationBadge') || document.querySelector('.notification-badge');
                    if (badge) {
                        badge.textContent = response.data.unread_count;
                    }
                    const unreadCardCount = document.getElementById('unreadNotificationsCount');
                    if (unreadCardCount) {
                        unreadCardCount.textContent = response.data.unread_count;
                    }
                }
            } else {
                console.error('Failed to update notification:', response);
            }
        } catch (err) {
            console.error('Error updating notification status:', err);
        } finally {
            toggleBtn.disabled = false;
            toggleBtn.style.opacity = '1';
        }
    });
});
