/**
 * MADAM HY - Add product form interactions.
 * Product creation form integration.
 */

document.addEventListener("DOMContentLoaded", () => {
    const form = document.getElementById("addProductForm");
    const imageInput = document.getElementById("productImage");
    const imagePreviewBox = document.getElementById("imagePreviewBox");
    const messageBox = document.getElementById("productFormMessage");

    if (!form) return;

    if (!canManageProducts()) {
        setManagementDisabled(form, messageBox, "You do not have permission to create products.");
        return;
    }

    loadCategories();

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

    form.addEventListener("submit", async event => {
        event.preventDefault();

        const requiredFields = [
            document.getElementById("productName"),
            document.getElementById("productSku"),
            document.getElementById("productCategory"),
            document.getElementById("retailPrice")
        ];

        const missingField = requiredFields.find(field => !field.value.trim());

        if (missingField) {
            showMessage(messageBox, "Please complete all required fields before saving.", "error");
            missingField.focus();
            return;
        }

        const response = await apiRequest("/products/create/", {
            method: "POST",
            body: {
                name: document.getElementById("productName").value.trim(),
                sku: document.getElementById("productSku").value.trim(),
                category_id: Number(document.getElementById("productCategory").value),
                selling_price: document.getElementById("retailPrice").value,
                cost_price: document.getElementById("costPrice").value || null,
                reorder_level: document.getElementById("reorderLevel").value || 0,
                description: document.getElementById("productDescription").value.trim()
            }
        });

        if (!response.success) {
            showApiErrors(messageBox, response);
            return;
        }

        showMessage(messageBox, response.message || "Product created successfully.", "success");
        const productId = response.data?.id;
        window.setTimeout(() => {
            window.location.href = productId
                ? `/preview/products/detail/?id=${productId}`
                : "/preview/products/";
        }, 500);
    });
});

async function loadCategories() {
    const select = document.getElementById("productCategory");
    if (!select) return;
    const response = await apiRequest("/products/categories/");
    if (!response.success) {
        showMessage(document.getElementById("productFormMessage"), response.message || "Unable to load categories.", "error");
        return;
    }
    select.replaceChildren(new Option("Select category", ""));
    (response.data?.categories || []).forEach(category => {
        select.add(new Option(category.name, String(category.id)));
    });
}

function setManagementDisabled(form, messageBox, message) {
    form.querySelectorAll("input, select, textarea, button").forEach(control => {
        control.disabled = true;
    });
    showMessage(messageBox, message, "error");
}

function showApiErrors(element, response) {
    const errors = response.errors;
    const details = errors && typeof errors === "object"
        ? Object.values(errors).flat().join(" ")
        : "";
    showMessage(element, details || response.message || "Unable to save product.", "error");
}

function showMessage(element, text, type) {
    if (!element) return;

    element.hidden = false;
    element.textContent = text;
    element.classList.remove("alert-success", "alert-error", "alert-info", "alert-warning");
    element.classList.add(type === "error" ? "alert-error" : "alert-success");
}
