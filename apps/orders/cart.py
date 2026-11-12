from decimal import Decimal

from apps.products.models import Product

CART_SESSION_KEY = 'customer_cart'


class CustomerCart:
    """
    Session-backed customer shopping cart.
    Stores items in request.session[CART_SESSION_KEY] as a dict mapping product_id (as str) to integer quantity.
    """

    def __init__(self, request):
        self.session = request.session
        cart = self.session.get(CART_SESSION_KEY)
        if not isinstance(cart, dict):
            cart = {}
            self.session[CART_SESSION_KEY] = cart
        self.cart = cart

    def save(self):
        self.session[CART_SESSION_KEY] = self.cart
        self.session.modified = True

    def clear(self):
        self.cart = {}
        self.save()

    def get_quantity(self, product_id):
        return int(self.cart.get(str(product_id), 0))

    def add(self, product, quantity=1):
        """
        Add quantity to existing cart item, strictly enforcing stock bounds.
        Returns (success, message, new_quantity).
        """
        if quantity <= 0:
            return False, "Quantity must be a positive integer.", self.get_quantity(product.id)

        available_stock = getattr(product, 'inventory_item', None).quantity if hasattr(product, 'inventory_item') and product.inventory_item else 0
        if available_stock <= 0:
            return False, f"Product '{product.name}' is out of stock.", self.get_quantity(product.id)

        current_qty = self.get_quantity(product.id)
        target_qty = current_qty + quantity

        if target_qty > available_stock:
            return False, f"Cannot add {quantity} units. Total requested quantity ({target_qty}) exceeds available stock ({available_stock}).", current_qty

        self.cart[str(product.id)] = target_qty
        self.save()
        return True, "Item added to cart.", target_qty

    def set_quantity(self, product, quantity):
        """
        Update cart item quantity directly, enforcing stock bounds.
        """
        if quantity <= 0:
            self.remove(product.id)
            return True, "Item removed from cart.", 0

        available_stock = getattr(product, 'inventory_item', None).quantity if hasattr(product, 'inventory_item') and product.inventory_item else 0
        if quantity > available_stock:
            return False, f"Requested quantity ({quantity}) exceeds available stock ({available_stock}).", self.get_quantity(product.id)

        self.cart[str(product.id)] = quantity
        self.save()
        return True, "Cart quantity updated.", quantity

    def remove(self, product_id):
        key = str(product_id)
        if key in self.cart:
            del self.cart[key]
            self.save()
            return True
        return False

    def get_cart_data(self):
        """
        Retrieve enriched cart items, subtotal, and stock statuses.
        Automatically prunes inactive or non-existent products.
        """
        product_ids = [int(pid) for pid in self.cart.keys() if str(pid).isdigit()]
        products = (
            Product.objects.filter(id__in=product_ids, is_active=True)
            .select_related('category')
            .prefetch_related('images', 'inventory_item')
        )
        product_map = {p.id: p for p in products}

        items = []
        subtotal = Decimal('0.00')
        total_quantity = 0
        valid_keys = set()

        for pid in product_ids:
            product = product_map.get(pid)
            if not product:
                continue
            valid_keys.add(str(pid))
            quantity = int(self.cart.get(str(pid), 0))
            if quantity <= 0:
                continue

            available_stock = (
                getattr(product, 'inventory_item', None).quantity
                if hasattr(product, 'inventory_item') and product.inventory_item
                else 0
            )

            primary_img = product.primary_image
            img_url = primary_img.image.url if (primary_img and primary_img.image) else None
            if not img_url and product.images.first() and product.images.first().image:
                img_url = product.images.first().image.url

            line_total = product.selling_price * quantity
            subtotal += line_total
            total_quantity += quantity

            items.append({
                'product_id': product.id,
                'id': product.id,
                'name': product.name,
                'slug': product.slug,
                'sku': product.sku,
                'category': product.category.name if product.category else 'Uncategorized',
                'price': str(product.selling_price),
                'unit_price': str(product.selling_price),
                'quantity': quantity,
                'available_stock': available_stock,
                'line_total': str(line_total),
                'image': img_url,
                'allow_pay_on_delivery': getattr(product, 'allow_pay_on_delivery', True),
                'is_out_of_stock': available_stock <= 0,
                'is_low_stock': 0 < available_stock <= product.reorder_level,
                'stock_status': (
                    'OUT_OF_STOCK'
                    if available_stock <= 0
                    else ('LOW_STOCK' if available_stock <= product.reorder_level else 'IN_STOCK')
                ),
            })

        if set(self.cart.keys()) != valid_keys:
            self.cart = {k: v for k, v in self.cart.items() if k in valid_keys}
            self.save()

        allow_cod = all(getattr(p, 'allow_pay_on_delivery', True) for p in product_map.values()) if product_map else True

        return {
            'items': items,
            'item_count': total_quantity,
            'subtotal': str(subtotal),
            'tax': '0.00',
            'delivery': '0.00',
            'shipping': '0.00',
            'total': str(subtotal),
            'allow_cod': allow_cod,
        }

    def get_items(self):
        """Returns list of item dicts for current cart items."""
        return self.get_cart_data().get('items', [])
