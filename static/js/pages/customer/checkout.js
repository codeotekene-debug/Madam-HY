/**
 * MADAM HY - Customer Checkout Controller
 * Standardized on Paystack Online & Conditional Pay on Delivery
 */

let checkoutData = { items: [], subtotal: '0.00', total: '0.00', allow_cod: true, customer: null };

document.addEventListener('DOMContentLoaded', () => {
    loadCheckoutReview();
    bindFormEvents();
    bindPaymentOptions();
});

function bindPaymentOptions() {
    const options = document.querySelectorAll('.payment-option');
    const updateInstruction = (method) => {
        const textEl = document.getElementById('paymentInstructionText');
        if (!textEl) return;
        if (method === 'cod') {
            textEl.textContent = 'Pay on Delivery is available only when every product in your cart permits it.';
        } else if (method === 'credit') {
            textEl.textContent = 'Use your approved store credit balance for this order.';
        } else {
            textEl.textContent = 'Continue to Paystack to see the payment options currently available to you.';
        }
    };

    options.forEach(option => {
        const radio = option.querySelector('input[type="radio"]');
        option.addEventListener('click', () => {
            if (radio && !radio.disabled) {
                radio.checked = true;
                options.forEach(o => o.classList.remove('active'));
                option.classList.add('active');
                updateInstruction(radio.value);
            }
        });
        radio?.addEventListener('change', () => {
            options.forEach(o => o.classList.remove('active'));
            option.classList.add('active');
            updateInstruction(radio.value);
        });
    });
}

async function loadCheckoutReview() {
    const response = await apiRequest('/customer/checkout/?format=json');
    if (!response.success) {
        if (response.status === 401) {
            window.location.href = '/accounts/login/?next=' + encodeURIComponent(window.location.pathname);
            return;
        }
        showCheckoutError(response.message || 'Unable to load checkout review.');
        return;
    }

    checkoutData = response.data || {};
    renderCheckoutSummary();
    populateCustomerFields();
    applyCodEligibility();
    applyCreditEligibility();
}

function applyCreditEligibility() {
    const credit = checkoutData.credit;
    if (!credit || !credit.has_account) return;

    const selectedZoneFee = document.getElementById('checkoutDeliveryType')?.value === 'Pickup'
        ? 0
        : Number(document.getElementById('checkoutDeliveryZone')?.selectedOptions?.[0]?.dataset?.fee || 0);
    const total = Number(checkoutData.subtotal || checkoutData.total || 0) + selectedZoneFee;
    const available = Number(credit.available_credit || 0);
    const canUseCredit = credit.can_use_credit !== false && total <= available;

    const creditRadio = document.getElementById('payMethodCredit');
    const creditCard = document.getElementById('payMethodCardCredit');
    const noticeText = document.getElementById('creditNoticeText');
    const badge = document.getElementById('creditStatusBadge');
    const availableDisplay = document.getElementById('creditAvailableDisplay');

    if (availableDisplay) {
        availableDisplay.textContent = formatCurrency(available);
    }

    if (!canUseCredit) {
        if (creditRadio) {
            creditRadio.disabled = true;
            if (creditRadio.checked) {
                const paystackRadio = document.getElementById('payMethodPaystack');
                if (paystackRadio) {
                    paystackRadio.checked = true;
                    document.querySelectorAll('.payment-option').forEach(o => o.classList.remove('active'));
                    document.getElementById('payMethodCardPaystack')?.classList.add('active');
                    const textEl = document.getElementById('paymentInstructionText');
                    if (textEl) textEl.textContent = 'You will be securely redirected to Paystack to complete your payment with debit card, USSD, or direct bank transfer.';
                }
            }
        }
        if (creditCard) {
            creditCard.classList.add('disabled');
            creditCard.style.opacity = '0.65';
            creditCard.style.cursor = 'not-allowed';
            creditCard.title = `Cart total (₦${formatCurrency(total)}) exceeds available credit of ₦${formatCurrency(available)}`;
        }
        if (noticeText) {
            noticeText.textContent = `Credit limit exceeded: Available credit is ₦${formatCurrency(available)}, but cart total is ₦${formatCurrency(total)}.`;
            noticeText.className = 'text-danger';
        }
        if (badge) {
            badge.textContent = 'Limit Exceeded';
            badge.className = 'badge badge-warning';
        }
    } else {
        if (creditRadio) {
            creditRadio.disabled = false;
        }
        if (creditCard) {
            creditCard.classList.remove('disabled');
            creditCard.style.opacity = '1';
            creditCard.style.cursor = 'pointer';
            creditCard.title = 'Pay with Store Credit';
        }
        if (noticeText) {
            noticeText.textContent = 'Settle purchase instantly using your approved store credit facility.';
            noticeText.className = '';
        }
        if (badge) {
            badge.textContent = 'Instant Credit';
            badge.className = 'badge badge-primary';
        }
    }
}

