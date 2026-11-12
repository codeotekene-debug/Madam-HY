const posProducts = [];
const cart = [];
let activeQrPollInterval = null;
let currentQrReference = null;
let activeDraftSale = null;
let activeTerminalPollInterval = null;
let activeTerminalTimerInterval = null;
let currentTerminalReference = null;
let currentTerminalSaleId = null;
let selectedCreditCustomer = null;
let creditCustomerSearchTimeout = null;

document.addEventListener('DOMContentLoaded', () => {
    bindPosEvents();
    loadProducts();
    updateCartSummary();
});

function bindPosEvents() {
    const searchInput = document.getElementById('productSearchInput');
    const barcodeInput = document.getElementById('barcode-input');
    const legacySearchInput = document.getElementById('search-input');

    if (searchInput) {
        searchInput.addEventListener('input', () => {
            if (barcodeInput) barcodeInput.value = searchInput.value;
            if (legacySearchInput) legacySearchInput.value = searchInput.value;
            renderProducts();
        });

        // Fast barcode scanner support: scanners fire 'Enter' key upon reading a barcode
        searchInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                handleBarcodeInput(searchInput.value.trim());
            }
        });
    }

    if (barcodeInput) {
        barcodeInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                handleBarcodeInput(barcodeInput.value.trim());
            }
        });
    }

    document.getElementById('categoryFilter')?.addEventListener('change', renderProducts);

    document.getElementById('discountInput')?.addEventListener('input', updateCartSummary);
    document.getElementById('amountReceivedInput')?.addEventListener('input', updateCartSummary);
    document.getElementById('paymentMethodSelect')?.addEventListener('change', updatePaymentFields);
    document.getElementById('clearCartBtn')?.addEventListener('click', clearCart);
    document.getElementById('checkoutBtn')?.addEventListener('click', createDraftSale);
    document.getElementById('productRetryBtn')?.addEventListener('click', loadProducts);

    // Quick touch payment tabs
    document.querySelectorAll('.pay-method-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const method = btn.dataset.method;
            document.querySelectorAll('.pay-method-btn').forEach(option => {
                const selected = option === btn;
                option.classList.toggle('active', selected);
                option.setAttribute('aria-pressed', String(selected));
            });
            const select = document.getElementById('paymentMethodSelect');
            if (select) {
                select.value = method;
                updatePaymentFields();
            }
            if (method === 'TRANSFER' && cart.length > 0) {
                openQrModal();
            } else if (method === 'CARD' && cart.length > 0) {
                openPosTerminalModal();
            }
        });
    });

    document.getElementById('toggleCatalogBtn')?.addEventListener('click', () => {
        const list = document.getElementById('productList');
        const button = document.getElementById('toggleCatalogBtn');
        if (!list || !button) return;
        list.classList.toggle('compact-grid');
        const isCompact = list.classList.contains('compact-grid');
        button.innerHTML = isCompact
            ? '<i class="bi bi-grid" aria-hidden="true"></i><span>Grid view</span>'
            : '<i class="bi bi-list-ul" aria-hidden="true"></i><span>List view</span>';
    });

    document.getElementById('closeQrModalBtn')?.addEventListener('click', closeQrModal);
    document.getElementById('cancelQrPaymentBtn')?.addEventListener('click', closeQrModal);
    document.getElementById('checkQrStatusBtn')?.addEventListener('click', () => {
        if (currentQrReference && activeDraftSale) {
            showMessage('Verifying customer transfer status...', 'success');
            checkQrStatus(currentQrReference, activeDraftSale.id);
        } else {
            showMessage('No active QR transaction to verify.', 'error');
        }
    });

    document.getElementById('closeTerminalModalBtn')?.addEventListener('click', closeTerminalModal);
    document.getElementById('cancelTerminalPushBtn')?.addEventListener('click', closeTerminalModal);
    document.getElementById('checkTerminalStatusBtn')?.addEventListener('click', () => {
        if (currentTerminalReference) {
            showMessage('Checking terminal payment status...', 'success');
            checkTerminalStatus(currentTerminalReference, currentTerminalSaleId);
        } else {
            showMessage('No active terminal transaction to check.', 'error');
        }
    });

    const copyStoreBtn = document.getElementById('copyStoreAccountBtn');
    const storeAccEl = document.getElementById('storeAccountNumber');
    if (copyStoreBtn && storeAccEl) {
        copyStoreBtn.addEventListener('click', () => {
            navigator.clipboard.writeText(storeAccEl.textContent.trim()).then(() => {
                copyStoreBtn.innerHTML = '<i class="bi bi-check2"></i>';
                setTimeout(() => { copyStoreBtn.innerHTML = '<i class="bi bi-clipboard"></i>'; }, 2000);
            });
        });
    }

    document.getElementById('confirmTransferBtn')?.addEventListener('click', confirmDirectStoreBankTransfer);

    // Credit Ledger Customer Search & Receipt Modal events
    const creditSearchInput = document.getElementById('creditCustomerSearchInput');
    const creditDropdown = document.getElementById('creditCustomerDropdown');

    if (creditSearchInput) {
        creditSearchInput.addEventListener('input', (e) => {
            const query = e.target.value.trim();
            if (creditCustomerSearchTimeout) clearTimeout(creditCustomerSearchTimeout);
            if (!query) {
                if (creditDropdown) {
                    creditDropdown.style.display = 'none';
                    creditDropdown.innerHTML = '';
                }
                return;
            }
            creditCustomerSearchTimeout = setTimeout(() => {
                searchCreditCustomers(query);
            }, 300);
        });

        creditSearchInput.addEventListener('focus', () => {
            const query = creditSearchInput.value.trim();
            if (query.length >= 1) {
                searchCreditCustomers(query);
            }
        });
    }

    document.getElementById('clearSelectedCustomerBtn')?.addEventListener('click', clearCreditCustomer);

    document.addEventListener('click', (e) => {
        if (!e.target.closest('.credit-search-box') && creditDropdown) {
            creditDropdown.style.display = 'none';
        }
    });

    document.getElementById('closePosReceiptBtn')?.addEventListener('click', closePosReceiptModal);
    document.getElementById('posReceiptPrintBtn')?.addEventListener('click', printPosReceipt);
    document.getElementById('posReceiptNewSaleBtn')?.addEventListener('click', startNewSaleFromReceipt);

    updatePaymentFields();
}

function handleBarcodeInput(query) {
    if (!query) return;
    const lowerQuery = query.toLowerCase();

    // Check exact SKU or ID match first
    const exactMatch = posProducts.find(p => p.sku.toLowerCase() === lowerQuery || String(p.id) === query)
        || posProducts.find(p => p.name.toLowerCase() === lowerQuery);

    if (exactMatch) {
        addToCart(exactMatch.id, 1);
        const searchInput = document.getElementById('productSearchInput');
        if (searchInput) {
            searchInput.value = '';
            renderProducts();
        }
        return;
    }

    // Check single filtered match
    const matching = posProducts.filter(p => [p.name, p.category, p.sku].some(v => v.toLowerCase().includes(lowerQuery)));
    if (matching.length === 1) {
        addToCart(matching[0].id, 1);
        const searchInput = document.getElementById('productSearchInput');
        if (searchInput) {
            searchInput.value = '';
            renderProducts();
        }
    }
}

