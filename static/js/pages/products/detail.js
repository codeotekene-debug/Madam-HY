/** MADAM HY - Read-only product detail. */

document.addEventListener("DOMContentLoaded", loadProductDetail);

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
        gallery.replaceChildren(...(product.images || []).map(item => {
            const imageElement = document.createElement("img");
            imageElement.src = item.url || "data:image/gif;base64,R0lGODlhAQABAAD/ACwAAAAAAQABAAACADs=";
            imageElement.alt = item.alt_text || product.name;
            imageElement.className = item.is_primary ? "is-primary" : "";
            return imageElement;
        }));
    }
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
