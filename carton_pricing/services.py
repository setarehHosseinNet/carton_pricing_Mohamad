# services.py
import math
from typing import Iterable, Tuple

def choose_per_sheet_and_width(required_w: float,
                               fixed_widths: Iterable[float],
                               waste_warn_threshold: float = 0.10
                               ) -> Tuple[int, float, float, bool, str]:
    """
    ورودی:
      required_w: عرض موردنیاز (مثلاً K20)
      fixed_widths: لیست عرض‌های استاندارد موجود (mm یا cm؛ واحد باید با required_w یکی باشد)
      waste_warn_threshold: اگر نسبت پرت (waste_ratio) >= این مقدار بود، warn=True

    خروجی:
      (count_per_sheet, chosen_width, waste_ratio, warn, note)
    """
    widths = [float(w) for w in (fixed_widths or []) if w]
    note = ""
    if not widths:
        # اگر عرض ثابت نداری، مجبوریم با همان required_w حساب کنیم
        chosen = float(required_w)
        count = 1
        waste_ratio = 0.0
        warn = False
        note = "عرض استاندارد تعریف نشده؛ از عرض موردنیاز استفاده شد."
        return count, chosen, waste_ratio, warn, note

    # کوچکترین عرضی که نیاز را پوشش دهد
    widths = sorted(set(widths))
    greater_or_equal = [w for w in widths if w >= required_w]
    chosen = min(greater_or_equal) if greater_or_equal else max(widths)
    if chosen < required_w:
        # هیچ عرضی کافی نیست؛ مجبوریم بزرگترین را انتخاب کنیم و حداقل 1 عدد در هر شیت
        count = 1
    else:
        count = max(1, int(chosen // required_w))  # چند بار required_w در chosen جا می‌شود

    used = required_w * count
    waste = max(0.0, chosen - used)
    waste_ratio = (waste / chosen) if chosen else 0.0
    warn = waste_ratio >= waste_warn_threshold

    if not greater_or_equal:
        note = "هیچ عرضی >= نیاز نبود؛ بزرگ‌ترین عرض انتخاب شد."
    elif warn:
        note = f"پرت بالا: {waste_ratio:.1%}"

    return count, float(chosen), float(waste_ratio), bool(warn), note