async function loadProducts() {
    const productList = document.getElementById('productList');
    if (!productList) return;
    productList.innerHTML = loadingRow('Loading product catalogue...');
    const response = await apiRequest('/products/?page_size=100&sort_by=name');
    if (!response.success) {
        productList.innerHTML = '';
        showEmptyState('Product catalogue could not load. Try again.', true);
        showMessage(response.message || 'Product catalogue could not load.', 'error');
        return;
    }

    posProducts.length = 0;
    (response.data?.products || []).forEach(product => {
        if (!product.is_active) return;
        posProducts.push({
            id: product.id,
            name: product.name,
            category: product.category?.name || 'Uncategorised',
            sku: product.sku,
            price: Number(product.selling_price || 0),
            stock: product.stock || { quantity: 0, status: 'OUT_OF_STOCK' },
            image: product.image?.url || product.image_url || product.primary_image?.url || (typeof product.image === 'string' ? product.image : ''),
        });
    });
    populateCategoryFilter();
    renderProducts();
}

function populateCategoryFilter() {
    const select = document.getElementById('categoryFilter');
    const categories = [...new Set(posProducts.map(product => product.category))].sort();

    if (select) {
        const selected = select.value;
        select.innerHTML = '<option value="all">All categories</option>' + categories.map(category => (
            `<option value="${escapeHtml(category)}">${escapeHtml(category)}</option>`
        )).join('');
        select.value = categories.includes(selected) ? selected : 'all';
    }
}

function renderProducts() {
    const productList = document.getElementById('productList');
    const query = document.getElementById('productSearchInput')?.value.trim().toLowerCase() || '';
    const category = document.getElementById('categoryFilter')?.value || 'all';
    if (!productList) return;

    const products = posProducts.filter(product => {
        const matchesQuery = !query || [product.name, product.category, product.sku]
            .some(value => value.toLowerCase().includes(query));
        return matchesQuery && (category === 'all' || product.category === category);
    });

    if (!products.length) {
        productList.innerHTML = '';
        showEmptyState('No products match this search.', false);
        return;
    }

    showEmptyState('', false);
    productList.innerHTML = products.map(product => {
        const quantity = Number(product.stock.quantity || 0);
        const isOutOfStock = quantity <= 0;
        const isLowStock = quantity > 0 && quantity <= 5;
        const stockLabel = isOutOfStock ? 'Out of Stock' : (isLowStock ? `Low (${quantity})` : `In Stock (${quantity})`);
        const stockClass = isOutOfStock ? 'stock-out' : (isLowStock ? 'stock-low' : 'stock-in');

        return `
            <article class="product-card-pos" aria-label="${escapeHtml(product.name)}">
                <div class="pos-product-image">
                    ${product.image
                        ? `<img src="${escapeHtml(product.image)}" alt="${escapeHtml(product.name)}" loading="lazy" />`
                        : `<div class="pos-product-fallback" aria-hidden="true"><i class="bi bi-box-seam"></i></div>`
                    }
                </div>
                <div class="pos-product-body">
                    <div class="pos-product-top">
                        <span class="pos-product-category">${escapeHtml(product.category)}</span>
                        <strong class="pos-product-price">₦ ${formatCurrency(product.price)}</strong>
                    </div>
                    <div class="pos-product-name" title="${escapeHtml(product.name)}">${escapeHtml(product.name)}</div>
                    <div class="pos-product-meta">
                        <span class="pos-sku"><i class="bi bi-upc-scan" aria-hidden="true"></i> ${escapeHtml(product.sku)}</span>
                        <span class="pos-stock-badge ${stockClass}">${escapeHtml(stockLabel)}</span>
                    </div>
                    <div class="pos-product-actions">
                        <button type="button" class="btn btn-primary btn-sm btn-quick-add" data-add-product="${product.id}" ${isOutOfStock ? 'disabled style="opacity: 0.6; cursor: not-allowed;"' : ''} aria-label="Add ${escapeHtml(product.name)} to ticket">
                            <i class="bi bi-plus-lg" aria-hidden="true"></i>
                            <span>${isOutOfStock ? 'Sold Out' : 'Add to Ticket'}</span>
                        </button>
                    </div>
                </div>
            </article>
        `;
    }).join('');

    productList.querySelectorAll('[data-add-product]').forEach(button => {
        button.addEventListener('click', () => addToCart(Number(button.dataset.addProduct), 1));
    });
}

function addToCart(productId, quantity) {
    const product = posProducts.find(item => item.id === productId);
    if (!product || product.stock.quantity <= 0) {
        showMessage('This product is unavailable or out of stock.', 'error');
        return;
    }
    const existing = cart.find(item => item.product_id === productId);
    const nextQuantity = (existing?.quantity || 0) + quantity;
    if (nextQuantity > product.stock.quantity) {
        showMessage(`Cannot exceed available stock of ${product.stock.quantity}.`, 'error');
        return;
    }
    if (existing) {
        existing.quantity = nextQuantity;
    } else {
        cart.push({
            product_id: product.id,
            name: product.name,
            sku: product.sku,
            quantity,
            price: product.price,
            stock: product.stock.quantity,
            discount: '0.00',
        });
    }
    updateCartSummary();
    showMessage(`${product.name} added to cart.`, 'success');
}

function updateCartSummary() {
    const cartItems = document.getElementById('cartItems') || document.getElementById('cart-items');
    const emptyState = document.getElementById('cartEmptyState');
    if (!cartItems) return;

    if (!cart.length) {
        cartItems.innerHTML = '';
        emptyState?.classList.remove('empty-state-hidden');
        setText('cartItemCount', '0 items');
        setText('subtotalValue', '₦ 0.00');
        setText('subtotal', '₦ 0.00');
        setText('tax', 'Not calculated');
        setText('totalValue', '₦ 0.00');
        setText('total-amount', '₦ 0.00');
        setText('changeValue', '₦ 0.00');
        updateCreditLedgerActionState();
        return;
    }

    emptyState?.classList.add('empty-state-hidden');
    const subtotal = cart.reduce((sum, item) => sum + item.price * item.quantity - Number(item.discount || 0), 0);
    const discount = Math.max(Number(document.getElementById('discountInput')?.value || 0), 0);
    const total = Math.max(subtotal - discount, 0);
    const amount = Math.max(Number(document.getElementById('amountReceivedInput')?.value || 0), 0);
    const change = Math.max(amount - total, 0);

    const totalCount = cart.reduce((sum, item) => sum + item.quantity, 0);
    setText('cartItemCount', `${totalCount} item${totalCount === 1 ? '' : 's'}`);
    setText('subtotalValue', `₦ ${formatCurrency(subtotal)}`);
    setText('subtotal', `₦ ${formatCurrency(subtotal)}`);
    setText('tax', 'Not calculated');
    setText('totalValue', `₦ ${formatCurrency(total)}`);
    setText('total-amount', `₦ ${formatCurrency(total)}`);
    setText('changeValue', `₦ ${formatCurrency(change)}`);
    updateCreditLedgerActionState();

    cartItems.innerHTML = cart.map(item => `
        <div class="cart-item" data-cart-item="${item.product_id}">
            <div class="cart-item-main">
                <span class="cart-item-name" title="${escapeHtml(item.name)}">${escapeHtml(item.name)}</span>
                <div class="cart-item-meta">
                    <span>${escapeHtml(item.sku)}</span>
                    <span>₦ ${formatCurrency(item.price)} each</span>
                </div>
            </div>
            <div class="cart-item-actions">
                <div class="qty-control" aria-label="Quantity controls for ${escapeHtml(item.name)}">
                    <button type="button" data-decrease="${item.product_id}" aria-label="Decrease quantity">
                        <i class="bi bi-dash" aria-hidden="true"></i>
                    </button>
                    <span class="qty-display">${item.quantity}</span>
                    <button type="button" data-increase="${item.product_id}" aria-label="Increase quantity" ${item.quantity >= item.stock ? 'disabled style="opacity: 0.5; cursor: not-allowed;"' : ''}>
                        <i class="bi bi-plus" aria-hidden="true"></i>
                    </button>
                </div>
                <strong class="cart-item-price">₦ ${formatCurrency(item.price * item.quantity)}</strong>
                <button type="button" class="cart-item-remove" data-remove="${item.product_id}" aria-label="Remove ${escapeHtml(item.name)}">
                    <i class="bi bi-trash3" aria-hidden="true"></i>
                </button>
            </div>
        </div>
    `).join('');

    cartItems.querySelectorAll('[data-increase]').forEach(btn => btn.addEventListener('click', () => increaseQuantity(Number(btn.dataset.increase))));
    cartItems.querySelectorAll('[data-decrease]').forEach(btn => btn.addEventListener('click', () => decreaseQuantity(Number(btn.dataset.decrease))));
    cartItems.querySelectorAll('[data-remove]').forEach(btn => btn.addEventListener('click', () => removeFromCart(Number(btn.dataset.remove))));
}

