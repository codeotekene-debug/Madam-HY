/**
 * MADAM HY - Register and password reset interactions.
 * Frontend-only behavior for Phase 1.
 */

document.addEventListener("DOMContentLoaded", () => {
    setupPasswordToggles();
    setupPasswordStrength();
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

            const showing =
                input.type === "password";

            input.type =
                showing ? "text" : "password";

            toggle.textContent =
                showing ? "Hide" : "Show";

            toggle.setAttribute(
                "aria-label",
                showing ? "Hide password" : "Show password"
            );
        });
    });
}


function setupPasswordStrength() {
    const passwordInput =
        document.querySelector("[data-strength-source]");

    const meter =
        document.querySelector("[data-strength-meter]");

    const label =
        document.querySelector("[data-strength-label]");

    if (!passwordInput || !meter || !label) return;

    passwordInput.addEventListener("input", () => {
        const score =
            calculatePasswordScore(passwordInput.value);

        meter.classList.remove("is-fair", "is-good", "is-strong");

        if (score >= 4) {
            meter.classList.add("is-strong");
            label.textContent = "Strong password.";
        } else if (score === 3) {
            meter.classList.add("is-good");
            label.textContent = "Good password.";
        } else if (score === 2) {
            meter.classList.add("is-fair");
            label.textContent = "Fair password.";
        } else {
            label.textContent = "Use at least 8 characters.";
        }
    });
}


function calculatePasswordScore(value) {
    let score = 0;

    if (value.length >= 8) score += 1;
    if (/[A-Z]/.test(value)) score += 1;
    if (/[0-9]/.test(value)) score += 1;
    if (/[^A-Za-z0-9]/.test(value)) score += 1;

    return score;
}


function setupDemoForms() {
    const forms =
        document.querySelectorAll("[data-demo-form]");

    forms.forEach(form => {
        form.addEventListener("submit", event => {
            event.preventDefault();

            const valid =
                validateRequiredFields(form) &&
                validatePasswordConfirmation(form);

            if (!valid) {
                showMessage(
                    form,
                    "Please review the highlighted fields.",
                    "error"
                );

                return;
            }

            setSubmitLoading(form, true);

            window.setTimeout(() => {
                setSubmitLoading(form, false);

                showMessage(
                    form,
                    "This account form is ready for backend integration.",
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


function validatePasswordConfirmation(form) {
    const confirmations =
        form.querySelectorAll("[data-confirm-password]");

    let valid = true;

    confirmations.forEach(field => {
        const source =
            document.getElementById(field.dataset.confirmPassword);

        const error =
            form.querySelector(`[data-error-for="${field.id}"]`);

        const mismatch =
            source && field.value && field.value !== source.value;

        field.classList.toggle("is-invalid", mismatch);

        if (error && mismatch) {
            error.textContent = "Passwords must match.";
        }

        if (mismatch) {
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
