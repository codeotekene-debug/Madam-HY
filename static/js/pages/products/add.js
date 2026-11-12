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

        if (file.size > 5 * 1024 * 1024) {
            showMessage(messageBox, "Image file must be 5MB or smaller.", "error");
            imageInput.value = "";
            imagePreviewBox.innerHTML = "<span>No image selected</span>";
            return;
        }

        const extension = file.name.toLowerCase().split(".").pop();
        if (file.type && !["image/jpeg", "image/png", "image/webp"].includes(file.type)
            || !["jpg", "jpeg", "png", "webp"].includes(extension)) {
            showMessage(messageBox, "Please select a valid JPEG, PNG, or WEBP image.", "error");
            imageInput.value = "";
            imagePreviewBox.innerHTML = "<span>No image selected</span>";
            return;
        }

        const reader = new FileReader();
        reader.onload = () => {
            imagePreviewBox.innerHTML = `<img src="${reader.result}" alt="Product preview" style="max-width: 100%; max-height: 100%; object-fit: contain;" />`;
        };
        reader.readAsDataURL(file);
    });

    form.addEventListener("reset", () => {
        if (imagePreviewBox) {
            imagePreviewBox.innerHTML = "<span>No image selected</span>";
        }
        if (messageBox) {
            messageBox.hidden = true;
        }
    });

    form.addEventListener("submit", async event => {
        event.preventDefault();

        const requiredFields = [
            document.getElementById("productName"),
            document.getElementById("productSku"),
            document.getElementById("productCategory")
        ];

        const missingField = requiredFields.find(field => !field || !field.value.trim());

        if (missingField) {
            showMessage(messageBox, "Please complete all required fields before saving.", "error");
            missingField.focus();
            return;
        }

        const retailPriceEl = document.getElementById("retailPrice");
        const costPriceEl = document.getElementById("costPrice");
        const categoryId = document.getElementById("productCategory").value;

        const formData = new FormData();
        formData.append("name", document.getElementById("productName").value.trim());
        formData.append("sku", document.getElementById("productSku").value.trim());
        formData.append("category_id", categoryId);
        formData.append("selling_price", retailPriceEl && retailPriceEl.value ? retailPriceEl.value : "0.00");
        if (costPriceEl && costPriceEl.value) {
            formData.append("cost_price", costPriceEl.value);
        }
        formData.append("reorder_level", document.getElementById("reorderLevel")?.value || 0);
        formData.append("description", document.getElementById("productDescription")?.value.trim() || "");

        const file = imageInput?.files && imageInput.files[0];
        if (file) {
            formData.append("image", file);
        }

        const submitBtn = form.querySelector('button[type="submit"]');
        if (submitBtn) submitBtn.disabled = true;

        try {
            const response = await apiRequest("/products/create/", {
                method: "POST",
                body: formData
            });

            if (!response.success) {
                showApiErrors(messageBox, response);
                return;
            }

            showMessage(messageBox, response.message || "Product created successfully.", "success");
            const productId = response.data?.id;
            window.setTimeout(() => {
                window.location.href = productId
                    ? `/products/${productId}/`
                    : "/products/";
            }, 500);
        } finally {
            if (submitBtn) submitBtn.disabled = false;
        }
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