function increaseQuantity(productId) {
    const item = cart.find(entry => entry.product_id === productId);
    const product = posProducts.find(p => p.id === productId);
    const maxStock = Number(product?.stock?.quantity ?? item?.stock ?? 0);
    if (item && item.quantity >= maxStock) {
        showMessage(`Cannot exceed available physical stock (${maxStock} units).`, 'error');
        return;
    }
    addToCart(productId, 1);
}

function decreaseQuantity(productId) {
    const item = cart.find(entry => entry.product_id === productId);
    if (!item) return;
    if (item.quantity <= 1) removeFromCart(productId);
    else { item.quantity -= 1; updateCartSummary(); }
}

function removeFromCart(productId) {
    const index = cart.findIndex(item => item.product_id === productId);
    if (index >= 0) cart.splice(index, 1);
    updateCartSummary();
}

function clearCart() {
    cart.length = 0;
    const discountEl = document.getElementById('discountInput');
    const amountEl = document.getElementById('amountReceivedInput');
    if (discountEl) discountEl.value = '0';
    if (amountEl) amountEl.value = '';
    updateCartSummary();
    showMessage('Cart cleared.', 'success');
}

async function createDraftSale() {
    if (!cart.length) {
        showMessage('Add products to the cart before checking out.', 'error');
        return;
    }
    const paymentMethod = document.getElementById('paymentMethodSelect')?.value || 'CASH';
    const customerId = document.getElementById('customerIdInput')?.value.trim() || null;

    if (paymentMethod === 'CREDIT') {
        if (!selectedCreditCustomer && !customerId) {
            showMessage('Customer selection is required for credit sales.', 'error');
            return;
        }
        const subtotal = cart.reduce((sum, item) => sum + item.price * item.quantity - Number(item.discount || 0), 0);
        const discount = Math.max(Number(document.getElementById('discountInput')?.value || 0), 0);
        const total = Math.max(subtotal - discount, 0);
        const available = selectedCreditCustomer ? Number(selectedCreditCustomer.available_credit || 0) : 0;
        if (selectedCreditCustomer && total > available) {
            showMessage(`Credit limit exceeded: Available credit is ₦ ${formatCurrency(available)}, but cart total is ₦ ${formatCurrency(total)}.`, 'error');
            return;
        }
        processCreditSaleConfirmation(selectedCreditCustomer || { id: Number(customerId), name: 'Customer' }, total, discount);
        return;
    }

    if (paymentMethod === 'CARD') {
        openPosTerminalModal();
        return;
    }

    if (paymentMethod === 'TRANSFER') {
        openQrModal();
        return;
    }

    if (paymentMethod === 'BANK_TRANSFER') {
        confirmDirectStoreBankTransfer();
        return;
    }

    const button = document.getElementById('checkoutBtn');
    setButtonLoading(button, 'Creating draft...');
    const response = await apiRequest('/sales/', {
        method: 'POST',
        body: {
            customer_id: customerId ? Number(customerId) : null,
            payment_method: paymentMethod,
            discount: String(Math.max(Number(document.getElementById('discountInput')?.value || 0), 0).toFixed(2)),
            notes: '',
            items: cart.map(item => ({ product_id: item.product_id, quantity: item.quantity, discount: item.discount })),
        },
    });
    setButtonLoading(button, 'Complete Sale');
    if (!response.success) {
        showMessage(formatApiError(response), 'error');
        return;
    }
    const sale = response.data?.sale;
    if (!sale?.id) {
        showMessage('The draft sale response was incomplete.', 'error');
        return;
    }
    sessionStorage.setItem('madamHyDraftSale', JSON.stringify({ sale, items: response.data.items || [] }));
    window.location.href = `/sales/checkout/?sale_id=${sale.id}`;
}

