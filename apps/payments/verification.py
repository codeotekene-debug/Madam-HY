import json
import os
import socket
import urllib.error
import urllib.parse
import urllib.request
import uuid
from decimal import Decimal, InvalidOperation
from enum import Enum
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import Payment


class PaymentVerificationStatus(str, Enum):
    VERIFIED = 'VERIFIED'
    FAILED = 'FAILED'
    PENDING = 'PENDING'
    UNKNOWN = 'UNKNOWN'
    MISMATCH = 'MISMATCH'


class PaymentVerificationResult:
    """Standardized result of a payment verification evaluation."""

    def __init__(
        self,
        status,
        verified_amount=None,
        provider_reference='',
        payment_reference='',
        payment_id=None,
        provider='mock',
        discrepancies=None,
        metadata=None,
        verified_at=None,
    ):
        self.status = str(status)
        self.verified_amount = Decimal(str(verified_amount)) if verified_amount is not None else None
        self.provider_reference = str(provider_reference or '')
        self.payment_reference = str(payment_reference or '')
        self.payment_id = payment_id
        self.provider = str(provider)
        self.discrepancies = list(discrepancies or [])
        self.metadata = dict(metadata or {})
        self.verified_at = verified_at or timezone.now()

    @property
    def is_verified(self):
        return self.status == PaymentVerificationStatus.VERIFIED.value

    @property
    def has_discrepancy(self):
        return bool(self.discrepancies or self.status == PaymentVerificationStatus.MISMATCH.value)

    def to_dict(self):
        return {
            'status': self.status,
            'verified_amount': str(self.verified_amount) if self.verified_amount is not None else None,
            'provider_reference': self.provider_reference,
            'payment_reference': self.payment_reference,
            'payment_id': self.payment_id,
            'provider': self.provider,
            'discrepancies': self.discrepancies,
            'discrepancy_detected': self.has_discrepancy,
            'verification_timestamp': self.verified_at.isoformat() if hasattr(self.verified_at, 'isoformat') else str(self.verified_at),
            'metadata': self.metadata,
        }

    def __repr__(self):
        return f'<PaymentVerificationResult status={self.status} ref={self.payment_reference} amount={self.verified_amount}>'


class BasePaymentVerifier:
    """Abstract base class for payment verification providers."""

    provider_name = 'base'

    def verify(self, payment, **kwargs) -> PaymentVerificationResult:
        raise NotImplementedError('Subclasses must implement verify()')


