/**
 * MADAM HY - Customer Profile
 * Frontend-only customer profile management
 */

const profileData = {
    name: 'Aisha Bello',
    email: 'aisha@email.com',
    phone: '08123456789',
    address: '123 Main Street, Lagos, Nigeria',
    memberSince: '2025-06-15',
    status: 'Active',
    totalOrders: 12
};

document.addEventListener('DOMContentLoaded', () => {
    renderProfile();
    bindActions();
});

function renderProfile() {
    // View mode
    document.getElementById('profileName')?.replaceChildren(document.createTextNode(profileData.name));
    document.getElementById('profileEmail')?.replaceChildren(document.createTextNode(profileData.email));
    document.getElementById('profilePhone')?.replaceChildren(document.createTextNode(profileData.phone));
    document.getElementById('profileAddress')?.replaceChildren(document.createTextNode(profileData.address));

    // Account info
    document.getElementById('profileMemberSince')?.replaceChildren(document.createTextNode(formatDate(profileData.memberSince)));
    document.getElementById('profileAccountStatus')?.replaceChildren(document.createTextNode(profileData.status));
    document.getElementById('profileTotalOrders')?.replaceChildren(document.createTextNode(String(profileData.totalOrders)));

    // Edit mode
    document.getElementById('profileEditName')?.setAttribute('value', profileData.name);
    document.getElementById('profileEditEmail')?.setAttribute('value', profileData.email);
    document.getElementById('profileEditPhone')?.setAttribute('value', profileData.phone);
    document.getElementById('profileEditAddress')?.setAttribute('value', profileData.address);
}

function bindActions() {
    const editBtn = document.getElementById('editProfileBtn');
    const cancelBtn = document.getElementById('profileCancelBtn');
    const form = document.getElementById('profileEditForm');
    const viewMode = document.getElementById('profileViewMode');
    const successAlert = document.getElementById('profileEditSuccess');
    const errorAlert = document.getElementById('profileEditError');

    editBtn?.addEventListener('click', () => {
        viewMode?.classList.add('hidden');
        form?.classList.remove('hidden');
    });

    cancelBtn?.addEventListener('click', () => {
        viewMode?.classList.remove('hidden');
        form?.classList.add('hidden');
        renderProfile();
        successAlert?.classList.add('hidden');
        errorAlert?.classList.add('hidden');
    });

    form?.addEventListener('submit', (e) => {
        e.preventDefault();
        errorAlert?.classList.add('hidden');
        successAlert?.classList.add('hidden');

        const name = document.getElementById('profileEditName')?.value.trim();
        const email = document.getElementById('profileEditEmail')?.value.trim();
        const phone = document.getElementById('profileEditPhone')?.value.trim();
        const address = document.getElementById('profileEditAddress')?.value.trim();

        if (!name || !email || !phone || !address) {
            errorAlert?.classList.remove('hidden');
            errorAlert!.textContent = 'Please fill in all required fields.';
            return;
        }

        profileData.name = name;
        profileData.email = email;
        profileData.phone = phone;
        profileData.address = address;

        successAlert?.classList.remove('hidden');
        successAlert!.textContent = 'Your profile has been updated successfully.';

        setTimeout(() => {
            viewMode?.classList.remove('hidden');
            form?.classList.add('hidden');
            renderProfile();
            successAlert?.classList.add('hidden');
        }, 2000);
    });
}

function formatDate(value) {
    return new Date(value).toLocaleDateString('en-GB', {
        day: '2-digit',
        month: 'short',
        year: 'numeric'
    });
}