async function openQrModal() {
    if (!cart.length) {
        showMessage('Add products to the cart before generating QR payment.', 'error');
        return;
    }

    const modal = document.getElementById('qrPaymentModal');
    if (!modal) return;
    modal.classList.add('active');
    modal.setAttribute('aria-hidden', 'false');

    const qrWrapper = document.getElementById('qrCodeWrapper');
    const qrAmountEl = document.getElementById('qrModalAmount');
    const qrStatusEl = document.getElementById('qrStatusText');
    const qrRefBadge = document.getElementById('qrReferenceBadge');
    const qrRefValue = document.getElementById('qrReferenceValue');

    const subtotal = cart.reduce((sum, item) => sum + item.price * item.quantity - Number(item.discount || 0), 0);
    const discount = Math.max(Number(document.getElementById('discountInput')?.value || 0), 0);
    const total = Math.max(subtotal - discount, 0);

    if (qrAmountEl) qrAmountEl.textContent = `₦ ${formatCurrency(total)}`;
    if (qrStatusEl) qrStatusEl.textContent = 'Generating counter QR code...';
    if (qrWrapper) {
        qrWrapper.innerHTML = `
            <div class="qr-placeholder" id="qrPlaceholder">
                <span class="spinner" aria-hidden="true"></span>
                <p>Generating dynamic counter QR code...</p>
            </div>
        `;
    }

    // Step 1: Create draft sale
    const customerId = document.getElementById('customerIdInput')?.value.trim() || null;
    const saleRes = await apiRequest('/sales/', {
        method: 'POST',
        body: {
            customer_id: customerId ? Number(customerId) : null,
            payment_method: 'TRANSFER',
            discount: String(discount.toFixed(2)),
            notes: 'Counter POS Dynamic QR Checkout',
            items: cart.map(item => ({ product_id: item.product_id, quantity: item.quantity, discount: item.discount })),
        },
    });

    if (!saleRes.success || !saleRes.data?.sale?.id) {
        if (qrStatusEl) qrStatusEl.textContent = 'Failed to create sale. Try again.';
        showMessage(formatApiError(saleRes), 'error');
        return;
    }

    activeDraftSale = saleRes.data.sale;

    // Step 2: Request Dynamic QR from backend
    const qrRes = await apiRequest('/payments/qr/generate/', {
        method: 'POST',
        body: {
            sale_id: activeDraftSale.id,
            target_type: 'sale',
            provider: 'paystack',
            amount: total,
            format: 'png',
        },
    });

    if (!qrRes.success || !qrRes.data) {
        if (qrStatusEl) qrStatusEl.textContent = qrRes.message || 'Could not generate QR code.';
        if (qrWrapper) {
            qrWrapper.innerHTML = `<div class="empty-state"><p>${escapeHtml(qrRes.message || 'QR generation failed.')}</p></div>`;
        }
        return;
    }

    const qrData = qrRes.data;
    currentQrReference = qrData.payment_reference;

    if (qrRefBadge && qrRefValue && currentQrReference) {
        qrRefValue.textContent = currentQrReference;
        qrRefBadge.style.display = 'inline-flex';
    }

    // Render QR Code (Standard Base64 img tag or SVG fallback)
    if (qrWrapper) {
        const src = qrData.qr_code_data || qrData.qr_code_png || qrData.qr_code_base64 || qrData.qr_code_data_uri || qrData.qr_data_uri || qrData.qr_code;
        const svg = qrData.qr_code_svg || qrData.qr_svg;
        if (src) {
            qrWrapper.innerHTML = `<img id="qrCodeImage" class="qr-code-img" src="${escapeHtml(src)}" alt="Payment QR Code" style="max-width: 100%; height: auto; padding: 10px; background: #ffffff; border: 1px solid var(--border); border-radius: var(--radius-md); box-shadow: var(--shadow-sm); display: block; margin: 0 auto;" />`;
        } else if (svg) {
            qrWrapper.innerHTML = `<div id="qrCodeContainer" class="qr-rendered-svg">${svg}</div>`;
        } else {
            qrWrapper.innerHTML = `<div class="qr-placeholder" id="qrPlaceholder"><p>Scan with bank app to pay ₦ ${formatCurrency(total)}</p></div>`;
        }
    }

    // Populate explicit fallback details below QR
    const fallbackRefEl = document.getElementById('posFallbackRefValue');
    const fallbackBankEl = document.getElementById('posFallbackBankName');
    const fallbackAccEl = document.getElementById('posFallbackAccountNumber');
    const fallbackAmountEl = document.getElementById('posFallbackAmount');
    const fallbackLinkEl = document.getElementById('posQrPaymentLink');
    const fallbackLinkTextEl = document.getElementById('posQrPaymentLinkText');

    if (fallbackRefEl) fallbackRefEl.textContent = qrData.payment_reference || currentQrReference;
    if (fallbackBankEl) fallbackBankEl.textContent = qrData.bank_name || 'Moniepoint MFB';
    if (fallbackAccEl) fallbackAccEl.textContent = qrData.account_number || '-';
    if (fallbackAmountEl) fallbackAmountEl.textContent = `₦ ${formatCurrency(total)}`;

    const payUrl = qrData.payment_url || qrData.checkout_url || qrData.qr_payload || 'javascript:void(0);';
    if (fallbackLinkEl) fallbackLinkEl.href = payUrl;
    if (fallbackLinkTextEl) fallbackLinkTextEl.textContent = (payUrl && !payUrl.startsWith('javascript:')) ? payUrl : '-';

    bindPosFallbackCopyHandlers();
    startPosFallbackTimer();

    if (qrStatusEl) qrStatusEl.textContent = 'Awaiting customer transfer...';
    startQrPolling(currentQrReference, activeDraftSale.id);
}

let posFallbackTimerInterval = null;

function bindPosFallbackCopyHandlers() {
    const copyAccBtn = document.getElementById('copyPosAccountBtn');
    const accEl = document.getElementById('posFallbackAccountNumber');
    if (copyAccBtn && accEl) {
        copyAccBtn.onclick = () => {
            navigator.clipboard.writeText(accEl.textContent.trim()).then(() => {
                copyAccBtn.innerHTML = '<i class="bi bi-check2"></i>';
                setTimeout(() => { copyAccBtn.innerHTML = '<i class="bi bi-clipboard"></i>'; }, 2000);
            });
        };
    }

    const copyLinkBtn = document.getElementById('copyPosPaymentLinkBtn');
    const linkEl = document.getElementById('posQrPaymentLink');
    if (copyLinkBtn && linkEl) {
        copyLinkBtn.onclick = () => {
            const urlToCopy = linkEl.href && !linkEl.href.includes('javascript:') && !linkEl.href.endsWith('#') ? linkEl.href : linkEl.textContent.trim();
            if (urlToCopy && urlToCopy !== '-') {
                navigator.clipboard.writeText(urlToCopy).then(() => {
                    copyLinkBtn.innerHTML = '<i class="bi bi-check2"></i> Copied';
                    setTimeout(() => { copyLinkBtn.innerHTML = '<i class="bi bi-link-45deg"></i> Copy'; }, 2000);
                });
            }
        };
    }
}