class MockPaymentVerifier(BasePaymentVerifier):
    """Default internal/mock payment verifier that inspects payment records, references,

    amounts, and metadata without external network calls.
    """

    provider_name = 'mock'

    def verify(self, payment, **kwargs) -> PaymentVerificationResult:
        if not isinstance(payment, Payment) or payment.pk is None:
            raise ValidationError({'payment': 'A valid saved Payment instance is required for verification.'})

        discrepancies = []
        metadata = {
            'method': payment.payment_method,
            'local_status': payment.payment_status,
            **getattr(payment, 'transaction_metadata', {}),
        }

        # Determine reference
        provider_reference = payment.transaction_reference or payment.payment_reference
        verified_amount = payment.amount

        # Check non-positive amount
        if payment.amount is None or payment.amount <= 0:
            discrepancies.append('Payment amount must be greater than zero.')
            return PaymentVerificationResult(
                status=PaymentVerificationStatus.FAILED.value,
                verified_amount=Decimal('0.00'),
                provider_reference=provider_reference,
                payment_reference=payment.payment_reference,
                payment_id=payment.id,
                provider=self.provider_name,
                discrepancies=discrepancies,
                metadata=metadata,
            )

        # 1. Inspect explicit simulation flags in transaction_metadata if present
        mock_meta = payment.transaction_metadata or {}
        if 'mock_verified_amount' in mock_meta:
            try:
                verified_amount = Decimal(str(mock_meta['mock_verified_amount']))
            except (InvalidOperation, TypeError, ValueError):
                discrepancies.append('Invalid mock verified amount format.')
            if verified_amount != payment.amount:
                discrepancies.append(
                    f'Amount mismatch: recorded amount ({payment.amount}) does not match provider verified amount ({verified_amount}).'
                )

        if 'mock_reference' in mock_meta:
            mock_ref = str(mock_meta['mock_reference'])
            provider_reference = mock_ref
            if mock_ref != (payment.transaction_reference or payment.payment_reference):
                discrepancies.append(
                    f'Reference mismatch: recorded reference does not match provider reference ({mock_ref}).'
                )

        if 'currency' in mock_meta and mock_meta['currency'] != 'NGN':
            discrepancies.append(f"Currency mismatch: unexpected currency '{mock_meta['currency']}' (expected 'NGN').")

        # 2. Inspect kwargs overrides (e.g. expected_amount, expected_reference)
        if 'expected_amount' in kwargs and kwargs['expected_amount'] is not None:
            try:
                exp_amt = Decimal(str(kwargs['expected_amount']))
                if exp_amt != payment.amount:
                    discrepancies.append(
                        f'Amount mismatch: recorded amount ({payment.amount}) does not match expected amount ({exp_amt}).'
                    )
            except (InvalidOperation, TypeError, ValueError):
                discrepancies.append('Invalid expected amount format.')

        if 'expected_reference' in kwargs and kwargs['expected_reference']:
            exp_ref = str(kwargs['expected_reference']).strip()
            if exp_ref != payment.transaction_reference and exp_ref != payment.payment_reference:
                discrepancies.append(
                    f'Reference mismatch: recorded reference does not match expected reference ({exp_ref}).'
                )

        # 3. Determine status
        if 'mock_status' in mock_meta:
            status = str(mock_meta['mock_status']).upper()
            if status not in [s.value for s in PaymentVerificationStatus]:
                status = PaymentVerificationStatus.UNKNOWN.value
            if status in (PaymentVerificationStatus.FAILED.value, PaymentVerificationStatus.MISMATCH.value) and not discrepancies:
                discrepancies.append(f'Simulated verification status: {status}.')
        elif discrepancies:
            status = PaymentVerificationStatus.MISMATCH.value
        elif payment.payment_status == Payment.PaymentStatus.COMPLETED:
            status = PaymentVerificationStatus.VERIFIED.value
        elif payment.payment_status == Payment.PaymentStatus.PENDING:
            status = PaymentVerificationStatus.PENDING.value
        elif payment.payment_status == Payment.PaymentStatus.FAILED:
            status = PaymentVerificationStatus.FAILED.value
            discrepancies.append('Payment record has FAILED status.')
        elif payment.payment_status == Payment.PaymentStatus.REFUNDED:
            status = PaymentVerificationStatus.MISMATCH.value
            discrepancies.append('Payment record has REFUNDED status.')
        else:
            status = PaymentVerificationStatus.UNKNOWN.value

        return PaymentVerificationResult(
            status=status,
            verified_amount=verified_amount,
            provider_reference=provider_reference,
            payment_reference=payment.payment_reference,
            payment_id=payment.id,
            provider=self.provider_name,
            discrepancies=discrepancies,
            metadata=metadata,
        )


class InternalPaymentVerifier(MockPaymentVerifier):
    """Internal provider verifier alias."""

    provider_name = 'internal'


