/**
 * MADAM HY - Account login and password-help interactions.
 * Frontend-only behavior for Phase 1.
 */

document.addEventListener("DOMContentLoaded", () => {
    setupPasswordToggles();
    setupDemoForms();
});


function setupPasswordToggles() {
    const toggles =
        document.querySelectorAll("[data-password-toggle]");

    toggles.forEach(toggle => {
        toggle.addEventListener("click", () => {
            const input =
                document.getElementById(toggle.dataset.passwordToggle);

            if (!input) return;

            const isPassword =
                input.type === "password";

            input.type =
                isPassword ? "text" : "password";

            toggle.textContent =
                isPassword ? "Hide" : "Show";

            toggle.setAttribute(
                "aria-label",
                isPassword ? "Hide password" : "Show password"
            );
        });
    });
}


function setupDemoForms() {
    const forms =
        document.querySelectorAll("[data-demo-form]");

    forms.forEach(form => {
        form.addEventListener("submit", event => {
            event.preventDefault();

            if (!validateRequiredFields(form)) {
                showMessage(
                    form,
                    "Please complete the required fields before continuing.",
                    "error"
                );

                return;
            }

            setSubmitLoading(form, true);

            window.setTimeout(() => {
                setSubmitLoading(form, false);

                showMessage(
                    form,
                    "This page is ready for backend authentication integration.",
                    "info"
                );
            }, 450);
        });
    });
}


function validateRequiredFields(form) {
    let valid = true;

    const fields =
        form.querySelectorAll("[required]");

    fields.forEach(field => {
        const error =
            form.querySelector(`[data-error-for="${field.id}"]`);

        const empty =
            field.type === "checkbox"
                ? !field.checked
                : !field.value.trim();

        field.classList.toggle("is-invalid", empty);

        if (error) {
            error.textContent =
                empty ? "This field is required." : "";
        }

        if (empty) {
            valid = false;
        }
    });

    return valid;
}


function showMessage(form, message, type) {
    const messageBox =
        form.parentElement.querySelector(".account-message");

    if (!messageBox) return;

    messageBox.hidden = false;
    messageBox.textContent = message;

    messageBox.classList.toggle("alert-error", type === "error");
    messageBox.classList.toggle("alert-info", type !== "error");
}


function setSubmitLoading(form, loading) {
    const button =
        form.querySelector("button[type='submit']");

    if (!button) return;

    if (!button.dataset.defaultText) {
        button.dataset.defaultText = button.textContent.trim();
    }

    button.disabled = loading;
    button.textContent =
        loading ? "Please wait..." : button.dataset.defaultText;
}
