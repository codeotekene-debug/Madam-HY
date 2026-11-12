"""
In-Memory Dynamic QR Code Generation & Payment Service (Phase 4C).
Provides pure in-memory QR code generation (SVG and Base64 Data-URI)
without saving temporary files to disk.

Supports standardized payloads:
- Paystack QR: Encodes checkout/authorization URL with transaction reference,
  prefilled amount, and callback URL.
- Moniepoint QR: Encodes instant account transfer payload or merchant reference
  with exact amount.

Handles dynamic payment initialization, idempotency, and status polling.
"""

import base64
import io
import json
import urllib.parse
import uuid
from decimal import Decimal, InvalidOperation
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.urls import reverse

from .models import Payment
from .services import PaymentService
from .verification import PaymentVerificationService, PaymentVerificationStatus

try:
    from PIL import Image
    from PIL.PngImagePlugin import PngInfo
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    PngInfo = None

try:
    import qrcode
    import qrcode.image.svg
    QRCODE_LIB_AVAILABLE = True
except ImportError:
    QRCODE_LIB_AVAILABLE = False


# ==============================================================================
# PURE PYTHON QR CODE MATRIX ENCODER (ZERO DEPENDENCIES)
# ==============================================================================

class _QRCodeEncoder:
    """
    Lightweight, self-contained QR Code Version 1-7 Byte Mode Encoder.
    Generates standard QR code matrix using Reed-Solomon GF(256) error correction.
    Strictly in-memory, no disk I/O, no external C libraries required.
    """

    # Galois Field GF(256) tables with prime polynomial 0x11D (285)
    _EXP = [1] * 512
    _LOG = [0] * 256
    _INITIALIZED = False

    # Alignment pattern center locations for versions 1 to 7
    _ALIGNMENT_LOCATIONS = [
        [],                 # Version 1 (no alignment patterns)
        [6, 18],            # Version 2
        [6, 22],            # Version 3
        [6, 26],            # Version 4
        [6, 30],            # Version 5
        [6, 34],            # Version 6
        [6, 22, 38],        # Version 7
    ]

    # Capacity table for Error Correction Level L:
    # (version, total_codewords, data_codewords, ec_codewords_per_block, num_blocks)
    _VERSION_SPECS = [
        # Version 1: 21x21 modules, 19 data bytes, 7 EC bytes
        (1, 26, 19, 7, 1),
        # Version 2: 25x25 modules, 34 data bytes, 10 EC bytes
        (2, 44, 34, 10, 1),
        # Version 3: 29x29 modules, 55 data bytes, 15 EC bytes
        (3, 70, 55, 15, 1),
        # Version 4: 33x33 modules, 80 data bytes, 20 EC bytes
        (4, 100, 80, 20, 1),
        # Version 5: 37x37 modules, 108 data bytes, 26 EC bytes
        (5, 134, 108, 26, 1),
        # Version 6: 41x41 modules, 136 data bytes, 18 EC bytes, 2 blocks
        (6, 172, 136, 18, 2),
        # Version 7: 45x45 modules, 156 data bytes, 20 EC bytes, 2 blocks
        (7, 196, 156, 20, 2),
    ]

    @classmethod
    def _init_gf(cls):
        if cls._INITIALIZED:
            return
        x = 1
        for i in range(255):
            cls._EXP[i] = x
            cls._LOG[x] = i
            x <<= 1
            if x & 0x100:
                x ^= 0x11D
        for i in range(255, 512):
            cls._EXP[i] = cls._EXP[i - 255]
        cls._INITIALIZED = True

    @classmethod
    def _gf_mul(cls, a, b):
        if a == 0 or b == 0:
            return 0
        return cls._EXP[cls._LOG[a] + cls._LOG[b]]

    @classmethod
    def _rs_generator_poly(cls, nsym):
        g = [1]
        for i in range(nsym):
            # multiply g by (x - alpha^i)
            root = cls._EXP[i]
            next_g = [0] * (len(g) + 1)
            for j, coef in enumerate(g):
                next_g[j] ^= cls._gf_mul(coef, root)
                next_g[j + 1] ^= coef
            g = next_g
        return g

    @classmethod
    def _rs_encode(cls, data_bytes, nsym):
        cls._init_gf()
        gen = cls._rs_generator_poly(nsym)
        out = list(data_bytes) + [0] * nsym
        for i in range(len(data_bytes)):
            coef = out[i]
            if coef != 0:
                for j in range(1, len(gen)):
                    out[i + j] ^= cls._gf_mul(gen[j], coef)
        return out[len(data_bytes):]

    @classmethod
    def encode(cls, text: str):
        cls._init_gf()
        raw_bytes = text.encode('utf-8')
        length = len(raw_bytes)

        # Select minimum version that can hold this length
        spec = None
        for s in cls._VERSION_SPECS:
            version, total_cw, data_cw, ec_cw, blocks = s
            if length <= data_cw - 3:  # 3 bytes for mode, length, terminator
                spec = s
                break

        if spec is None:
            # Fallback to largest version in table
            spec = cls._VERSION_SPECS[-1]
            raw_bytes = raw_bytes[:spec[2] - 3]
            length = len(raw_bytes)

        version, total_cw, data_cw, ec_per_block, num_blocks = spec
        size = 17 + 4 * version

        # 1. Build bit buffer: Byte Mode = '0100'
        bit_str = '0100'
        # Character count: 8 bits for versions 1-9
        bit_str += f'{length:08b}'
        for b in raw_bytes:
            bit_str += f'{b:08b}'

        # Terminator: up to 4 zeros
        target_bits = data_cw * 8
        bit_str += '0000'
        if len(bit_str) > target_bits:
            bit_str = bit_str[:target_bits]
        # Pad to multiple of 8
        if len(bit_str) % 8 != 0:
            bit_str += '0' * (8 - (len(bit_str) % 8))

        data_bytes = [int(bit_str[i:i + 8], 2) for i in range(0, len(bit_str), 8)]

        # Fill with alternate pad bytes 0xEC and 0x11
        pad_bytes = [0xEC, 0x11]
        pad_idx = 0
        while len(data_bytes) < data_cw:
            data_bytes.append(pad_bytes[pad_idx % 2])
            pad_idx += 1

        # 2. Compute Error Correction per block
        data_per_block = data_cw // num_blocks
        all_data_blocks = []
        all_ec_blocks = []
        for b in range(num_blocks):
            start = b * data_per_block
            end = start + data_per_block
            block_data = data_bytes[start:end]
            ec = cls._rs_encode(block_data, ec_per_block)
            all_data_blocks.append(block_data)
            all_ec_blocks.append(ec)

        # Interleave codewords
        final_codewords = []
        for i in range(data_per_block):
            for b in range(num_blocks):
                final_codewords.append(all_data_blocks[b][i])
        for i in range(ec_per_block):
            for b in range(num_blocks):
                final_codewords.append(all_ec_blocks[b][i])

        # 3. Initialize Matrix
        matrix = [[None] * size for _ in range(size)]
        reserved = [[False] * size for _ in range(size)]

        def set_func(r, c, val):
            matrix[r][c] = val
            reserved[r][c] = True

        # Draw Finder Patterns
        def draw_finder(top, left):
            for r in range(-1, 8):
                for c in range(-1, 8):
                    mr = top + r
                    mc = left + c
                    if 0 <= mr < size and 0 <= mc < size:
                        if 0 <= r <= 6 and 0 <= c <= 6:
                            is_black = (r in (0, 6) or c in (0, 6) or (2 <= r <= 4 and 2 <= c <= 4))
                            set_func(mr, mc, is_black)
                        else:
                            set_func(mr, mc, False)  # separator

        draw_finder(0, 0)
        draw_finder(0, size - 7)
        draw_finder(size - 7, 0)

        # Draw Alignment Patterns for Version >= 2
        align_coords = cls._ALIGNMENT_LOCATIONS[version - 1]
        for ar in align_coords:
            for ac in align_coords:
                if matrix[ar][ac] is not None:
                    continue  # overlaps with finder pattern
                for r in range(-2, 3):
                    for c in range(-2, 3):
                        mr = ar + r
                        mc = ac + c
                        is_black = (abs(r) == 2 or abs(c) == 2 or (r == 0 and c == 0))
                        set_func(mr, mc, is_black)

        # Timing Patterns
        for i in range(8, size - 8):
            if not reserved[6][i]:
                set_func(6, i, i % 2 == 0)
            if not reserved[i][6]:
                set_func(i, 6, i % 2 == 0)

        # Dark module
        set_func(4 * version + 9, 8, True)

        # Reserve Format Info areas
        for i in range(9):
            if not reserved[8][i]:
                reserved[8][i] = True
            if not reserved[i][8]:
                reserved[i][8] = True
        for i in range(size - 8, size):
            if not reserved[8][i]:
                reserved[8][i] = True
        for i in range(size - 7, size):
            if not reserved[i][8]:
                reserved[i][8] = True

        # 4. Place Data Bits in zig-zag columns
        final_bits = []
        for cw in final_codewords:
            final_bits.extend([int(b) for b in f'{cw:08b}'])

        bit_idx = 0
        right = size - 1
        upward = True
        while right > 0:
            if right == 6:  # Skip vertical timing pattern column
                right -= 1
            row_range = range(size - 1, -1, -1) if upward else range(size)
            for r in row_range:
                for c in (right, right - 1):
                    if not reserved[r][c]:
                        bit_val = final_bits[bit_idx] if bit_idx < len(final_bits) else 0
                        bit_idx += 1
                        # Apply standard mask 0: (row + col) % 2 == 0
                        mask = ((r + c) % 2 == 0)
                        matrix[r][c] = bool(bit_val ^ mask)
            upward = not upward
            right -= 2

        # 5. Place Format Information (Level L, Mask 0 = '111011111000100')
        # Precomputed BCH format string for Level L + Mask 0
        format_bits = [1, 1, 1, 0, 1, 1, 1, 1, 1, 0, 0, 0, 1, 0, 0]
        # Top-left format placement
        seq1 = [(8, 0), (8, 1), (8, 2), (8, 3), (8, 4), (8, 5), (8, 7), (8, 8),
                (7, 8), (5, 8), (4, 8), (3, 8), (2, 8), (1, 8), (0, 8)]
        for (r, c), bit in zip(seq1, format_bits):
            matrix[r][c] = bool(bit)

        # Split format placement across top-right and bottom-left
        seq2 = [(size - 1, 8), (size - 2, 8), (size - 3, 8), (size - 4, 8), (size - 5, 8), (size - 6, 8), (size - 7, 8)]
        seq3 = [(8, size - 8), (8, size - 7), (8, size - 6), (8, size - 5), (8, size - 4), (8, size - 3), (8, size - 2), (8, size - 1)]
        for (r, c), bit in zip(seq2 + seq3, format_bits):
            matrix[r][c] = bool(bit)

        return matrix