class PaystackPaymentVerifier(BasePaymentVerifier):
    """
    Official Paystack verification adapter (Phase 4A).
    Queries Paystack's transaction verification endpoint:
        GET https://api.paystack.co/transaction/verify/{reference}
    Authenticates via Bearer secret key from environment or settings.
    Converts kobo amounts to Naira (Decimal(kobo) / 100).
    Maps Paystack gateway statuses ('success', 'failed', 'abandoned', 'pending')
    to PaymentVerificationStatus.
    Detects discrepancies in amounts, currencies, and references.
    Handles network timeouts and errors gracefully returning UNKNOWN status.
    Maintains strict read-only guarantees on database records.
    """

    provider_name = 'paystack'

    def __init__(self, secret_key=None, base_url=None):
        self._secret_key = secret_key
        self._base_url = base_url

    def get_secret_key(self) -> str:
        if self._secret_key:
            return self._secret_key.strip()
        key = getattr(settings, 'PAYSTACK_SECRET_KEY', None) or os.getenv('PAYSTACK_SECRET_KEY', '')
        return str(key).strip()

    def get_base_url(self) -> str:
        if self._base_url:
            return self._base_url.strip().rstrip('/')
        url = getattr(settings, 'PAYSTACK_BASE_URL', None) or os.getenv('PAYSTACK_BASE_URL', 'https://api.paystack.co')
        return str(url).strip().rstrip('/')

    def _execute_http_request(self, url: str, secret_key: str, timeout: int = 15):
        """Helper to execute the HTTP request to Paystack API using standard urllib.request."""
        req = urllib.request.Request(
            url,
            headers={
                'Authorization': f'Bearer {secret_key}',
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'User-Agent': 'SmartShop-PaystackVerifier/1.0',
            },
            method='GET',
        )
        with urllib.request.urlopen(req, timeout=timeout) as response:
            status_code = response.getcode()
            body = response.read().decode('utf-8')
            return status_code, body

    def verify(self, payment, **kwargs) -> PaymentVerificationResult:
        if not isinstance(payment, Payment) or payment.pk is None:
            raise ValidationError({'payment': 'A valid saved Payment instance is required for verification.'})

        discrepancies = []
        secret_key = kwargs.get('secret_key') or self.get_secret_key()
        base_url = kwargs.get('base_url') or self.get_base_url()
        timeout = int(kwargs.get('timeout', 15))

        if 'reference' in kwargs and kwargs['reference'] is not None:
            target_reference = kwargs['reference']
        else:
            target_reference = payment.transaction_reference or payment.payment_reference

        if not target_reference or not str(target_reference).strip():
            discrepancies.append('No payment or transaction reference provided on payment for Paystack verification.')
            return PaymentVerificationResult(
                status=PaymentVerificationStatus.FAILED.value,
                verified_amount=Decimal('0.00'),
                provider_reference='',
                payment_reference=payment.payment_reference,
                payment_id=payment.id,
                provider=self.provider_name,
                discrepancies=discrepancies,
                metadata={'provider': self.provider_name, 'error': 'missing_reference'},
            )

        target_reference = str(target_reference).strip()

        if not secret_key:
            discrepancies.append('Paystack secret key is not configured in environment (PAYSTACK_SECRET_KEY).')
            return PaymentVerificationResult(
                status=PaymentVerificationStatus.UNKNOWN.value,
                verified_amount=None,
                provider_reference=target_reference,
                payment_reference=payment.payment_reference,
                payment_id=payment.id,
                provider=self.provider_name,
                discrepancies=discrepancies,
                metadata={'provider': self.provider_name, 'error': 'missing_api_key'},
            )

        encoded_ref = urllib.parse.quote(target_reference)
        url = f'{base_url}/transaction/verify/{encoded_ref}'

        try:
            status_code, response_body = self._execute_http_request(url, secret_key, timeout=timeout)
            parsed_json = json.loads(response_body)
        except urllib.error.HTTPError as exc:
            err_body = ''
            try:
                err_body = exc.read().decode('utf-8')
                err_json = json.loads(err_body)
                err_msg = err_json.get('message', exc.reason)
            except Exception:
                err_msg = str(exc.reason)

            if exc.code == 404:
                discrepancies.append(f'Transaction reference not found on Paystack (HTTP 404): {err_msg}')
                status = PaymentVerificationStatus.FAILED.value
            elif exc.code in (401, 403):
                discrepancies.append(f'Paystack authentication failed (HTTP {exc.code}): {err_msg}. Verify PAYSTACK_SECRET_KEY.')
                status = PaymentVerificationStatus.UNKNOWN.value
            else:
                discrepancies.append(f'Paystack API returned HTTP {exc.code}: {err_msg}')
                status = PaymentVerificationStatus.UNKNOWN.value

            return PaymentVerificationResult(
                status=status,
                verified_amount=None,
                provider_reference=target_reference,
                payment_reference=payment.payment_reference,
                payment_id=payment.id,
                provider=self.provider_name,
                discrepancies=discrepancies,
                metadata={'provider': self.provider_name, 'http_status': exc.code, 'error_response': err_body[:500]},
            )
        except (urllib.error.URLError, socket.timeout, TimeoutError) as exc:
            discrepancies.append(f'Network timeout or connection error contacting Paystack API: {exc}')
            return PaymentVerificationResult(
                status=PaymentVerificationStatus.UNKNOWN.value,
                verified_amount=None,
                provider_reference=target_reference,
                payment_reference=payment.payment_reference,
                payment_id=payment.id,
                provider=self.provider_name,
                discrepancies=discrepancies,
                metadata={'provider': self.provider_name, 'error': 'network_timeout', 'exception': str(exc)},
            )
        except json.JSONDecodeError as exc:
            discrepancies.append(f'Invalid JSON response received from Paystack API: {exc}')
            return PaymentVerificationResult(
                status=PaymentVerificationStatus.UNKNOWN.value,
                verified_amount=None,
                provider_reference=target_reference,
                payment_reference=payment.payment_reference,
                payment_id=payment.id,
                provider=self.provider_name,
                discrepancies=discrepancies,
                metadata={'provider': self.provider_name, 'error': 'invalid_json'},
            )
        except Exception as exc:
            discrepancies.append(f'Unexpected error during Paystack verification: {exc}')
            return PaymentVerificationResult(
                status=PaymentVerificationStatus.UNKNOWN.value,
                verified_amount=None,
                provider_reference=target_reference,
                payment_reference=payment.payment_reference,
                payment_id=payment.id,
                provider=self.provider_name,
                discrepancies=discrepancies,
                metadata={'provider': self.provider_name, 'error': 'unexpected_exception', 'exception': str(exc)},
            )

        api_status = parsed_json.get('status')
        api_message = parsed_json.get('message', '')
        data = parsed_json.get('data') or {}

        if not api_status:
            discrepancies.append(f'Paystack reported verification unsuccessful: {api_message}')
            return PaymentVerificationResult(
                status=PaymentVerificationStatus.FAILED.value,
                verified_amount=None,
                provider_reference=target_reference,
                payment_reference=payment.payment_reference,
                payment_id=payment.id,
                provider=self.provider_name,
                discrepancies=discrepancies,
                metadata={'provider': self.provider_name, 'api_status': False, 'message': api_message},
            )

        paystack_status = str(data.get('status', '')).strip().lower()
        paystack_ref = str(data.get('reference', '')).strip() or target_reference
        raw_kobo = data.get('amount')
        paystack_currency = str(data.get('currency', 'NGN')).strip().upper()
        gateway_response = data.get('gateway_response', '')
        channel = data.get('channel', '')
        paid_at = data.get('paid_at')
        fees_kobo = data.get('fees')
        customer_data = data.get('customer') or {}

        verified_amount = None
        if raw_kobo is not None:
            try:
                verified_amount = (Decimal(str(raw_kobo)) / Decimal('100')).quantize(Decimal('0.01'))
            except (InvalidOperation, TypeError, ValueError):
                discrepancies.append(f'Invalid amount value returned by Paystack: {raw_kobo}')
        else:
            discrepancies.append('No amount returned by Paystack API.')

        fees_naira = None
        if fees_kobo is not None:
            try:
                fees_naira = (Decimal(str(fees_kobo)) / Decimal('100')).quantize(Decimal('0.01'))
            except Exception:
                pass

        metadata = {
            'provider': self.provider_name,
            'gateway_status': paystack_status,
            'gateway_response': gateway_response,
            'channel': channel,
            'paid_at': paid_at,
            'currency': paystack_currency,
            'fees_naira': str(fees_naira) if fees_naira is not None else None,
            'customer_email': customer_data.get('email'),
            'paystack_id': data.get('id'),
        }

        # Check currency
        if paystack_currency != 'NGN':
            discrepancies.append(f"Currency mismatch: expected 'NGN', Paystack returned '{paystack_currency}'.")

        # Check reference matching
        if payment.transaction_reference and paystack_ref != payment.transaction_reference:
            discrepancies.append(
                f"Reference mismatch: recorded transaction reference ({payment.transaction_reference}) does not match Paystack reference ({paystack_ref})."
            )

        # Check amount matching
        if verified_amount is not None and payment.amount is not None:
            if verified_amount != payment.amount:
                discrepancies.append(
                    f"Amount mismatch: recorded amount ({payment.amount}) does not match Paystack verified amount ({verified_amount})."
                )

        # Check kwargs expected_amount
        if 'expected_amount' in kwargs and kwargs['expected_amount'] is not None:
            try:
                exp_amt = Decimal(str(kwargs['expected_amount'])).quantize(Decimal('0.01'))
                if verified_amount != exp_amt:
                    discrepancies.append(
                        f"Expected amount mismatch: expected {exp_amt}, Paystack verified {verified_amount}."
                    )
            except (InvalidOperation, TypeError, ValueError):
                discrepancies.append('Invalid expected_amount format.')

        # Check kwargs expected_reference
        if 'expected_reference' in kwargs and kwargs['expected_reference']:
            exp_ref = str(kwargs['expected_reference']).strip()
            if paystack_ref != exp_ref:
                discrepancies.append(
                    f"Expected reference mismatch: expected {exp_ref}, Paystack returned {paystack_ref}."
                )

        # Determine overall verification status
        if paystack_status == 'success':
            if discrepancies:
                status = PaymentVerificationStatus.MISMATCH.value
            else:
                status = PaymentVerificationStatus.VERIFIED.value
        elif paystack_status == 'failed':
            status = PaymentVerificationStatus.FAILED.value
            discrepancies.append(f"Paystack reported transaction failure: {gateway_response or 'Payment failed'}.")
        elif paystack_status == 'abandoned':
            status = PaymentVerificationStatus.FAILED.value
            discrepancies.append('Paystack reported transaction abandoned by customer.')
        elif paystack_status in ('pending', 'processing', 'ongoing'):
            status = PaymentVerificationStatus.PENDING.value
        else:
            status = PaymentVerificationStatus.UNKNOWN.value
            discrepancies.append(f"Unknown Paystack status: '{paystack_status}'.")

        return PaymentVerificationResult(
            status=status,
            verified_amount=verified_amount,
            provider_reference=paystack_ref,
            payment_reference=payment.payment_reference,
            payment_id=payment.id,
            provider=self.provider_name,
            discrepancies=discrepancies,
            metadata=metadata,
        )