function applyCodEligibility() {
    const allowCod = checkoutData.allow_cod !== false;
    const codRadio = document.getElementById('payMethodCOD');
    const codCard = document.getElementById('payMethodCardCOD');

    if (!allowCod) {
        if (codRadio) {
            codRadio.disabled = true;
            if (codRadio.checked) {
                const paystackRadio = document.getElementById('payMethodPaystack');
                if (paystackRadio) {
                    paystackRadio.checked = true;
                    document.querySelectorAll('.payment-option').forEach(o => o.classList.remove('active'));
                    document.getElementById('payMethodCardPaystack')?.classList.add('active');
                }
            }
        }
        if (codCard) {
            codCard.classList.add('disabled');
            codCard.style.opacity = '0.6';
            codCard.style.cursor = 'not-allowed';
        }
    } else {
        if (codRadio) {
            codRadio.disabled = false;
        }
        if (codCard) {
            codCard.classList.remove('disabled');
            codCard.style.opacity = '1';
            codCard.style.cursor = 'pointer';
        }
    }
}

function populateCustomerFields() {
    const customer = checkoutData.customer;
    if (!customer) return;

    const nameInput = document.getElementById('checkoutName');
    const emailInput = document.getElementById('checkoutEmail');
    const phoneInput = document.getElementById('checkoutPhone');

    if (nameInput && !nameInput.value && customer.name) nameInput.value = customer.name;
    if (emailInput && !emailInput.value && customer.email) emailInput.value = customer.email;
    if (phoneInput && !phoneInput.value && customer.phone) phoneInput.value = customer.phone;
}

function bindFormEvents() {
    const form = document.getElementById('checkoutForm');
    form?.addEventListener('submit', submitOrder);
    const deliveryType = document.getElementById('checkoutDeliveryType');
    deliveryType?.addEventListener('change', () => { updateAddressField(); renderCheckoutSummary(); applyCreditEligibility(); });
    document.getElementById('checkoutDeliveryZone')?.addEventListener('change', () => { renderCheckoutSummary(); applyCreditEligibility(); });
    updateAddressField();
}

function updateAddressField() {
    const pickup = document.getElementById('checkoutDeliveryType')?.value === 'Pickup';
    const address = document.getElementById('checkoutAddress');
    const label = document.getElementById('checkoutAddressLabel');
    const hint = document.getElementById('checkoutAddressHint');
    const zoneGroup = document.getElementById('checkoutZoneGroup');
    const zone = document.getElementById('checkoutDeliveryZone');
    if (!address || !label || !hint) return;

    address.required = !pickup;
    if (zoneGroup) zoneGroup.hidden = pickup;
    if (zone) zone.required = !pickup;
    label.innerHTML = pickup ? 'Pickup instructions <span class="optional">(optional)</span>' : 'Delivery address <span class="required">*</span>';
    address.placeholder = pickup
        ? 'Add any notes that may help with store pickup...'
        : 'Enter your street address and a nearby landmark...';
    hint.textContent = pickup
        ? 'You can leave this blank for in-store pickup.'
        : 'A delivery address is required for doorstep delivery.';
}