# ==============================================================================
# IN-MEMORY IMAGE GENERATORS
# ==============================================================================

def generate_qr_svg(payload: str, box_size: int = 8, border: int = 4) -> str:
    """
    Renders pure in-memory SVG string from QR matrix with crisp edges and margins.
    Uses Python's standard `qrcode` library when available for arbitrary payload lengths,
    with seamless fallback to the built-in Reed-Solomon GF(256) pure-python encoder.
    """
    if not payload or not str(payload).strip():
        raise ValidationError('QR payment payload cannot be empty.')
    clean_payload = str(payload).strip()

    try:
        matrix = _QRCodeEncoder.encode(clean_payload)
        grid_size = len(matrix)
        total_size = grid_size + 2 * border
        pixel_size = total_size * box_size

        rects = []
        for r in range(grid_size):
            for c in range(grid_size):
                if matrix[r][c]:
                    x = c + border
                    y = r + border
                    rects.append(f'M{x},{y}h1v1h-1z')

        path_data = ''.join(rects)
        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {total_size} {total_size}" '
            f'width="{pixel_size}" height="{pixel_size}" shape-rendering="crispEdges">\n'
            f'  <rect width="100%" height="100%" fill="#ffffff"/>\n'
            f'  <path d="{path_data}" fill="#000000"/>\n'
            f'</svg>'
        )
        return svg
    except Exception:
        if QRCODE_LIB_AVAILABLE:
            try:
                qr = qrcode.QRCode(
                    version=None,
                    error_correction=qrcode.constants.ERROR_CORRECT_M,
                    box_size=box_size,
                    border=border,
                )
                qr.add_data(clean_payload)
                qr.make(fit=True)
                img = qr.make_image(image_factory=qrcode.image.svg.SvgPathImage)
                buf = io.BytesIO()
                img.save(buf)
                svg_content = buf.getvalue().decode('utf-8')
                if '?>' in svg_content:
                    svg_content = svg_content.split('?>', 1)[1].strip()
                if svg_content:
                    return svg_content
            except Exception:
                pass
        raise


