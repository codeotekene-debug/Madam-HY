"""
Paystack Online Checkout & Direct Rails Integration Service (Phase 4A).
Provides transaction initialization, authorization URL generation,
and standard/inline checkout synchronization.
"""

import logging
import os
import time
import uuid
from decimal import Decimal, InvalidOperation

import requests
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.activity_logs.models import ActivityLog
from apps.activity_logs.services import log_activity
from apps.sales.models import Sale
from apps.orders.models import Order

from .models import Payment

logger = logging.getLogger('apps.payments')


class PaystackCheckoutService:
    """
    Handles Paystack inline/standard checkout initialization and authorization URL dispatch.
    """

    @classmethod
    def get_secret_key(cls, override_key: str = None) -> str:
        if override_key:
            return override_key.strip()
        key = getattr(settings, 'PAYSTACK_SECRET_KEY', None) or os.getenv('PAYSTACK_SECRET_KEY', '')
        return str(key).strip()

    @classmethod
    def get_base_url(cls, override_url: str = None) -> str:
        if override_url:
            return override_url.strip().rstrip('/')
        url = getattr(settings, 'PAYSTACK_BASE_URL', None) or os.getenv('PAYSTACK_BASE_URL', 'https://api.paystack.co')
        return str(url).strip().rstrip('/')

    @classmethod
    def initialize_transaction(
        cls,
        target,
        email: str = None,
        amount=None,
        callback_url: str = None,
        reference: str = None,
        channels: list = None,
        secret_key: str = None,
        base_url: str = None,
        timeout: int = 15,
        max_retries: int = 2,
    ) -> dict:
        """
        Initializes a Paystack online payment transaction and returns authorization URL.

        Parameters:
            target: A Payment instance, Sale instance, or Order instance.
            email: Customer email address (required by Paystack).
            amount: Optional override amount in NGN.
            callback_url: Redirect URL after customer completes payment.
            reference: Optional custom transaction reference.
            channels: List of permitted payment channels (e.g. ['card', 'bank', 'ussd', 'qr']).
            secret_key: Optional secret key override.
            base_url: Optional base URL override.
            timeout: Network request timeout in seconds.
            max_retries: Number of retry attempts on transient network errors.

        Returns:
            dict containing authorization_url, access_code, reference, and payment_id.
        """
        resolved_secret_key = cls.get_secret_key(secret_key)
        resolved_base_url = cls.get_base_url(base_url)

        is_payment = isinstance(target, Payment)
        is_sale = isinstance(target, Sale)
        is_order = isinstance(target, Order)

        if not (is_payment or is_sale or is_order):
            raise ValidationError({'target': 'Target must be an instance of Payment, Sale, or Order.'})

        if amount is not None:
            try:
                dec_amount = Decimal(str(amount)).quantize(Decimal('0.01'))
            except (InvalidOperation, TypeError, ValueError):
                raise ValidationError({'amount': 'Amount must be a valid monetary value.'})
        elif is_payment:
            dec_amount = target.amount
        else:
            dec_amount = target.total

        if dec_amount <= Decimal('0.00'):
            raise ValidationError({'amount': 'Payment amount must be greater than zero.'})

        kobo_amount = int(dec_amount * 100)

        # Resolve email
        resolved_email = email
        if not resolved_email:
            customer = getattr(target, 'customer', None)
            if customer:
                resolved_email = getattr(customer, 'email', None)

        if not resolved_email or not str(resolved_email).strip():
            raise ValidationError({'email': 'A valid customer email address is required for Paystack checkout.'})
        resolved_email = str(resolved_email).strip()

        # Resolve callback URL
        cb_url = callback_url or getattr(settings, 'PAYSTACK_CALLBACK_URL', 'https://smartshop.ng/payments/verify')

        # Get or create Payment record
        with transaction.atomic():
            if is_payment:
                payment = target
                if payment.payment_status == Payment.PaymentStatus.COMPLETED:
                    raise ValidationError({'payment': 'Payment is already completed.'})
            else:
                txn_ref = reference or f"PSTK-{uuid.uuid4().hex[:12].upper()}"
                payment_ref = f"PAY-PSTK-{target.pk}-{uuid.uuid4().hex[:6].upper()}"
                target_customer = getattr(target, 'customer', None)
                target_cashier = getattr(target, 'cashier', None) or getattr(target, 'created_by', None)

                payment, _ = Payment.objects.get_or_create(
                    sale=target if is_sale else None,
                    order=target if not is_sale else None,
                    payment_status=Payment.PaymentStatus.PENDING,
                    payment_method=Payment.PaymentMethod.CARD,
                    defaults={
                        'amount': dec_amount,
                        'payment_reference': payment_ref,
                        'transaction_reference': txn_ref,
                        'customer': target_customer,
                        'cashier': target_cashier,
                        'transaction_metadata': {
                            'channel': 'PAYSTACK_ONLINE',
                            'kobo_amount': kobo_amount,
                        },
                        'notes': 'Paystack online checkout initialized.',
                    },
                )

        merchant_ref = payment.transaction_reference or payment.payment_reference

        payload = {
            'email': resolved_email,
            'amount': kobo_amount,
            'reference': merchant_ref,
            'currency': 'NGN',
            'callback_url': cb_url,
        }
        if channels:
            payload['channels'] = channels

        headers = {
            'Authorization': f'Bearer {resolved_secret_key}',
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'User-Agent': 'SmartShop-PaystackCheckout/1.0',
        }

        url = f'{resolved_base_url}/transaction/initialize'
        response_data = None
        http_status = None
        last_exception = None
        request_success = False

        for attempt in range(max_retries + 1):
            try:
                resp = requests.post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=timeout,
                )
                http_status = resp.status_code
                try:
                    response_data = resp.json()
                except Exception:
                    response_data = {'raw_text': resp.text[:500]}

                if http_status in (200, 201):
                    request_success = bool(response_data.get('status', False))
                    break
                elif http_status in (400, 401, 403, 404):
                    request_success = False
                    break
                else:
                    if attempt < max_retries:
                        time.sleep(0.5 * (attempt + 1))
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
                last_exception = exc
                if attempt < max_retries:
                    time.sleep(0.5 * (attempt + 1))
            except Exception as exc:
                last_exception = exc
                break

        auth_url = ''
        access_code = ''
        if request_success and isinstance(response_data, dict):
            data_body = response_data.get('data') or {}
            auth_url = data_body.get('authorization_url', '')
            access_code = data_body.get('access_code', '')

        # Record metadata
        meta = dict(payment.transaction_metadata or {})
        meta['paystack_initialization'] = {
            'initialized_at': timezone.now().isoformat(),
            'http_status': http_status,
            'success': request_success,
            'authorization_url': auth_url,
            'access_code': access_code,
            'error': str(last_exception) if last_exception else None,
        }
        payment.transaction_metadata = meta
        payment.save(update_fields=['transaction_metadata', 'updated_at'])

        log_activity(
            actor=None,
            action_type=ActivityLog.ActionType.PAYMENT,
            action_label='Initialized Paystack online checkout',
            description=f'Initialized Paystack checkout for NGN {dec_amount:,.2f} (ref: {merchant_ref}).',
            related_object=payment,
            metadata={
                'payment_id': payment.id,
                'reference': merchant_ref,
                'amount': str(dec_amount),
                'email': resolved_email,
                'success': request_success,
            },
        )

        return {
            'success': request_success,
            'status': 'PENDING' if request_success else 'FAILED',
            'authorization_url': auth_url,
            'access_code': access_code,
            'reference': merchant_ref,
            'payment_id': payment.id,
            'payment_reference': payment.payment_reference,
            'amount': f'{dec_amount:.2f}',
            'kobo_amount': kobo_amount,
            'currency': 'NGN',
            'message': response_data.get('message', 'Checkout initialized successfully.') if response_data else 'Checkout request processed.',
            'response': response_data,
            'error': str(last_exception) if last_exception else None,
        }


# Standard alias
PaystackService = PaystackCheckoutService