async function submitOrder(event) {
    event.preventDefault();
    const button = document.getElementById('submitOrderBtn');

    if (!checkoutData.items || !checkoutData.items.length) {
        showCheckoutError('Your cart is empty. Add products before placing an order.');
        return;
    }

    const name = document.getElementById('checkoutName')?.value.trim();
    const email = document.getElementById('checkoutEmail')?.value.trim();
    const phone = document.getElementById('checkoutPhone')?.value.trim();
    const deliveryType = document.getElementById('checkoutDeliveryType')?.value;
    const deliveryZoneId = document.getElementById('checkoutDeliveryZone')?.value;
    const address = document.getElementById('checkoutAddress')?.value.trim();

    if (!name || !email || !phone) {
        showCheckoutError('Please provide your complete contact details.');
        return;
    }
    if (deliveryType !== 'Pickup' && !address) {
        showCheckoutError('Please provide your delivery address.');
        return;
    }
    if (deliveryType !== 'Pickup' && !deliveryZoneId) {
        showCheckoutError('Choose the delivery area so the correct fee can be included in your order total.');
        return;
    }

    const selectedRadio = document.querySelector('input[name="payment_method"]:checked')
        || document.querySelector('input[name="paymentMethod"]:checked');
    const paymentMethod = selectedRadio ? selectedRadio.value.toLowerCase() : 'paystack';

    // Verify COD eligibility
    if (paymentMethod === 'cod') {
        if (checkoutData.allow_cod === false || (selectedRadio && selectedRadio.disabled)) {
            showCheckoutError('One or more items in your cart are not eligible for Pay on Delivery. Please pay online via Paystack.');
            return;
        }
    }

    if (button) {
        button.disabled = true;
        button.innerHTML = '<i class="bi bi-hourglass-split"></i> Processing Order...';
    }
    hideCheckoutError();

    const notesParts = [
        deliveryType ? `Delivery: ${deliveryType}` : '',
        name ? `Recipient: ${name}` : '',
    ].filter(Boolean);

    const csrfToken = document.querySelector('input[name="csrfmiddlewaretoken"]')?.value;

    const response = await apiRequest('/customer/checkout/', {
        method: 'POST',
        headers: csrfToken ? { 'X-CSRFToken': csrfToken } : {},
        body: {
            payment_method: paymentMethod,
            delivery_address: address,
            customer_phone: phone,
            delivery_type: deliveryType,
            delivery_zone_id: deliveryType === 'Pickup' ? '' : deliveryZoneId,
            notes: notesParts.join(' | '),
        },
    });

    if (button) {
        button.disabled = false;
        button.innerHTML = '<i class="bi bi-check2-circle"></i> Place &amp; Settle Order';
    }

    if (!response.success) {
        let errorMsg = response.message || 'Unable to place your order.';
        if (response.errors) {
            const errorDetails = Object.entries(response.errors)
                .map(([field, err]) => Array.isArray(err) ? err.join(', ') : String(err))
                .join('; ');
            if (errorDetails) errorMsg += ` (${errorDetails})`;
        }
        showCheckoutError(errorMsg);
        return;
    }

    const data = response.data || {};
    const authUrl = data.authorization_url || data.payment?.authorization_url;
    const orderRef = data.order_reference || data.order?.order_number;
    const orderId = data.order?.id;

    // Purge local cart cache/storage if any
    try {
        localStorage.removeItem('madamhy_cart');
        sessionStorage.removeItem('madamhy_cart');
    } catch (e) {}

    // Paystack Online: redirect to Paystack authorization URL
    if (paymentMethod === 'paystack' || paymentMethod === 'card') {
        if (authUrl) {
            window.location.href = authUrl;
            return;
        }
    }

    // Pay on Delivery (or fallback order confirmation): redirect to success page
    if (orderRef) {
        window.location.href = `/customer/orders/success/?ref=${encodeURIComponent(orderRef)}`;
    } else if (orderId) {
        window.location.href = `/customer/orders/${orderId}/success/`;
    } else {
        window.location.href = '/customer/orders/';
    }
}

function renderCheckoutSummary() {
    const list = document.getElementById('checkoutItemsList');
    if (!list) return;

    const items = checkoutData.items || [];
    if (!items.length) {
        list.replaceChildren(document.createTextNode('Your shopping cart is empty.'));
    } else {
        list.innerHTML = items.map(item => `
            <div class="checkout-item">
                <span>${escapeHtml(item.name)} × ${item.quantity}</span>
                <strong>₦${formatCurrency(item.line_total || (item.unit_price * item.quantity))}</strong>
            </div>
        `).join('');
    }

    const subtotal = checkoutData.subtotal || '0.00';
    const pickup = document.getElementById('checkoutDeliveryType')?.value === 'Pickup';
    const selectedZone = document.getElementById('checkoutDeliveryZone')?.selectedOptions?.[0];
    const deliveryFee = pickup ? 0 : Number(selectedZone?.dataset?.fee || 0);
    const total = Number(subtotal) + deliveryFee;

    document.getElementById('checkoutSubtotal')?.replaceChildren(document.createTextNode(`₦ ${formatCurrency(subtotal)}`));
    document.getElementById('checkoutTax')?.replaceChildren(document.createTextNode('Not calculated'));
    document.getElementById('checkoutDelivery')?.replaceChildren(document.createTextNode(pickup ? '₦ 0.00' : (selectedZone?.value ? `₦ ${formatCurrency(deliveryFee)}` : 'Choose an area')));
    document.getElementById('checkoutTotal')?.replaceChildren(document.createTextNode(`₦ ${formatCurrency(total)}`));

    const submitBtn = document.getElementById('submitOrderBtn');
    if (submitBtn) {
        submitBtn.disabled = !items.length;
    }
}

function showCheckoutError(message) {
    const target = document.getElementById('checkoutFormError');
    if (target) {
        target.textContent = message;
        target.classList.remove('hidden');
    }
}

function hideCheckoutError() {
    document.getElementById('checkoutFormError')?.classList.add('hidden');
}

function formatCurrency(value) {
    return Number(value || 0).toLocaleString('en-NG', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function escapeHtml(value) {
    const element = document.createElement('span');
    element.textContent = value == null ? '' : String(value);
    return element.innerHTML;
}