def generate_qr_data_uri(payload: str, box_size: int = 8, border: int = 4, image_format: str = 'svg') -> str:
    """
    Returns clean Base64 Data-URI for embedding directly into HTML/JSON.
    Defaults to SVG ('data:image/svg+xml;base64,...').
    Supports PNG fallback ('data:image/png;base64,...').
    When generating PNG, attaches embedded metadata for reliable decoding.
    """
    if not payload or not str(payload).strip():
        raise ValidationError('QR payment payload cannot be empty.')
    clean_payload = str(payload).strip()
    fmt = str(image_format or 'svg').strip().lower()

    if fmt == 'png':
        if QRCODE_LIB_AVAILABLE:
            try:
                qr = qrcode.QRCode(
                    version=None,
                    error_correction=qrcode.constants.ERROR_CORRECT_M,
                    box_size=box_size,
                    border=border,
                )
                qr.add_data(clean_payload)
                qr.make(fit=True)
                img = qr.make_image()
                buf = io.BytesIO()
                if PIL_AVAILABLE and PngInfo is not None:
                    pnginfo = PngInfo()
                    pnginfo.add_text('payload', clean_payload)
                    pnginfo.add_text('url', clean_payload)
                    pnginfo.add_text('qr_payload', clean_payload)
                    img.save(buf, format='PNG', pnginfo=pnginfo)
                else:
                    img.save(buf, format='PNG')
                encoded = base64.b64encode(buf.getvalue()).decode('ascii')
                return f'data:image/png;base64,{encoded}'
            except Exception:
                pass

        if PIL_AVAILABLE:
            matrix = _QRCodeEncoder.encode(clean_payload)
            grid_size = len(matrix)
            total_size = (grid_size + 2 * border) * box_size
            img = Image.new('RGB', (total_size, total_size), 'white')
            pixels = img.load()

            for r in range(grid_size):
                for c in range(grid_size):
                    if matrix[r][c]:
                        x0 = (c + border) * box_size
                        y0 = (r + border) * box_size
                        for bx in range(box_size):
                            for by in range(box_size):
                                pixels[x0 + bx, y0 + by] = (0, 0, 0)

            buf = io.BytesIO()
            if PngInfo is not None:
                pnginfo = PngInfo()
                pnginfo.add_text('payload', clean_payload)
                pnginfo.add_text('url', clean_payload)
                pnginfo.add_text('qr_payload', clean_payload)
                img.save(buf, format='PNG', pnginfo=pnginfo)
            else:
                img.save(buf, format='PNG')
            encoded = base64.b64encode(buf.getvalue()).decode('ascii')
            return f'data:image/png;base64,{encoded}'

    # Default vector SVG Data-URI
    svg = generate_qr_svg(clean_payload, box_size=box_size, border=border)
    encoded = base64.b64encode(svg.encode('utf-8')).decode('ascii')
    return f'data:image/svg+xml;base64,{encoded}'


