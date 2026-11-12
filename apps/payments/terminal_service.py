"""
Moniepoint POS Terminal Integration Service (Phase 4B).
Provides terminal charge push, device polling, status synchronization, and authentication
for in-store POS cashier terminals and merchant devices.
"""
import http.client 
import json
import logging
import os
import threading
import time
import uuid
from decimal import Decimal, InvalidOperation

import requests
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.activity_logs.models import ActivityLog
from apps.activity_logs.services import log_activity
from apps.sales.models import Sale
from apps.orders.models import Order

from .models import Payment
from .verification import PaymentVerificationService, PaymentVerificationStatus

logger = logging.getLogger('apps.payments')


class MoniepointConfigurationError(ImproperlyConfigured):
    """Raised when Moniepoint environment configuration or credentials are missing/invalid."""
    pass


class MoniepointAPIError(Exception):
    """Base exception for Moniepoint API communication or gateway failures."""
    def __init__(self, message, status_code=None, response_data=None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.response_data = response_data or {}


class MoniepointTimeoutError(MoniepointAPIError):
    """Raised when a gateway network timeout occurs."""
    pass


class MoniepointAuthError(MoniepointAPIError):
    """Raised when authentication with Moniepoint gateway fails."""
    pass


class MoniepointAuthManager:
    """
    Manages authentication headers for Moniepoint API requests.
    Supports:
      1. Direct API Key authentication (default for https://api.pos.moniepoint.com)
         Header: Authorization: Bearer <API_KEY>
      2. OAuth Client Credentials authentication (for https://channel.moniepoint.com or partner gateway)
         Endpoint: POST /v1/auth
         Header: Authorization: Bearer <accessToken>
         Safely caches token in-memory and refreshes before expiration.
    """
    _token_cache = {}  # {cache_key: (access_token, expires_at_timestamp)}
    _lock = threading.Lock()

    @classmethod
    def clear_cache(cls):
        """Clears all cached tokens (useful for testing and key rotations)."""
        with cls._lock:
            cls._token_cache.clear()

    @classmethod
    def get_auth_mode(cls, base_url: str = None) -> str:
        """
        Determines the authentication mode:
        Returns 'CLIENT_CREDENTIALS' or 'API_KEY'.
        """
        configured_mode = getattr(settings, 'MONIEPOINT_AUTH_METHOD', None) or os.getenv('MONIEPOINT_AUTH_METHOD', '')
        configured_mode = str(configured_mode).strip().upper()
        if configured_mode in ('CLIENT_CREDENTIALS', 'OAUTH'):
            return 'CLIENT_CREDENTIALS'
        if configured_mode in ('API_KEY', 'DIRECT'):
            return 'API_KEY'

        # Auto-detection heuristic:
        client_id = getattr(settings, 'MONIEPOINT_CLIENT_ID', None) or os.getenv('MONIEPOINT_CLIENT_ID', '')
        client_secret = (
            getattr(settings, 'MONIEPOINT_CLIENT_SECRET', None)
            or os.getenv('MONIEPOINT_CLIENT_SECRET', '')
        )
        api_key = getattr(settings, 'MONIEPOINT_API_KEY', None) or os.getenv('MONIEPOINT_API_KEY', '')

        if client_id and client_secret:
            return 'CLIENT_CREDENTIALS'
        if api_key:
            return 'API_KEY'

        resolved_url = str(base_url or getattr(settings, 'MONIEPOINT_BASE_URL', '')).lower()
        if 'channel.moniepoint.com' in resolved_url:
            return 'CLIENT_CREDENTIALS'

        return 'API_KEY'

    @classmethod
    def get_authorization_header(
        cls,
        api_key: str = None,
        client_id: str = None,
        client_secret: str = None,
        base_url: str = None,
        timeout: int = 15,
    ) -> dict:
        """
        Returns the HTTP headers containing a valid Authorization Bearer token.
        Never exposes secrets in logs or error messages.
        """
        mode = cls.get_auth_mode(base_url=base_url)

        if mode == 'CLIENT_CREDENTIALS':
            cid = str(client_id or getattr(settings, 'MONIEPOINT_CLIENT_ID', None) or os.getenv('MONIEPOINT_CLIENT_ID', '')).strip()
            csecret = str(
                client_secret
                or getattr(settings, 'MONIEPOINT_CLIENT_SECRET', None)
                or getattr(settings, 'MONIEPOINT_SECRET_KEY', None)
                or os.getenv('MONIEPOINT_CLIENT_SECRET', '')
                or os.getenv('MONIEPOINT_SECRET_KEY', '')
            ).strip()

            if not cid or not csecret:
                raise MoniepointConfigurationError(
                    "Moniepoint client credentials are required for OAuth authentication. "
                    "Configure MONIEPOINT_CLIENT_ID and MONIEPOINT_CLIENT_SECRET."
                )

            token = cls._get_or_refresh_oauth_token(cid, csecret, base_url=base_url, timeout=timeout)
            return {'Authorization': f'Bearer {token}'}

        else:
            # Direct API Key authentication
            key = str(
                api_key
                or getattr(settings, 'MONIEPOINT_API_KEY', None)
                or os.getenv('MONIEPOINT_API_KEY', '')
            ).strip()

            if not key:
                # Check fallback to secret key if configured as API key
                secret_key = str(
                    getattr(settings, 'MONIEPOINT_SECRET_KEY', None)
                    or os.getenv('MONIEPOINT_SECRET_KEY', '')
                ).strip()
                if secret_key and not secret_key.startswith('api-client-'):
                    key = secret_key

            if not key:
                raise MoniepointConfigurationError(
                    "Moniepoint API key is not configured. Set MONIEPOINT_API_KEY in environment."
                )

            return {'Authorization': f'Bearer {key}'}

    @classmethod
    def _get_or_refresh_oauth_token(
        cls,
        client_id: str,
        client_secret: str,
        base_url: str = None,
        timeout: int = 15,
    ) -> str:
        """Exchanges client credentials for a bearer token via POST /v1/auth with thread-safe token caching."""
        resolved_url = (base_url or getattr(settings, 'MONIEPOINT_BASE_URL', None) or 'https://api.pos.moniepoint.com').rstrip('/')
        cache_key = f"{client_id}@{resolved_url}"
        now = time.time()

        with cls._lock:
            cached = cls._token_cache.get(cache_key)
            if cached:
                token, expires_at = cached
                if expires_at > now + 60:  # 60s safety buffer
                    return token

            # Token expired or missing; perform POST /v1/auth
            auth_url = f"{resolved_url}/v1/auth"
            payload = {
                'username': client_id,
                'password': client_secret,
                'clientId': client_id,
                'clientSecret': client_secret,
            }
            headers = {
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'User-Agent': 'SmartShop-MoniepointPOS/1.0',
            }

            try:
                resp = requests.post(auth_url, json=payload, headers=headers, timeout=timeout)
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
                raise MoniepointTimeoutError(f"Connection timeout contacting Moniepoint auth endpoint: {exc}")
            except Exception as exc:
                raise MoniepointAuthError(f"Unexpected error communicating with Moniepoint auth endpoint: {exc}")

            if resp.status_code not in (200, 201):
                err_text = resp.text[:300]
                raise MoniepointAuthError(
                    f"Moniepoint authentication failed with status {resp.status_code}: {err_text}",
                    status_code=resp.status_code,
                )

            try:
                data = resp.json()
            except Exception:
                raise MoniepointAuthError("Moniepoint auth endpoint returned non-JSON response.")

            token = (
                data.get('accessToken')
                or data.get('token')
                or (data.get('data', {}).get('accessToken') if isinstance(data.get('data'), dict) else None)
                or (data.get('responseBody', {}).get('accessToken') if isinstance(data.get('responseBody'), dict) else None)
            )

            if not token:
                raise MoniepointAuthError("Malformed response from Moniepoint auth endpoint: missing accessToken.")

            expires_in = (
                data.get('expiresIn')
                or data.get('expires_in')
                or (data.get('data', {}).get('expiresIn') if isinstance(data.get('data'), dict) else None)
                or (data.get('responseBody', {}).get('expiresIn') if isinstance(data.get('responseBody'), dict) else None)
                or 3600
            )

            try:
                expires_in = int(expires_in)
            except (ValueError, TypeError):
                expires_in = 3600

            expires_at = now + expires_in
            cls._token_cache[cache_key] = (token, expires_at)
            return token


class MoniepointClient:
    """
    Low-level client for Moniepoint POS API endpoints.
    Targets official Moniepoint POS endpoints:
      - POST /v1/transactions (Push transaction to terminal)
      - GET /v1/transactions/merchants/{merchantReference} (Query transaction details)
      - GET /v1/introspect (Verify token/API key and permissions)
    """

    def __init__(self, base_url: str = None, timeout: int = 15):
        self.base_url = (base_url or getattr(settings, 'MONIEPOINT_BASE_URL', None) or 'https://api.pos.moniepoint.com').rstrip('/')
        try:
            self.timeout = int(timeout or getattr(settings, 'MONIEPOINT_TIMEOUT', 15))
        except (ValueError, TypeError):
            self.timeout = 15

    def introspect(self, api_key: str = None) -> dict:
        """Calls GET /v1/introspect to verify credentials and scopes."""
        url = f"{self.base_url}/v1/introspect"
        auth_headers = MoniepointAuthManager.get_authorization_header(
            api_key=api_key,
            base_url=self.base_url,
            timeout=self.timeout,
        )
        headers = {
            **auth_headers,
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'User-Agent': 'SmartShop-MoniepointPOS/1.0',
        }
        try:
            resp = requests.get(url, headers=headers, timeout=self.timeout)
            return resp.json() if resp.status_code == 200 else {'status_code': resp.status_code, 'data': resp.text[:300]}
        except Exception as exc:
            return {'status_code': 500, 'error': str(exc)}

    def push_transaction(
        self,
        terminal_serial: str,
        amount_kobo: int,
        merchant_reference: str,
        payment_method: str = "CARD_PURCHASE",
        api_key: str = None,
        max_retries: int = 2,
    ) -> dict:
        """
        Pushes a payment transaction request to a Moniepoint POS terminal.
        Endpoint: POST /v1/transactions
        Payload:
            terminalSerial (str, required): Hardware serial number of POS terminal.
            amount (int, required): Amount in KOBO as 64-bit integer (min: 100).
            merchantReference (str, required): Unique merchant reference.
            transactionType (str, required): "PURCHASE".
            paymentMethod (str, required): "CARD_PURCHASE" or "POS_TRANSFER".
        """
        clean_serial = str(terminal_serial or '').strip()
        if not clean_serial:
            raise ValidationError({'terminal_serial': 'A valid terminal serial number is required.'})

        if clean_serial.startswith('api-client-'):
            raise ValidationError({
                'terminal_serial': (
                    f"'{clean_serial}' is an API Client ID, not a physical POS hardware serial number. "
                    "Configure MONIEPOINT_TERMINAL_ID with the device serial number."
                )
            })

        if not isinstance(amount_kobo, int) or amount_kobo < 100:
            raise ValidationError({'amount': 'Amount must be an integer >= 100 kobo (₦1.00).'})

        clean_ref = str(merchant_reference or '').strip()
        if not clean_ref:
            raise ValidationError({'merchant_reference': 'A unique merchant reference is required.'})

        valid_methods = {'CARD_PURCHASE', 'POS_TRANSFER', 'ANY'}
        norm_method = str(payment_method or '').strip().upper()
        if norm_method not in valid_methods:
            norm_method = 'CARD_PURCHASE'

        payload = {
            'terminalSerial': clean_serial,
            'amount': amount_kobo,
            'merchantReference': clean_ref,
            'transactionType': 'PURCHASE',
            'paymentMethod': norm_method,
        }

        auth_headers = MoniepointAuthManager.get_authorization_header(
            api_key=api_key,
            base_url=self.base_url,
            timeout=self.timeout,
        )
        headers = {
            **auth_headers,
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'User-Agent': 'SmartShop-MoniepointPOS/1.0',
        }

        url = f'{self.base_url}/v1/transactions'
        response_data = None
        http_status = None
        last_exception = None
        request_success = False

        for attempt in range(max_retries + 1):
            try:
                resp = requests.post(url, json=payload, headers=headers, timeout=self.timeout)
                http_status = resp.status_code
                try:
                    response_data = resp.json()
                except Exception:
                    response_data = {'raw_text': resp.text[:500]}

                # Official Moniepoint POS returns HTTP 202 Accepted on successful push
                if http_status in (200, 201, 202):
                    request_success = True
                    break
                elif http_status in (400, 401, 403, 404, 422):
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

        msg = (
            'Transaction pushed to POS terminal successfully.'
            if request_success
            else 'Failed to communicate with POS terminal.'
        )
        if isinstance(response_data, dict) and response_data.get('message'):
            msg = response_data['message']

        return {
            'success': request_success,
            'status': 'PENDING' if request_success else 'FAILED',
            'terminal_serial': clean_serial,
            'terminal_id': clean_serial,
            'merchant_reference': clean_ref,
            'amount_kobo': amount_kobo,
            'amount_naira': f"{Decimal(amount_kobo) / Decimal(100):.2f}",
            'payment_method': norm_method,
            'http_status': http_status,
            'response': response_data,
            'message': msg,
            'error': str(last_exception) if last_exception else None,
        }

    def get_transaction_status(self, merchant_reference: str, api_key: str = None, **kwargs) -> dict:
        """
        Queries Moniepoint POS API for transaction status.
        Endpoint: GET /v1/transactions/merchants/{merchantReference}
        """
        clean_ref = str(merchant_reference or '').strip()
        if not clean_ref:
            return {
                'success': False,
                'status': 'FAILED',
                'processing_status': 'EMPTY_REFERENCE',
                'merchant_reference': '',
                'message': 'Merchant reference is required.',
            }

        auth_headers = MoniepointAuthManager.get_authorization_header(
            api_key=api_key,
            base_url=self.base_url,
            timeout=self.timeout,
        )
        headers = {
            **auth_headers,
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'User-Agent': 'SmartShop-MoniepointPOS/1.0',
        }
        url = f'{self.base_url}/v1/transactions/merchants/{clean_ref}'

        try:
            resp = requests.get(url, headers=headers, timeout=self.timeout)
            http_status = resp.status_code
            try:
                data = resp.json()
            except Exception:
                data = {'raw_text': resp.text[:500]}

            if http_status == 200 and isinstance(data, dict):
                payload_data = data.get('data') if isinstance(data.get('data'), dict) else data

                raw_status = str(payload_data.get('processingStatus') or payload_data.get('status') or '').upper().strip()
                response_code = payload_data.get('responseCode') if payload_data.get('responseCode') is not None else data.get('responseCode')
                is_explicit_false = payload_data.get('status') is False or data.get('status') is False

                # Handle actualAmount (convert kobo to naira if in kobo)
                actual_raw = payload_data.get('actualAmount') if payload_data.get('actualAmount') is not None else payload_data.get('amount')
                actual_kobo = None
                actual_naira = None
                if actual_raw is not None:
                    try:
                        dec_val = Decimal(str(actual_raw))
                        expected_amt = kwargs.get('expected_amount')
                        if expected_amt is not None and dec_val == Decimal(str(expected_amt)):
                            actual_naira = dec_val
                            actual_kobo = int(round(float(dec_val) * 100))
                        elif dec_val >= Decimal('100'):
                            actual_kobo = int(dec_val)
                            actual_naira = (dec_val / Decimal('100')).quantize(Decimal('0.01'))
                        else:
                            actual_naira = dec_val.quantize(Decimal('0.01'))
                            actual_kobo = int(round(float(dec_val) * 100))
                    except (InvalidOperation, ValueError, TypeError):
                        pass

                resp_msg = payload_data.get('responseMessage') or payload_data.get('message') or data.get('message') or ''

                # Validate responseCode and failure conditions
                has_error_code = response_code not in (None, '00', '0', 0, 200)

                if is_explicit_false or has_error_code:
                    norm_status = 'FAILED'
                elif raw_status in ('SUCCESSFUL', 'COMPLETED', 'PROCESSED', 'APPROVED', 'PAID'):
                    norm_status = 'SUCCESS'
                elif raw_status in ('PENDING', 'QUEUED', 'INITIALIZED'):
                    norm_status = 'PENDING'
                elif raw_status in ('FAILED', 'REJECTED', 'CANCELLED', 'EXPIRED', 'DECLINED'):
                    norm_status = 'FAILED'
                else:
                    norm_status = 'PENDING' if not raw_status else 'FAILED'

                # Verify reference match if returned
                resp_ref = payload_data.get('merchantReference') or payload_data.get('merchant_reference')
                ref_mismatch = False
                if resp_ref and str(resp_ref).strip() != clean_ref:
                    ref_mismatch = True
                    norm_status = 'FAILED'
                    resp_msg = f"Merchant reference mismatch: expected {clean_ref}, got {resp_ref}."

                return {
                    'success': norm_status == 'SUCCESS',
                    'status': norm_status,
                    'processing_status': raw_status,
                    'merchant_reference': clean_ref,
                    'actual_amount_kobo': actual_kobo,
                    'actual_amount_naira': str(actual_naira) if actual_naira is not None else None,
                    'transaction_reference': payload_data.get('transactionReference'),
                    'rrn': payload_data.get('rrn'),
                    'terminal_serial': payload_data.get('terminalSerial'),
                    'response_message': resp_msg,
                    'response_code': response_code,
                    'reference_mismatch': ref_mismatch,
                    'data': data,
                    'http_status': http_status,
                }
            elif http_status == 404:
                return {
                    'success': False,
                    'status': 'PENDING',
                    'processing_status': 'NOT_FOUND',
                    'merchant_reference': clean_ref,
                    'message': 'Transaction not yet found at Moniepoint gateway.',
                    'http_status': 404,
                    'data': data,
                }
            else:
                err_msg = data.get('message') if isinstance(data, dict) else f'HTTP {http_status}'
                return {
                    'success': False,
                    'status': 'FAILED',
                    'processing_status': 'GATEWAY_ERROR',
                    'merchant_reference': clean_ref,
                    'message': err_msg or 'Moniepoint POS status query failed.',
                    'http_status': http_status,
                    'data': data,
                }
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
            return {
                'success': False,
                'status': 'PENDING',  # Do not declare payment failed on transient timeout
                'processing_status': 'NETWORK_TIMEOUT',
                'merchant_reference': clean_ref,
                'message': f'Network timeout communicating with Moniepoint: {exc}',
                'error': str(exc),
            }
        except Exception as exc:
            return {
                'success': False,
                'status': 'FAILED',
                'processing_status': 'EXCEPTION',
                'merchant_reference': clean_ref,
                'message': str(exc),
                'error': str(exc),
            }


class MoniepointTerminalService:
    """
    High-level domain service for Moniepoint POS Terminal integration.
    Coordinates local Payment and Sale/Order lifecycles with gateway communication.
    """

    @classmethod
    def get_api_key(cls, override_key: str = None) -> str:
        if override_key:
            return override_key.strip()
        key = getattr(settings, 'MONIEPOINT_API_KEY', None) or os.getenv('MONIEPOINT_API_KEY', '')
        return str(key).strip()

    @classmethod
    def get_secret_key(cls, override_key: str = None) -> str:
        if override_key:
            return override_key.strip()
        key = getattr(settings, 'MONIEPOINT_SECRET_KEY', None) or os.getenv('MONIEPOINT_SECRET_KEY', '')
        return str(key).strip()

    @classmethod
    def get_client_id(cls, override_id: str = None) -> str:
        if override_id:
            return override_id.strip()
        cid = getattr(settings, 'MONIEPOINT_CLIENT_ID', None) or os.getenv('MONIEPOINT_CLIENT_ID', '')
        return str(cid).strip()

    @classmethod
    def get_client_secret(cls, override_secret: str = None) -> str:
        if override_secret:
            return override_secret.strip()
        sec = (
            getattr(settings, 'MONIEPOINT_CLIENT_SECRET', None)
            or getattr(settings, 'MONIEPOINT_SECRET_KEY', None)
            or os.getenv('MONIEPOINT_CLIENT_SECRET', '')
            or os.getenv('MONIEPOINT_SECRET_KEY', '')
        )
        return str(sec).strip()

    @classmethod
    def get_base_url(cls, override_url: str = None) -> str:
        if override_url:
            return override_url.strip().rstrip('/')
        url = getattr(settings, 'MONIEPOINT_BASE_URL', None) or os.getenv('MONIEPOINT_BASE_URL', 'https://api.pos.moniepoint.com')
        return str(url).strip().rstrip('/')

    @classmethod
    def get_terminal_id(cls, override_id: str = None) -> str:
        if override_id:
            return override_id.strip()
        term_id = getattr(settings, 'MONIEPOINT_TERMINAL_ID', None) or os.getenv('MONIEPOINT_TERMINAL_ID', '')
        return str(term_id).strip()

    @classmethod
    def get_client(cls, base_url: str = None, timeout: int = 15) -> MoniepointClient:
        return MoniepointClient(
            base_url=cls.get_base_url(base_url),
            timeout=timeout or getattr(settings, 'MONIEPOINT_TIMEOUT', 15),
        )

    @classmethod
    def push_transaction(
        cls,
        terminal_serial: str,
        amount_naira,
        merchant_reference: str,
        payment_method: str = "CARD_PURCHASE",
        api_key: str = None,
        base_url: str = None,
        timeout: int = 15,
        max_retries: int = 2,
    ) -> dict:
        """
        Pushes transaction to POS terminal (convenience delegation to MoniepointClient).
        """
        try:
            dec_amount = Decimal(str(amount_naira)).quantize(Decimal('0.01'))
        except (InvalidOperation, TypeError, ValueError):
            raise ValidationError({'amount': 'Amount must be a valid monetary value.'})

        kobo_amount = int(round(float(dec_amount) * 100))
        resolved_serial = str(terminal_serial or '').strip() or cls.get_terminal_id() or 'DEFAULT_POS_TERMINAL'

        client = cls.get_client(base_url=base_url, timeout=timeout)
        return client.push_transaction(
            terminal_serial=resolved_serial,
            amount_kobo=kobo_amount,
            merchant_reference=merchant_reference,
            payment_method=payment_method,
            api_key=api_key,
            max_retries=max_retries,
        )

    @classmethod
    def get_transaction_status(
        cls,
        merchant_reference: str,
        api_key: str = None,
        base_url: str = None,
        timeout: int = 15,
        **kwargs,
    ) -> dict:
        """
        Queries transaction status (convenience delegation to MoniepointClient).
        """
        client = cls.get_client(base_url=base_url, timeout=timeout)
        return client.get_transaction_status(
            merchant_reference=merchant_reference,
            api_key=api_key,
            **kwargs,
        )

    @classmethod
    def push_to_pos(
        cls,
        target,
        terminal_id: str = None,
        amount=None,
        cashier=None,
        customer=None,
        reference: str = None,
        description: str = None,
        payment_method: str = "CARD_PURCHASE",
        api_key: str = None,
        base_url: str = None,
        max_retries: int = 2,
        timeout: int = 15,
    ) -> dict:
        """
        Initiates a payment charge push to an in-store Moniepoint POS terminal device.
        Ensures local Payment record is persisted before calling the provider.
        """
        resolved_terminal_id = cls.get_terminal_id(terminal_id)
        if not resolved_terminal_id:
            resolved_terminal_id = 'DEFAULT_POS_TERMINAL'

        # 1. Resolve Target Transaction & Amount
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

        kobo_amount = int(round(float(dec_amount) * 100))

        # 2. Get or create associated Payment record under atomic transaction
        with transaction.atomic():
            if is_payment:
                payment = target
                if payment.payment_status == Payment.PaymentStatus.COMPLETED:
                    raise ValidationError({'payment': 'Payment is already completed.'})
            else:
                target_customer = customer or getattr(target, 'customer', None)
                target_cashier = cashier or getattr(target, 'cashier', None) or getattr(target, 'created_by', None)
                txn_ref = reference or f"POS-{uuid.uuid4().hex[:12].upper()}"
                payment_ref = f"PAY-POS-{target.pk}-{uuid.uuid4().hex[:6].upper()}"

                # Reuse existing PENDING payment for this target if present
                existing_query = Payment.objects.filter(
                    sale=target if is_sale else None,
                    order=target if not is_sale else None,
                    payment_status=Payment.PaymentStatus.PENDING,
                )
                existing_payment = existing_query.first()

                if existing_payment:
                    payment = existing_payment
                    if not payment.transaction_reference:
                        payment.transaction_reference = txn_ref
                        payment.save(update_fields=['transaction_reference', 'updated_at'])
                else:
                    payment = Payment.objects.create(
                        payment_reference=payment_ref,
                        transaction_reference=txn_ref,
                        sale=target if is_sale else None,
                        order=target if not is_sale else None,
                        customer=target_customer,
                        cashier=target_cashier,
                        amount=dec_amount,
                        payment_method=Payment.PaymentMethod.CARD,
                        payment_status=Payment.PaymentStatus.PENDING,
                        transaction_metadata={
                            'channel': 'MONIEPOINT_POS',
                            'terminal_id': resolved_terminal_id,
                            'terminal_serial': resolved_terminal_id,
                            'kobo_amount': kobo_amount,
                        },
                        notes=f'Moniepoint POS terminal charge initiated for {resolved_terminal_id}.',
                    )

        merchant_ref = payment.transaction_reference or payment.payment_reference

        # 3. Call MoniepointClient push_transaction
        client = cls.get_client(base_url=base_url, timeout=timeout)
        push_res = client.push_transaction(
            terminal_serial=resolved_terminal_id,
            amount_kobo=kobo_amount,
            merchant_reference=merchant_ref,
            payment_method=payment_method,
            api_key=api_key,
            max_retries=max_retries,
        )

        request_success = push_res['success']
        http_status = push_res['http_status']
        response_data = push_res['response']
        last_exception = push_res.get('error')

        # 4. Record metadata & Audit log
        meta = dict(payment.transaction_metadata or {})
        meta['terminal_push'] = {
            'terminal_id': resolved_terminal_id,
            'terminal_serial': resolved_terminal_id,
            'pushed_at': timezone.now().isoformat(),
            'http_status': http_status,
            'success': request_success,
            'error': last_exception,
            'response': response_data,
        }
        payment.transaction_metadata = meta
        payment.save(update_fields=['transaction_metadata', 'updated_at'])

        log_activity(
            actor=cashier,
            action_type=ActivityLog.ActionType.PAYMENT,
            action_label='Pushed charge to Moniepoint POS',
            description=f'Pushed NGN {dec_amount:,.2f} charge to Moniepoint terminal {resolved_terminal_id} (ref: {merchant_ref}).',
            related_object=payment,
            metadata={
                'payment_id': payment.id,
                'reference': merchant_ref,
                'terminal_id': resolved_terminal_id,
                'amount': str(dec_amount),
                'http_status': http_status,
                'success': request_success,
            },
        )

        return {
            'success': request_success,
            'status': 'PENDING' if request_success else 'FAILED',
            'payment_id': payment.id,
            'payment_reference': payment.payment_reference,
            'transaction_reference': payment.transaction_reference,
            'terminal_id': resolved_terminal_id,
            'terminal_serial': resolved_terminal_id,
            'amount': f'{dec_amount:.2f}',
            'kobo_amount': kobo_amount,
            'currency': 'NGN',
            'message': push_res.get('message', 'Charge pushed to POS terminal successfully.'),
            'http_status': http_status,
            'response': response_data,
            'error': last_exception,
        }

    @classmethod
    def poll_terminal_status(cls, reference: str, cashier=None, **kwargs) -> dict:
        """
        Polls the Moniepoint POS terminal status for a transaction reference.
        Guarantees idempotency and double-deduction prevention using database row locks.
        On SUCCESS:
            - Validates amount match.
            - Atomically transitions Payment to COMPLETED.
            - Atomically calls Sale.complete_sale() if Sale is in DRAFT status.
            - Confirms Order if Order is in PENDING status.
        """
        clean_ref = str(reference or '').strip()
        if not clean_ref:
            return {
                'found': False,
                'status': 'UNKNOWN',
                'is_completed': False,
                'message': 'Payment reference is required.',
            }

        # 1. Row-lock Payment to serialize state transitions
        with transaction.atomic():
            payment = Payment.objects.select_for_update().filter(
                transaction_reference=clean_ref
            ).first() or Payment.objects.select_for_update().filter(
                payment_reference=clean_ref
            ).first()

            if not payment:
                try:
                    payment = Payment.objects.select_for_update().get(pk=int(clean_ref))
                except (Payment.DoesNotExist, ValueError, TypeError):
                    payment = None

            if not payment:
                return {
                    'found': False,
                    'status': 'UNKNOWN',
                    'is_completed': False,
                    'message': f'Payment reference "{clean_ref}" not found.',
                }

            # If ALREADY COMPLETED: return immediate success response without duplicate operations
            if payment.payment_status == Payment.PaymentStatus.COMPLETED:
                sale_id = payment.sale_id
                order_id = payment.order_id

                # Ensure draft sale is finalized if previously interrupted
                if payment.sale_id:
                    try:
                        sale = Sale.objects.select_for_update().get(pk=payment.sale_id)
                        if sale.status == Sale.SaleStatus.DRAFT:
                            if sale.amount_received is None:
                                sale.amount_received = payment.amount
                            if sale.change_amount is None:
                                sale.change_amount = Decimal('0.00')
                            sale.complete_sale()
                    except Exception as exc:
                        logger.warning(f"Error finalizing draft sale for completed payment {payment.id}: {exc}")

                return {
                    'found': True,
                    'success': True,
                    'payment_id': payment.id,
                    'payment_reference': payment.payment_reference,
                    'transaction_reference': payment.transaction_reference,
                    'status': 'SUCCESS',
                    'payment_status': Payment.PaymentStatus.COMPLETED,
                    'is_completed': True,
                    'is_verified': True,
                    'amount': f'{payment.amount:.2f}',
                    'sale_id': sale_id,
                    'order_id': order_id,
                    'message': 'Payment completed.',
                }

            # If FAILED or CANCELLED, do not revert to PENDING
            if payment.payment_status in (Payment.PaymentStatus.FAILED, Payment.PaymentStatus.REFUNDED):
                return {
                    'found': True,
                    'success': False,
                    'payment_id': payment.id,
                    'payment_reference': payment.payment_reference,
                    'transaction_reference': payment.transaction_reference,
                    'status': payment.payment_status,
                    'payment_status': payment.payment_status,
                    'is_completed': False,
                    'is_verified': False,
                    'amount': f'{payment.amount:.2f}',
                    'sale_id': payment.sale_id,
                    'order_id': payment.order_id,
                    'message': f'Payment is {payment.payment_status}.',
                }

        # 2. Query gateway transaction status
        ref_to_query = payment.transaction_reference or payment.payment_reference
        client = cls.get_client(base_url=kwargs.get('base_url'), timeout=kwargs.get('timeout'))
        status_info = client.get_transaction_status(
            ref_to_query,
            expected_amount=payment.amount,
            **kwargs,
        )
        norm_status = status_info.get('status', 'PENDING')

        # 3. Handle SUCCESS outcome
        if norm_status == 'SUCCESS':
            # Amount verification guard: verify charged amount matches recorded amount
            actual_naira_str = status_info.get('actual_amount_naira')
            if actual_naira_str is not None:
                try:
                    actual_naira = Decimal(str(actual_naira_str)).quantize(Decimal('0.01'))
                    if actual_naira != payment.amount:
                        meta = dict(payment.transaction_metadata or {})
                        meta['discrepancy'] = f"Amount mismatch: expected {payment.amount}, gateway returned {actual_naira}."
                        payment.transaction_metadata = meta
                        payment.save(update_fields=['transaction_metadata', 'updated_at'])
                        return {
                            'found': True,
                            'success': False,
                            'status': 'MISMATCH',
                            'payment_id': payment.id,
                            'payment_reference': payment.payment_reference,
                            'transaction_reference': payment.transaction_reference,
                            'amount': f'{payment.amount:.2f}',
                            'actual_amount': str(actual_naira),
                            'message': f"Amount mismatch: expected {payment.amount}, received {actual_naira}.",
                        }
                except Exception:
                    pass

            with transaction.atomic():
                # Re-fetch under lock to prevent race conditions
                locked_payment = Payment.objects.select_for_update().get(pk=payment.pk)
                if locked_payment.payment_status == Payment.PaymentStatus.COMPLETED:
                    return {
                        'found': True,
                        'success': True,
                        'payment_id': locked_payment.id,
                        'payment_reference': locked_payment.payment_reference,
                        'transaction_reference': locked_payment.transaction_reference,
                        'status': 'SUCCESS',
                        'payment_status': Payment.PaymentStatus.COMPLETED,
                        'is_completed': True,
                        'is_verified': True,
                        'amount': f'{locked_payment.amount:.2f}',
                        'sale_id': locked_payment.sale_id,
                        'order_id': locked_payment.order_id,
                        'message': 'Payment completed.',
                    }

                locked_payment.payment_status = Payment.PaymentStatus.COMPLETED
                meta = dict(locked_payment.transaction_metadata or {})
                meta['terminal_status_result'] = status_info
                meta['completed_at'] = timezone.now().isoformat()
                locked_payment.transaction_metadata = meta
                locked_payment.save(update_fields=['payment_status', 'transaction_metadata', 'updated_at'])

                # Complete sale and deduct inventory exactly once
                if locked_payment.sale_id:
                    try:
                        sale = Sale.objects.select_for_update().get(pk=locked_payment.sale_id)
                        if sale.status == Sale.SaleStatus.DRAFT:
                            if sale.amount_received is None:
                                sale.amount_received = locked_payment.amount
                            if sale.change_amount is None:
                                sale.change_amount = Decimal('0.00')
                            sale.complete_sale()
                        elif sale.payment_status != Sale.PaymentStatus.COMPLETED:
                            sale.payment_status = Sale.PaymentStatus.COMPLETED
                            sale.save(update_fields=['payment_status', 'updated_at'])
                    except Exception as exc:
                        logger.error(f"Error completing sale {locked_payment.sale_id} on POS confirmation: {exc}")

                # Confirm order if applicable
                if locked_payment.order_id:
                    try:
                        order = Order.objects.select_for_update().get(pk=locked_payment.order_id)
                        if order.status == Order.OrderStatus.PENDING:
                            order.status = Order.OrderStatus.CONFIRMED
                            order.payment_status = Order.PaymentStatus.PAID
                            order.save(update_fields=['status', 'payment_status', 'updated_at'])
                    except Exception as exc:
                        logger.error(f"Error confirming order {locked_payment.order_id} on POS confirmation: {exc}")

                log_activity(
                    actor=cashier,
                    action_type=ActivityLog.ActionType.PAYMENT,
                    action_label='Moniepoint POS Payment Confirmed',
                    description=f'Payment {locked_payment.payment_reference} confirmed successfully via Moniepoint POS.',
                    related_object=locked_payment,
                    metadata={
                        'payment_id': locked_payment.id,
                        'reference': ref_to_query,
                        'amount': str(locked_payment.amount),
                        'terminal_serial': status_info.get('terminal_serial'),
                        'rrn': status_info.get('rrn'),
                    },
                )

            return {
                'found': True,
                'success': True,
                'payment_id': locked_payment.id,
                'payment_reference': locked_payment.payment_reference,
                'transaction_reference': locked_payment.transaction_reference,
                'status': 'SUCCESS',
                'payment_status': Payment.PaymentStatus.COMPLETED,
                'is_completed': True,
                'is_verified': True,
                'amount': f'{locked_payment.amount:.2f}',
                'sale_id': locked_payment.sale_id,
                'order_id': locked_payment.order_id,
                'details': status_info,
                'message': 'Payment confirmed successfully via Moniepoint POS.',
            }

        # 4. Handle FAILED outcome
        if norm_status == 'FAILED':
            with transaction.atomic():
                locked_payment = Payment.objects.select_for_update().get(pk=payment.pk)
                if locked_payment.payment_status != Payment.PaymentStatus.COMPLETED:
                    locked_payment.payment_status = Payment.PaymentStatus.FAILED
                    meta = dict(locked_payment.transaction_metadata or {})
                    meta['terminal_failure_result'] = status_info
                    locked_payment.transaction_metadata = meta
                    locked_payment.save(update_fields=['payment_status', 'transaction_metadata', 'updated_at'])

            return {
                'found': True,
                'success': False,
                'payment_id': payment.id,
                'payment_reference': payment.payment_reference,
                'transaction_reference': payment.transaction_reference,
                'status': 'FAILED',
                'payment_status': Payment.PaymentStatus.FAILED,
                'is_completed': False,
                'is_verified': False,
                'amount': f'{payment.amount:.2f}',
                'sale_id': payment.sale_id,
                'order_id': payment.order_id,
                'details': status_info,
                'message': status_info.get('response_message') or 'Transaction failed on POS terminal.',
            }

        # 5. Handle PENDING / IN_PROGRESS outcome
        return {
            'found': True,
            'success': False,
            'payment_id': payment.id,
            'payment_reference': payment.payment_reference,
            'transaction_reference': payment.transaction_reference,
            'status': 'PENDING',
            'payment_status': payment.payment_status,
            'is_completed': False,
            'is_verified': False,
            'amount': f'{payment.amount:.2f}',
            'sale_id': payment.sale_id,
            'order_id': payment.order_id,
            'details': status_info,
            'message': status_info.get('message') or 'Waiting for customer card or PIN on terminal...',
        }
