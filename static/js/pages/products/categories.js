document.addEventListener("DOMContentLoaded", loadCategories);

async function loadCategories() {
    const list = document.getElementById("categoryList");
    if (!list) return;
    document.getElementById("categoryForm")?.addEventListener("submit", event => event.preventDefault());
    const response = await apiRequest("/products/categories/");
    if (!response.success) {
        list.replaceChildren(document.createTextNode(response.message || "Unable to load categories."));
        return;
    }

    list.innerHTML = (response.data?.categories || []).map(category => `
        <div class="category-item">
            <div class="category-item-main">
                <span class="category-color"></span>
                <div>
                    <div class="category-name">${category.name}</div>
                    <div class="category-meta">${category.slug} · ${category.description || "No description available."}</div>
                </div>
            </div>
            <span class="category-meta">${category.is_active ? "Active" : "Inactive"}</span>
        </div>
    `).join("");
}
