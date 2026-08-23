from django.core.exceptions import ValidationError
from django.db import transaction

from .models import InventoryItem, StockMovement


@transaction.atomic
def adjust_inventory_stock(
    inventory_item,
    quantity_delta,
    reason='',
    reference='',
    created_by=None,
    movement_type=StockMovement.MovementType.ADJUSTMENT,
):
    """
    Adjust stock through the authoritative inventory mutation path.

    The inventory row is locked before its quantity is read so callers never
    apply a delta to a stale in-memory balance.
    """
    if quantity_delta == 0:
        raise ValidationError({'quantity': 'Movement quantity cannot be zero.'})

    locked_item = (
        InventoryItem.objects.select_for_update()
        .select_related('product')
        .get(pk=inventory_item.pk)
    )

    previous_quantity = locked_item.quantity
    new_quantity = previous_quantity + quantity_delta

    if new_quantity < 0:
        raise ValidationError({'quantity': 'Stock cannot become negative.'})

    locked_item.quantity = new_quantity
    locked_item.full_clean()
    locked_item.save(update_fields=['quantity', 'updated_at'])

    movement = StockMovement(
        inventory_item=locked_item,
        product=locked_item.product,
        movement_type=movement_type,
        quantity=quantity_delta,
        previous_quantity=previous_quantity,
        new_quantity=new_quantity,
        reason=reason,
        reference=reference,
        created_by=created_by,
    )
    movement.full_clean()
    movement.save()

    return locked_item