function startPosFallbackTimer() {
    if (posFallbackTimerInterval) clearInterval(posFallbackTimerInterval);
    const timerEl = document.getElementById('posFallbackTimer');
    let remaining = 900;
    posFallbackTimerInterval = setInterval(() => {
        remaining--;
        if (remaining <= 0) {
            clearInterval(posFallbackTimerInterval);
            if (timerEl) timerEl.textContent = 'Expired';
            return;
        }
        const mins = Math.floor(remaining / 60);
        const secs = remaining % 60;
        if (timerEl) {
            timerEl.textContent = `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
        }
    }, 1000);
}

function closeQrModal() {
    stopQrPolling();
    if (posFallbackTimerInterval) {
        clearInterval(posFallbackTimerInterval);
        posFallbackTimerInterval = null;
    }
    const modal = document.getElementById('qrPaymentModal');
    if (modal) {
        modal.classList.remove('active');
        modal.setAttribute('aria-hidden', 'true');
    }
    if (typeof window.closeModal === 'function') {
        window.closeModal('qrPaymentModal');
    }
}

function startQrPolling(reference, saleId) {
    stopQrPolling();
    if (!reference) return;
    activeQrPollInterval = window.setInterval(() => {
        checkQrStatus(reference, saleId);
    }, 3500);
}

function stopQrPolling() {
    if (activeQrPollInterval) {
        window.clearInterval(activeQrPollInterval);
        activeQrPollInterval = null;
    }
}

async function checkQrStatus(reference, saleId) {
    if (!reference) return;
    const qrStatusEl = document.getElementById('qrStatusText');
    const indicator = document.getElementById('qrStatusIndicator');
    const res = await apiRequest(`/payments/qr/${encodeURIComponent(reference)}/status/`);
    if (!res.success) return;

    const data = res.data;
    const isCompleted = data.status === 'COMPLETED' || data.payment_status === 'COMPLETED' || data.is_verified === true || data.status === 'PAID' || data.status === 'SUCCESS';
    const isFailed = data.status === 'FAILED' || data.payment_status === 'FAILED';
    const isExpired = data.status === 'EXPIRED' || data.payment_status === 'EXPIRED';

    if (isCompleted) {
        stopQrPolling();
        if (qrStatusEl) qrStatusEl.textContent = 'Payment Confirmed! Finalizing sale...';
        if (indicator) {
            indicator.style.background = 'var(--primary-light)';
            indicator.style.color = 'var(--primary-dark)';
        }
        showMessage('Payment confirmed successfully via QR transfer.', 'success');
        window.setTimeout(() => {
            closeQrModal();
            cart.length = 0;
            updateCartSummary();
            window.location.href = `/sales/receipt/?sale_id=${saleId}`;
        }, 1200);
    } else if (isFailed) {
        stopQrPolling();
        if (qrStatusEl) qrStatusEl.textContent = 'Payment failed. Please retry with another payment method.';
        showMessage('QR payment failed.', 'error');
    } else if (isExpired) {
        stopQrPolling();
        if (qrStatusEl) qrStatusEl.textContent = 'QR session expired. Please generate a new code.';
        showMessage('QR payment expired.', 'warning');
    }
}

function updatePaymentFields() {
    const paymentMethod = document.getElementById('paymentMethodSelect')?.value || 'CASH';
    const customerGroup = document.getElementById('customerIdGroup');
    const amountGroup = document.getElementById('amountReceivedGroup');
    const amountInput = document.getElementById('amountReceivedInput');
    const changeRow = document.getElementById('changeDueRow');
    const transferGroup = document.getElementById('directBankTransferGroup');
    const checkoutBtn = document.getElementById('checkoutBtn');

    customerGroup?.classList.toggle('payment-field-hidden', paymentMethod !== 'CREDIT');
    amountGroup?.classList.toggle('payment-field-hidden', paymentMethod !== 'CASH');
    changeRow?.classList.toggle('payment-field-hidden', paymentMethod !== 'CASH');
    transferGroup?.classList.toggle('payment-field-hidden', paymentMethod !== 'BANK_TRANSFER');
    if (amountInput) amountInput.disabled = paymentMethod !== 'CASH';

    if (checkoutBtn) {
        if (paymentMethod === 'CARD') {
            checkoutBtn.innerHTML = '<svg class="retail-svg icon-sm" aria-hidden="true" style="margin-right: 4px;"><use href="#icon-retail-pos"></use></svg> <span>Push to Moniepoint POS</span>';
        } else if (paymentMethod === 'TRANSFER') {
            checkoutBtn.innerHTML = '<svg class="retail-svg icon-sm" aria-hidden="true" style="margin-right: 4px;"><use href="#icon-retail-qr"></use></svg> <span>Generate Dynamic QR</span>';
        } else if (paymentMethod === 'BANK_TRANSFER') {
            checkoutBtn.innerHTML = '<i class="bi bi-bank" aria-hidden="true" style="margin-right: 4px;"></i> <span>Direct Bank Transfer</span>';
        } else if (paymentMethod === 'CREDIT') {
            checkoutBtn.innerHTML = '<svg class="retail-svg icon-sm" aria-hidden="true" style="margin-right: 4px;"><use href="#icon-retail-credit"></use></svg> <span>Complete Credit Sale</span>';
        } else {
            checkoutBtn.innerHTML = '<i class="bi bi-check2-circle" aria-hidden="true"></i> <span>Complete Sale</span>';
        }
    }

    if (paymentMethod === 'BANK_TRANSFER') {
        const subtotal = cart.reduce((sum, item) => sum + item.price * item.quantity - Number(item.discount || 0), 0);
        const discount = Math.max(Number(document.getElementById('discountInput')?.value || 0), 0);
        const total = Math.max(subtotal - discount, 0);
        const amtEl = document.getElementById('storeTransferAmount');
        const refEl = document.getElementById('storeTransferRef');
        if (amtEl) amtEl.textContent = `₦ ${formatCurrency(total)}`;
        if (refEl && !refEl.dataset.generated) {
            refEl.textContent = `HY-POS-${Date.now().toString().slice(-6)}`;
            refEl.dataset.generated = 'true';
        }
    }

    // Synchronize touch buttons
    document.querySelectorAll('.pay-method-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.method === paymentMethod);
    });

    updateCreditLedgerActionState();
}

async function openPosTerminalModal() {
    if (!cart.length) {
        showMessage('Add products to the cart before initiating POS push.', 'error');
        return;
    }

    const modal = document.getElementById('posTerminalModal');
    if (!modal) return;
    modal.classList.add('active');
    modal.setAttribute('aria-hidden', 'false');

    const terminalAmountEl = document.getElementById('terminalModalAmount');
    const terminalStatusEl = document.getElementById('terminalStatusText');
    const terminalRefBadge = document.getElementById('terminalRefBadge');
    const terminalRefValue = document.getElementById('terminalRefValue');

    const subtotal = cart.reduce((sum, item) => sum + item.price * item.quantity - Number(item.discount || 0), 0);
    const discount = Math.max(Number(document.getElementById('discountInput')?.value || 0), 0);
    const total = Math.max(subtotal - discount, 0);

    if (terminalAmountEl) terminalAmountEl.textContent = `₦ ${formatCurrency(total)}`;
    if (terminalStatusEl) terminalStatusEl.textContent = 'Initiating Moniepoint POS push...';

    setTerminalStep(1);

    const customerId = document.getElementById('customerIdInput')?.value.trim() || null;
    const saleRes = await apiRequest('/sales/', {
        method: 'POST',
        body: {
            customer_id: customerId ? Number(customerId) : null,
            payment_method: 'CARD',
            discount: String(discount.toFixed(2)),
            notes: 'Counter POS Terminal Push',
            items: cart.map(item => ({ product_id: item.product_id, quantity: item.quantity, discount: item.discount })),
        },
    });

    if (!saleRes.success || !saleRes.data?.sale?.id) {
        if (terminalStatusEl) terminalStatusEl.textContent = 'Failed to create sale ticket.';
        showMessage(formatApiError(saleRes), 'error');
        return;
    }

    currentTerminalSaleId = saleRes.data.sale.id;
    activeDraftSale = saleRes.data.sale;

    const termSerial = document.getElementById('posTerminalSerialDisplay')?.textContent.trim() || 'DEFAULT_POS_TERMINAL';
    const pushRes = await apiRequest('/payments/terminal/push/', {
        method: 'POST',
        body: {
            sale_id: currentTerminalSaleId,
            terminal_id: termSerial,
            amount: total,
            payment_method: 'CARD_PURCHASE',
        },
    });

    if (!pushRes.success || !pushRes.data) {
        if (terminalStatusEl) terminalStatusEl.textContent = pushRes.message || 'Terminal push failed.';
        showMessage(pushRes.message || 'Could not reach Moniepoint terminal.', 'error');
        return;
    }

    const pushData = pushRes.data;
    currentTerminalReference = pushData.transaction_reference || pushData.payment_reference || pushData.merchant_reference;

    if (terminalRefBadge && terminalRefValue && currentTerminalReference) {
        terminalRefValue.textContent = currentTerminalReference;
        terminalRefBadge.style.display = 'inline-flex';
    }

    setTerminalStep(2);
    if (terminalStatusEl) terminalStatusEl.textContent = 'Waiting for customer card tap or insert on terminal...';

    startTerminalPushTimer(120);
    startTerminalPolling(currentTerminalReference, currentTerminalSaleId);
}

function setTerminalStep(step) {
    const s1 = document.getElementById('terminalStep1');
    const s2 = document.getElementById('terminalStep2');
    const s3 = document.getElementById('terminalStep3');
    const c1 = document.getElementById('circleStep1');
    const c2 = document.getElementById('circleStep2');
    const c3 = document.getElementById('circleStep3');
    const l1 = document.getElementById('labelStep1');
    const l2 = document.getElementById('labelStep2');
    const l3 = document.getElementById('labelStep3');

    [s1, s2, s3].forEach(s => s?.classList.remove('active'));
    if (step >= 1) {
        s1?.classList.add('active');
        if (c1) { c1.style.background = 'var(--primary)'; c1.style.color = '#fff'; }
        if (l1) { l1.style.color = 'var(--text)'; l1.style.fontWeight = '600'; }
    }
    if (step >= 2) {
        s2?.classList.add('active');
        if (c2) { c2.style.background = 'var(--primary)'; c2.style.color = '#fff'; }
        if (l2) { l2.style.color = 'var(--text)'; l2.style.fontWeight = '600'; }
    } else {
        if (c2) { c2.style.background = 'var(--border)'; c2.style.color = 'var(--muted)'; }
        if (l2) { l2.style.color = 'var(--muted)'; l2.style.fontWeight = 'normal'; }
    }
    if (step >= 3) {
        s3?.classList.add('active');
        if (c3) { c3.style.background = 'var(--success, #16a34a)'; c3.style.color = '#fff'; }
        if (l3) { l3.style.color = 'var(--success, #16a34a)'; l3.style.fontWeight = '700'; }
    } else {
        if (c3) { c3.style.background = 'var(--border)'; c3.style.color = 'var(--muted)'; }
        if (l3) { l3.style.color = 'var(--muted)'; l3.style.fontWeight = 'normal'; }
    }
}

function startTerminalPushTimer(durationSeconds = 120) {
    if (activeTerminalTimerInterval) clearInterval(activeTerminalTimerInterval);
    const timerEl = document.getElementById('posPushTimer');
    let remaining = durationSeconds;
    activeTerminalTimerInterval = setInterval(() => {
        remaining--;
        if (remaining <= 0) {
            clearInterval(activeTerminalTimerInterval);
            activeTerminalTimerInterval = null;
            if (timerEl) timerEl.textContent = 'Expired (00:00)';
            stopTerminalPolling();
            const statusEl = document.getElementById('terminalStatusText');
            if (statusEl) statusEl.textContent = 'Push timed out after 120s. Please retry.';
            showMessage('Moniepoint POS charge push timed out.', 'warning');
            return;
        }
        const mins = Math.floor(remaining / 60);
        const secs = remaining % 60;
        if (timerEl) {
            timerEl.textContent = `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
        }
    }, 1000);
}

