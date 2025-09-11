# helpers/settings_adapter.py  (یا بالای views.py)

from typing import Any
from django.db import transaction
from carton_pricing.models import BaseSettings

# فقط یک‌جا فهرست فیلدهای مجاز را نگه‌دار تا drift پیش نیاید:
BASESETTINGS_FIELDS = [
    "overhead_per_meter",
    "sheet_price_cash",
    "sheet_price_credit",
    "profit_rate_percent",
    "shipping_cost",
    "pallet_cost",
    "interface_cost",
    "fixed_widths",
]

def _read_value(src: Any, name: str, default=None):
    """از dict یا آبجکت سرویس مقدار را امن بخوان؛ در غیر این صورت default."""
    if src is None:
        return default
    if isinstance(src, dict):
        return src.get(name, default)
    return getattr(src, name, default)

def _get_singleton() -> BaseSettings:
    """
    بسته به مدل خودت یکی را انتخاب کن:
    - اگر فیلد singleton_key داری:
        obj, _ = BaseSettings.objects.get_or_create(singleton_key="ONLY")
    - اگر نداری و ساده می‌خواهی:
        obj, _ = BaseSettings.objects.get_or_create(pk=1)
    """
    obj, _ = BaseSettings.objects.get_or_create(singleton_key="ONLY")
    return obj

def ensure_settings_model(src: Any) -> BaseSettings:
    """
    هر نوع ورودی را به نمونهٔ مدل BaseSettings تبدیل می‌کند
    بدون اینکه الزاماً ذخیره کند؛ اگر مقداری تغییر کرد، ذخیره انجام می‌شود.
    """
    if isinstance(src, BaseSettings):
        return src

    obj = _get_singleton()
    dirty = False

    for fld in BASESETTINGS_FIELDS:
        val = _read_value(src, fld, default=None)
        if val is None:
            continue  # چیزی برای به‌روزرسانی نداریم
        # فقط وقتی ست کن که واقعاً تغییر می‌کند
        if getattr(obj, fld) != val:
            setattr(obj, fld, val)
            dirty = True

    if dirty:
        obj.save(update_fields=BASESETTINGS_FIELDS)

    return obj
