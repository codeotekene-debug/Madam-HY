/**
 * MADAM HY - Profile page interactions.
 * Frontend-only behavior for Phase 1.
 */

document.addEventListener("DOMContentLoaded", () => {
    setupProfileTabs();
    setupProfileEditing();
    setupProfilePlaceholders();
});


function setupProfileTabs() {
    const tabs =
        document.querySelectorAll("[data-profile-tab]");

    const panels =
        document.querySelectorAll("[data-profile-panel]");

    tabs.forEach(tab => {
        tab.addEventListener("click", () => {
            const target =
                tab.dataset.profileTab;

            tabs.forEach(item => {
                const active =
                    item === tab;

                item.classList.toggle("active", active);
                item.setAttribute("aria-selected", String(active));
            });

            panels.forEach(panel => {
                const active =
                    panel.dataset.profilePanel === target;

                panel.classList.toggle("active", active);
                panel.hidden = !active;
            });
        });
    });
}


function setupProfileEditing() {
    const form =
        document.getElementById("profileForm");

    const editButton =
        document.querySelector("[data-profile-edit-toggle]");

    const saveButton =
        document.querySelector("[data-profile-save]");

    if (!form || !editButton || !saveButton) return;

    const editableFields =
        form.querySelectorAll(
            "#detailsPanel input, #detailsPanel textarea"
        );

    form.addEventListener("submit", event => {
        event.preventDefault();

        showProfileMessage(
            "Use the Save changes button to stage profile updates."
        );
    });

    editButton.addEventListener("click", () => {
        const editing =
            editButton.dataset.editing === "true";

        setEditingState(
            editableFields,
            editButton,
            saveButton,
            !editing
        );
    });

    saveButton.addEventListener("click", () => {
        setEditingState(
            editableFields,
            editButton,
            saveButton,
            false
        );

        showProfileMessage(
            "Profile changes are staged for future backend saving."
        );
    });
}


function setupProfilePlaceholders() {
    const securityActions =
        document.querySelectorAll("[data-profile-security-action]");

    securityActions.forEach(action => {
        action.addEventListener("click", () => {
            showProfileMessage(
                "Security changes are ready for future backend integration."
            );
        });
    });
}


function setEditingState(
    fields,
    editButton,
    saveButton,
    editing
) {
    fields.forEach(field => {
        field.disabled = !editing;
    });

    editButton.dataset.editing =
        String(editing);

    editButton.textContent =
        editing ? "Cancel edit" : "Edit profile";

    saveButton.disabled =
        !editing;
}


function showProfileMessage(message) {
    const messageBox =
        document.getElementById("profileMessage");

    if (!messageBox) return;

    messageBox.hidden = false;
    messageBox.textContent = message;
}
