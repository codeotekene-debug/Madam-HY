/**
 * MADAM HY - Add product form interactions.
 * Frontend-only UI validation and preview for product creation.
 */

document.addEventListener("DOMContentLoaded", () => {
    const form = document.getElementById("addProductForm");
    const imageInput = document.getElementById("productImage");
    const imagePreviewBox = document.getElementById("imagePreviewBox");
    const messageBox = document.getElementById("productFormMessage");

    if (!form) return;

    imageInput?.addEventListener("change", event => {
        const file = event.target.files && event.target.files[0];

        if (!file) {
            imagePreviewBox.innerHTML = "<span>No image selected</span>";
            return;
        }

        const reader = new FileReader();
        reader.onload = () => {
            imagePreviewBox.innerHTML = `<img src="${reader.result}" alt="Product preview" />`;
        };
        reader.readAsDataURL(file);
    });

    form.addEventListener("submit", event => {
        event.preventDefault();

        const requiredFields = [
            document.getElementById("productName"),
            document.getElementById("productSku"),
            document.getElementById("productCategory"),
            document.getElementById("retailPrice"),
            document.getElementById("stockQty")
        ];

        const missingField = requiredFields.find(field => !field.value.trim());

        if (missingField) {
            showMessage(messageBox, "Please complete all required fields before saving.", "error");
            missingField.focus();
            return;
        }

        showMessage(messageBox, "Product saved to the frontend catalog draft.", "success");
        form.reset();
        imagePreviewBox.innerHTML = "<span>No image selected</span>";
    });
});

function showMessage(element, text, type) {
    if (!element) return;

    element.hidden = false;
    element.textContent = text;
    element.classList.remove("alert-success", "alert-error", "alert-info", "alert-warning");
    element.classList.add(type === "error" ? "alert-error" : "alert-success");
}
