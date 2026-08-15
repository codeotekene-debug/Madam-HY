document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('requestForm');
    const errorBox = document.getElementById('requestFormError');
    const successBox = document.getElementById('requestFormSuccess');
    const cancelBtn = document.getElementById('requestCancelBtn');

    form?.addEventListener('submit', (event) => {
        event.preventDefault();
        clearAlerts();

        const requestType = document.getElementById('requestType')?.value.trim();
        const requestPriority = document.getElementById('requestPriority')?.value.trim();
        const requestTitle = document.getElementById('requestTitle')?.value.trim();
        const requestCustomer = document.getElementById('requestCustomer')?.value.trim();
        const requestDescription = document.getElementById('requestDescription')?.value.trim();

        if (!requestType || !requestPriority || !requestTitle || !requestCustomer || !requestDescription) {
            errorBox?.classList.remove('hidden');
            errorBox.textContent = 'Please complete all required fields before submitting the request.';
            return;
        }

        successBox?.classList.remove('hidden');
        successBox.textContent = `Request for "${requestTitle}" has been prepared successfully. The shop team can review it in the next follow-up stage.`;

        form.reset();
    });

    cancelBtn?.addEventListener('click', () => {
        form?.reset();
        clearAlerts();
    });

    function clearAlerts() {
        errorBox?.classList.add('hidden');
        successBox?.classList.add('hidden');
        errorBox.textContent = '';
        successBox.textContent = '';
    }
});
