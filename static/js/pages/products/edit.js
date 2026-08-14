/**
 * MADAM HY - Edit product form interactions.
 * Frontend-only form handling, validation, and preview updates.
 */

document.addEventListener("DOMContentLoaded", () => {
    const form = document.getElementById("editProductForm");
    const imageInput = document.getElementById("editProductImage");
    const imagePreviewBox = document.getElementById("editImagePreviewBox");
    const messageBox = document.getElementById("editProductMessage");

    if (!form) return;

    imageInput?.addEventListener("change", event => {
        const file = event.target.files && event.target.files[0];

        if (!file) {
            imagePreviewBox.innerHTML = '<img src="https://images.unsplash.com/photo-1521572267360-ee0c2909d518?auto=format&fit=crop&w=600&q=80" alt="Edited product preview" />';
            return;
        }

        const reader = new FileReader();
        reader.onload = () => {
            imagePreviewBox.innerHTML = `<img src="${reader.result}" alt="Updated product preview" />`;
        };
        reader.readAsDataURL(file);
    });

    form.addEventListener("submit", event => {
        event.preventDefault();

        const requiredFields = [
            document.getElementById("editProductName"),
            document.getElementById("editProductSku"),
            document.getElementById("editProductCategory"),
            document.getElementById("editRetailPrice"),
            document.getElementById("editStockQty")
        ];

        const missingField = requiredFields.find(field => !field.value.trim());

        if (missingField) {
            showMessage(messageBox, "Please complete all required fields before updating this product.", "error");
            missingField.focus();
            return;
        }

        showMessage(messageBox, "Product information updated in the frontend preview.", "success");
    });
});

function showMessage(element, text, type) {
    if (!element) return;

    element.hidden = false;
    element.textContent = text;
    element.classList.remove("alert-success", "alert-error", "alert-info", "alert-warning");
    element.classList.add(type === "error" ? "alert-error" : "alert-success");
}
