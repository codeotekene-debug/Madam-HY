/**
 * MADAM HY - Core Notifications Manager
 * Handles unread count badge polling, navbar integration, and global notification utilities.
 */

(function () {
    'use strict';

    const NotificationsManager = {
        badgeElement: null,
        pollInterval: null,
        intervalMs: 60000, // 60 seconds

        init() {
            const appContext = document.getElementById('app-context');
            const isAuthenticated = appContext && appContext.dataset && appContext.dataset.authenticated === 'true';

            if (!isAuthenticated) {
                return;
            }

            this.badgeElement = document.getElementById('notificationBadge') || document.querySelector('.notification-badge');

            // Initial fetch
            this.fetchUnreadCount();

            // Visibility-aware polling
            this.startPolling();
            document.addEventListener('visibilitychange', () => {
                if (document.visibilityState === 'visible') {
                    this.fetchUnreadCount();
                }
            });
        },

        async fetchUnreadCount() {
            try {
                let unreadCount = 0;

                if (typeof window.apiRequest === 'function') {
                    const res = await window.apiRequest('/notifications/unread-count/');
                    if (res && res.success) {
                        unreadCount = res.unread_count !== undefined ? res.unread_count : (res.data?.unread_count || 0);
                    }
                } else {
                    const fetchRes = await fetch('/notifications/unread-count/', {
                        headers: {
                            'Accept': 'application/json',
                        },
                    });
                    if (fetchRes.ok) {
                        const json = await fetchRes.json();
                        unreadCount = json.unread_count !== undefined ? json.unread_count : (json.data?.unread_count || 0);
                    }
                }

                this.updateBadge(unreadCount);
                return unreadCount;
            } catch (err) {
                // Silently handle transient network issues
                return 0;
            }
        },

        updateBadge(count) {
            if (!this.badgeElement) {
                this.badgeElement = document.getElementById('notificationBadge') || document.querySelector('.notification-badge');
            }
            if (!this.badgeElement) {
                return;
            }

            const num = Number(count) || 0;
            this.badgeElement.textContent = num > 99 ? '99+' : num;

            if (num > 0) {
                this.badgeElement.style.display = 'flex';
                this.badgeElement.classList.add('has-unread');
            } else {
                this.badgeElement.classList.remove('has-unread');
            }
        },

        startPolling() {
            if (this.pollInterval) {
                clearInterval(this.pollInterval);
            }
            this.pollInterval = setInterval(() => {
                if (document.visibilityState === 'visible') {
                    this.fetchUnreadCount();
                }
            }, this.intervalMs);
        },

        async markAsRead(notificationId) {
            if (!notificationId) return null;
            try {
                if (typeof window.apiRequest === 'function') {
                    const res = await window.apiRequest(`/notifications/${notificationId}/read/`, { method: 'POST' });
                    if (res && res.success) {
                        await this.fetchUnreadCount();
                    }
                    return res;
                }
                const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value || '';
                const fetchRes = await fetch(`/notifications/${notificationId}/read/`, {
                    method: 'POST',
                    headers: {
                        'X-CSRFToken': csrfToken,
                        'Accept': 'application/json',
                    },
                });
                const data = await fetchRes.json().catch(() => ({}));
                await this.fetchUnreadCount();
                return data;
            } catch (err) {
                console.error('Failed to mark notification as read:', err);
                return null;
            }
        },

        async markAllAsRead() {
            try {
                if (typeof window.apiRequest === 'function') {
                    const res = await window.apiRequest('/notifications/read-all/', { method: 'POST' });
                    if (res && res.success) {
                        this.updateBadge(0);
                    }
                    return res;
                }
                const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value || '';
                const fetchRes = await fetch('/notifications/read-all/', {
                    method: 'POST',
                    headers: {
                        'X-CSRFToken': csrfToken,
                        'Accept': 'application/json',
                    },
                });
                const data = await fetchRes.json().catch(() => ({}));
                this.updateBadge(0);
                return data;
            } catch (err) {
                console.error('Failed to mark all notifications as read:', err);
                return null;
            }
        },
    };

    window.Notifications = NotificationsManager;

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => NotificationsManager.init());
    } else {
        NotificationsManager.init();
    }
})();