function stopTerminalPushTimer() {
    if (activeTerminalTimerInterval) {
        clearInterval(activeTerminalTimerInterval);
        activeTerminalTimerInterval = null;
    }
}

function startTerminalPolling(reference, saleId) {
    stopTerminalPolling();
    if (!reference) return;
    activeTerminalPollInterval = window.setInterval(() => {
        checkTerminalStatus(reference, saleId);
    }, 3000);
}

function stopTerminalPolling() {
    if (activeTerminalPollInterval) {
        window.clearInterval(activeTerminalPollInterval);
        activeTerminalPollInterval = null;
    }
}

async function checkTerminalStatus(reference, saleId) {
    if (!reference) return;
    const statusEl = document.getElementById('terminalStatusText');
    const indicator = document.getElementById('terminalStatusIndicator');

    const res = await apiRequest(`/payments/pos-status/${encodeURIComponent(reference)}/`);
    if (!res.success && res.status !== 200) return;

    const data = res.data || {};
    const statusStr = (data.status || data.payment_status || '').toUpperCase();
    const isCompleted = statusStr === 'SUCCESS' || statusStr === 'SUCCESSFUL' || statusStr === 'COMPLETED' || data.is_completed === true;
    const isFailed = statusStr === 'FAILED' || statusStr === 'REJECTED' || statusStr === 'CANCELLED' || statusStr === 'EXPIRED';

    if (isCompleted) {
        stopTerminalPolling();
        stopTerminalPushTimer();
        setTerminalStep(3);
        if (statusEl) statusEl.textContent = 'Payment Confirmed! Printing receipt...';
        if (indicator) {
            indicator.style.background = 'var(--primary-light)';
            indicator.style.color = 'var(--primary-dark)';
        }
        showMessage('Moniepoint POS payment confirmed successfully!', 'success');
        window.setTimeout(() => {
            closeTerminalModal();
            cart.length = 0;
            updateCartSummary();
            const sid = saleId || data.sale_id || (activeDraftSale ? activeDraftSale.id : '');
            window.location.href = `/sales/receipt/?id=${sid}&sale_id=${sid}`;
        }, 1200);
    } else if (isFailed) {
        stopTerminalPolling();
        stopTerminalPushTimer();
        if (statusEl) statusEl.textContent = `Transaction ${statusStr.toLowerCase()} on terminal.`;
        showMessage(`POS transaction ${statusStr.toLowerCase()}.`, 'error');
    }
}

function closeTerminalModal() {
    stopTerminalPolling();
    stopTerminalPushTimer();
    const modal = document.getElementById('posTerminalModal');
    if (modal) {
        modal.classList.remove('active');
        modal.setAttribute('aria-hidden', 'true');
    }
}

async function confirmDirectStoreBankTransfer() {
    if (!cart.length) {
        showMessage('Add products to the cart before confirming transfer.', 'error');
        return;
    }

    const senderRef = document.getElementById('transferSenderInput')?.value.trim();
    if (!senderRef) {
        showMessage('Please enter the customer sender name or transfer reference.', 'error');
        document.getElementById('transferSenderInput')?.focus();
        return;
    }

    const confirmBtn = document.getElementById('confirmTransferBtn');
    setButtonLoading(confirmBtn, 'Confirming Transfer...');

    const subtotal = cart.reduce((sum, item) => sum + item.price * item.quantity - Number(item.discount || 0), 0);
    const discount = Math.max(Number(document.getElementById('discountInput')?.value || 0), 0);
    const total = Math.max(subtotal - discount, 0);

    const customerId = document.getElementById('customerIdInput')?.value.trim() || null;
    const saleRes = await apiRequest('/sales/', {
        method: 'POST',
        body: {
            customer_id: customerId ? Number(customerId) : null,
            payment_method: 'TRANSFER',
            discount: String(discount.toFixed(2)),
            notes: `Direct Store Bank Transfer - Sender: ${senderRef}`,
            items: cart.map(item => ({ product_id: item.product_id, quantity: item.quantity, discount: item.discount })),
        },
    });

    if (!saleRes.success || !saleRes.data?.sale?.id) {
        setButtonLoading(confirmBtn, 'Confirm Transfer & Print Receipt');
        showMessage(formatApiError(saleRes), 'error');
        return;
    }

    const saleId = saleRes.data.sale.id;

    const completeRes = await apiRequest(`/sales/${saleId}/complete/`, {
        method: 'POST',
        body: {
            amount_received: total,
            notes: `Direct Store Bank Transfer confirmed by cashier. Sender: ${senderRef}`,
        },
    });

    setButtonLoading(confirmBtn, 'Confirm Transfer & Print Receipt');

    if (!completeRes.success) {
        showMessage(formatApiError(completeRes), 'error');
        return;
    }

    showMessage('Bank transfer confirmed and sale completed.', 'success');
    cart.length = 0;
    updateCartSummary();
    window.location.href = `/sales/receipt/?id=${saleId}&sale_id=${saleId}`;
}

