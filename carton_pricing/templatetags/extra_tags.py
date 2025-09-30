from django import template
register = template.Library()

@register.filter
def get_item(dictionary, key):
    return dictionary.get(key)
# carton_pricing/templatetags/extra_tags.py
from django import template
from decimal import Decimal, InvalidOperation

register = template.Library()

@register.filter
def intcomma0(value):
    """حذف اعشار و جداسازی سه‌رقمی با کاما؛ ورودی نامعتبر را همان‌طور برمی‌گرداند."""
    if value in (None, ""):
        return "0"
    try:
        n = int(Decimal(str(value)).quantize(Decimal("1")))
    except (InvalidOperation, ValueError):
        try:
            n = int(float(value))
        except Exception:
            return value
    return format(n, ",")
