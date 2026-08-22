/**
 * MADAM HY - Edit product form interactions.
 * Product update form integration.
 */

document.addEventListener("DOMContentLoaded", () => {
    const form = document.getElementById("editProductForm");
    const imageInput = document.getElementById("editProductImage");
    const imagePreviewBox = document.getElementById("editImagePreviewBox");
    const messageBox = document.getElementById("editProductMessage");

    if (!form) return;

    if (!canManageProducts()) {
        setManagementDisabled(form, messageBox, "You do not have permission to update products.");
        return;
    }

    const productId = getProductId();
    if (!productId) {
        showMessage(messageBox, "Product ID was not found.", "error");
        return;
    }

    loadProduct(productId);

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

    form.addEventListener("submit", async event => {
        event.preventDefault();

        const requiredFields = [
            document.getElementById("editProductName"),
            document.getElementById("editProductCategory"),
            document.getElementById("editRetailPrice")
        ];

        const missingField = requiredFields.find(field => !field.value.trim());

        if (missingField) {
            showMessage(messageBox, "Please complete all required fields before updating this product.", "error");
            missingField.focus();
            return;
        }

        const response = await apiRequest(`/products/${productId}/update/`, {
            method: "POST",
            body: {
                name: document.getElementById("editProductName").value.trim(),
                category_id: Number(document.getElementById("editProductCategory").value),
                selling_price: document.getElementById("editRetailPrice").value,
                cost_price: document.getElementById("editCostPrice").value || null,
                reorder_level: document.getElementById("editReorderLevel").value || 0,
                description: document.getElementById("editDescription").value.trim()
            }
        });

        if (!response.success) {
            showApiErrors(messageBox, response);
            return;
        }

        showMessage(messageBox, response.message || "Product updated successfully.", "success");
        window.setTimeout(() => {
            window.location.href = `/preview/products/detail/?id=${productId}`;
        }, 500);
    });
});

async function loadProduct(productId) {
    const response = await apiRequest(`/products/${productId}/`);
    if (!response.success || !response.data) {
        showMessage(document.getElementById("editProductMessage"), response.message || "Unable to load product.", "error");
        return;
    }

    const product = response.data;
    await loadCategories(product.category?.id);
    setValue("editProductName", product.name);
    setValue("editProductSku", product.sku);
    setValue("editDescription", product.description || "");
    setValue("editRetailPrice", product.selling_price);
    setValue("editCostPrice", product.cost_price || "");
    setValue("editReorderLevel", product.reorder_level ?? 0);
    setValue("editStockQty", product.stock?.quantity ?? 0);
    document.getElementById("editProductSku").disabled = true;
    document.getElementById("editStockQty").disabled = true;
}

async function loadCategories(selectedId) {
    const select = document.getElementById("editProductCategory");
    if (!select) return;
    const response = await apiRequest("/products/categories/");
    if (!response.success) {
        showMessage(document.getElementById("editProductMessage"), response.message || "Unable to load categories.", "error");
        return;
    }
    select.replaceChildren(new Option("Select category", ""));
    (response.data?.categories || []).forEach(category => {
        select.add(new Option(category.name, String(category.id)));
    });
    if (selectedId !== undefined) select.value = String(selectedId);
}

function getProductId() {
    return new URLSearchParams(window.location.search).get("id");
}

function setValue(id, value) {
    const element = document.getElementById(id);
    if (element) element.value = value;
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
    showMessage(element, details || response.message || "Unable to update product.", "error");
}

function showMessage(element, text, type) {
    if (!element) return;

    element.hidden = false;
    element.textContent = text;
    element.classList.remove("alert-success", "alert-error", "alert-info", "alert-warning");
    element.classList.add(type === "error" ? "alert-error" : "alert-success");
}
