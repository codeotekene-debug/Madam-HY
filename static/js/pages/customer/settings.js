/**
 * MADAM HY - Customer Settings
 * Frontend-only customer settings and preferences
 */

const settingsData = {
    notifications: {
        orders: true,
        promotions: true,
        requests: true,
        payments: true
    },
    preferences: {
        language: 'en',
        currency: 'NGN',
        marketing: true
    },
    delivery: {
        preferredMethod: 'Delivery'
    }
};

document.addEventListener('DOMContentLoaded', () => {
    loadSettings();
    bindActions();
});

function loadSettings() {
    // Notifications
    const orderNotif = document.getElementById('orderNotifications');
    const promoNotif = document.getElementById('promotionNotifications');
    const reqNotif = document.getElementById('requestNotifications');
    const payNotif = document.getElementById('paymentNotifications');

    if (orderNotif) orderNotif.checked = settingsData.notifications.orders;
    if (promoNotif) promoNotif.checked = settingsData.notifications.promotions;
    if (reqNotif) reqNotif.checked = settingsData.notifications.requests;
    if (payNotif) payNotif.checked = settingsData.notifications.payments;

    // Preferences
    const lang = document.getElementById('languageSelect');
    const currency = document.getElementById('currencySelect');
    const marketing = document.getElementById('marketingEmails');

    if (lang) lang.value = settingsData.preferences.language;
    if (currency) currency.value = settingsData.preferences.currency;
    if (marketing) marketing.checked = settingsData.preferences.marketing;

    // Delivery
    const delivery = document.getElementById('defaultDelivery');
    if (delivery) delivery.value = settingsData.delivery.preferredMethod;
}

function bindActions() {
    const saveBtn = document.getElementById('settingsSaveBtn');
    const resetBtn = document.getElementById('settingsResetBtn');
    const successAlert = document.getElementById('settingsSaveSuccess');
    const deleteBtn = document.getElementById('deleteAccountBtn');

    saveBtn?.addEventListener('click', () => {
        // Save settings
        settingsData.notifications.orders = document.getElementById('orderNotifications')?.checked || false;
        settingsData.notifications.promotions = document.getElementById('promotionNotifications')?.checked || false;
        settingsData.notifications.requests = document.getElementById('requestNotifications')?.checked || false;
        settingsData.notifications.payments = document.getElementById('paymentNotifications')?.checked || false;

        settingsData.preferences.language = document.getElementById('languageSelect')?.value || 'en';
        settingsData.preferences.currency = document.getElementById('currencySelect')?.value || 'NGN';
        settingsData.preferences.marketing = document.getElementById('marketingEmails')?.checked || false;

        settingsData.delivery.preferredMethod = document.getElementById('defaultDelivery')?.value || 'Delivery';

        successAlert?.classList.remove('hidden');
        setTimeout(() => {
            successAlert?.classList.add('hidden');
        }, 3000);
    });

    resetBtn?.addEventListener('click', () => {
        loadSettings();
        alert('Settings have been reset to defaults.');
    });

    deleteBtn?.addEventListener('click', () => {
        const confirmed = confirm('Are you sure you want to delete your account? This cannot be undone.');
        if (confirmed) {
            alert('Account deletion requested. This would be processed by the backend in a real application.');
        }
    });
}