function showEmptyState(message, error) {
    const emptyState = document.getElementById('productEmptyState');
    if (!emptyState) return;
    emptyState.classList.toggle('inventory-load-error', error);
    emptyState.classList.toggle('empty-state-hidden', !message);
    const paragraph = emptyState.querySelector('p');
    if (paragraph && message) paragraph.textContent = message;
}

function loadingRow(message) { return `<div class="empty-state">${escapeHtml(message)}</div>`; }
function setText(id, value) { const element = document.getElementById(id); if (element) element.textContent = value; }
function setButtonLoading(button, label) { if (button) { button.disabled = label !== 'Complete Sale'; button.textContent = label; } }
function formatNumber(value) { return Number(value || 0).toLocaleString('en-NG'); }
function formatCurrency(value) { return Number(value || 0).toLocaleString('en-NG', { minimumFractionDigits: 2, maximumFractionDigits: 2 }); }
function formatApiError(response) { return response.errors ? Object.values(response.errors).flat().join(' ') : (response.message || 'Request failed.'); }
function showMessage(message, type = '') { const element = document.getElementById('saleMessage'); if (!element) return; element.textContent = message; element.className = `sale-message ${type}`; }
function escapeHtml(value) { return String(value ?? '').replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }[char])); }

async function searchCreditCustomers(query) {
    const dropdown = document.getElementById('creditCustomerDropdown');
    if (!dropdown) return;
    dropdown.innerHTML = '<div style="padding: 10px 12px; font-size: 12px; color: var(--muted);"><span class="spinner" style="width: 14px; height: 14px; display: inline-block; vertical-align: middle; margin-right: 6px;"></span> Searching customers...</div>';
    dropdown.style.display = 'block';

    const response = await apiRequest(`/sales/customers/search/?q=${encodeURIComponent(query)}`);
    if (!response.success || !response.data?.customers?.length) {
        dropdown.innerHTML = '<div style="padding: 10px 12px; font-size: 12px; color: var(--muted);">No matching customers found</div>';
        return;
    }

    dropdown.innerHTML = response.data.customers.map(customer => {
        const hasCredit = customer.credit_account_status === 'ACTIVE' || customer.credit_account_status === 'APPROVED';
        const avail = Number(customer.available_credit || 0);
        return `
            <div class="credit-customer-option" data-cust-id="${customer.id}" style="padding: 9px 12px; border-bottom: 1px solid var(--border); cursor: pointer; display: flex; justify-content: space-between; align-items: center; transition: background 0.15s ease;">
                <div>
                    <strong style="display: block; font-size: 13px; color: var(--text-heading);">${escapeHtml(customer.name)}</strong>
                    <span style="font-size: 11.5px; color: var(--muted);"><i class="bi bi-telephone"></i> ${escapeHtml(customer.phone || 'No phone')} | ${escapeHtml(customer.email || '')}</span>
                </div>
                <div style="text-align: right;">
                    <span class="badge ${hasCredit ? 'badge-success' : 'badge-warning'}" style="font-size: 10.5px; display: block; margin-bottom: 2px;">
                        ${hasCredit ? `Avail: ₦ ${formatCurrency(avail)}` : 'No Credit'}
                    </span>
                    <small style="font-size: 10px; color: var(--muted); font-family: monospace;">Limit: ₦ ${formatCurrency(customer.credit_limit)}</small>
                </div>
            </div>
        `;
    }).join('');

    dropdown.querySelectorAll('.credit-customer-option').forEach(item => {
        item.addEventListener('mouseenter', () => { item.style.background = 'var(--background, #f1f5f9)'; });
        item.addEventListener('mouseleave', () => { item.style.background = 'transparent'; });
        item.addEventListener('click', () => {
            const custId = Number(item.dataset.custId);
            const found = response.data.customers.find(c => c.id === custId);
            if (found) {
                selectCreditCustomer(found);
            }
        });
    });
}

function selectCreditCustomer(customer) {
    selectedCreditCustomer = customer;
    const customerIdInput = document.getElementById('customerIdInput');
    const searchInput = document.getElementById('creditCustomerSearchInput');
    const dropdown = document.getElementById('creditCustomerDropdown');
    const card = document.getElementById('selectedCreditCustomerCard');

    if (customerIdInput) customerIdInput.value = customer.id;
    if (searchInput) searchInput.value = customer.name;
    if (dropdown) dropdown.style.display = 'none';

    setText('selectedCustomerName', customer.name);
    setText('selectedCustomerPhone', customer.phone ? `Phone: ${customer.phone}` : (customer.email || 'No phone recorded'));
    setText('selectedCreditLimit', `₦ ${formatCurrency(customer.credit_limit || 0)}`);
    setText('selectedCurrentDebt', `₦ ${formatCurrency(customer.outstanding_debt || 0)}`);
    setText('selectedAvailableCredit', `₦ ${formatCurrency(customer.available_credit || 0)}`);

    if (card) card.style.display = 'block';
    updateCreditLedgerActionState();
}

function clearCreditCustomer() {
    selectedCreditCustomer = null;
    const customerIdInput = document.getElementById('customerIdInput');
    const searchInput = document.getElementById('creditCustomerSearchInput');
    const card = document.getElementById('selectedCreditCustomerCard');
    const alertBox = document.getElementById('creditLimitAlert');

    if (customerIdInput) customerIdInput.value = '';
    if (searchInput) {
        searchInput.value = '';
        searchInput.focus();
    }
    if (card) card.style.display = 'none';
    if (alertBox) alertBox.style.display = 'none';

    updateCreditLedgerActionState();
}

