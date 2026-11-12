/**
 * MADAM HY - Dynamic Add Stock & Audit Reason Interactions.
 * Responds to Audit Reason (RESTOCK, CORRECTION, DAMAGE, EXPIRY) with action-specific
 * validation, live calculations, price history tracking, and real-time ledger updates.
 */

document.addEventListener("DOMContentLoaded", () => {
    const form = document.getElementById("stockForm");
    if (!form) return;

    // Core Controls
    const reasonSelect = document.getElementById("stockReason");
    const reasonDescriptionBox = document.getElementById("reasonDescriptionBox");
    const productSelect = document.getElementById("stockProduct");
    const saveButton = document.getElementById("saveStockBtn");
    const clearButton = document.getElementById("clearFormBtn");

    const errorBox = document.getElementById("stock-form-error");
    const successBox = document.getElementById("stock-form-success");

    // Product Preview Elements
    const previewCard = document.getElementById("productPreviewCard");
    const previewEmpty = document.getElementById("previewCardEmptyMessage");
    const previewContent = document.getElementById("previewCardContent");
    const productThumb = document.getElementById("productThumb");
    const productTitle = document.getElementById("productTitle");
    const productSku = document.getElementById("productSku");
    const productStockBadge = document.getElementById("productStockBadge");
    const metricStock = document.getElementById("metricStock");
    const metricCost = document.getElementById("metricCost");
    const metricSelling = document.getElementById("metricSelling");
    const metricMargin = document.getElementById("metricMargin");

    // Action Sections
    const restockSection = document.getElementById("restockSection");
    const correctionSection = document.getElementById("correctionFields");
    const damageSection = document.getElementById("damageFields");
    const expirySection = document.getElementById("expiryFields");

    // Restock Specific Inputs
    const stockQuantityInput = document.getElementById("stockQuantity");
    const stockSupplierInput = document.getElementById("stockSupplier");
    const stockDateInput = document.getElementById("stockDate");
    const stockReferenceInput = document.getElementById("stockReference");
    const stockNotesInput = document.getElementById("stockNotes");

    // Price Update Inputs
    const updatePricingToggle = document.getElementById("updatePricingToggle");
    const pricingFieldsContainer = document.getElementById("pricingFieldsContainer");
    const newCostPriceInput = document.getElementById("newCostPrice");
    const newSellingPriceInput = document.getElementById("newSellingPrice");
    const priceChangeReasonInput = document.getElementById("priceChangeReason");
    const previewGrossProfit = document.getElementById("previewGrossProfit");
    const previewGrossMargin = document.getElementById("previewGrossMargin");
    const pricingValidationError = document.getElementById("pricingValidationError");

    // Correction Inputs
    const correctionCurrentStock = document.getElementById("correctionCurrentStock");
    const actualQuantityInput = document.getElementById("actualQuantity");
    const correctionDiffBanner = document.getElementById("correctionDiffBanner");
    const correctionDiffText = document.getElementById("correctionDiffText");
    const correctionResultingStock = document.getElementById("correctionResultingStock");
    const correctionNotesInput = document.getElementById("correctionNotes");
    const confirmCorrectionCheckbox = document.getElementById("confirmCorrection");

    // Damage Inputs
    const damageQuantityInput = document.getElementById("damageQuantity");
    const damageDateInput = document.getElementById("damageDate");
    const damageReferenceInput = document.getElementById("damageReference");
    const damageAvailableStock = document.getElementById("damageAvailableStock");
    const damageReductionBanner = document.getElementById("damageReductionBanner");
    const damageReductionText = document.getElementById("damageReductionText");
    const damageRemainingStock = document.getElementById("damageRemainingStock");
    const damageReasonInput = document.getElementById("damageReason");
    const confirmDamageCheckbox = document.getElementById("confirmDamage");

    // Expiry Inputs
    const expiryQuantityInput = document.getElementById("expiryQuantity");
    const expiryDateInput = document.getElementById("expiryDate");
    const expiryBatchRefInput = document.getElementById("expiryBatchRef");
    const expiryDiscoveredDateInput = document.getElementById("expiryDiscoveredDate");
    const expiryAvailableStock = document.getElementById("expiryAvailableStock");
    const expiryReductionBanner = document.getElementById("expiryReductionBanner");
    const expiryReductionText = document.getElementById("expiryReductionText");
    const expiryRemainingStock = document.getElementById("expiryRemainingStock");
    const expiryNotesInput = document.getElementById("expiryNotes");
    const confirmExpiryCheckbox = document.getElementById("confirmExpiry");

    // Set default dates
    const today = new Date().toISOString().split("T")[0];
    if (stockDateInput && !stockDateInput.value) stockDateInput.value = today;
    if (damageDateInput && !damageDateInput.value) damageDateInput.value = today;
    if (expiryDiscoveredDateInput && !expiryDiscoveredDateInput.value) expiryDiscoveredDateInput.value = today;

    // Load Products Data from embedded JSON
    const productsMap = new Map();
    const productsDataScript = document.getElementById("products-data");
    if (productsDataScript && productsDataScript.textContent) {
        try {
            const rawList = JSON.parse(productsDataScript.textContent.trim());
            if (Array.isArray(rawList)) {
                rawList.forEach(p => {
                    productsMap.set(String(p.id), {
                        id: p.id,
                        name: p.name,
                        sku: p.sku,
                        current_stock: parseInt(p.current_stock, 10) || 0,
                        cost_price: parseFloat(p.cost_price) || 0,
                        selling_price: parseFloat(p.selling_price) || 0,
                        gross_profit: p.gross_profit || "0.00",
                        gross_margin_percentage: p.gross_margin_percentage || "0.0",
                        image_url: p.image_url || "/static/images/placeholder-product.svg",
                    });
                });
            }
        } catch (e) {
            console.error("Failed to parse embedded products data:", e);
        }
    }

    function getSelectedProduct() {
        const pid = productSelect?.value?.trim();
        return pid ? productsMap.get(String(pid)) : null;
    }

    function formatNaira(num) {
        const val = Number(num) || 0;
        return "₦" + val.toLocaleString("en-NG", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }

    function escapeHtml(str) {
        if (!str) return "";
        return String(str)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    function displayError(message, errors = null) {
        if (successBox) {
            successBox.classList.add("d-none");
            successBox.textContent = "";
        }
        if (!errorBox) return;

        let html = "";
        if (errors && typeof errors === "object") {
            const errorItems = [];
            for (const [field, fieldErrors] of Object.entries(errors)) {
                if (Array.isArray(fieldErrors)) {
                    fieldErrors.forEach(err => {
                        errorItems.push(`<li><strong>${escapeHtml(field)}:</strong> ${escapeHtml(err)}</li>`);
                    });
                } else if (typeof fieldErrors === "string") {
                    errorItems.push(`<li><strong>${escapeHtml(field)}:</strong> ${escapeHtml(fieldErrors)}</li>`);
                }
            }
            if (errorItems.length > 0) {
                html = `<div style="font-weight: 600; margin-bottom: 6px;">${escapeHtml(message || "Please correct the following errors:")}</div><ul style="margin: 0; padding-left: 20px;">${errorItems.join("")}</ul>`;
            }
        }
        if (!html) {
            html = `<strong>${escapeHtml(message || "An error occurred while saving stock.")}</strong>`;
        }

        errorBox.innerHTML = html;
        errorBox.classList.remove("d-none");
        errorBox.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }

    function displaySuccess(message) {
        if (errorBox) {
            errorBox.classList.add("d-none");
            errorBox.innerHTML = "";
        }
        if (successBox) {
            successBox.innerHTML = `<strong>${escapeHtml(message)}</strong>`;
            successBox.classList.remove("d-none");
            successBox.scrollIntoView({ behavior: "smooth", block: "nearest" });
        }
    }

    function clearMessages() {
        if (errorBox) {
            errorBox.classList.add("d-none");
            errorBox.innerHTML = "";
        }
        if (successBox) {
            successBox.classList.add("d-none");
            successBox.innerHTML = "";
        }
    }

    // --- Product Selection & Preview Card ---
    function updateProductPreview() {
        const prod = getSelectedProduct();
        if (!prod) {
            if (previewCard) {
                previewCard.classList.add("empty-preview");
                if (previewEmpty) previewEmpty.classList.remove("d-none");
                if (previewContent) previewContent.classList.add("d-none");
            }
            if (correctionCurrentStock) correctionCurrentStock.value = "--";
            if (damageAvailableStock) damageAvailableStock.value = "--";
            if (expiryAvailableStock) expiryAvailableStock.value = "--";
            updateCalculations();
            return;
        }

        if (previewCard) {
            previewCard.classList.remove("empty-preview");
            if (previewEmpty) previewEmpty.classList.add("d-none");
            if (previewContent) previewContent.classList.remove("d-none");
        }

        if (productThumb) productThumb.src = prod.image_url;
        if (productTitle) productTitle.textContent = prod.name;
        if (productSku) productSku.textContent = prod.sku;

        if (productStockBadge) {
            productStockBadge.className = "badge " + (prod.current_stock > 10 ? "badge-success" : prod.current_stock > 0 ? "badge-warning" : "badge-danger");
            productStockBadge.textContent = `${prod.current_stock} units in stock`;
        }

        if (metricStock) metricStock.textContent = `${prod.current_stock} units`;
        if (metricCost) metricCost.textContent = formatNaira(prod.cost_price);
        if (metricSelling) metricSelling.textContent = formatNaira(prod.selling_price);
        if (metricMargin) metricMargin.textContent = `${prod.gross_margin_percentage}%`;

        if (correctionCurrentStock) correctionCurrentStock.value = `${prod.current_stock} units`;
        if (damageAvailableStock) damageAvailableStock.value = `${prod.current_stock} units`;
        if (expiryAvailableStock) expiryAvailableStock.value = `${prod.current_stock} units`;

        // If pricing update fields are visible and blank, populate current prices
        if (updatePricingToggle && updatePricingToggle.checked) {
            if (newCostPriceInput && !newCostPriceInput.value) newCostPriceInput.value = prod.cost_price.toFixed(2);
            if (newSellingPriceInput && !newSellingPriceInput.value) newSellingPriceInput.value = prod.selling_price.toFixed(2);
        }

        updateCalculations();
    }

    // --- Dynamic Action Switching ---
    function updateActionUI() {
        const action = reasonSelect?.value || "RESTOCK";

        // Reset section classes
        if (restockSection) restockSection.classList.add("d-none");
        if (correctionSection) correctionSection.classList.add("d-none");
        if (damageSection) damageSection.classList.add("d-none");
        if (expirySection) expirySection.classList.add("d-none");

        if (reasonDescriptionBox) {
            reasonDescriptionBox.className = "action-description-box";
        }

        if (action === "RESTOCK") {
            if (restockSection) restockSection.classList.remove("d-none");
            if (reasonDescriptionBox) {
                reasonDescriptionBox.innerHTML = "<strong>Restock Intake:</strong> Record newly purchased or delivered inventory from suppliers. Increases available stock and optionally updates product cost and selling prices.";
            }
            if (saveButton) saveButton.textContent = "Confirm Restock Intake";

        } else if (action === "CORRECTION") {
            if (correctionSection) correctionSection.classList.remove("d-none");
            if (reasonDescriptionBox) {
                reasonDescriptionBox.classList.add("action-correction");
                reasonDescriptionBox.innerHTML = "<strong>Physical Inventory Audit:</strong> Correct an inaccurate stock balance following an authorized stocktake. Counted physical stock will replace the current balance.";
            }
            if (saveButton) saveButton.textContent = "Apply Stock Correction";

        } else if (action === "DAMAGE") {
            if (damageSection) damageSection.classList.remove("d-none");
            if (reasonDescriptionBox) {
                reasonDescriptionBox.classList.add("action-damage");
                reasonDescriptionBox.innerHTML = "<strong>Damaged Stock Write-Off:</strong> Record inventory that is broken, contaminated, or defective. Units will be permanently deducted from sellable inventory.";
            }
            if (saveButton) saveButton.textContent = "Write Off Damaged Stock";

        } else if (action === "EXPIRY") {
            if (expirySection) expirySection.classList.remove("d-none");
            if (reasonDescriptionBox) {
                reasonDescriptionBox.classList.add("action-expiry");
                reasonDescriptionBox.innerHTML = "<strong>Expired Product Removal:</strong> Remove expired goods from available stock to prevent accidental sale and ensure inventory safety compliance.";
            }
            if (saveButton) saveButton.textContent = "Remove Expired Stock";
        }

        updateCalculations();
    }

    // --- Dynamic Real-time Calculations ---
    function updateCalculations() {
        const prod = getSelectedProduct();
        const currentStock = prod ? prod.current_stock : 0;
        const action = reasonSelect?.value || "RESTOCK";

        // 1. Restock Price Updates
        if (action === "RESTOCK" && updatePricingToggle && updatePricingToggle.checked) {
            const rawCost = parseFloat(newCostPriceInput?.value) || 0;
            const rawSelling = parseFloat(newSellingPriceInput?.value) || 0;
            const profit = rawSelling - rawCost;
            const margin = rawSelling > 0 ? ((profit / rawSelling) * 100).toFixed(1) : "0.0";

            if (previewGrossProfit) previewGrossProfit.textContent = formatNaira(profit);
            if (previewGrossMargin) previewGrossMargin.textContent = `${margin}%`;

            if (pricingValidationError) {
                if (rawSelling < rawCost && rawSelling > 0) {
                    pricingValidationError.classList.remove("d-none");
                } else {
                    pricingValidationError.classList.add("d-none");
                }
            }
        }

        // 2. Correction Calculations
        if (action === "CORRECTION") {
            const actualVal = actualQuantityInput?.value?.trim();
            if (actualVal !== "" && !isNaN(parseInt(actualVal, 10))) {
                const actual = parseInt(actualVal, 10);
                const diff = actual - currentStock;

                if (correctionDiffBanner) {
                    correctionDiffBanner.className = "calc-summary-banner " + (diff > 0 ? "banner-positive" : diff < 0 ? "banner-negative" : "banner-neutral");
                }
                if (correctionDiffText) {
                    if (diff > 0) {
                        correctionDiffText.innerHTML = `<span style="color:#166534; font-weight:700;">+${diff} units</span> (Increase)`;
                    } else if (diff < 0) {
                        correctionDiffText.innerHTML = `<span style="color:#991b1b; font-weight:700;">${diff} units</span> (Deduction)`;
                    } else {
                        correctionDiffText.innerHTML = `<span style="color:#475569; font-weight:600;">0 units (No Change)</span>`;
                    }
                }
                if (correctionResultingStock) {
                    correctionResultingStock.textContent = `${actual} units`;
                }
            } else {
                if (correctionDiffBanner) correctionDiffBanner.className = "calc-summary-banner banner-neutral";
                if (correctionDiffText) correctionDiffText.textContent = "Enter verified count above";
                if (correctionResultingStock) correctionResultingStock.textContent = `${currentStock} units`;
            }
        }

        // 3. Damage Calculations
        if (action === "DAMAGE") {
            const dmgVal = damageQuantityInput?.value?.trim();
            if (dmgVal !== "" && !isNaN(parseInt(dmgVal, 10))) {
                const dmg = parseInt(dmgVal, 10);
                const remaining = currentStock - dmg;

                if (damageReductionBanner) {
                    damageReductionBanner.className = "calc-summary-banner " + (dmg > currentStock ? "banner-negative" : "banner-negative");
                }
                if (damageReductionText) {
                    if (dmg > currentStock) {
                        damageReductionText.innerHTML = `<span style="color:#dc2626; font-weight:700;">Deduction of ${dmg} exceeds stock (${currentStock})!</span>`;
                    } else {
                        damageReductionText.innerHTML = `Write-off <strong>${dmg} units</strong>`;
                    }
                }
                if (damageRemainingStock) {
                    damageRemainingStock.textContent = `${remaining >= 0 ? remaining : 0} units`;
                }
            } else {
                if (damageReductionText) damageReductionText.textContent = "Enter damaged units above";
                if (damageRemainingStock) damageRemainingStock.textContent = `${currentStock} units`;
            }
        }

        // 4. Expiry Calculations
        if (action === "EXPIRY") {
            const expVal = expiryQuantityInput?.value?.trim();
            if (expVal !== "" && !isNaN(parseInt(expVal, 10))) {
                const exp = parseInt(expVal, 10);
                const remaining = currentStock - exp;

                if (expiryReductionBanner) {
                    expiryReductionBanner.className = "calc-summary-banner " + (exp > currentStock ? "banner-negative" : "banner-negative");
                }
                if (expiryReductionText) {
                    if (exp > currentStock) {
                        expiryReductionText.innerHTML = `<span style="color:#dc2626; font-weight:700;">Removal of ${exp} exceeds stock (${currentStock})!</span>`;
                    } else {
                        expiryReductionText.innerHTML = `Remove <strong>${exp} units</strong>`;
                    }
                }
                if (expiryRemainingStock) {
                    expiryRemainingStock.textContent = `${remaining >= 0 ? remaining : 0} units`;
                }
            } else {
                if (expiryReductionText) expiryReductionText.textContent = "Enter expired units above";
                if (expiryRemainingStock) expiryRemainingStock.textContent = `${currentStock} units`;
            }
        }
    }

    // --- Event Listeners ---
    if (reasonSelect) {
        reasonSelect.addEventListener("change", () => {
            clearMessages();
            updateActionUI();
        });
    }

    if (productSelect) {
        productSelect.addEventListener("change", () => {
            clearMessages();
            updateProductPreview();
        });
    }

    if (updatePricingToggle) {
        updatePricingToggle.addEventListener("change", () => {
            if (pricingFieldsContainer) {
                if (updatePricingToggle.checked) {
                    pricingFieldsContainer.classList.remove("d-none");
                    const prod = getSelectedProduct();
                    if (prod) {
                        if (newCostPriceInput && !newCostPriceInput.value) newCostPriceInput.value = prod.cost_price.toFixed(2);
                        if (newSellingPriceInput && !newSellingPriceInput.value) newSellingPriceInput.value = prod.selling_price.toFixed(2);
                    }
                } else {
                    pricingFieldsContainer.classList.add("d-none");
                }
            }
            updateCalculations();
        });
    }

    // Input calculation triggers
    newCostPriceInput?.addEventListener("input", updateCalculations);
    newSellingPriceInput?.addEventListener("input", updateCalculations);
    actualQuantityInput?.addEventListener("input", updateCalculations);
    damageQuantityInput?.addEventListener("input", updateCalculations);
    expiryQuantityInput?.addEventListener("input", updateCalculations);

    // Clear Button
    clearButton?.addEventListener("click", () => {
        form.reset();
        clearMessages();
        if (pricingFieldsContainer) pricingFieldsContainer.classList.add("d-none");
        if (stockDateInput) stockDateInput.value = today;
        if (damageDateInput) damageDateInput.value = today;
        if (expiryDiscoveredDateInput) expiryDiscoveredDateInput.value = today;
        updateActionUI();
        updateProductPreview();
    });

    // Check pre-population from URL
    const urlParams = new URLSearchParams(window.location.search);
    const targetProductId = urlParams.get("product") || urlParams.get("product_id");
    if (targetProductId && productSelect) {
        productSelect.value = targetProductId;
    }

    // Initial render
    updateActionUI();
    updateProductPreview();

    // --- Form Submission & Validation ---
    form.addEventListener("submit", async event => {
        event.preventDefault();
        event.stopPropagation();
        clearMessages();

        const prod = getSelectedProduct();
        if (!prod) {
            displayError("Please choose a product before submitting.", {
                product: "Product selection is required.",
            });
            productSelect?.focus();
            return;
        }

        const action = reasonSelect?.value || "RESTOCK";
        const payload = {
            action: action,
            product_id: prod.id,
        };

        // Action-specific validations
        if (action === "RESTOCK") {
            const rawQty = stockQuantityInput?.value?.trim() || "";
            const qty = parseInt(rawQty, 10);
            if (!rawQty || isNaN(qty) || qty <= 0) {
                displayError("Quantity received must be a positive whole number greater than 0.", {
                    quantity: "Quantity received is required and must be greater than zero.",
                });
                stockQuantityInput?.focus();
                return;
            }

            payload.quantity = qty;
            payload.supplier = stockSupplierInput?.value?.trim() || "";
            payload.reference = stockReferenceInput?.value?.trim() || "";
            payload.date = stockDateInput?.value || today;
            payload.notes = stockNotesInput?.value?.trim() || "";

            // Check optional price updates
            if (updatePricingToggle && updatePricingToggle.checked) {
                const rawNewCost = newCostPriceInput?.value?.trim() || "";
                const rawNewSelling = newSellingPriceInput?.value?.trim() || "";
                const pReason = priceChangeReasonInput?.value?.trim() || "";

                const newCost = parseFloat(rawNewCost);
                const newSelling = parseFloat(rawNewSelling);

                if (isNaN(newCost) || newCost < 0) {
                    displayError("New cost price must be a valid positive amount.", {
                        new_cost_price: "New cost price cannot be empty or negative.",
                    });
                    newCostPriceInput?.focus();
                    return;
                }

                if (isNaN(newSelling) || newSelling < 0) {
                    displayError("New selling price must be a valid positive amount.", {
                        new_selling_price: "New selling price cannot be empty or negative.",
                    });
                    newSellingPriceInput?.focus();
                    return;
                }

                if (newSelling < newCost) {
                    displayError("Selling price cannot be lower than cost price.", {
                        new_selling_price: "Selling price cannot be lower than the cost price.",
                    });
                    newSellingPriceInput?.focus();
                    return;
                }

                if (!pReason) {
                    displayError("A reason for the price change is required.", {
                        price_change_reason: "Reason for price change is required.",
                    });
                    priceChangeReasonInput?.focus();
                    return;
                }

                payload.update_pricing = true;
                payload.new_cost_price = newCost;
                payload.new_selling_price = newSelling;
                payload.price_change_reason = pReason;
            }

        } else if (action === "CORRECTION") {
            const rawActual = actualQuantityInput?.value?.trim() || "";
            const actual = parseInt(rawActual, 10);
            if (rawActual === "" || isNaN(actual) || actual < 0) {
                displayError("Verified physical stock count must be a non-negative whole number.", {
                    actual_quantity: "Verified count is required and must be 0 or higher.",
                });
                actualQuantityInput?.focus();
                return;
            }

            const diff = actual - prod.current_stock;
            if (diff === 0) {
                displayError("Counted quantity is identical to current stock. No correction adjustment needed.", {
                    actual_quantity: "Verified count matches current balance. No adjustment required.",
                });
                actualQuantityInput?.focus();
                return;
            }

            const cNotes = correctionNotesInput?.value?.trim() || "";
            if (!cNotes) {
                displayError("A meaningful correction explanation is required.", {
                    notes: "Explanation for the stock correction is required.",
                });
                correctionNotesInput?.focus();
                return;
            }

            if (confirmCorrectionCheckbox && !confirmCorrectionCheckbox.checked) {
                displayError("Please check the audit confirmation box before applying correction.", {
                    confirmation: "Confirmation of physical inventory audit is required.",
                });
                confirmCorrectionCheckbox.focus();
                return;
            }

            payload.actual_quantity = actual;
            payload.notes = cNotes;
            payload.confirm_correction = true;

        } else if (action === "DAMAGE") {
            const rawDmg = damageQuantityInput?.value?.trim() || "";
            const dmg = parseInt(rawDmg, 10);
            if (!rawDmg || isNaN(dmg) || dmg <= 0) {
                displayError("Damaged quantity must be a positive whole number greater than 0.", {
                    quantity: "Damaged quantity is required and must be greater than zero.",
                });
                damageQuantityInput?.focus();
                return;
            }

            if (dmg > prod.current_stock) {
                displayError(`Damaged quantity (${dmg}) cannot exceed available stock (${prod.current_stock}).`, {
                    quantity: `Cannot write off more units than currently in stock (${prod.current_stock}).`,
                });
                damageQuantityInput?.focus();
                return;
            }

            const dReason = damageReasonInput?.value?.trim() || "";
            if (!dReason) {
                displayError("A description of the damage and cause is required.", {
                    notes: "Damage description and inspection details are required.",
                });
                damageReasonInput?.focus();
                return;
            }

            if (confirmDamageCheckbox && !confirmDamageCheckbox.checked) {
                displayError("Please confirm the damage write-off checkbox before proceeding.", {
                    confirmation: "Confirmation of damaged stock reduction is required.",
                });
                confirmDamageCheckbox.focus();
                return;
            }

            payload.quantity = dmg;
            payload.notes = dReason;
            payload.reference = damageReferenceInput?.value?.trim() || "Damage write-off";
            payload.date = damageDateInput?.value || today;
            payload.confirm_damage = true;

        } else if (action === "EXPIRY") {
            const rawExp = expiryQuantityInput?.value?.trim() || "";
            const exp = parseInt(rawExp, 10);
            if (!rawExp || isNaN(exp) || exp <= 0) {
                displayError("Expired quantity must be a positive whole number greater than 0.", {
                    quantity: "Expired quantity is required and must be greater than zero.",
                });
                expiryQuantityInput?.focus();
                return;
            }

            if (exp > prod.current_stock) {
                displayError(`Expired quantity (${exp}) cannot exceed available stock (${prod.current_stock}).`, {
                    quantity: `Cannot remove more units than currently in stock (${prod.current_stock}).`,
                });
                expiryQuantityInput?.focus();
                return;
            }

            const eNotes = expiryNotesInput?.value?.trim() || "";
            const eBatch = expiryBatchRefInput?.value?.trim() || "";
            if (!eNotes && !eBatch) {
                displayError("Expiry notes or batch reference is required.", {
                    notes: "Please specify expiry details, disposal notes, or batch reference.",
                });
                expiryNotesInput?.focus();
                return;
            }

            if (confirmExpiryCheckbox && !confirmExpiryCheckbox.checked) {
                displayError("Please confirm the expired stock removal checkbox before proceeding.", {
                    confirmation: "Confirmation of expired product removal is required.",
                });
                confirmExpiryCheckbox.focus();
                return;
            }

            payload.quantity = exp;
            payload.notes = eNotes;
            payload.batch_reference = eBatch;
            payload.reference = eBatch || "Expired Stock Removal";
            payload.expiry_date = expiryDateInput?.value || "";
            payload.date = expiryDiscoveredDateInput?.value || today;
            payload.confirm_expiry = true;
        }

        // Submit API Request
        if (saveButton) {
            saveButton.disabled = true;
            saveButton.textContent = "Processing...";
        }

        try {
            const response = await apiRequest("/inventory/adjust/", {
                method: "POST",
                body: payload,
            });

            if (!response || !response.success || response.status >= 400) {
                const errorMsg = response?.message || "Failed to process inventory transaction.";
                displayError(errorMsg, response?.errors);
                return;
            }

            const newQty = response.data?.new_quantity ?? response.data?.inventory?.quantity ?? 0;
            const updatedPid = String(prod.id);

            // Update in-memory product map
            prod.current_stock = newQty;
            if (payload.update_pricing) {
                prod.cost_price = payload.new_cost_price;
                prod.selling_price = payload.new_selling_price;
                const newProfit = prod.selling_price - prod.cost_price;
                prod.gross_profit = newProfit.toFixed(2);
                prod.gross_margin_percentage = prod.selling_price > 0 ? ((newProfit / prod.selling_price) * 100).toFixed(1) : "0.0";
            }
            productsMap.set(updatedPid, prod);

            // Update dropdown option text
            const opt = productSelect.querySelector(`option[value="${updatedPid}"]`);
            if (opt) {
                opt.text = `${prod.name} (${prod.sku}) — Current Stock: ${newQty} units`;
            }

            // Update Ledger row
            refreshInventoryRow(updatedPid, newQty, prod.cost_price, prod.selling_price);

            // Update Preview Card
            updateProductPreview();

            // Reset action-specific inputs
            if (action === "RESTOCK") {
                if (stockQuantityInput) stockQuantityInput.value = "";
                if (stockNotesInput) stockNotesInput.value = "";
                if (updatePricingToggle) updatePricingToggle.checked = false;
                if (pricingFieldsContainer) pricingFieldsContainer.classList.add("d-none");
            } else if (action === "CORRECTION") {
                if (actualQuantityInput) actualQuantityInput.value = "";
                if (correctionNotesInput) correctionNotesInput.value = "";
                if (confirmCorrectionCheckbox) confirmCorrectionCheckbox.checked = false;
            } else if (action === "DAMAGE") {
                if (damageQuantityInput) damageQuantityInput.value = "";
                if (damageReasonInput) damageReasonInput.value = "";
                if (confirmDamageCheckbox) confirmDamageCheckbox.checked = false;
            } else if (action === "EXPIRY") {
                if (expiryQuantityInput) expiryQuantityInput.value = "";
                if (expiryNotesInput) expiryNotesInput.value = "";
                if (confirmExpiryCheckbox) confirmExpiryCheckbox.checked = false;
            }

            displaySuccess(response.message || "Inventory updated successfully.");

        } catch (err) {
            displayError(err.message || "Network error while saving stock entry.");
        } finally {
            if (saveButton) {
                saveButton.disabled = false;
                updateActionUI(); // Restores button CTA label
            }
        }
    });
});

function refreshInventoryRow(productId, newQuantity, newCost = null, newSelling = null) {
    const row = document.querySelector(`tr[data-product-row="${productId}"]`);
    if (!row) return;

    const qtyCell = row.querySelector(".stock-qty-cell");
    if (qtyCell) {
        qtyCell.innerHTML = `<strong>${newQuantity}</strong>`;
    }

    if (newCost !== null) {
        const costCell = row.querySelector(".stock-cost-cell");
        if (costCell) costCell.textContent = "₦" + Number(newCost).toFixed(2);
    }

    if (newSelling !== null) {
        const priceCell = row.querySelector(".stock-price-cell");
        if (priceCell) priceCell.textContent = "₦" + Number(newSelling).toFixed(2);
    }

    const reorderCell = row.querySelector(".reorder-level-cell");
    const reorderLevel = reorderCell ? Number(reorderCell.textContent.trim()) || 0 : 0;

    const badge = row.querySelector(".stock-status-badge");
    if (badge) {
        badge.classList.remove("badge-success", "badge-warning", "badge-danger");
        if (newQuantity <= 0) {
            badge.classList.add("badge-danger");
            badge.textContent = "Out of Stock";
        } else if (newQuantity <= reorderLevel) {
            badge.classList.add("badge-warning");
            badge.textContent = "Low Stock";
        } else {
            badge.classList.add("badge-success");
            badge.textContent = "In Stock";
        }
    }
}
