# carton_pricing/services/env.py
from __future__ import annotations
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Optional, Mapping

class Env:
    """خواندن ساده متغیرهای محیطی با مقدار پیش‌فرض."""
    def __init__(self, base_dir: str | Path | None = None):
        self.base_dir = Path(base_dir or Path(__file__).resolve().parents[2])

    def str(self, key: str, default: str | None = None) -> str | None:
        return os.environ.get(key, default)

    def bool(self, key: str, default: bool = False) -> bool:
        v = os.environ.get(key)
        if v is None:
            return default
        return v.strip().lower() in ("1", "true", "yes", "on")

    def int(self, key: str, default: int = 0) -> int:
        v = os.environ.get(key)
        try:
            return int(v) if v is not None else default
        except Exception:
            return default


class _DotNS(SimpleNamespace):
    """Namespace که برای کلیدهای ناموجود None برمی‌گرداند تا AttributeError نخوریم."""
    def __getattr__(self, name):
        return None


class SettingsLoader:
    """
    Loader تنظیمات برنامه.
    - متدهای env: برای ENV
    - load_latest(): آخرین تنظیمات بیزنسی از DB؛ اگر نبود، Fallback منطقی.
    """
    def __init__(self, base_dir: str | Path | None = None):
        self.env = Env(base_dir=base_dir)

    # ===== موجود قبلی =====
    def db_url(self) -> Optional[str]:
        return self.env.str("DATABASE_URL")

    def secret_key(self) -> str:
        return self.env.str("DJANGO_SECRET_KEY", "dev-insecure-secret-please-change")

    def debug(self) -> bool:
        return self.env.bool("DJANGO_DEBUG", True)

    # ===== جدید: برای سازگاری با views.py =====
    @classmethod
    def load_latest(cls) -> _DotNS:
        """
        تلاش می‌کند از مدل تنظیمات (اگر وجود داشته باشد) آخرین رکورد را بخواند.
        اگر مدل/دیتا نبود، یک fallback امن برمی‌گرداند تا view ها AttributeError نخورند.
        """
        # تلاش برای خواندن از DB اگر مدلی با نام‌های رایج وجود داشته باشد
        # هر کدام بود، از همان استفاده می‌کنیم.
        candidates = ("BusinessSettings", "AppSettings", "Settings", "SiteSettings")
        try:
            from django.apps import apps  # django آماده است این‌جا
            for model_name in candidates:
                model = apps.get_model("carton_pricing", model_name)
                if model is None:
                    continue
                obj = model.objects.order_by("-id").first()
                if obj:
                    # اگر مدل متدی برای dict دارد
                    if hasattr(obj, "to_dict"):
                        return _DotNS(**(obj.to_dict() or {}))
                    # یا اگر فیلدهای رایج دارد
                    data = {}
                    for f in getattr(obj, "_meta").get_fields():
                        # فقط فیلدهای ساده
                        if hasattr(obj, f.name) and not f.many_to_many and not f.one_to_many:
                            try:
                                data[f.name] = getattr(obj, f.name)
                            except Exception:
                                pass
                    return _DotNS(**data)
        except Exception:
            # اگر مدل نبود/DB آماده نبود، می‌افتیم روی fallback
            pass

        # ---- Fallback منطقی (می‌توانی بسته به نیاز پروژه تغییر دهی) ----
        return _DotNS(
            tax_percent=9.0,                 # درصد مالیات
            profit_rate_default=0.15,        # حاشیه سود پیش‌فرض
            sheet_fixed_widths_mm=[1000, 1050, 1100, 1200],  # عرض‌های استاندارد
            currency="IRR",
            round_price=True,
        )

    # در صورت نیاز اگر جایی instance-method صدا زده باشی:
    def load_latest_instance(self) -> _DotNS:
        return self.__class__.load_latest()

    @staticmethod
    def inject(bs, settlement, var: dict, cd: dict | None = None) -> dict:
        """
        bs: آبجکت تنظیمات (خروجی load_latest) — ممکنه DotNS باشه
        settlement: تنظیمات تسویه/پرداخت (هرچی ویو پاس میده؛ dict یا آبجکت)
        var: دیکشنری متغیرهای محاسباتی که باید با تنظیمات پر/تکمیل بشه
        cd: cleaned_data فرم (اختیاری)

        این متد باید «مقادیر موجود» رو نگه داره و فقط اگر کلیدی موجود نیست، از bs/settlement مقدار بده.
        """
        if var is None:
            var = {}

        def _get(obj, name, default=None):
            if obj is None:
                return default
            # پشتیبانی از هم attribute هم dict
            if isinstance(obj, dict):
                return obj.get(name, default)
            return getattr(obj, name, default)

        # از تنظیمات کلی (bs) مقدار بده—فقط اگر قبلاً داخل var نیست یا None است
        for key in ("tax_percent", "profit_rate_default", "currency", "round_price", "sheet_fixed_widths_mm"):
            val = _get(bs, key, None)
            if val is not None and (key not in var or var.get(key) is None):
                var[key] = val

        # اگر settlement دیکشنری/آبجکت قابل خواندن بود، مقادیر مفید را تزریق کن
        # (کلیدهای احتمالی: payment_type, fee_amount, discount_percent, due_days, ...)
        for key in ("payment_type", "fee_amount", "discount_percent", "due_days"):
            val = _get(settlement, key, None)
            if val is not None and (key not in var or var.get(key) is None):
                var[key] = val

        # اگر از cleaned_data چیز خاصی لازم داری (اختیاری)
        if cd:
            # مثال‌ها؛ در صورت نیاز کلیدهای واقعی پروژه‌ات را اضافه کن
            for key in ("E20_industrial_len", "K20_industrial_wid"):
                if key in cd and (key not in var or var.get(key) is None):
                    var[key] = cd.get(key)

        return var