class MoniepointPaymentVerifier(BasePaymentVerifier):
    """
    Official Moniepoint POS terminal verification adapter (Phase 4B).
    Queries Moniepoint's POS transaction query endpoint:
        GET https://api.pos.moniepoint.com/v1/transactions/merchants/{merchantReference}
    Authenticates via Bearer API key from environment (MONIEPOINT_API_KEY) or settings.
    Extracts and validates POS terminal attributes:
        terminalSerial, rrn, transactionReference, actualAmount, processingStatus.
    Maps Moniepoint processing statuses ('SUCCESSFUL', 'APPROVED', 'FAILED', 'DECLINED', 'PENDING')
    to standardized PaymentVerificationStatus.
    Detects discrepancies in charged amounts, terminal serials, RRNs, references, and currencies.
    Handles network timeouts and errors gracefully returning UNKNOWN status.
    Maintains strict read-only guarantees on database records.
    """

    provider_name = 'moniepoint'

    def __init__(self, api_key=None, secret_key=None, base_url=None):
        self._api_key = api_key
        self._secret_key = secret_key
        self._base_url = base_url

    def get_api_key(self) -> str:
        if self._api_key:
            return self._api_key.strip()
        key = getattr(settings, 'MONIEPOINT_API_KEY', None) or os.getenv('MONIEPOINT_API_KEY', '')
        return str(key).strip()

    def get_secret_key(self) -> str:
        if self._secret_key:
            return self._secret_key.strip()
        key = getattr(settings, 'MONIEPOINT_SECRET_KEY', None) or os.getenv('MONIEPOINT_SECRET_KEY', '')
        return str(key).strip()

    def get_base_url(self) -> str:
        if self._base_url:
            return self._base_url.strip().rstrip('/')
        url = getattr(settings, 'MONIEPOINT_BASE_URL', None) or os.getenv('MONIEPOINT_BASE_URL', 'https://api.pos.moniepoint.com')
        return str(url).strip().rstrip('/')

    def _execute_http_request(self, url: str, api_key: str, timeout: int = 15):
        """Helper to execute the HTTP request to Moniepoint POS API using urllib.request."""
        req = urllib.request.Request(
            url,
            headers={
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'User-Agent': 'SmartShop-MoniepointVerifier/1.0',
            },
            method='GET',
        )
        with urllib.request.urlopen(req, timeout=timeout) as response:
            status_code = response.getcode()
            body = response.read().decode('utf-8')
            return status_code, body

    def verify(self, payment, **kwargs) -> PaymentVerificationResult:
        if not isinstance(payment, Payment) or payment.pk is None:
            raise ValidationError({'payment': 'A valid saved Payment instance is required for verification.'})

        discrepancies = []
        api_key = kwargs.get('api_key') or self.get_api_key()
        base_url = kwargs.get('base_url') or self.get_base_url()
        timeout = int(kwargs.get('timeout', 15))

        if 'reference' in kwargs and kwargs['reference'] is not None:
            target_reference = kwargs['reference']
        elif 'merchant_reference' in kwargs and kwargs['merchant_reference'] is not None:
            target_reference = kwargs['merchant_reference']
        else:
            target_reference = payment.transaction_reference or payment.payment_reference

        if not target_reference or not str(target_reference).strip():
            discrepancies.append('No merchant reference or transaction reference provided on payment for Moniepoint verification.')
            return PaymentVerificationResult(
                status=PaymentVerificationStatus.FAILED.value,
                verified_amount=Decimal('0.00'),
                provider_reference='',
                payment_reference=payment.payment_reference,
                payment_id=payment.id,
                provider=self.provider_name,
                discrepancies=discrepancies,
                metadata={'provider': self.provider_name, 'error': 'missing_reference'},
            )

        target_reference = str(target_reference).strip()

        if not api_key:
            discrepancies.append('Moniepoint API key is not configured in environment (MONIEPOINT_API_KEY).')
            return PaymentVerificationResult(
                status=PaymentVerificationStatus.UNKNOWN.value,
                verified_amount=None,
                provider_reference=target_reference,
                payment_reference=payment.payment_reference,
                payment_id=payment.id,
                provider=self.provider_name,
                discrepancies=discrepancies,
                metadata={'provider': self.provider_name, 'error': 'missing_api_key'},
            )

        encoded_ref = urllib.parse.quote(target_reference)
        url = f'{base_url}/v1/transactions/merchants/{encoded_ref}'

        try:
            status_code, response_body = self._execute_http_request(url, api_key, timeout=timeout)
            parsed_json = json.loads(response_body)
        except urllib.error.HTTPError as exc:
            err_body = ''
            try:
                err_body = exc.read().decode('utf-8')
                err_json = json.loads(err_body)
                err_msg = err_json.get('message') or err_json.get('responseMessage', exc.reason)
            except Exception:
                err_msg = str(exc.reason)

            if exc.code == 404:
                discrepancies.append(f'Transaction reference not found on Moniepoint POS (HTTP 404): {err_msg}')
                status = PaymentVerificationStatus.FAILED.value
            elif exc.code in (401, 403):
                discrepancies.append(f'Moniepoint authentication failed (HTTP {exc.code}): {err_msg}. Verify MONIEPOINT_API_KEY.')
                status = PaymentVerificationStatus.UNKNOWN.value
            else:
                discrepancies.append(f'Moniepoint POS API returned HTTP {exc.code}: {err_msg}')
                status = PaymentVerificationStatus.UNKNOWN.value

            return PaymentVerificationResult(
                status=status,
                verified_amount=None,
                provider_reference=target_reference,
                payment_reference=payment.payment_reference,
                payment_id=payment.id,
                provider=self.provider_name,
                discrepancies=discrepancies,
                metadata={'provider': self.provider_name, 'http_status': exc.code, 'error_response': err_body[:500]},
            )
        except (urllib.error.URLError, socket.timeout, TimeoutError) as exc:
            discrepancies.append(f'Network timeout or connection error contacting Moniepoint POS API: {exc}')
            return PaymentVerificationResult(
                status=PaymentVerificationStatus.UNKNOWN.value,
                verified_amount=None,
                provider_reference=target_reference,
                payment_reference=payment.payment_reference,
                payment_id=payment.id,
                provider=self.provider_name,
                discrepancies=discrepancies,
                metadata={'provider': self.provider_name, 'error': 'network_timeout', 'exception': str(exc)},
            )
        except json.JSONDecodeError as exc:
            discrepancies.append(f'Invalid JSON response received from Moniepoint POS API: {exc}')
            return PaymentVerificationResult(
                status=PaymentVerificationStatus.UNKNOWN.value,
                verified_amount=None,
                provider_reference=target_reference,
                payment_reference=payment.payment_reference,
                payment_id=payment.id,
                provider=self.provider_name,
                discrepancies=discrepancies,
                metadata={'provider': self.provider_name, 'error': 'invalid_json'},
            )
        except Exception as exc:
            discrepancies.append(f'Unexpected error during Moniepoint verification: {exc}')
            return PaymentVerificationResult(
                status=PaymentVerificationStatus.UNKNOWN.value,
                verified_amount=None,
                provider_reference=target_reference,
                payment_reference=payment.payment_reference,
                payment_id=payment.id,
                provider=self.provider_name,
                discrepancies=discrepancies,
                metadata={'provider': self.provider_name, 'error': 'unexpected_exception', 'exception': str(exc)},
            )

        data = parsed_json.get('data') if isinstance(parsed_json.get('data'), dict) else parsed_json

        # Validate top-level response code if present
        resp_code = parsed_json.get('responseCode')
        if resp_code not in (None, '00', '0', 0, 200) and parsed_json.get('status') is False:
            resp_msg = parsed_json.get('responseMessage') or parsed_json.get('message', 'Terminal verification failed')
            discrepancies.append(f'Moniepoint reported terminal verification failure: {resp_msg}')
            return PaymentVerificationResult(
                status=PaymentVerificationStatus.FAILED.value,
                verified_amount=None,
                provider_reference=target_reference,
                payment_reference=payment.payment_reference,
                payment_id=payment.id,
                provider=self.provider_name,
                discrepancies=discrepancies,
                metadata={'provider': self.provider_name, 'responseCode': resp_code, 'message': resp_msg},
            )

        terminal_serial = data.get('terminalSerial') or data.get('terminal_serial') or data.get('terminalId')
        rrn = data.get('rrn') or data.get('retrievalReferenceNumber')
        provider_txn_ref = data.get('transactionReference') or data.get('transaction_reference') or target_reference
        merchant_ref = data.get('merchantReference') or data.get('merchant_reference')
        raw_amount = data.get('actualAmount') if data.get('actualAmount') is not None else data.get('amount')
        pos_currency = str(data.get('currency', 'NGN')).strip().upper()
        processing_status = str(data.get('processingStatus') or data.get('status') or data.get('transactionStatus') or '').strip().upper()
        payment_method = data.get('paymentMethod') or data.get('channel') or 'CARD'
        transaction_time = data.get('transactionTime') or data.get('transaction_time') or data.get('paid_at')

        verified_amount = None
        if raw_amount is not None:
            try:
                verified_amount = Decimal(str(raw_amount)).quantize(Decimal('0.01'))
            except (InvalidOperation, TypeError, ValueError):
                discrepancies.append(f'Invalid amount value returned by Moniepoint: {raw_amount}')
        else:
            discrepancies.append('No amount returned by Moniepoint POS API.')

        # Currency mismatch check
        if pos_currency != 'NGN':
            discrepancies.append(f"Currency mismatch: expected 'NGN', Moniepoint POS returned '{pos_currency}'.")

        # Amount mismatch check
        if verified_amount is not None and payment.amount is not None:
            if verified_amount != payment.amount:
                # Minor unit (kobo) conversion fallback
                if (verified_amount / Decimal('100')).quantize(Decimal('0.01')) == payment.amount:
                    verified_amount = (verified_amount / Decimal('100')).quantize(Decimal('0.01'))
                else:
                    discrepancies.append(
                        f"Amount mismatch: recorded amount ({payment.amount}) does not match Moniepoint POS charged amount ({verified_amount})."
                    )

        # Expected amount override check
        if 'expected_amount' in kwargs and kwargs['expected_amount'] is not None:
            try:
                exp_amt = Decimal(str(kwargs['expected_amount'])).quantize(Decimal('0.01'))
                if verified_amount != exp_amt:
                    discrepancies.append(
                        f"Expected amount mismatch: expected {exp_amt}, Moniepoint POS verified {verified_amount}."
                    )
            except (InvalidOperation, TypeError, ValueError):
                discrepancies.append('Invalid expected_amount format.')

        # Terminal serial mismatch check
        expected_terminal = (
            kwargs.get('terminal_serial')
            or kwargs.get('terminalSerial')
            or (payment.transaction_metadata or {}).get('terminal_serial')
            or (payment.transaction_metadata or {}).get('terminalSerial')
        )
        if expected_terminal:
            if terminal_serial and str(terminal_serial).strip() != str(expected_terminal).strip():
                discrepancies.append(
                    f"Terminal serial mismatch: expected terminal '{expected_terminal}', Moniepoint POS returned '{terminal_serial}'."
                )
            elif not terminal_serial:
                discrepancies.append(
                    f"Terminal serial missing from Moniepoint POS response (expected '{expected_terminal}')."
                )

        # RRN mismatch check
        expected_rrn = (
            kwargs.get('rrn')
            or kwargs.get('retrievalReferenceNumber')
            or (payment.transaction_metadata or {}).get('rrn')
            or (payment.transaction_metadata or {}).get('retrievalReferenceNumber')
        )
        if expected_rrn:
            if rrn and str(rrn).strip() != str(expected_rrn).strip():
                discrepancies.append(
                    f"RRN mismatch: expected RRN '{expected_rrn}', Moniepoint POS returned '{rrn}'."
                )
            elif not rrn:
                discrepancies.append(
                    f"RRN missing from Moniepoint POS response (expected '{expected_rrn}')."
                )

        # Expected reference check
        if 'expected_reference' in kwargs and kwargs['expected_reference']:
            exp_ref = str(kwargs['expected_reference']).strip()
            if provider_txn_ref != exp_ref and target_reference != exp_ref and merchant_ref != exp_ref:
                discrepancies.append(
                    f"Expected reference mismatch: expected {exp_ref}, Moniepoint returned {provider_txn_ref}."
                )

        # Recorded reference check
        if payment.transaction_reference:
            recorded_ref = str(payment.transaction_reference).strip()
            if recorded_ref not in (provider_txn_ref, target_reference, merchant_ref):
                discrepancies.append(
                    f"Reference mismatch: recorded transaction reference ({recorded_ref}) does not match Moniepoint reference ({provider_txn_ref})."
                )

        # Map Moniepoint processing status
        if processing_status in ('SUCCESSFUL', 'APPROVED', 'SUCCESS', 'COMPLETED'):
            if discrepancies:
                status = PaymentVerificationStatus.MISMATCH.value
            else:
                status = PaymentVerificationStatus.VERIFIED.value
        elif processing_status in ('FAILED', 'DECLINED', 'REJECTED'):
            status = PaymentVerificationStatus.FAILED.value
            discrepancies.append(
                f"Moniepoint reported terminal transaction declined/failed (status: {processing_status})."
            )
        elif processing_status in ('PENDING', 'PROCESSING', 'IN_PROGRESS', 'INITIALIZED'):
            status = PaymentVerificationStatus.PENDING.value
        else:
            status = PaymentVerificationStatus.UNKNOWN.value
            discrepancies.append(f"Unknown Moniepoint processing status: '{processing_status}'.")

        metadata = {
            'provider': self.provider_name,
            'processing_status': processing_status,
            'terminal_serial': terminal_serial,
            'rrn': rrn,
            'transaction_reference': provider_txn_ref,
            'merchant_reference': merchant_ref,
            'actual_amount': str(verified_amount) if verified_amount is not None else None,
            'currency': pos_currency,
            'payment_method': payment_method,
            'transaction_time': transaction_time,
        }

        return PaymentVerificationResult(
            status=status,
            verified_amount=verified_amount,
            provider_reference=provider_txn_ref or target_reference,
            payment_reference=payment.payment_reference,
            payment_id=payment.id,
            provider=self.provider_name,
            discrepancies=discrepancies,
            metadata=metadata,
        )


