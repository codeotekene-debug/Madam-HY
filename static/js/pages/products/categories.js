let editingCategoryId = null;

document.addEventListener("DOMContentLoaded", () => {
    setupCategoryForm();
    setupManagementControls();
    loadCategories();
});

async function loadCategories() {
    const list = document.getElementById("categoryList");
    if (!list) return;

    setCategoryListMessage("Loading categories...");
    const response = await apiRequest("/products/categories/");
    if (!response.success) {
        setCategoryListMessage(response.message || "Unable to load categories.", true, loadCategories);
        return;
    }

    const categories = response.data?.categories || [];
    if (!categories.length) {
        setCategoryListMessage("No active categories found.");
        return;
    }

    list.replaceChildren(...categories.map(renderCategory));
}

function setupManagementControls() {
    const canManage = canManageCategories();
    const createButton = document.getElementById("createCategoryButton");
    const form = document.getElementById("categoryForm");

    if (!canManage) {
        createButton?.remove();
        form?.querySelectorAll("input, textarea, select, button").forEach(control => {
            control.disabled = true;
        });
    }

    createButton?.addEventListener("click", () => {
        resetCategoryForm();
        document.getElementById("categoryName")?.focus();
    });
}

function setupCategoryForm() {
    const form = document.getElementById("categoryForm");
    if (!form) return;

    form.addEventListener("submit", async event => {
        event.preventDefault();
        if (!canManageCategories()) return;

        const name = document.getElementById("categoryName")?.value.trim() || "";
        if (!name) {
            showCategoryMessage("Category name is required.", "error");
            document.getElementById("categoryName")?.focus();
            return;
        }

        const description = document.getElementById("categoryDescription")?.value.trim() || "";
        const url = editingCategoryId
            ? `/products/categories/${editingCategoryId}/update/`
            : "/products/categories/create/";
        const response = await apiRequest(url, {
            method: "POST",
            body: { name, description }
        });

        if (!response.success) {
            showCategoryMessage(formatApiErrors(response) || "Unable to save category.", "error");
            return;
        }

        showCategoryMessage(response.message || "Category saved successfully.", "success");
        resetCategoryForm();
        await loadCategories();
    });

    document.getElementById("categoryResetButton")?.addEventListener("click", () => {
        window.setTimeout(resetCategoryForm, 0);
    });
}

function renderCategory(category) {
    const item = document.createElement("div");
    item.className = "category-item";

    const main = document.createElement("div");
    main.className = "category-item-main";
    const color = document.createElement("span");
    color.className = "category-color";
    color.style.backgroundColor = "var(--primary)";
    const details = document.createElement("div");
    const name = document.createElement("div");
    name.className = "category-name";
    name.textContent = category.name;
    const meta = document.createElement("div");
    meta.className = "category-meta";
    meta.textContent = `${category.slug} · ${category.description || "No description available."}`;
    details.append(name, meta);
    main.append(color, details);

    const status = document.createElement("span");
    status.className = "category-meta";
    status.textContent = category.is_active ? "Active" : "Inactive";

    item.append(main, status);
    if (canManageCategories()) {
        const actions = document.createElement("div");
        actions.className = "category-actions";
        const edit = createCategoryAction("Edit", () => beginEdit(category));
        const deactivate = createCategoryAction("Deactivate", () => deactivateCategory(category));
        actions.append(edit, deactivate);
        item.append(actions);
    }
    return item;
}

function createCategoryAction(label, handler) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "icon-button";
    button.textContent = label;
    button.addEventListener("click", handler);
    return button;
}

function beginEdit(category) {
    editingCategoryId = category.id;
    document.getElementById("categoryFormTitle").textContent = "Edit category";
    document.getElementById("categorySubmitButton").textContent = "Update category";
    document.getElementById("categoryName").value = category.name;
    document.getElementById("categoryDescription").value = category.description || "";
    document.getElementById("categoryName").focus();
}

async function deactivateCategory(category) {
    if (!window.confirm(`Deactivate "${category.name}"? It will remain available in the database but no longer be active.`)) return;

    const response = await apiRequest(`/products/categories/${category.id}/deactivate/`, { method: "POST" });
    if (!response.success) {
        showCategoryMessage(formatApiErrors(response) || "Unable to deactivate category.", "error");
        return;
    }

    showCategoryMessage(response.message || "Category deactivated successfully.", "success");
    await loadCategories();
}

function resetCategoryForm() {
    editingCategoryId = null;
    document.getElementById("categoryForm")?.reset();
    const title = document.getElementById("categoryFormTitle");
    const submit = document.getElementById("categorySubmitButton");
    if (title) title.textContent = "Add category";
    if (submit) submit.textContent = "Save category";
}

function showCategoryMessage(message, type) {
    const element = document.getElementById("categoryFormMessage");
    if (!element) return;
    element.hidden = false;
    element.textContent = message;
    element.classList.remove("alert-success", "alert-error", "alert-info", "alert-warning");
    element.classList.add(type === "error" ? "alert-error" : "alert-success");
}

function formatApiErrors(response) {
    const errors = response.errors;
    const details = errors && typeof errors === "object"
        ? Object.values(errors).flat().join(" ")
        : "";
    return details || response.message;
}

function setCategoryListMessage(message, isError = false, retry) {
    const list = document.getElementById("categoryList");
    if (!list) return;
    list.replaceChildren();
    const text = document.createElement("p");
    text.className = "category-meta";
    text.textContent = message;
    list.append(text);
    if (isError && retry) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "btn btn-secondary btn-sm";
        button.textContent = "Retry";
        button.addEventListener("click", retry);
        list.append(button);
    }
}
