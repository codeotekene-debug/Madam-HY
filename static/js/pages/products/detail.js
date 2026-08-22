/** MADAM HY - Read-only product detail. */

document.addEventListener("DOMContentLoaded", () => {
    loadProductDetail();
    setupManagementControls();
    setupImageManagement();
});

async function loadProductDetail() {
    const productId = document.querySelector(".product-detail-page")?.dataset.productId
        || new URLSearchParams(window.location.search).get("id")
        || window.location.pathname.match(/\/products\/(\d+)\/?$/)?.[1];
    if (!productId) {
        showDetailMessage("Product ID was not found.");
        return;
    }

    const response = await apiRequest(`/products/${productId}/`);
    if (!response.success || !response.data) {
        showDetailMessage(response.message || "Unable to load product details.");
        return;
    }

    renderProductDetail(response.data);
}

function setupManagementControls() {
    const page = document.querySelector(".product-detail-page");
    const productId = page?.dataset.productId
        || new URLSearchParams(window.location.search).get("id");
    const editLink = document.getElementById("editProductLink");
    const deactivateButton = document.getElementById("deactivateProductBtn");
    if (!canManageProducts()) {
        editLink?.remove();
        deactivateButton?.remove();
        return;
    }
    if (editLink && productId) editLink.href = `/preview/products/edit/?id=${productId}`;
    deactivateButton?.addEventListener("click", () => deactivateProduct(productId));
}

async function deactivateProduct(productId) {
    if (!productId || !window.confirm("Deactivate this product? It will remain in the database but no longer appear in the active catalog.")) return;
    const response = await apiRequest(`/products/${productId}/deactivate/`, { method: "POST" });
    if (!response.success) {
        showDetailMessage(formatApiErrors(response) || "Unable to deactivate product.");
        return;
    }
    window.location.href = "/preview/products/";
}

function renderProductDetail(product) {
    const status = normalizeStatus(product.stock?.status);
    const image = product.primary_image?.url || product.images?.[0]?.url || "data:image/gif;base64,R0lGODlhAQABAAD/ACwAAAAAAQABAAACADs=";
    setText("productName", product.name);
    setText("productSku", `SKU: ${product.sku}`);
    setText("productCategory", product.category?.name || "Uncategorised");
    setText("productPrice", `₦ ${formatCurrency(product.selling_price)}`);
    setText("productStockStatus", formatStatus(status));
    setText("productDescription", product.description || "No description available.");
    setText("productAvailability", `${product.stock?.quantity ?? 0} units`);
    setText("productCategoryDetail", product.category?.name || "Uncategorised");
    setText("productNameDetail", product.name);
    setText("productUnitCost", product.cost_price ? `₦ ${formatCurrency(product.cost_price)}` : "Not available");
    setText("productReorderLevel", `${product.reorder_level ?? 0} units`);
    setText("productAvailableStock", `${product.stock?.quantity ?? 0} units`);
    setText("productInventoryStatus", formatStatus(status));
    setText("productCreatedAt", formatDate(product.created_at));
    setText("productUpdatedAt", formatDate(product.updated_at));

    const stockBadge = document.getElementById("productStockStatus");
    stockBadge?.classList.add(`status-${status}`);
    const mainImage = document.getElementById("productMainImage");
    if (mainImage) {
        mainImage.src = image;
        mainImage.alt = product.primary_image?.alt_text || product.name;
    }

    const gallery = document.getElementById("productImageGallery");
    if (gallery) {
        gallery.replaceChildren(...(product.images || []).map(item => createImageCard(item, product.name)));
    }
}

function setupImageManagement() {
    const management = document.getElementById("imageManagement");
    const form = document.getElementById("imageUploadForm");
    if (!management || !form) return;

    if (!canManageImages()) return;
    management.hidden = false;

    const input = document.getElementById("productImageUpload");
    input?.addEventListener("change", previewImage);
    form.addEventListener("submit", uploadProductImage);
}

function previewImage(event) {
    const file = event.target.files?.[0];
    if (!file) return;
    if (file.size > 5 * 1024 * 1024) {
        showImageMessage("Image must be 5 MB or smaller.", "error");
        event.target.value = "";
        return;
    }
    const extension = file.name.toLowerCase().split(".").pop();
    if (file.type && !["image/jpeg", "image/png", "image/webp"].includes(file.type)
        || !["jpg", "jpeg", "png", "webp"].includes(extension)) {
        showImageMessage("Choose a JPEG, PNG, or WEBP image.", "error");
        event.target.value = "";
        return;
    }

    const preview = document.getElementById("imageUploadPreview");
    if (preview) {
        preview.replaceChildren();
        const image = document.createElement("img");
        image.src = URL.createObjectURL(file);
        image.alt = "Selected image preview";
        preview.append(image);
    }
}

