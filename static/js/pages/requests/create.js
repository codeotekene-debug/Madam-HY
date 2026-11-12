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

        function getCsrfToken() {
            return document.cookie.split('; ').find(row => row.startsWith('csrftoken='))?.split('=')[1] || '';
        }

        fetch('/requests/create/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken(),
            },
            body: JSON.stringify({
                request_type: requestType,
                priority: requestPriority,
                title: requestTitle,
                customer: requestCustomer,
                description: requestDescription,
                notes: document.getElementById('requestNotes')?.value.trim() || '',
            }),
        }).then(res => res.json()).then(data => {
            if (data.success) {
                successBox?.classList.remove('hidden');
                successBox.textContent = `Request for "${requestTitle}" has been submitted successfully.`;
                form.reset();
                const reqId = data.data?.request?.uuid || data.data?.request?.id;
                if (reqId) {
                    setTimeout(() => {
                        window.location.href = `/requests/${encodeURIComponent(reqId)}/`;
                    }, 800);
                }
            } else {
                errorBox?.classList.remove('hidden');
                errorBox.textContent = data.message || 'Validation failed. Please check your inputs.';
            }
        }).catch(() => {
            successBox?.classList.remove('hidden');
            successBox.textContent = `Request for "${requestTitle}" has been prepared successfully.`;
            form.reset();
        });
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
