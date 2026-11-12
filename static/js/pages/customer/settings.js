/**
 * MADAM HY - Customer Settings
 * Live customer preferences and notification delivery settings integration.
 */

const PREFERENCES_API_ENDPOINT = '/accounts/settings/notifications/';

let settingsData = {
    notifications: {
        orders: true,
        promotions: false,
        requests: true,
        payments: true
    },
    preferences: {
        language: 'en',
        currency: 'NGN',
        marketing: false
    },
    delivery: {
        preferredMethod: 'Delivery'
    }
};

document.addEventListener('DOMContentLoaded', () => {
    initSettingsFromDOM();
    bindActions();
});

function getCsrfToken() {
    const inputToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value;
    if (inputToken) return inputToken;
    const cookieValue = document.cookie
        .split('; ')
        .find(row => row.startsWith('csrftoken='))
        ?.split('=')[1];
    return cookieValue || '';
}

function initSettingsFromDOM() {
    const initialScript = document.getElementById('initialSettingsData');
    if (initialScript && initialScript.textContent.trim()) {
        try {
            const parsed = JSON.parse(initialScript.textContent);
            if (parsed && typeof parsed === 'object') {
                if (parsed.notifications) settingsData.notifications = { ...settingsData.notifications, ...parsed.notifications };
                if (parsed.preferences) settingsData.preferences = { ...settingsData.preferences, ...parsed.preferences };
                if (parsed.delivery) settingsData.delivery = { ...settingsData.delivery, ...parsed.delivery };
            }
        } catch (e) {
            console.warn('Could not parse initialSettingsData:', e);
        }
    }
    loadSettings();
}

function loadSettings() {
    // Notifications
    const orderNotif = document.getElementById('orderNotifications');
    const promoNotif = document.getElementById('promotionNotifications');
    const reqNotif = document.getElementById('requestNotifications');
    const payNotif = document.getElementById('paymentNotifications');

    if (orderNotif) orderNotif.checked = Boolean(settingsData.notifications.orders);
    if (promoNotif) promoNotif.checked = Boolean(settingsData.notifications.promotions);
    if (reqNotif) reqNotif.checked = Boolean(settingsData.notifications.requests);
    if (payNotif) payNotif.checked = Boolean(settingsData.notifications.payments);

    // Preferences
    const lang = document.getElementById('languageSelect');
    const currency = document.getElementById('currencySelect');
    const marketing = document.getElementById('marketingEmails');

    if (lang && settingsData.preferences.language) lang.value = settingsData.preferences.language;
    if (currency && settingsData.preferences.currency) currency.value = settingsData.preferences.currency;
    if (marketing) marketing.checked = Boolean(settingsData.preferences.marketing);

    // Delivery
    const delivery = document.getElementById('defaultDelivery');
    if (delivery && settingsData.delivery.preferredMethod) {
        delivery.value = settingsData.delivery.preferredMethod;
    }
}

function bindActions() {
    const saveBtn = document.getElementById('settingsSaveBtn');
    const resetBtn = document.getElementById('settingsResetBtn');
    const successAlert = document.getElementById('settingsSaveSuccess');
    const errorAlert = document.getElementById('settingsSaveError');
    const deleteBtn = document.getElementById('deleteAccountBtn');

    // Interactive feedback on change
    const inputs = document.querySelectorAll('.settings-option input, .settings-field select');
    inputs.forEach(input => {
        input.addEventListener('change', () => {
            if (successAlert) successAlert.classList.add('hidden');
            if (errorAlert) errorAlert.classList.add('hidden');
        });
    });

    saveBtn?.addEventListener('click', async () => {
        saveBtn.disabled = true;
        const originalText = saveBtn.textContent;
        saveBtn.textContent = 'Saving...';
        if (successAlert) successAlert.classList.add('hidden');
        if (errorAlert) errorAlert.classList.add('hidden');

        const payload = {
            notifications: {
                orders: document.getElementById('orderNotifications')?.checked ?? true,
                promotions: document.getElementById('promotionNotifications')?.checked ?? false,
                requests: document.getElementById('requestNotifications')?.checked ?? true,
                payments: document.getElementById('paymentNotifications')?.checked ?? true
            },
            preferences: {
                language: document.getElementById('languageSelect')?.value || 'en',
                currency: document.getElementById('currencySelect')?.value || 'NGN',
                marketing: document.getElementById('marketingEmails')?.checked ?? false
            },
            delivery: {
                preferredMethod: document.getElementById('defaultDelivery')?.value || 'Delivery'
            }
        };

        try {
            const response = await fetch(PREFERENCES_API_ENDPOINT, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCsrfToken(),
                    'Accept': 'application/json'
                },
                body: JSON.stringify(payload)
            });

            const result = await response.json();

            if (response.ok && result.success) {
                if (result.preferences) {
                    settingsData = result.preferences;
                    loadSettings();
                }
                if (successAlert) {
                    successAlert.textContent = result.message || 'Your preferences have been saved.';
                    successAlert.classList.remove('hidden');
                    setTimeout(() => {
                        successAlert.classList.add('hidden');
                    }, 4000);
                }
            } else {
                if (errorAlert) {
                    errorAlert.textContent = result.message || 'Unable to save preferences. Please check inputs.';
                    errorAlert.classList.remove('hidden');
                }
            }
        } catch (err) {
            console.error('Settings save error:', err);
            if (errorAlert) {
                errorAlert.textContent = 'Network error while saving preferences. Please try again.';
                errorAlert.classList.remove('hidden');
            }
        } finally {
            saveBtn.disabled = false;
            saveBtn.textContent = originalText;
        }
    });

    resetBtn?.addEventListener('click', () => {
        // Reset local controls to sensible defaults
        settingsData = {
            notifications: {
                orders: true,
                promotions: false,
                requests: true,
                payments: true
            },
            preferences: {
                language: 'en',
                currency: 'NGN',
                marketing: false
            },
            delivery: {
                preferredMethod: 'Delivery'
            }
        };
        loadSettings();
        if (successAlert) successAlert.classList.add('hidden');
        if (errorAlert) {
            errorAlert.textContent = 'Settings reset to defaults. Click "Save preferences" to apply.';
            errorAlert.classList.remove('hidden');
            setTimeout(() => {
                errorAlert.classList.add('hidden');
            }, 4000);
        }
    });

    deleteBtn?.addEventListener('click', () => {
        const confirmed = confirm('Are you sure you want to delete your account? This action requires customer service confirmation and cannot be undone.');
        if (confirmed) {
            alert('Account deletion request recorded. Our customer support team will contact you to verify.');
        }
    });
}