function updateCreditLedgerActionState() {
    const paymentMethod = document.getElementById('paymentMethodSelect')?.value || 'CASH';
    const checkoutBtn = document.getElementById('checkoutBtn');
    const alertBox = document.getElementById('creditLimitAlert');
    const alertText = document.getElementById('creditLimitAlertText');

    if (paymentMethod !== 'CREDIT') {
        if (alertBox) alertBox.style.display = 'none';
        if (checkoutBtn) {
            checkoutBtn.style.background = '';
            checkoutBtn.style.borderColor = '';
            checkoutBtn.style.color = '';
        }
        return;
    }

    const subtotal = cart.reduce((sum, item) => sum + item.price * item.quantity - Number(item.discount || 0), 0);
    const discount = Math.max(Number(document.getElementById('discountInput')?.value || 0), 0);
    const total = Math.max(subtotal - discount, 0);

    if (!selectedCreditCustomer) {
        if (alertBox) alertBox.style.display = 'none';
        if (checkoutBtn) {
            checkoutBtn.disabled = true;
            checkoutBtn.style.background = '';
            checkoutBtn.style.borderColor = '';
            checkoutBtn.style.color = '';
            checkoutBtn.innerHTML = '<svg class="retail-svg icon-sm" aria-hidden="true" style="margin-right: 4px;"><use href="#icon-retail-credit"></use></svg> <span>Select Customer for Credit</span>';
        }
        return;
    }

    const available = Number(selectedCreditCustomer.available_credit || 0);

    if (cart.length === 0) {
        if (alertBox) alertBox.style.display = 'none';
        if (checkoutBtn) {
            checkoutBtn.disabled = true;
            checkoutBtn.style.background = '';
            checkoutBtn.style.borderColor = '';
            checkoutBtn.style.color = '';
            checkoutBtn.innerHTML = '<svg class="retail-svg icon-sm" aria-hidden="true" style="margin-right: 4px;"><use href="#icon-retail-credit"></use></svg> <span>Charge to Credit Account</span>';
        }
        return;
    }

    if (total <= available) {
        if (alertBox) alertBox.style.display = 'none';
        if (checkoutBtn) {
            checkoutBtn.disabled = false;
            checkoutBtn.style.background = '#16a34a';
            checkoutBtn.style.borderColor = '#15803d';
            checkoutBtn.style.color = '#ffffff';
            checkoutBtn.innerHTML = `<svg class="retail-svg icon-sm" aria-hidden="true" style="margin-right: 4px;"><use href="#icon-retail-credit"></use></svg> <span>Charge ₦ ${formatCurrency(total)} to Credit Account</span>`;
        }
    } else {
        if (alertBox) {
            alertBox.style.display = 'block';
            if (alertText) {
                alertText.textContent = `Credit Limit Exceeded: Available credit is ₦ ${formatCurrency(available)}, but cart total is ₦ ${formatCurrency(total)}.`;
            }
        }
        if (checkoutBtn) {
            checkoutBtn.disabled = true;
            checkoutBtn.style.background = '#dc2626';
            checkoutBtn.style.borderColor = '#b91c1c';
            checkoutBtn.style.color = '#ffffff';
            checkoutBtn.innerHTML = '<svg class="retail-svg icon-sm" aria-hidden="true" style="margin-right: 4px;"><use href="#icon-retail-credit"></use></svg> <span>Credit Limit Exceeded</span>';
        }
    }
}

async function processCreditSaleConfirmation(customer, total, discount) {
    const checkoutBtn = document.getElementById('checkoutBtn');
    setButtonLoading(checkoutBtn, 'Charging Credit...');

    // 1. Create draft sale
    const draftRes = await apiRequest('/sales/', {
        method: 'POST',
        body: {
            customer_id: customer.id,
            payment_method: 'CREDIT',
            discount: String(discount.toFixed(2)),
            notes: 'In-store POS Credit Ledger Sale',
            items: cart.map(item => ({ product_id: item.product_id, quantity: item.quantity, discount: item.discount })),
        },
    });

    if (!draftRes.success || !draftRes.data?.sale?.id) {
        updateCreditLedgerActionState();
        showMessage(formatApiError(draftRes), 'error');
        return;
    }

    const saleId = draftRes.data.sale.id;
    const saleItemsSnapshot = cart.map(item => ({ ...item }));

    // 2. Complete sale
    const completeRes = await apiRequest(`/sales/${saleId}/complete/`, {
        method: 'POST',
        body: {
            notes: `Charged ₦ ${formatCurrency(total)} to customer credit account.`,
        },
    });

    if (!completeRes.success) {
        updateCreditLedgerActionState();
        showMessage(formatApiError(completeRes), 'error');
        return;
    }

    // 3. Launch POS Receipt Modal
    const completedData = completeRes.data || {};
    openPosReceiptModal(completedData, customer, saleItemsSnapshot);

    // 4. Reset Cart
    cart.length = 0;
    updateCartSummary();
    showMessage('Credit sale charged and completed successfully!', 'success');
}

function openPosReceiptModal(saleData, customer, items) {
    const modal = document.getElementById('posReceiptModal');
    if (!modal) return;

    setText('posReceiptNumber', saleData.sale_number || `HY-POS-${Date.now().toString().slice(-6)}`);
    setText('posReceiptDate', new Date().toLocaleString('en-GB', { dateStyle: 'medium', timeStyle: 'short' }));
    setText('posReceiptCashier', saleData.cashier?.name || 'Cashier');
    setText('posReceiptPaymentMethod', 'Credit Ledger');

    const custName = customer?.name || `${customer?.first_name || ''} ${customer?.last_name || ''}`.trim() || 'Store Credit Customer';
    const custPhone = customer?.phone ? `(${customer.phone})` : '';
    setText('posReceiptCustomerName', custName);
    setText('posReceiptCustomerPhone', custPhone);

    const itemsTbody = document.getElementById('posReceiptItemsBody');
    if (itemsTbody) {
        itemsTbody.innerHTML = (items || []).map(item => {
            const lineTotal = Number(item.price || 0) * Number(item.quantity || 1) - Number(item.discount || 0);
            return `
                <tr style="border-bottom: 1px solid var(--border);">
                    <td style="padding: 6px 0; font-weight: 500;">${escapeHtml(item.name)}</td>
                    <td style="text-align: center; padding: 6px 0;">${item.quantity}</td>
                    <td style="text-align: right; padding: 6px 0; font-family: monospace;">₦ ${formatCurrency(lineTotal)}</td>
                </tr>
            `;
        }).join('');
    }

    const subtotal = saleData.subtotal ? Number(saleData.subtotal) : (items || []).reduce((s, i) => s + (i.price * i.quantity), 0);
    const discount = saleData.discount ? Number(saleData.discount) : 0;
    const total = saleData.total ? Number(saleData.total) : (subtotal - discount);

    setText('posReceiptSubtotal', `₦ ${formatCurrency(subtotal)}`);
    setText('posReceiptDiscount', `₦ ${formatCurrency(discount)}`);
    setText('posReceiptTotal', `₦ ${formatCurrency(total)}`);

    const discountRow = document.getElementById('posReceiptDiscountRow');
    if (discountRow) {
        discountRow.style.display = discount > 0 ? 'flex' : 'none';
    }

    // Updated debt & available balance
    if (saleData.credit_account) {
        setText('posReceiptDebtBalance', `₦ ${formatCurrency(saleData.credit_account.current_balance || saleData.credit_account.outstanding_balance)}`);
        setText('posReceiptAvailableCredit', `₦ ${formatCurrency(saleData.credit_account.available_credit)}`);
    } else {
        const debt = Number(customer?.outstanding_debt || customer?.outstanding_balance || 0) + total;
        const limit = Number(customer?.credit_limit || 0);
        setText('posReceiptDebtBalance', `₦ ${formatCurrency(debt)}`);
        setText('posReceiptAvailableCredit', `₦ ${formatCurrency(Math.max(limit - debt, 0))}`);
    }

    modal.classList.add('active');
    modal.setAttribute('aria-hidden', 'false');
}

function closePosReceiptModal() {
    const modal = document.getElementById('posReceiptModal');
    if (modal) {
        modal.classList.remove('active');
        modal.setAttribute('aria-hidden', 'true');
    }
    clearCreditCustomer();
}

function printPosReceipt() {
    window.print();
}

function startNewSaleFromReceipt() {
    closePosReceiptModal();
    clearCart();
    const searchInput = document.getElementById('productSearchInput');
    if (searchInput) searchInput.focus();
}
