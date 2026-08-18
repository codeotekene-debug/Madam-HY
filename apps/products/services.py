import os
from io import BytesIO
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max
from django.http import Http404
from PIL import Image as PILImage

from .models import Product, ProductImage

MAX_PRODUCT_IMAGE_SIZE = 5 * 1024 * 1024
ALLOWED_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp'}
ALLOWED_IMAGE_MIME_TYPES = {'image/jpeg', 'image/png', 'image/webp'}


def _raise_validation_error(message, field='image'):
    raise ValidationError({field: message})


def _validate_uploaded_image(uploaded_file, *, require_content=True):
    if uploaded_file is None:
        _raise_validation_error('Image file is required.')

    if not hasattr(uploaded_file, 'name') or not uploaded_file.name:
        _raise_validation_error('Image file is required.')

    ext = os.path.splitext(uploaded_file.name)[1].lower()
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        _raise_validation_error('Unsupported image format. Allowed formats: JPEG, PNG, WEBP.')

    if uploaded_file.size is None or uploaded_file.size <= 0:
        _raise_validation_error('Image file is empty.')

    if uploaded_file.size > MAX_PRODUCT_IMAGE_SIZE:
        _raise_validation_error(f'Image file is too large. Maximum allowed size is {MAX_PRODUCT_IMAGE_SIZE // (1024 * 1024)}MB.')

    if require_content:
        try:
            uploaded_file.seek(0)
            with PILImage.open(uploaded_file) as img:
                img.verify()
            uploaded_file.seek(0)
            with PILImage.open(uploaded_file) as img:
                img.load()
                if img.format not in {'JPEG', 'PNG', 'WEBP'}:
                    _raise_validation_error('Unsupported image format. Allowed formats: JPEG, PNG, WEBP.')
        except Exception:
            _raise_validation_error('Uploaded file is not a valid image.')
        finally:
            uploaded_file.seek(0)

    content_type = getattr(uploaded_file, 'content_type', '') or ''
    normalized = content_type.lower()
    if normalized and normalized not in ALLOWED_IMAGE_MIME_TYPES:
        _raise_validation_error('Unsupported image content type.')

    return True


def _can_manage_product_images(user):
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    return user.role in ('OWNER', 'MANAGER')


def _can_read_product_images(user):
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    return True


def _get_product_or_404(product_id):
    try:
        return Product.objects.get(id=product_id)
    except Product.DoesNotExist as exc:
        raise Http404 from exc


def _get_product_image_or_404(product_id, image_id):
    try:
        return ProductImage.objects.get(product_id=product_id, id=image_id)
    except ProductImage.DoesNotExist as exc:
        raise Http404 from exc


def _serialize_product_image(image):
    return {
        'id': image.id,
        'product_id': image.product_id,
        'url': image.image.url if image.image else None,
        'alt_text': image.alt_text,
        'display_order': image.display_order,
        'is_primary': image.is_primary,
        'created_at': image.created_at.isoformat(),
    }


def upload_product_image(product_id, uploaded_file, *, alt_text='', display_order=None, is_primary=False):
    with transaction.atomic():
        product = Product.objects.select_for_update().get(id=product_id)
        _validate_uploaded_image(uploaded_file)

        if display_order is None:
            display_order = (product.images.aggregate(Max('display_order'))['display_order__max'] or 0) + 1

        try:
            display_order = int(display_order)
        except (TypeError, ValueError):
            raise ValidationError({'display_order': 'Display order must be a positive integer.'})

        if display_order <= 0:
            raise ValidationError({'display_order': 'Display order must be a positive integer.'})

        is_primary = bool(is_primary)

        if is_primary:
            product.images.select_for_update().filter(is_primary=True).update(is_primary=False)

        image = ProductImage.objects.create(
            product=product,
            image=uploaded_file,
            alt_text=(alt_text or '').strip()[:200],
            display_order=display_order,
            is_primary=is_primary,
        )

    return image


def update_product_image(product_id, image_id, *, alt_text=None, display_order=None, is_primary=None):
    with transaction.atomic():
        product = Product.objects.select_for_update().get(id=product_id)
        image = product.images.select_for_update().get(id=image_id)

        has_change = False

        if alt_text is not None:
            alt_value = alt_text.strip()[:200]
            if len(alt_value) > 200:
                raise ValidationError({'alt_text': 'Alt text must be 200 characters or fewer.'})
            image.alt_text = alt_value
            has_change = True

        if display_order is not None:
            try:
                display_order = int(display_order)
            except (TypeError, ValueError):
                raise ValidationError({'display_order': 'Display order must be a positive integer.'})
            if display_order <= 0:
                raise ValidationError({'display_order': 'Display order must be a positive integer.'})
            image.display_order = display_order
            has_change = True

        if is_primary is not None:
            if not isinstance(is_primary, bool):
                raise ValidationError({'is_primary': 'is_primary must be a boolean value.'})

            if is_primary is True:
                if image.is_primary is not True:
                    product.images.select_for_update().exclude(id=image.id).filter(is_primary=True).update(is_primary=False)
                    ProductImage.objects.filter(pk=image.pk).update(is_primary=True)
                    has_change = True
                else:
                    product.images.select_for_update().exclude(id=image.id).filter(is_primary=True).update(is_primary=False)
            elif is_primary is False:
                if image.is_primary is True:
                    replacement = product.images.select_for_update().exclude(id=image.id).order_by('display_order', 'created_at').first()
                    ProductImage.objects.filter(pk=image.pk).update(is_primary=False)
                    if replacement is not None:
                        ProductImage.objects.filter(pk=replacement.pk).update(is_primary=True)
                    has_change = True

        if not has_change:
            raise ValidationError({'detail': 'No valid image fields were provided for update.'})

        if alt_text is not None or display_order is not None:
            image.save()

        image.refresh_from_db()
        return image


def set_primary_product_image(product_id, image_id):
    with transaction.atomic():
        product = Product.objects.select_for_update().get(id=product_id)
        image = product.images.select_for_update().get(id=image_id)
        product.images.select_for_update().exclude(id=image.id).filter(is_primary=True).update(is_primary=False)
        image.is_primary = True
        image.save(update_fields=['is_primary'])

    return image


def delete_product_image(product_id, image_id):
    with transaction.atomic():
        product = Product.objects.select_for_update().get(id=product_id)
        image = product.images.select_for_update().get(id=image_id)

        was_primary = image.is_primary
        next_image = None

        if was_primary:
            next_image = product.images.select_for_update().exclude(id=image.id).order_by('display_order', 'created_at').first()

        if was_primary and next_image is not None:
            ProductImage.objects.filter(pk=image.pk).update(is_primary=False)
            ProductImage.objects.filter(pk=next_image.pk).update(is_primary=True)

        if image.image:
            image.image.delete(save=False)
        image.delete()

    return {
        'deleted': True,
        'product_id': product_id,
        'image_id': image_id,
        'promoted_image_id': next_image.id if next_image else None,
    }