class PaymentVerificationService:
    """Central service for managing and executing payment verifications."""

    _verifiers = {
        'mock': MockPaymentVerifier,
        'internal': InternalPaymentVerifier,
        'paystack': PaystackPaymentVerifier,
        'moniepoint': MoniepointPaymentVerifier,
    }

    @classmethod
    def register_verifier(cls, provider_name, verifier_cls):
        """Register a new payment verifier class."""
        if not issubclass(verifier_cls, BasePaymentVerifier):
            raise TypeError('Verifier class must inherit from BasePaymentVerifier.')
        cls._verifiers[str(provider_name).strip().lower()] = verifier_cls

    @classmethod
    def get_verifier(cls, provider_name='mock') -> BasePaymentVerifier:
        """Instantiate a verifier by provider name."""
        name = str(provider_name or 'mock').strip().lower()
        verifier_cls = cls._verifiers.get(name)
        if not verifier_cls:
            return MockPaymentVerifier()
        return verifier_cls()

    @classmethod
    def verify_payment_transaction(cls, payment, provider='mock', **kwargs) -> PaymentVerificationResult:
        """Execute non-destructive, idempotent verification for a Payment record."""
        if isinstance(provider, BasePaymentVerifier):
            verifier = provider
        else:
            verifier = cls.get_verifier(provider)
        return verifier.verify(payment, **kwargs)


def verify_payment_transaction(payment, provider='mock', **kwargs) -> PaymentVerificationResult:
    """Convenience top-level function for payment verification."""
    return PaymentVerificationService.verify_payment_transaction(payment, provider=provider, **kwargs)


# Pre-register built-in providers
PaymentVerificationService.register_verifier('paystack', PaystackPaymentVerifier)
PaymentVerificationService.register_verifier('moniepoint', MoniepointPaymentVerifier)
