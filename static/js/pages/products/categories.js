/**
 * MADAM HY - Product category interactions.
 * Frontend-only category management demo for retail catalog grouping.
 */

const categoryData = [
    { name: "Fashion", description: "Clothing, accessories, and style pieces", color: "#087a3d" },
    { name: "Beauty", description: "Skincare and wellness essentials", color: "#4aa96c" },
    { name: "Home", description: "Household and interior items", color: "#d4a373" },
    { name: "Electronics", description: "Modern devices and accessories", color: "#5b8def" }
];

document.addEventListener("DOMContentLoaded", () => {
    renderCategoryList();
    const form = document.getElementById("categoryForm");

    form?.addEventListener("submit", event => {
        event.preventDefault();

        const nameInput = document.getElementById("categoryName");

        if (!nameInput || !nameInput.value.trim()) {
            alert("Please enter a category name.");
            return;
        }

        categoryData.unshift({
            name: nameInput.value.trim(),
            description: document.getElementById("categoryDescription")?.value.trim() || "Custom retail category",
            color: document.getElementById("categoryColor")?.value || "#087a3d"
        });

        form.reset();
        renderCategoryList();
    });
});

function renderCategoryList() {
    const list = document.getElementById("categoryList");
    if (!list) return;

    list.innerHTML = categoryData.map(category => `
        <div class="category-item">
            <div class="category-item-main">
                <span class="category-color" style="background:${category.color};"></span>
                <div>
                    <div class="category-name">${category.name}</div>
                    <div class="category-meta">${category.description}</div>
                </div>
            </div>
            <div class="category-actions">
                <button type="button" class="icon-button" aria-label="Edit ${category.name}">✎</button>
                <button type="button" class="icon-button" aria-label="Delete ${category.name}">🗑</button>
            </div>
        </div>
    `).join("");
}
