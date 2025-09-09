# settings_api.py
from dataclasses import dataclass
from decimal import Decimal
from typing import List

@dataclass
class BizSettings:
    profit_rate_percent: Decimal = Decimal("10")   # %
    shipping_cost:       Decimal = Decimal("0")
    pallet_cost:         Decimal = Decimal("0")
    interface_cost:      Decimal = Decimal("0")
    overhead_per_meter:  Decimal = Decimal("0")
    fixed_widths:        List[float] = None        # مثل [100, 120, 130]
    sheet_price_cash:    Decimal = Decimal("0")
    sheet_price_credit:  Decimal = Decimal("0")

def get_settings() -> BizSettings:
    """
    اگر مدل تنظیمات داری از DB بخوان؛
    در غیر این صورت، مقادیر پیش‌فرض را بده تا import خطا ندهد.
    """
    # این import داخل تابع است تا اگر مدل/اپ متفاوت بود، ماژول import نشکند
    try:
        from .models import BusinessSettings  # نام مدل خودت را جایگزین کن
        bs = BusinessSettings.objects.first()
        if bs:
            return BizSettings(
                profit_rate_percent = Decimal(bs.profit_rate_percent),
                shipping_cost       = Decimal(bs.shipping_cost),
                pallet_cost         = Decimal(bs.pallet_cost),
                interface_cost      = Decimal(bs.interface_cost),
                overhead_per_meter  = Decimal(bs.overhead_per_meter),
                fixed_widths        = list(bs.fixed_widths or []),
                sheet_price_cash    = Decimal(bs.sheet_price_cash),
                sheet_price_credit  = Decimal(bs.sheet_price_credit),
            )
    except Exception:
        pass

    # fallback
    return BizSettings(
        fixed_widths=[100, 120, 130],
    )

def ensure_default_formulas() -> None:
    """
    اگر جدول فرمول‌ها خالی است، چند کلید پایه را مقداردهی کن.
    فرمول‌ها را به «سبک اکسل» بگذار؛ اگر از مبدل Excel→Python استفاده می‌کنی،
    در زمان ارزیابی تبدیل خواهند شد.
    """
    try:
        from .models import CalcFormula
    except Exception:
        return

    if CalcFormula.objects.exists():
        return

    defaults = {
        # نمونه‌های ساده؛ حتماً در آینده فرمول‌های واقعی را جایگزین کن
        # این‌ها اکسل-مانند هستند: =IF(…)
        "E20": "=E15 + E17",         # طول صنعتی نمونه
        "K20": "=G15",                # عرض صنعتی نمونه
        "E28": "=I8 * 1",             # مصرف کارتن (placeholder)
        "E38": "=E20 * K20 / 10000",  # مساحت شیت (m2) فرضی
        "I38": "=I8 / F24",           # تعداد شیت تقریبی
        "E41": "=sheet_price * E38",  # هزینه کارکرد
        "E40": "=M30 * E20 / 1000",   # سربار
        "M40": "=E40 + E41 + H43 + J43 + E43",
        "M41": "=M40 * I41 / 100",
        "H46": "=M40 + M41",
        "J48": "=H46 * 0.09",
        "E48": "=H46 + J48",
    }
    for k, v in defaults.items():
        CalcFormula.objects.create(key=k, expression=v)
