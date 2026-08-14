/**
 * MADAM HY - Add stock interactions.
 * Frontend-only validation and success messaging for stock intake.
 */

document.addEventListener("DOMContentLoaded", () => {
    const form = document.getElementById("stockForm");
    const messageBox = document.getElementById("stockFormMessage");

    if (!form) return;

    const dateInput = document.getElementById("stockDate");
    if (dateInput && !dateInput.value) {
        dateInput.valueAsDate = new Date();
    }

    form.addEventListener("submit", event => {
        event.preventDefault();

        const product = document.getElementById("stockProduct");
        const quantity = document.getElementById("stockQuantity");

        if (!product || !quantity || !product.value.trim() || !quantity.value.trim()) {
            showMessage(messageBox, "Please choose a product and quantity before saving.", "error");
            return;
        }

        showMessage(messageBox, `${quantity.value} units were recorded for ${product.value} in the frontend inventory draft.`, "success");
        form.reset();

        if (dateInput) {
            dateInput.valueAsDate = new Date();
        }
    });
});

function showMessage(element, text, type) {
    if (!element) return;

    element.hidden = false;
    element.textContent = text;
    element.classList.remove("alert-success", "alert-error", "alert-info", "alert-warning");
    element.classList.add(type === "error" ? "alert-error" : "alert-success");
}