async function uploadProductImage(event) {
    event.preventDefault();
    const page = document.querySelector(".product-detail-page");
    const productId = page?.dataset.productId || new URLSearchParams(window.location.search).get("id");
    const input = document.getElementById("productImageUpload");
    const file = input?.files?.[0];
    if (!productId || !file) {
        showImageMessage("Select an image to upload.", "error");
        return;
    }
    const formData = new FormData();
    formData.append("image", file);
    formData.append("alt_text", document.getElementById("imageAltText")?.value.trim() || "");
    const displayOrder = document.getElementById("imageDisplayOrder")?.value;
    if (displayOrder) formData.append("display_order", displayOrder);
    formData.append("is_primary", String(Boolean(document.getElementById("imageIsPrimary")?.checked)));

    const response = await apiRequest(`/products/${productId}/images/`, {
        method: "POST",
        body: formData
    });
    if (!response.success) {
        showImageMessage(formatApiErrors(response) || "Unable to upload image.", "error");
        return;
    }
    showImageMessage(response.message || "Image uploaded successfully.", "success");
    event.target.reset();
    document.getElementById("imageUploadPreview")?.replaceChildren();
    await loadProductDetail();
}

function createImageCard(image, productName) {
    const card = document.createElement("article");
    card.className = `product-image-card${image.is_primary ? " is-primary" : ""}`;
    card.dataset.imageId = image.id;

    const preview = document.createElement("img");
    preview.src = image.url || "data:image/gif;base64,R0lGODlhAQABAAD/ACwAAAAAAQABAAACADs=";
    preview.alt = image.alt_text || productName;
    preview.onerror = () => {
        preview.src = "data:image/gif;base64,R0lGODlhAQABAAD/ACwAAAAAAQABAAACADs=";
    };
    preview.addEventListener("click", () => setMainImage(image));

    const imageId = document.createElement("span");
    imageId.className = "image-meta";
    imageId.textContent = `Image ${image.id} · Order ${image.display_order}`;

    const altInput = document.createElement("input");
    altInput.className = "form-control";
    altInput.type = "text";
    altInput.maxLength = 200;
    altInput.value = image.alt_text || "";
    altInput.placeholder = "Alt text";

    const orderInput = document.createElement("input");
    orderInput.className = "form-control";
    orderInput.type = "number";
    orderInput.min = "1";
    orderInput.value = image.display_order;
    orderInput.title = "Display order";

    const actions = document.createElement("div");
    actions.className = "image-card-actions";
    const primary = createImageAction(image.is_primary ? "Primary" : "Set primary", () => updateImage(image.id, { is_primary: true }));
    primary.disabled = image.is_primary;
    const save = createImageAction("Save", () => updateImage(image.id, {
        alt_text: altInput.value.trim(),
        display_order: orderInput.value
    }));
    const remove = createImageAction("Remove", () => deleteImage(image.id, image.is_primary));
    actions.append(primary, save, remove);

    card.append(preview, imageId, altInput, orderInput, actions);
    return card;
}

function createImageAction(label, handler) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "btn btn-secondary btn-sm";
    button.textContent = label;
    button.addEventListener("click", handler);
    return button;
}

function setMainImage(image) {
    const main = document.getElementById("productMainImage");
    if (!main) return;
    main.src = image.url || "data:image/gif;base64,R0lGODlhAQABAAD/ACwAAAAAAQABAAACADs=";
    main.alt = image.alt_text || "Product";
}

async function updateImage(imageId, fields) {
    const productId = getProductId();
    const response = await apiRequest(`/products/${productId}/images/${imageId}/`, {
        method: "PATCH",
        body: fields
    });
    if (!response.success) {
        showImageMessage(formatApiErrors(response) || "Unable to update image.", "error");
        return;
    }
    showImageMessage(response.message || "Image updated successfully.", "success");
    await loadProductDetail();
}

async function deleteImage(imageId, isPrimary) {
    if (!window.confirm(isPrimary
        ? "Remove this primary image? The backend will promote a replacement when available."
        : "Remove this image?")) return;
    const productId = getProductId();
    const response = await apiRequest(`/products/${productId}/images/${imageId}/`, { method: "DELETE" });
    if (!response.success) {
        showImageMessage(formatApiErrors(response) || "Unable to remove image.", "error");
        return;
    }
    showImageMessage(response.message || "Image removed successfully.", "success");
    await loadProductDetail();
}

function getProductId() {
    return document.querySelector(".product-detail-page")?.dataset.productId
        || new URLSearchParams(window.location.search).get("id");
}

function showImageMessage(message, type) {
    const element = document.getElementById("imageManagementMessage");
    if (!element) return;
    element.hidden = false;
    element.textContent = message;
    element.classList.remove("alert-success", "alert-error", "alert-info", "alert-warning");
    element.classList.add(type === "error" ? "alert-error" : "alert-success");
}

function formatApiErrors(response) {
    const errors = response.errors;
    return errors && typeof errors === "object"
        ? Object.values(errors).flat().join(" ")
        : response.message;
}

function setText(id, value) {
    document.getElementById(id)?.replaceChildren(document.createTextNode(value));
}

function normalizeStatus(status) {
    return String(status || "OUT_OF_STOCK").toLowerCase().replaceAll("_", "-");
}

function formatStatus(status) {
    if (status === "in-stock") return "In stock";
    if (status === "low-stock") return "Low stock";
    return "Out of stock";
}

function formatCurrency(value) {
    return Number(value).toLocaleString("en-NG");
}

function formatDate(value) {
    return value ? new Date(value).toLocaleString() : "Not available";
}

function showDetailMessage(message) {
    document.querySelector(".product-detail-page")?.prepend(Object.assign(document.createElement("div"), {
        className: "empty-state",
        textContent: message
    }));
}

function formatApiErrors(response) {
    return response.errors && typeof response.errors === "object"
        ? Object.values(response.errors).flat().join(" ")
        : response.message;
}