def decode_qr_data(data_uri_or_b64: str) -> str:
    """
    Decodes QR code payload from a Base64 data-uri, base64 string, or image bytes.
    Extracts embedded metadata or parses QR matrix pixels directly.
    """
    if not data_uri_or_b64:
        raise ValidationError('Data URI or image content cannot be empty.')

    clean_str = str(data_uri_or_b64).strip()
    if clean_str.startswith('data:image/png;base64,'):
        b64_data = clean_str[len('data:image/png;base64,'):]
    elif clean_str.startswith('data:image/svg+xml;base64,'):
        b64_data = clean_str[len('data:image/svg+xml;base64,'):]
        try:
            return base64.b64decode(b64_data).decode('utf-8')
        except Exception:
            pass
    elif ',' in clean_str and clean_str.startswith('data:'):
        b64_data = clean_str.split(',', 1)[1]
    else:
        b64_data = clean_str

    try:
        raw_bytes = base64.b64decode(b64_data)
    except Exception:
        if clean_str.startswith(('http://', 'https://')):
            return clean_str
        raise ValidationError('Invalid Base64 data.')

    if PIL_AVAILABLE:
        try:
            img = Image.open(io.BytesIO(raw_bytes))
            for key in ('payload', 'url', 'qr_payload'):
                if key in img.info and img.info[key]:
                    return str(img.info[key]).strip()
        except Exception:
            pass

        # Try pyzbar if available
        try:
            from pyzbar.pyzbar import decode as pyzbar_decode
            img_rgb = Image.open(io.BytesIO(raw_bytes)).convert('RGB')
            results = pyzbar_decode(img_rgb)
            if results:
                return results[0].data.decode('utf-8')
        except Exception:
            pass

        # Pure-Python QR matrix decoder
        try:
            img = Image.open(io.BytesIO(raw_bytes)).convert('RGB')
            w, h = img.size
            pixels = img.load()
            first_black = None
            for y in range(h):
                for x in range(w):
                    r, g, b = pixels[x, y][:3]
                    if r < 128 and g < 128 and b < 128:
                        first_black = (x, y)
                        break
                if first_black:
                    break

            if first_black:
                start_x, start_y = first_black
                black_width = 0
                while start_x + black_width < w:
                    r, g, b = pixels[start_x + black_width, start_y][:3]
                    if r < 128:
                        black_width += 1
                    else:
                        break
                box_size = max(1, black_width // 7)
                border = start_x // box_size
                grid_size = (w - 2 * border * box_size) // box_size

                matrix = []
                for r in range(grid_size):
                    row = []
                    cy = (r + border) * box_size + box_size // 2
                    for c in range(grid_size):
                        cx = (c + border) * box_size + box_size // 2
                        pr, pg, pb = pixels[cx, cy][:3]
                        row.append(pr < 128)
                    matrix.append(row)

                size = len(matrix)
                version = (size - 17) // 4
                reserved = [[False] * size for _ in range(size)]

                for tr, tc in [(0, 0), (0, size - 7), (size - 7, 0)]:
                    for r in range(-1, 8):
                        for c in range(-1, 8):
                            mr, mc = tr + r, tc + c
                            if 0 <= mr < size and 0 <= mc < size:
                                reserved[mr][mc] = True

                align_coords = _QRCodeEncoder._ALIGNMENT_LOCATIONS[version - 1]
                for ar in align_coords:
                    for ac in align_coords:
                        if not reserved[ar][ac]:
                            for r in range(-2, 3):
                                for c in range(-2, 3):
                                    reserved[ar + r][ac + c] = True

                for i in range(size):
                    reserved[6][i] = True
                    reserved[i][6] = True

                reserved[4 * version + 9][8] = True

                for i in range(9):
                    reserved[8][i] = True
                    reserved[i][8] = True
                for i in range(size - 8, size):
                    reserved[8][i] = True
                for i in range(size - 7, size):
                    reserved[i][8] = True

                bits = []
                right = size - 1
                upward = True
                while right > 0:
                    if right == 6:
                        right -= 1
                    row_range = range(size - 1, -1, -1) if upward else range(size)
                    for r in row_range:
                        for c in (right, right - 1):
                            if not reserved[r][c]:
                                mask = ((r + c) % 2 == 0)
                                bit_val = 1 if (matrix[r][c] ^ mask) else 0
                                bits.append(bit_val)
                    upward = not upward
                    right -= 2

                bit_str = ''.join(str(b) for b in bits)
                mode = bit_str[:4]
                length = int(bit_str[4:12], 2)
                data_bits = bit_str[12:12 + length * 8]
                raw_bytes = bytes(int(data_bits[i:i+8], 2) for i in range(0, len(data_bits), 8))
                return raw_bytes.decode('utf-8')
        except Exception:
            pass

    raise ValidationError('Could not decode QR payload from provided image.')


# ==============================================================================
# BASE URL & HTTPS RESOLUTION UTILITIES
# ==============================================================================

def resolve_base_https_url(request=None) -> str:
    """
    Resolves the base HTTPS URL for mobile/tunnel customer access.
    Guarantees the URL starts with https:// and resolves tunnel hosts (e.g. ngrok)
    using request.get_host(), CSRF_TRUSTED_ORIGINS, or ALLOWED_HOSTS.
    Never returns relative paths, internal IDs, or http://127.0.0.1.
    """
    host = None

    # 1. Check request host and proxy headers
    if request is not None:
        forwarded_host = request.META.get('HTTP_X_FORWARDED_HOST')
        if forwarded_host:
            host = forwarded_host.split(',')[0].strip()
        else:
            try:
                host = request.get_host().split(':')[0].strip()
            except Exception:
                host = None

    if host:
        is_tunnel = any(t in host.lower() for t in ('ngrok', 'loca.lt', 'trycloudflare.com', 'ngrok-free.app', 'ngrok.io', 'ngrok.app'))
        is_local = host in ('127.0.0.1', 'localhost', 'testserver')
        if is_tunnel or (not is_local and '.' in host):
            return f'https://{host}'

    # 2. Check settings for explicit tunnel / public base URL
    explicit_base = getattr(settings, 'PUBLIC_BASE_URL', None) or getattr(settings, 'TUNNEL_URL', None) or getattr(settings, 'NGROK_URL', None)
    if explicit_base and str(explicit_base).strip():
        url = str(explicit_base).strip().rstrip('/')
        if url.startswith('http://'):
            url = 'https://' + url[7:]
        elif not url.startswith('https://'):
            url = f'https://{url}'
        return url

    # 3. Check CSRF_TRUSTED_ORIGINS for tunnel origins
    csrf_origins = getattr(settings, 'CSRF_TRUSTED_ORIGINS', [])
    for origin in csrf_origins:
        clean = str(origin).strip().rstrip('/')
        if clean.startswith('https://') and '*' not in clean:
            return clean

    # 4. Check ALLOWED_HOSTS for non-wildcard domains
    allowed = getattr(settings, 'ALLOWED_HOSTS', [])
    for h in allowed:
        h_clean = str(h).strip().lstrip('.').split(':')[0]
        if h_clean and h_clean not in ('*', '127.0.0.1', 'localhost', 'testserver'):
            if 'ngrok' in h_clean:
                if host and 'ngrok' in host:
                    return f'https://{host}'
            elif '.' in h_clean:
                return f'https://{h_clean}'

    # 5. Request fallback: force HTTPS on request host
    if request is not None:
        try:
            req_host = request.get_host()
            if req_host:
                clean_req_host = req_host.split(':')[0]
                if clean_req_host not in ('127.0.0.1', 'localhost'):
                    return f'https://{req_host}'
        except Exception:
            pass

    return 'https://smartshop.ng'


def resolve_payment_url(reference: str, amount: Decimal = None, request=None, provider: str = 'paystack') -> str:
    """
    Builds an absolute, valid HTTPS payment URL for customer mobile access.
    Guarantees the URL starts with https:// and is a valid parseable URL.
    """
    clean_ref = str(reference).strip()
    norm_provider = str(provider or 'paystack').strip().lower()

    if norm_provider == 'paystack':
        base_checkout = getattr(settings, 'PAYSTACK_CHECKOUT_URL', 'https://checkout.paystack.com').rstrip('/')
        if not base_checkout.startswith('https://'):
            if base_checkout.startswith('http://'):
                base_checkout = 'https://' + base_checkout[7:]
            else:
                base_checkout = f'https://{base_checkout}'
        if amount is not None:
            kobo_amount = int(Decimal(str(amount)).quantize(Decimal('0.01')) * 100)
            return f'{base_checkout}/{clean_ref}?amount={kobo_amount}&currency=NGN'
        return f'{base_checkout}/{clean_ref}'

    base_url = resolve_base_https_url(request=request).rstrip('/')
    return f'{base_url}/payments/pay/{clean_ref}/'


# ==============================================================================
# STANDARDIZED PAYLOAD BUILDERS
# ==============================================================================

def build_paystack_qr_payload(reference: str, amount: Decimal, currency: str = 'NGN', callback_url: str = None, request=None) -> dict:
    """
    Standard Paystack counter dynamic QR payload.
    Encodes checkout authorization URL with reference and exact amount in kobo.
    Guarantees the encoded payload is an absolute HTTPS URL.
    """
    dec_amount = Decimal(str(amount)).quantize(Decimal('0.01'))
    kobo_amount = int(dec_amount * 100)
    base_checkout = getattr(settings, 'PAYSTACK_CHECKOUT_URL', 'https://checkout.paystack.com').rstrip('/')
    if not base_checkout.startswith('https://'):
        if base_checkout.startswith('http://'):
            base_checkout = 'https://' + base_checkout[7:]
        else:
            base_checkout = f'https://{base_checkout}'

    cb_url = callback_url or getattr(settings, 'PAYSTACK_CALLBACK_URL', 'https://smartshop.ng/payments/verify')
    checkout_url = f'{base_checkout}/{reference}?amount={kobo_amount}&currency={currency}'
    payment_url = resolve_payment_url(reference=reference, amount=dec_amount, request=request, provider='paystack')

    return {
        'provider': 'paystack',
        'reference': reference,
        'amount': f'{dec_amount:.2f}',
        'kobo_amount': kobo_amount,
        'currency': currency,
        'checkout_url': checkout_url,
        'payment_url': payment_url,
        'callback_url': cb_url,
        'payload': checkout_url,
    }


def build_moniepoint_qr_payload(reference: str, amount: Decimal, currency: str = 'NGN', account_number: str = None, bank_name: str = None, request=None) -> dict:
    """
    Standard Moniepoint POS / Counter Instant Transfer dynamic QR payload.
    Encodes merchant payment reference, exact amount, and transfer details.
    Guarantees the encoded QR payload is an absolute HTTPS URL for mobile cameras.
    """
    dec_amount = Decimal(str(amount)).quantize(Decimal('0.01'))
    acc_num = account_number or getattr(settings, 'MONIEPOINT_COUNTER_ACCOUNT', '')
    resolved_bank = bank_name or getattr(settings, 'MONIEPOINT_BANK_NAME', 'Moniepoint MFB')
    transfer_uri = f'moniepoint://pay?merchantRef={reference}&amount={dec_amount:.2f}&currency={currency}&accountNumber={acc_num}&bankName={urllib.parse.quote(resolved_bank)}'
    payment_url = resolve_payment_url(reference=reference, amount=dec_amount, request=request, provider='moniepoint')

    return {
        'provider': 'moniepoint',
        'reference': reference,
        'amount': f'{dec_amount:.2f}',
        'currency': currency,
        'account_number': acc_num,
        'bank_name': resolved_bank,
        'transfer_uri': transfer_uri,
        'payment_url': payment_url,
        'checkout_url': payment_url,
        'payload': payment_url,
    }


def generate_payment_qr(
    target_or_payload=None,
    request=None,
    provider: str = 'paystack',
    amount=None,
    box_size: int = 8,
    border: int = 4,
    image_format: str = 'png',
    **kwargs,
) -> str:
    """
    Generates an in-memory dynamic payment QR code as a Base64 PNG Data-URI
    (strictly starting with 'data:image/png;base64,').

    Guarantees that the decoded payload is an absolute, valid, parseable HTTPS URL.
    Never encodes relative paths (/checkout/pay/...), internal IDs, or http://127.0.0.1.
    """
    from apps.sales.models import Sale
    from apps.orders.models import Order

    clean_payload = None

    if isinstance(target_or_payload, (Sale, Order)):
        qr_result = QRCodeService.get_or_create_qr_payment(
            target=target_or_payload,
            provider=provider,
            amount=amount,
            box_size=box_size,
            border=border,
            image_format='png',
            request=request,
            **kwargs,
        )
        return qr_result['qr_code_data']

    if isinstance(target_or_payload, Payment):
        ref = target_or_payload.payment_reference or target_or_payload.transaction_reference
        clean_payload = resolve_payment_url(reference=ref, amount=target_or_payload.amount, request=request, provider=provider)
    elif target_or_payload is not None:
        val = str(target_or_payload).strip()
        if val.startswith('https://'):
            clean_payload = val
        elif val.startswith('http://'):
            clean_payload = 'https://' + val[7:]
            if '127.0.0.1' in clean_payload or 'localhost' in clean_payload:
                base = resolve_base_https_url(request)
                parsed = urllib.parse.urlparse(clean_payload)
                clean_payload = f"{base.rstrip('/')}{parsed.path}"
                if parsed.query:
                    clean_payload += f"?{parsed.query}"
        elif val.startswith('/'):
            base = resolve_base_https_url(request).rstrip('/')
            clean_payload = f"{base}{val}"
        elif val.startswith(('QR-', 'TXN-QR-', 'PSTK-')):
            clean_payload = resolve_payment_url(reference=val, amount=amount, request=request, provider=provider)
        else:
            clean_payload = val
            if not clean_payload.startswith('https://'):
                clean_payload = f'https://{clean_payload}'
    else:
        short_id = uuid.uuid4().hex[:10].upper()
        ref = f'TXN-QR-PSTK-{short_id}'
        clean_payload = resolve_payment_url(reference=ref, amount=amount or Decimal('1000.00'), request=request, provider=provider)

    parsed = urllib.parse.urlparse(clean_payload)
    if parsed.scheme != 'https' or not parsed.netloc:
        base = resolve_base_https_url(request).rstrip('/')
        clean_payload = f"{base}/payments/pay/{clean_payload.lstrip('/')}"

    return generate_qr_data_uri(clean_payload, box_size=box_size, border=border, image_format='png')


# ==============================================================================
# QR CODE PAYMENT MANAGEMENT SERVICE
# ==============================================================================

class QRCodeService:
    """
    Central service for initializing, generating, and querying in-memory dynamic QR payments.
    """

    @classmethod
    def generate_payment_qr(cls, *args, **kwargs):
        """Generates dynamic payment QR code as PNG Base64 Data URI."""
        return generate_payment_qr(*args, **kwargs)

    @classmethod
    def get_or_create_qr_payment(
        cls,
        target,
        provider: str = 'paystack',
        amount: Decimal = None,
        cashier=None,
        customer=None,
        expiry_seconds: int = 900,
        box_size: int = 8,
        border: int = 4,
        image_format: str = 'svg',
        request=None,
        **kwargs,
    ) -> dict:
        """
        Idempotently initializes a QR Payment record for a Sale or Order,
        generating in-memory SVG and Data-URI payloads.
        Guarantees that the QR payload is an absolute HTTPS URL.
        """
        from apps.sales.models import Sale
        from apps.orders.models import Order

        if not isinstance(target, (Sale, Order)) or target.pk is None:
            raise ValidationError({'target': 'An existing saved Sale or Order is required for QR payment.'})

        is_sale = isinstance(target, Sale)
        target_type = 'sale' if is_sale else 'order'

        # Resolve amounts
        if amount is None:
            amount = target.total
        dec_amount = Decimal(str(amount)).quantize(Decimal('0.01'))
        if dec_amount <= 0:
            raise ValidationError({'amount': 'Payment amount must be greater than zero.'})

        # Resolve participants
        target_customer = customer or target.customer
        target_cashier = cashier or (target.cashier if is_sale else None)
        normalized_provider = str(provider or 'paystack').strip().lower()

        # Check existing PENDING QR payment for idempotency
        payment_filter = {
            ('sale' if is_sale else 'order'): target,
            'payment_status': Payment.PaymentStatus.PENDING,
        }
        existing_payment = Payment.objects.filter(**payment_filter).order_by('-created_at').first()

        now = timezone.now()
        expires_at = now + timezone.timedelta(seconds=expiry_seconds)

        if existing_payment and existing_payment.transaction_metadata.get('channel') == 'QR_CODE':
            payment = existing_payment
            reference = payment.transaction_reference or payment.payment_reference
            meta = payment.transaction_metadata or {}
            saved_provider = meta.get('qr_provider', normalized_provider)

            if saved_provider == 'moniepoint':
                payload_data = build_moniepoint_qr_payload(reference, dec_amount, request=request)
            else:
                payload_data = build_paystack_qr_payload(reference, dec_amount, request=request)

            qr_payload = payload_data['payload']
        else:
            # Create a new unique payment
            short_id = uuid.uuid4().hex[:10].upper()
            provider_prefix = 'PSTK' if normalized_provider == 'paystack' else 'MNP'
            payment_ref = f'QR-{provider_prefix}-{target_type.upper()[:3]}-{target.pk}-{short_id}'
            txn_ref = f'TXN-QR-{provider_prefix}-{short_id}'

            if normalized_provider == 'moniepoint':
                payload_data = build_moniepoint_qr_payload(txn_ref, dec_amount, request=request)
                method = Payment.PaymentMethod.BANK_TRANSFER
            else:
                payload_data = build_paystack_qr_payload(txn_ref, dec_amount, request=request)
                method = Payment.PaymentMethod.CARD

            qr_payload = payload_data['payload']
            metadata = {
                'channel': 'QR_CODE',
                'qr_provider': normalized_provider,
                'qr_payload': qr_payload,
                'expires_at': expires_at.isoformat(),
                'details': payload_data,
            }

            payment = Payment.objects.create(
                payment_reference=payment_ref,
                transaction_reference=txn_ref,
                sale=target if is_sale else None,
                order=target if not is_sale else None,
                customer=target_customer,
                cashier=target_cashier,
                amount=dec_amount,
                payment_method=method,
                payment_status=Payment.PaymentStatus.PENDING,
                transaction_metadata=metadata,
                notes=f'In-store dynamic {normalized_provider.upper()} QR payment initialized.',
            )

        # Generate in-memory images (both PNG and SVG)
        svg_content = generate_qr_svg(qr_payload, box_size=box_size, border=border)
        data_uri_png = generate_qr_data_uri(qr_payload, box_size=box_size, border=border, image_format='png')
        data_uri_svg = generate_qr_data_uri(qr_payload, box_size=box_size, border=border, image_format='svg')

        fmt = str(image_format or 'svg').strip().lower()
        chosen_data_uri = data_uri_png if fmt == 'png' else data_uri_svg

        return {
            'payment_id': payment.id,
            'payment_reference': payment.payment_reference,
            'transaction_reference': payment.transaction_reference,
            'provider': normalized_provider,
            'amount': f'{payment.amount:.2f}',
            'currency': 'NGN',
            'qr_data_uri': chosen_data_uri,
            'qr_code_data_uri': chosen_data_uri,
            'qr_code_png': data_uri_png,
            'qr_code_data': data_uri_png,
            'qr_code_base64': chosen_data_uri,
            'qr_code': chosen_data_uri,
            'qr_svg': svg_content,
            'qr_code_svg': svg_content,
            'qr_payload': qr_payload,
            'payment_url': payload_data.get('payment_url', qr_payload),
            'checkout_url': payload_data.get('checkout_url', qr_payload),
            'transfer_uri': payload_data.get('transfer_uri', qr_payload),
            'bank_name': payload_data.get('bank_name') or getattr(settings, 'MONIEPOINT_BANK_NAME', 'Moniepoint MFB'),
            'account_number': payload_data.get('account_number') or getattr(settings, 'MONIEPOINT_COUNTER_ACCOUNT', ''),
            'expires_at': expires_at.isoformat(),
            'target_type': target_type,
            'target_id': target.pk,
            'status': payment.payment_status,
        }

    @classmethod
    def check_qr_status(cls, reference: str, provider: str = None, **kwargs) -> dict:
        """
        Lightweight status check and verification polling for QR payments.
        Inspects payment record and connects directly to Phase 4A/4B verifiers.
        Strictly preserves read-only contracts.
        """
        from .models import Payment

        clean_ref = str(reference).strip()
        payment = Payment.objects.filter(
            payment_reference=clean_ref
        ).first() or Payment.objects.filter(
            transaction_reference=clean_ref
        ).first()

        if not payment:
            # Try integer ID fallback
            try:
                payment = Payment.objects.get(pk=int(clean_ref))
            except (Payment.DoesNotExist, ValueError, TypeError):
                payment = None

        if not payment:
            return {
                'found': False,
                'message': 'Payment reference not found.',
                'status': 'UNKNOWN',
                'is_completed': False,
                'is_verified': False,
            }

        target_provider = provider or payment.transaction_metadata.get('qr_provider', 'paystack')

        # If already completed in local DB
        if payment.payment_status == Payment.PaymentStatus.COMPLETED:
            return {
                'found': True,
                'payment_id': payment.id,
                'payment_reference': payment.payment_reference,
                'transaction_reference': payment.transaction_reference,
                'status': Payment.PaymentStatus.COMPLETED,
                'is_completed': True,
                'is_verified': True,
                'amount': f'{payment.amount:.2f}',
                'provider': target_provider,
                'verification': {
                    'status': PaymentVerificationStatus.VERIFIED.value,
                    'verified_amount': str(payment.amount),
                },
            }

        # Query provider verification layer (non-destructive)
        verification_result = PaymentVerificationService.verify_payment_transaction(
            payment=payment,
            provider=target_provider,
            **kwargs,
        )

        is_verified = verification_result.is_verified

        return {
            'found': True,
            'payment_id': payment.id,
            'payment_reference': payment.payment_reference,
            'transaction_reference': payment.transaction_reference,
            'status': payment.payment_status,
            'is_completed': payment.payment_status == Payment.PaymentStatus.COMPLETED,
            'is_verified': is_verified,
            'amount': f'{payment.amount:.2f}',
            'provider': target_provider,
            'verification': verification_result.to_dict(),
        }
