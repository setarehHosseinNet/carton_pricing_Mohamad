# carton_pricing/views.py
# -*- coding: utf-8 -*-
from __future__ import annotations

# ───────────────────────── stdlib ─────────────────────────
from decimal import Decimal
from typing import Any


# ───────────────────────── Django ─────────────────────────
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from django.http import HttpRequest, HttpResponse
import logging
logger = logging.getLogger(__name__)

# ─────────────────────── App Imports ──────────────────────
from .models import BaseSettings,  Customer
from .forms import (
    BaseSettingsForm,
    CalcFormulaForm,
    CustomerForm,
    PhoneForm,
    PriceForm,
)
from .constants import VARIABLE_LABELS


# ─────────────────────── Helpers / Logger ─────────────────


# اعداد فارسی → انگلیسی + پارس امن عدد
PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")
def as_num_or_none(x: Any) -> float | None:
    try:
        if x is None:
            return None
        if isinstance(x, (int, float)):
            return float(x)
        s = str(x).strip().translate(PERSIAN_DIGITS)
        if s in ("", "*"):
            return None
        s = s.replace(",", "").replace("٬", "")  # کاما انگلیسی/فارسی
        return float(s)
    except Exception:
        return None



# ───────────────────────── API (Ajax) ─────────────────────
@require_POST
def api_add_customer(request: HttpRequest) -> JsonResponse:
    form = CustomerForm(request.POST)
    if form.is_valid():
        c = form.save()
        return JsonResponse({"ok": True, "id": c.id, "text": str(c)})
    return JsonResponse({"ok": False, "errors": form.errors}, status=400)


@require_POST
def api_add_phone(request: HttpRequest) -> JsonResponse:
    form = PhoneForm(request.POST)
    if form.is_valid():
        p = form.save()
        return JsonResponse({"ok": True, "id": p.id, "text": p.number})
    return JsonResponse({"ok": False, "errors": form.errors}, status=400)


@require_POST
def api_last_order(request: HttpRequest) -> JsonResponse:
    """آخرین سفارش مشتری برای نمایش زنده کنار فرم."""
    cid = request.POST.get("customer_id")
    if not cid:
        return JsonResponse({"ok": False, "error": "customer_id required"}, status=400)
    try:
        c = Customer.objects.get(id=cid)
    except Customer.DoesNotExist:
        return JsonResponse({"ok": False, "error": "customer not found"}, status=404)

    o = c.orders.order_by("-registered_at").first()
    if not o:
        return JsonResponse({"ok": True, "data": None})

    data = {
        "last_date": o.registered_at.isoformat() if o.registered_at else None,
        "last_fee": float(getattr(o, "last_fee", 0) or 0),
        "last_rate": float(getattr(o, "last_unit_rate", 0) or 0),
    }
    return JsonResponse({"ok": True, "data": data})

#--------------------------------------------------------------------------





def get_or_create_settings() -> BaseSettings:
    """
    فقط اگر هیچ رکوردی وجود نداشت، یک رکورد می‌سازد.
    ⚠️ هرگز مقادیر موجود را با پیش‌فرض‌ها/خارجی‌ها overwrite نکن.
    """
    bs = BaseSettings.objects.filter(singleton_key="ONLY").order_by("-id").first()
    if bs:
        return bs

    # فقط در حالت نبود رکورد، می‌توان از پیش‌فرض‌ها استفاده کرد (داخل مدل هم safe defaults داریم)
    return BaseSettings.objects.create()  # از defaultهای خود مدل استفاده می‌شود


# utils.py (یا هر جایی که مناسب است)

import json
import re
from typing import Any, Iterable, List

# اعداد و جداکننده‌های فارسی → لاتین
_PERSIAN_MAP = str.maketrans("۰۱۲۳۴۵۶۷۸۹٬٫،", "0123456789,.,")


def _normalize_fixed_widths(
    value: Any,
    *,
    dedupe: bool = True,
    sort_result: bool = True,
    min_value: float = 1.0,
    precision: int = 0,
) -> List[float]:
    """
    مقدار ورودی `fixed_widths` را به لیستی از اعداد تبدیل می‌کند.

    ورودی‌های قابل قبول:
      - list/tuple/set از اعداد یا رشته‌ها
      - رشته‌ی JSON آرایه‌ای مانند: "[80, 90, 100]"
      - رشته‌ی CSV/space-separated مانند: "80,90,100" یا "80 90 100"
      - شامل اعداد فارسی و جداکننده‌های فارسی

    پارامترها:
      dedupe: حذف مقادیر تکراری
      sort_result: مرتب‌سازی صعودی خروجی
      min_value: حذف مقادیر کوچکتر از این عدد (پیش‌فرض فقط اعداد مثبت)
      precision: تعداد رقم اعشار برای گرد کردن (۰ یعنی عدد صحیح)

    خروجی: List[float]
    """
    # 1) None یا خالی
    if value is None or value == "":
        return []

    # 2) اگر خودش قابل iteration است (مثل list/tuple/set)
    if isinstance(value, (list, tuple, set)):
        tokens: Iterable[Any] = value
    else:
        # 3) اگر رشته باشد: نرمال‌سازی و تبدیل
        if not isinstance(value, str):
            value = str(value)

        s = value.translate(_PERSIAN_MAP).strip()
        if not s:
            return []

        # اول سعی در JSON array
        if s.startswith("[") and s.endswith("]"):
            try:
                parsed = json.loads(s)
                return _normalize_fixed_widths(
                    parsed,
                    dedupe=dedupe,
                    sort_result=sort_result,
                    min_value=min_value,
                    precision=precision,
                )
            except Exception:
                pass

        # سپس CSV / فاصله
        tokens = (t for t in re.split(r"[,\s;|/]+", s) if t)

    # 4) تبدیل به عدد، فیلتر و گرد کردن
    out: List[float] = []
    for t in tokens:
        try:
            num = float(str(t).translate(_PERSIAN_MAP))
        except Exception:
            continue
        if num >= min_value:
            if precision is not None and precision >= 0:
                num = round(num, precision)
            out.append(num)

    # 5) یکتا و مرتب‌سازی طبق نیاز
    if dedupe:
        # یکتا با حفظ ترتیب
        seen = set()
        out = [x for x in out if not (x in seen or seen.add(x))]

    if sort_result:
        out = sorted(out)

    return out

def base_settings_view(request: HttpRequest) -> HttpResponse:
    """
    صفحهٔ اطلاعات پایه:
    - فقط آخرین رکورد Singleton را لود می‌کنیم و همان را آپدیت می‌کنیم.
    - هیچ همگام‌سازی خودکاری با منابع خارجی انجام نمی‌شود.
    - fixed_widths به‌صورت امن normalized می‌شود.
    """
    bs = get_or_create_settings()

    if request.method == "POST":
        print(">>> POST stage=", request.POST.get("stage"), "sheet_choice=", request.POST.get("sheet_choice"))
        form = BaseSettingsForm(request.POST, instance=bs)
        if form.is_valid():
            cd = form.cleaned_data

            # fixed_widths را محکم‌کاری کن (اگر ویجت JSON درست کار نکرده یا CSV آمده)
            fixed_widths = _normalize_fixed_widths(cd.get("fixed_widths"))
            if not fixed_widths:
                # اگر کاربر خالی گذاشت، می‌توانی یا خالی ثبت کنی یا یک پیش‌فرض معقول بدهی
                fixed_widths = [80, 90, 100, 110, 120, 125, 140]

            with transaction.atomic():
                bs.overhead_per_meter = cd.get("overhead_per_meter") or Decimal("0")
                bs.sheet_price_cash   = cd.get("sheet_price_cash")   or Decimal("0")
                bs.sheet_price_credit = cd.get("sheet_price_credit") or Decimal("0")
                bs.profit_rate_percent = cd.get("profit_rate_percent") or Decimal("0")
                bs.shipping_cost      = cd.get("shipping_cost")      or Decimal("0")
                bs.pallet_cost        = cd.get("pallet_cost")        or Decimal("0")
                bs.interface_cost     = cd.get("interface_cost")     or Decimal("0")
                bs.fixed_widths       = fixed_widths
                # custom_vars اگر در فرم هست:
                if "custom_vars" in cd and cd.get("custom_vars") is not None:
                    bs.custom_vars = cd["custom_vars"]
                # Singleton key را تثبیت کن
                bs.singleton_key = "ONLY"
                bs.save()

            messages.success(request, "اطلاعات پایه ذخیره شد.")
            return redirect("carton_pricing:base_settings")
        else:
            messages.error(request, "خطا در ذخیره تنظیمات. لطفاً مقادیر ورودی را بررسی کنید.")
    else:
        # فقط نمایش؛ هیچ تغییری روی شیء نده
        form = BaseSettingsForm(instance=bs)

    return render(request, "carton_pricing/base_settings.html", {"form": form})



# ─────────────── Pages: Base Settings & Formulas ───────────────
def seed_defaults_from_external(ext: dict) -> dict:
    """مقادیر اولیه‌ی مناسب برای ساخت اولین رکورد BaseSettings."""
    ext = ext or {}
    return {
        "overhead_per_meter": ext.get("overhead_per_meter", 0) or 0,
        "sheet_price_cash":   ext.get("sheet_price_cash", 0) or 0,
        "sheet_price_credit": ext.get("sheet_price_credit", 0) or 0,
        "profit_rate_percent":ext.get("profit_rate_percent", 0) or 0,
        "interface_cost":     ext.get("interface_cost", 0) or 0,
        "pallet_cost":        ext.get("pallet_cost", 0) or 0,
        "shipping_cost":      ext.get("shipping_cost", 0) or 0,
        "fixed_widths":       ext.get("fixed_widths", ""),   # TextField/JSONField
    }




# ایجاد پیش‌فرض فرمول‌ها اگر settings_api خودش انجام نده
def _ensure_default_formulas_if_needed() -> None:
    defaults: Dict[str, str] = {
        "E20": "E15 + (E17 if A3==1 else 0) + 20",   # طول صنعتی (cm)
        "K20": "G15 + 20",                            # عرض صنعتی (cm)
        "E28": "E20 * K20",                           # مصرف کارتن (cm^2)
        "E38": "(E20/100) * (sheet_width/100)",       # متراژ هر ورق (m²)
        "I38": "ceil(I8 / F24)",                      # تعداد ورق
        "E41": "E38 * sheet_price",                   # مایه کاری ورق
        "E40": "E38 * M30",                           # مایه کاری سربار
        "M40": "E41 + E40",                           # مایه کاری کلی
        "M41": "(I41/100) * M40",                     # مبلغ سود
        "H46": "M41 + J43 + H43 + E43 + E46 + M40",   # قیمت بدون مالیات
        "J48": "(H46/100) * 10",                      # مالیات 10٪
        "E48": "H46 + J48",                           # قیمت با مالیات
    }
    for k, expr in defaults.items():
        CalcFormula.objects.get_or_create(
            key=k, defaults={"expression": expr, "description": k}
        )

def formulas_view(request: HttpRequest) -> HttpResponse:
    """
    صفحه فرمول‌ها (ایجاد پیش‌فرض‌ها، افزودن و ویرایش گروهی).
    اگر ماژول بیرونی ensure_default_formulas را انجام نداده، از fallback داخلی کمک می‌گیریم.
    """
    try:
        from .settings_api import ensure_default_formulas  # type: ignore
        ensure_default_formulas()
    except Exception:
        _ensure_default_formulas_if_needed()

    qs = CalcFormula.objects.order_by("key")

    if request.method == "POST":
        if "add_new" in request.POST:
            form = CalcFormulaForm(request.POST)
            if form.is_valid():
                form.save()
                messages.success(request, "فرمول جدید اضافه شد.")
                return redirect("carton_pricing:formulas")
            messages.error(request, "خطا در افزودن فرمول.")
        else:
            updated = 0
            for f in qs:
                new_expr = request.POST.get(f"expr_%s" % f.id)
                if new_expr is not None and new_expr != f.expression:
                    f.expression = new_expr
                    f.save(update_fields=["expression"])
                    updated += 1
            messages.success(request, f"فرمول‌ها ذخیره شدند. ({updated} مورد)")
            return redirect("carton_pricing:formulas")

    add_form = CalcFormulaForm()
    return render(
        request,
        "carton_pricing/formulas.html",
        {"formulas": qs, "labels": VARIABLE_LABELS, "add_form": add_form},
    )


# ───────────────────────── Price Form ─────────────────────────
# ... بقیهٔ ایمپورت‌ها و کد شما بالاتر ...

# ───────────────────────── helpers at module level ─────────────────────────

from decimal import Decimal
from typing import Any



def DBG(*parts: Any) -> None:
    try:
        print(" ".join(str(p) for p in parts))
    except Exception:
        print(" ".join(repr(p) for p in parts))

def q2(val: float | Decimal, places: str) -> Decimal:
    return Decimal(val).quantize(Decimal(places), rounding=ROUND_HALF_UP)

def _normalize_digits(s: str) -> str:
    """تبدیل ارقام فارسی/عربی و جداکننده‌ها به لاتین برای پارس مطمئن."""
    if not isinstance(s, str):
        s = str(s or "")
    trans = {
        ord("۰"): "0", ord("۱"): "1", ord("۲"): "2", ord("۳"): "3", ord("۴"): "4",
        ord("۵"): "5", ord("۶"): "6", ord("۷"): "7", ord("۸"): "8", ord("۹"): "9",
        ord("٠"): "0", ord("١"): "1", ord("٢"): "2", ord("٣"): "3", ord("٤"): "4",
        ord("٥"): "5", ord("٦"): "6", ord("٧"): "7", ord("٨"): "8", ord("٩"): "9",
        ord("،"): ",", ord("٬"): ",", ord("٫"): ".",
    }
    return s.translate(trans)

def _as_num_or_none(x: Any) -> float | None:
    try:
        if x is None:
            return None
        if isinstance(x, (int, float)):
            return float(x)
        s = str(x).strip()
        if s in ("", "*"):
            return None
        return float(s.replace(",", ""))
    except Exception:
        return None

def as_num(x: Any, default: float = 0.0) -> float:
    v = _as_num_or_none(x)
    return default if v is None else v

def _parse_fixed_widths_from_settings(raw_fw) -> list[float]:
    """
    ورودی می‌تواند JSON/list باشد یا رشته‌ای مثل:
    '[80,90,100,110,120,125,140]' یا '80 , 90 , 100 …'
    """
    if raw_fw is None or raw_fw == "":
        return []
    if isinstance(raw_fw, (list, tuple)):
        out = []
        for x in raw_fw:
            v = _as_num_or_none(x)
            if v and v > 0:
                out.append(float(v))
        return sorted(set(out))
    s = _normalize_digits(str(raw_fw))
    nums = re.findall(r"\d+(?:\.\d+)?", s)
    widths = [float(n) for n in nums if as_num(n, 0.0) > 0]
    return sorted(set(widths))


# ───────────────────────── end helpers ─────────────────────────
# ─── HARD WIRED SHEET WIDTHS ───────────────────────────────────────────
HARD_FIXED_WIDTHS: list[float] = [80, 90, 100, 110, 120, 125, 140]

def get_fixed_widths_hard() -> list[float]:
    """همیشه همین لیست را بر‌می‌گرداند؛ تنظیمات را نادیده می‌گیرد."""
    return HARD_FIXED_WIDTHS[:]  # کپی امن

# بالای ویو یا در utils
_PERSIAN_ARABIC_TRANS = str.maketrans({
    "۰":"0","۱":"1","۲":"2","۳":"3","۴":"4","۵":"5","۶":"6","۷":"7","۸":"8","۹":"9",
    "٠":"0","١":"1","٢":"2","٣":"3","٤":"4","٥":"5","٦":"6","٧":"7","٨":"8","٩":"9",
    "٬":",", "،":",", "٫":"."    # جداکننده‌های فارسی
})

def _normalize_num_text(x: Any) -> str:
    s = "" if x is None else str(x)
    s = s.strip().translate(_PERSIAN_ARABIC_TRANS)
    # حذف هزارگان و یکدست کردن اعشار
    s = s.replace(",", "")
    return s


def best_for_each_width(k15: float, widths: list[float], e20: float, fmax: int = 30) -> list[dict]:
    """
    برای هر عرض w بزرگ‌ترین F<=fmax را می‌یابد که F*k15 <= w.
    خروجی هر ردیف:
      - sheet_width → برای ستون «عرض ورق (M24)»
      - f24         → برای ستون «F24 (≤30)»
      - I22         → دورریز (cm)
      - E28         → مصرف کارتن همان ردیف = E20 * (F*k15)  (cm^2)
      - need        → F*k15 (cm) (نمایشی/دیباگ)
      - ok          → True اگر 0 < دورریز < 11
    """
    ws = sorted({float(w) for w in widths if w and float(w) > 0})
    try: k15v = float(k15)
    except Exception: k15v = 0.0
    try: e20v = float(e20)
    except Exception: e20v = 0.0

    rows: list[dict] = []
    if k15v <= 0 or not ws:
        return [{"sheet_width": w, "f24": 0, "I22": None, "E28": None, "need": None, "ok": False} for w in ws]

    for w in ws:
        best_f = None
        for f in range(int(fmax), 0, -1):
            need = f * k15v
            if need <= w + 1e-9:
                waste = w - need               # I22
                e28   = (e20v or 0.0) * need   # مصرف کارتن همان ردیف
                rows.append({
                    "sheet_width": w,
                    "f24": int(f),
                    "I22": round(float(waste), 2),
                    "E28": round(float(e28),   2),
                    "need": round(float(need), 2),
                    "ok": (0.0 < float(waste) < 11.0),
                })
                best_f = f
                break
        if best_f is None:
            rows.append({"sheet_width": w, "f24": 0, "I22": None, "E28": None, "need": None, "ok": False})
    return rows



def _calc_e20_row(env_row: dict, formulas_raw: dict) -> float:
    """
    E20 را با همان env ردیف (دارای A6,E15,G15 و...) محاسبه می‌کند.
    اگر فرمول بانک نبود/خطا داد، fallback امن برمی‌گرداند.
    """
    try:
        r, _e, f = build_resolver(formulas_raw, env_row)
        if "E20" in f:
            v = r("E20")
            v = as_num_or_none(v)
            if v is not None:
                return float(v)
    except Exception:
        pass

    # --- fallback: بر اساس مقادیر فرم ---
    A6  = int(as_num(env_row.get("A6"), 0))
    E15 = as_num(env_row.get("E15"), 0.0)
    G15 = as_num(env_row.get("G15"), 0.0)
    if E15 == 0 and G15 == 0:
        return 0.0
    if A6 == 2211:
        return E15 + G15 + 3.5
    return (E15 + G15) * 2 + 3.5


def _calc_e28_row(env_row: dict, formulas_raw: dict) -> float:
    """
    E28 را با env ردیف محاسبه می‌کند؛ اگر فرمول بانک نبود/خطا داد،
    از E20_row*M24/F24/10000 استفاده می‌شود.
    """
    try:
        r, _e, f = build_resolver(formulas_raw, env_row)
        if "E28" in f:
            v = r("E28")
            v = as_num_or_none(v)
            if v is not None:
                return float(v)
    except Exception:
        pass

    e20 = _calc_e20_row(env_row, formulas_raw)
    F24 = as_num(env_row.get("F24"), 0.0)
    M24 = as_num(env_row.get("M24"), 0.0)
    if e20 and F24:
        return (e20 * M24) / F24 / 10000.0
    return 0.0

# views.py


import re
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, Iterable, List, Optional, Tuple


from .models import BaseSettings
from .utils import build_resolver  # همان کمکی که فرمول‌های CalcFormula را resolve می‌کند


# =============================== ابزارهای عمومی (Utility) ===============================

PERSIAN_MAP = str.maketrans("۰۱۲۳۴۵۶۷۸۹٬٫،", "0123456789,,.")


def _norm_num(x: Any) -> str:
    """رشتهٔ عددی را از ارقام فارسی/عربی به لاتین تبدیل و جداکننده‌های هزارگان را حذف می‌کند."""
    s = "" if x is None else str(x)
    return s.translate(PERSIAN_MAP).replace(",", "")


def as_num_or_none(x: Any) -> Optional[float]:
    """تبدیل امن به عدد اعشاری؛ اگر خالی/نامعتبر بود None می‌دهد."""
    try:
        if x is None:
            return None
        if isinstance(x, (int, float, Decimal)):
            return float(x)
        s = _norm_num(x).strip()
        if s in ("", "*"):
            return None
        return float(s)
    except Exception:
        return None


def as_num(x: Any, default: float = 0.0) -> float:
    """تبدیل امن به عدد با مقدار پیش‌فرض."""
    v = as_num_or_none(x)
    return default if v is None else v


def q2(val: float | Decimal, places: str) -> Decimal:
    """گرد کردن با الگوی اعشار (مثلاً '0.01' یا '0.0001')."""
    return Decimal(val).quantize(Decimal(places), rounding=ROUND_HALF_UP)


# =============================== داده/سازه‌های بین‌میانی ===============================

@dataclass
class Env:
    """ظرف متغیرها برای ارزیابی فرمول‌ها و ساخت جدول."""
    var: Dict[str, Any]
    formulas_raw: Dict[str, str]

    def copy(self) -> "Env":
        return Env(var=dict(self.var), formulas_raw=dict(self.formulas_raw))


@dataclass
class TableRow:
    sheet_width: float   # M24
    f24: int             # F24
    I22: Optional[float] # دورریز
    E28: Optional[float] # مصرف کارتن cm²


# =============================== لود و تزریق تنظیمات ===============================

class SettingsLoader:
    """
    خواندن BaseSettings و تزریق متغیرهای قیمت/سربار و Fee_amount
    """

    @staticmethod
    def load_latest() -> BaseSettings:
        return BaseSettings.objects.order_by("-id").first() or BaseSettings.objects.create()

    @staticmethod
    def inject(bs: BaseSettings, settlement: str, var: Dict[str, Any], cd: Optional[dict] = None) -> None:
        def f(x): return as_num(x, 0.0)
        var["M30"] = f(bs.overhead_per_meter)
        var["M31"] = f(bs.sheet_price_cash)
        var["M33"] = f(bs.sheet_price_credit)
        var["I41"] = f(bs.profit_rate_percent)
        var["E43"] = f(bs.shipping_cost)
        var["H43"] = f(bs.pallet_cost)
        var["J43"] = f(bs.interface_cost)

        e46 = as_num(cd.get("E46_round_adjust"), 0.0) if cd else 0.0
        if not e46:
            try:
                e46 = as_num((bs.custom_vars or {}).get("E46"), 0.0)
            except Exception:
                e46 = 0.0
        var["E46"] = e46

        # تعیین Fee_amount مطابق حالت تسویه
        fee = var["M33"] if settlement == "credit" else var["M31"]
        if fee <= 0:
            try:
                fee = as_num((bs.custom_vars or {}).get("Fee_amount"), 0.0)
            except Exception:
                fee = 0.0
        if fee <= 0:
            fee = 1.0  # کف ایمنی
        var["sheet_price"] = fee
        var["Fee_amount"] = fee


# =============================== موتور ارزیابی فرمول ===============================

class FormulaEngine:
    """
    پوستهٔ امن روی build_resolver:
    - یک‌بار parse می‌کند؛
    - خواندن مقدار کلیدها با handling خطا؛
    - یادآوری: expression باید «یک عبارت» باشد (بدون assignment/کامنت).
    """

    def __init__(self, env: Env):
        self.env = env
        self._resolve, self._env, self._compiled = build_resolver(env.formulas_raw, env.var)

    def has(self, key: str) -> bool:
        return key in self._compiled

    def get(self, key: str) -> Optional[float]:
        if key not in self._compiled:
            return None
        try:
            v = self._resolve(key)
            return as_num_or_none(v)
        except Exception:
            return None

    def rebuild_with(self, extra_vars: Dict[str, Any]) -> "FormulaEngine":
        new = self.env.copy()
        new.var.update(extra_vars)
        return FormulaEngine(new)


# =============================== محاسبهٔ E17 بر اساس قوانین شما ===============================

class E17Calculator:
    """
    قوانین:
      - tail ∈ {11,12}  ⇒ «درب باز/نامتوازن»: E17 = (لب بالا) + (لب پایین)  ← هر دو از فرم
      - tail ∈ {21,22}  ⇒ E17 = G15 / 2
      - tail ∈ {31,32}  ⇒ E17 = G15
      - سایر حالات      ⇒ تلاش از فرمول DB (E17) وگرنه 0
    """

    OPEN_TAILS = {11, 12}
    HALF_TAILS = {21, 22}
    FULL_TAILS = {31, 32}

    @classmethod
    def compute(cls, *, tail: int, g15: float, cd: dict, stage: str, eng: FormulaEngine, form: PriceForm) -> float:
        e17_top = as_num_or_none(cd.get("E17_lip"))
        e17_bot = as_num_or_none(cd.get("open_bottom_door"))

        if tail in cls.OPEN_TAILS:
            # جمع لب‌ها؛ در مرحلهٔ نهایی، خالی‌بودن هرکدام خطاست
            if stage == "final" and (e17_top is None or e17_bot is None):
                if e17_top is None:
                    form.add_error("E17_lip", "لب درب بالا برای این حالت الزامی است.")
                if e17_bot is None:
                    form.add_error("open_bottom_door", "درب باز پایین برای این حالت الزامی است.")
            return (0.0 if e17_top is None else float(e17_top)) + (0.0 if e17_bot is None else float(e17_bot))

        if tail in cls.HALF_TAILS:
            return g15 / 2.0
        if tail in cls.FULL_TAILS:
            return g15

        # تلاش از فرمول DB
        e17_db = eng.get("E17")
        return as_num(e17_db, 0.0)


# =============================== محاسبهٔ K15 با fallback و clamp ===============================

class K15Calculator:
    """
    - اول تلاش از فرمول DB (K15)
    - سپس fallback منطقی بر مبنای tail و I17/E17/I15
    - در نهایت clamp به بیشینهٔ fixed_widths
    """

    @staticmethod
    def fallback_k15(*, tail: int, I17: float, E17: float, I15: float) -> float:
        coef = 2 if (tail % 10) == 1 else 1
        if tail in (11, 12):
            return max(0.0, I17 * coef + I15)
        if tail in (21, 22, 31, 32):
            return max(0.0, E17 * coef + I15)
        return max(E17 * 2 + I15, I17 * 2 + I15)

    @classmethod
    def compute(cls, *, eng: FormulaEngine, tail: int, var: Dict[str, Any], fixed_widths: Iterable[float]) -> float:
        k15_db = as_num(eng.get("K15"), 0.0)
        k15_fb = cls.fallback_k15(
            tail=tail,
            I17=as_num(var.get("I17"), 0.0),
            E17=as_num(var.get("E17"), 0.0),
            I15=as_num(var.get("I15"), 0.0),
        )
        try:
            max_w = float(max(float(w) for w in fixed_widths))
        except Exception:
            max_w = 140.0

        # اگر نامعتبر/صفر/خیلی بزرگ بود ⇒ fallback
        if (not math.isfinite(k15_db)) or k15_db <= 0 or k15_db > max_w:
            k15_db = k15_fb
        return min(k15_db, max_w)


# =============================== محاسبات per-row: E20 و E28 ===============================

class RowCalcs:
    """
    محاسبات E20 و E28 برای یک ردیف جدول (وابسته به M24/F24 همان ردیف)
    """

    @staticmethod
    def e20_row(env_row: Dict[str, Any], eng: FormulaEngine) -> float:
        # اطمینان از seed
        env_row = dict(env_row)
        env_row["E15"] = as_num(env_row.get("E15"), 0.0)
        env_row["G15"] = as_num(env_row.get("G15"), 0.0)
        env_row["A6"] = int(as_num(env_row.get("A6"), 0))
        env_row.pop("E20", None)

        eng_row = eng.rebuild_with(env_row)
        v = eng_row.get("E20")
        if v is not None and math.isfinite(v) and v > 0:
            return float(v)

        # fallback امن
        A6, E15, G15 = env_row["A6"], env_row["E15"], env_row["G15"]
        if E15 == 0 and G15 == 0:
            return 0.0
        return (E15 + G15 + 3.5) if A6 == 2211 else ((E15 + G15) * 2 + 3.5)

    @staticmethod
    def e28_row(env_row: Dict[str, Any], eng: FormulaEngine) -> float:
        env_row = dict(env_row)
        e20 = RowCalcs.e20_row(env_row, eng)
        env_row["E20"] = e20
        env_row.pop("E28", None)

        eng_row = eng.rebuild_with(env_row)
        v = eng_row.get("E28")
        if v is not None and math.isfinite(v) and v >= 0:
            return float(v)

        F24 = as_num(env_row.get("F24"), 0.0)
        M24 = as_num(env_row.get("M24"), 0.0)
        return (e20 * M24 / F24 / 10000.0) if (e20 and F24) else 0.0


# =============================== سازندهٔ جدول مرحله ۱ ===============================

class TableBuilder:
    """ساخت سطرهای جدول بر اساس K15 و لیست عرض‌های ثابت."""

    @staticmethod
    def _normalize_widths(widths: Iterable[float]) -> List[float]:
        ws: List[float] = []
        for w in widths or []:
            try:
                v = float(w)
                if v > 0:
                    ws.append(v)
            except Exception:
                pass
        # مرتب + حذف تکراری
        return sorted(set(ws))

    @classmethod
    def build_rows(cls, *, k15: float, widths: Iterable[float], env_base: Dict[str, Any], eng: FormulaEngine) -> List[TableRow]:
        rows: List[TableRow] = []
        k15v = float(k15 or 0.0)
        ws = cls._normalize_widths(widths)

        if k15v <= 0:
            return [TableRow(sheet_width=w, f24=0, I22=None, E28=None) for w in ws]

        for w in ws:
            # F24: بیشینهٔ 30
            f = int(min(30, math.floor((w + 1e-9) / k15v)))
            if f <= 0:
                rows.append(TableRow(sheet_width=w, f24=0, I22=None, E28=None))
                continue

            waste = w - (k15v * f)
            row_env = {**env_base, "M24": float(w), "sheet_width": float(w), "F24": float(f)}
            e20 = RowCalcs.e20_row(row_env, eng)
            row_env["E20"] = e20
            e28 = RowCalcs.e28_row(row_env, eng)

            rows.append(
                TableRow(
                    sheet_width=float(w),
                    f24=int(f),
                    I22=round(float(waste), 2),
                    E28=round(float(e28), 4),
                )
            )
        return rows


# =============================== ویوی باریک‌شده (Orchestrator) ===============================



try:
    import jdatetime  # برای تاریخ شمسی
except Exception:  # pragma: no cover
    jdatetime = None


from .models import  CalcFormula


# نام چک‌باکس‌های «موارد انتخابی» که می‌خواهیم از سفارش مبدأ در initial ست شوند
FLAG_FIELD_NAMES = [
    "flag_customer_dims",
    "flag_customer_sample",
    "flag_sample_dims",
    "flag_new_cliche",
    "flag_staple",
    "flag_handle_slot",
    "flag_punch",
    "flag_pallet_wrap",
    "flag_shipping_not_seller",
]



from .forms import  FLAG_FIELD_NAMES

# 1) چیزهایی که در پکیج services هستند:
from .services import Env,  FormulaEngine

# 2) چیزهایی که مربوط به legacy (services.py قدیمی) هستند:
from .legacy_services import (
    CalcFormula,
    TableRow, RowCalcs,


)


from .utils import as_num, as_num_or_none, q2

try:
    import jdatetime
except Exception:
    jdatetime = None

from django.apps import apps
from types import SimpleNamespace
from types import SimpleNamespace
from django.apps import apps

# views.py
import math
import logging



logger = logging.getLogger(__name__)

# تغییرات از اینجا


import math
from types import SimpleNamespace
from decimal import Decimal
from typing import Any, Dict, Optional

from django.contrib import messages
from django.db import transaction
from django.shortcuts import render
from django.utils import timezone

from .forms import PriceForm
from .models import PriceQuotation, OverheadItem, ExtraCharge, Paper
from .services.area import CompositionAreaCalculator
from .services.utils import as_num, as_num_or_none, q2  # فرض بر این است موجودند
from .services.env import SettingsLoader
     # همان Loader خودت

import logging
logger = logging.getLogger(__name__)

# --- جایگزینِ utils های گم‌شده -------------------------
from decimal import Decimal, InvalidOperation

def as_num(val, default=0.0):
    try:
        if val is None or str(val).strip() == "":
            return float(default)
        return float(str(val).replace(",", ""))
    except Exception:
        return float(default)

def as_num_or_none(val):
    try:
        if val is None or str(val).strip() == "":
            return None
        return float(str(val).replace(",", ""))
    except Exception:
        return None

def q2(value, quant="0.01"):
    """Quantize به نزدیک‌ترین مقدار دلخواه با Decimal."""
    try:
        return Decimal(str(value)).quantize(Decimal(str(quant)))
    except (InvalidOperation, Exception):
        try:
            return Decimal("0").quantize(Decimal(str(quant)))
        except Exception:
            return Decimal("0.00")
# -------------------------------------------------------
# ─────────────────────────────────────────────────────────────────────────────
# views.py — price_form_view  (نسخهٔ بازنویسی‌شده و با لاگ مناسب)
# ─────────────────────────────────────────────────────────────────────────────


import math
import logging
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, Dict, Optional

from django.shortcuts import render
from django.utils import timezone
from django.contrib import messages
from django.db import transaction

from .forms import PriceForm
from .models import PriceQuotation, OverheadItem, ExtraCharge, Paper
from .services.area import CompositionAreaCalculator

from .services.utils import as_num, as_num_or_none, q2


logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# سازندهٔ فرم (Keyword-only)
# -----------------------------------------------------------------------------
def _build_form(*, request, initial: dict | None = None, stage: str = "s1") -> PriceForm:
    """
    یک فرم را با توجه به مرحله می‌سازد و در مرحلهٔ s1، فیلدهای ترکیب کاغذ را
    optional و با queryset کامل تنظیم می‌کند تا بعد از POST هم خالی نشوند.
    """
    # در POST فرم bound می‌شود، در غیر این‌صورت unbound
    form = PriceForm(request.POST if request.method == "POST" else None, initial=initial)

    # این‌ها اختیاری‌اند
    for name in ("E17_lip", "open_bottom_door"):
        if name in form.fields:
            form.fields[name].required = False

    # در مرحلهٔ s1، فیلدهای کاغذ را اختیاری + empty_label + queryset کامل
    if stage == "s1":
        for fld in ("pq_glue_machine", "pq_be_flute", "pq_middle_layer", "pq_c_flute", "pq_bottom_layer"):
            if fld in form.fields:
                f = form.fields[fld]
                f.required = False
                f.empty_label = "---------"
                f.queryset = Paper.objects.all().order_by("name_paper")

    return form


# -----------------------------------------------------------------------------
# ابزار تاریخ جلالی (ایمن اگر jdatetime نصب نبود)
# -----------------------------------------------------------------------------
def _to_jalali(dt) -> str:
    if not dt:
        return "—"
    try:
        dt = timezone.localtime(dt)
    except Exception:
        pass
    try:
        import jdatetime  # type: ignore
        return jdatetime.datetime.fromgregorian(datetime=dt).strftime("%Y/%m/%d")
    except Exception:
        return dt.strftime("%Y-%m-%d")


def _today_jalali() -> str:
    try:
        import jdatetime  # type: ignore
        return jdatetime.datetime.now().strftime("%Y/%m/%d")
    except Exception:
        return timezone.localtime().strftime("%Y-%m-%d")


# -----------------------------------------------------------------------------
# ویو اصلی
# -----------------------------------------------------------------------------
def price_form_view(request) -> Any:
    """
    جریان دو مرحله‌ای:
      s1   : گرفتن A1..A4 و E15,G15,I15 ⇒ ساخت جدول (انتخاب | M24 | F24 | I22 | E28)
      final: بعد از انتخاب ردیف ⇒ محاسبات نهایی، هزینه‌ها، سود، مالیات، و نگاشت به مدل
    """
    print(">>> price_form_view:", request.method, "path=", request.path)
    logger.info("price_form_view start: method=%s path=%s", request.method, request.path)

    # ---------- تنظیمات + کانتکست پایه ----------
    bs = SettingsLoader.load_latest()
    ctx: Dict[str, Any] = {"settings": bs}
    copy_from = (request.GET.get("copy_from") or request.POST.get("copy_from") or "").strip()
    PROFIT_KW = "سود فاکتور"

    # ---------- هلسپرهای مشتری ----------
    def _get_customer_from_request(req):
        cid = req.GET.get("customer") or req.POST.get("customer")
        if not cid:
            return None
        try:
            cust = Customer.objects.get(pk=int(cid))  # بدون only → مقاوم
            print("DBG customer param=", cid, "found:", bool(cust))
            return cust
        except Exception as e:
            print("DBG customer fetch failed:", e)
            return None

    def _get_customer_from_request(req):
        """مشتری را از ?customer=<id> یا POST['customer'] می‌آورد (ایمن و بدون only)."""
        cid = req.GET.get("customer") or req.POST.get("customer")
        if not cid:
            return None
        try:
            cust = Customer.objects.get(pk=int(cid))
            # دیباگ اختیاری:
            # print("DBG customer:", cust.pk, str(cust))
            return cust
        except Exception:
            return None

    def _get_customer_phone(cust) -> str:
        """
        تلفن مشتری را برگردان:
        1) ابتدا میان فیلدهای رایج (contact_phone/phone/mobile/...) جست‌وجو می‌کند.
        2) اگر نبود، به‌صورت داینامیک هر فیلدی که نامش شامل phone/tel/«تلفن/موب» است را چک می‌کند.
        3) اگر باز هم نبود، از آخرین سفارش همان مشتری تلفن را برمی‌دارد.
        """
        if not cust:
            return ""

        # 1) فیلدهای رایج به‌ترتیب ترجیح
        common_fields = (
            "contact_phone", "phone", "mobile", "cell", "cellphone",
            "telephone", "tel", "phone_number", "mobile_number"
        )
        for fld in common_fields:
            if hasattr(cust, fld):
                v = getattr(cust, fld) or ""
                if isinstance(v, str) and v.strip():
                    return v.strip()

        # 2) جست‌وجوی داینامیک روی تمام اتربیوت‌های مدل (برای نام‌های سفارشی/فارسی)
        try:
            for name, val in vars(cust).items():
                # فقط رشته‌ها مهم‌اند
                if not isinstance(val, str):
                    continue
                lname = str(name).lower()
                if ("phone" in lname) or ("tel" in lname) or ("تلفن" in name) or ("موب" in name):
                    if val.strip():
                        return val.strip()
        except Exception:
            pass

        # 3) fallback: از آخرین سفارش همین مشتری
        try:
            last = (PriceQuotation.objects
                    .filter(customer_id=cust.id)
                    .exclude(contact_phone__isnull=True)
                    .exclude(contact_phone__exact="")
                    .order_by("-id")
                    .first())
            if last and last.contact_phone:
                return str(last.contact_phone).strip()
        except Exception:
            pass

        return ""

    # --- استفاده ---
    req_customer = _get_customer_from_request(request)

    # ---------- سازندهٔ امن فرم ----------
    def _build_form_safe(*, request, initial=None, stage="s1"):
        """
        تلاش می‌کند از _build_form پروژه استفاده کند؛ اگر signature آن پارامتر customer را نپذیرفت
        یا اصلاً موجود نبود، مستقیم PriceForm را می‌سازد.
        """
        # به فرم، خود آبجکت مشتری را هم پاس بده تا __init__ بتواند فیلتر کند
        try:
            return _build_form(request=request, initial=initial, stage=stage, customer=req_customer)
        except TypeError:
            try:
                return _build_form(request=request, initial=initial, stage=stage)
            except Exception:
                pass
        except NameError:
            pass

        if request.method == "POST":
            return PriceForm(request.POST, request.FILES, initial=initial, customer=req_customer)
        return PriceForm(initial=initial, customer=req_customer)

    def _truthy(v: Any) -> bool:
        return str(v).strip().lower() in {"1", "true", "t", "y", "yes", "on"}

    def _overheads_qs():
        return OverheadItem.objects.filter(is_active=True).order_by("name")

    def _selected_overhead_ids(req) -> set[int]:
        out: set[int] = set()
        for k in req.POST.keys():
            if k.startswith("oh_"):
                try:
                    out.add(int(k.split("_", 1)[1]))
                except Exception:
                    pass
        return out

    def _initial_from_order(src: PriceQuotation) -> dict:
        data = {
            "customer":        src.customer_id,
            "contact_phone":   src.contact_phone,
            "prepared_by":     src.prepared_by,
            "product_code":    src.product_code,
            "carton_type":     src.carton_type,
            "carton_name":     src.carton_name,
            "description":     src.description,
            "payment_type":    getattr(src, "payment_type", None),
            # پارامترها
            "I8_qty":           src.I8_qty or 1,
            "A1_layers":        src.A1_layers,
            "A2_pieces":        src.A2_pieces,
            "A3_door_type":     src.A3_door_type,
            "A4_door_count":    src.A4_door_count,
            "E15_len":          src.E15_len,
            "G15_wid":          src.G15_wid,
            "I15_hgt":          src.I15_hgt,
            "E17_lip":          src.E17_lip,
            "D31_flute":        src.D31_flute,
            "E46_round_adjust": src.E46_round_adjust,
            # کاغذها
            "pq_glue_machine":  src.pq_glue_machine_id,
            "pq_be_flute":      src.pq_be_flute_id,
            "pq_middle_layer":  src.pq_middle_layer_id,
            "pq_c_flute":       src.pq_c_flute_id,
            "pq_bottom_layer":  src.pq_bottom_layer_id,
            # «درب باز پایین»
            "open_bottom_door": getattr(src, "E18_lip", None),
            # کمک به فیلتر عرض ورق در فرم
            "chosen_sheet_width": getattr(src, "chosen_sheet_width", None),
        }
        for name in FLAG_FIELD_NAMES:
            if hasattr(src, name):
                data[name] = _truthy(getattr(src, name))
        if hasattr(src, "has_print_notes"):
            data["has_print_notes_bool"] = _truthy(getattr(src, "has_print_notes"))
        return data

    def _settlement_from_post() -> str:
        pay = (request.POST.get("settlement") or request.POST.get("payment_type") or "cash").strip().lower()
        return "credit" if pay == "credit" else "cash"

    def _seed_vars(cd: dict) -> dict[str, Any]:
        v: dict[str, Any] = {
            "A1": int(cd.get("A1_layers") or 0),
            "A2": int(cd.get("A2_pieces") or 0),
            "A3": int(cd.get("A3_door_type") or 0),
            "A4": int(cd.get("A4_door_count") or 0),
            "E15": as_num(cd.get("E15_len") or request.POST.get("E15_len"), 0.0),
            "G15": as_num(cd.get("G15_wid") or request.POST.get("G15_wid"), 0.0),
            "I15": as_num(cd.get("I15_hgt") or request.POST.get("I15_hgt"), 0.0),
            "I8":  as_num(cd.get("I8_qty"), 0.0),
            "E46": as_num(cd.get("E46_round_adjust"), 0.0),
            "E17": as_num(cd.get("E17_lip"), 0.0),
        }
        a6_str = f'{v["A1"]}{v["A2"]}{v["A3"]}{v["A4"]}'
        v["A6"] = int(a6_str) if a6_str.isdigit() else 0
        ctx["a6"] = a6_str
        return v

    # ---------- قفل از سفارش/مشتری ----------
    lock_initial: dict | None = None
    src_order: Optional[PriceQuotation] = None
    if copy_from.isdigit():
        src_order = PriceQuotation.objects.filter(pk=int(copy_from)).first()
        if src_order:
            lock_initial = {"customer": src_order.customer_id, "contact_phone": src_order.contact_phone}

    # اگر کپی از سفارش نداریم ولی customer داریم → قفل از مشتری
    if not lock_initial and req_customer:
        lock_initial = {
            "customer": req_customer.id,
            "contact_phone": _get_customer_phone(req_customer),
        }

    def _fill_last_order_context(customer_id: Optional[int]):
        ctx["today_jalali"] = _today_jalali()
        ctx["last_order_date_jalali"] = "—"
        ctx["last_order_fee"] = "—"
        ctx["last_order_price"] = "—"
        if not customer_id:
            return
        last = PriceQuotation.objects.filter(customer_id=customer_id).order_by("-id").first()
        if not last:
            return
        last_dt = None
        for fname in ("created", "created_at", "created_on", "timestamp", "created_datetime"):
            if hasattr(last, fname):
                last_dt = getattr(last, fname)
                if last_dt:
                    break
        ctx["last_order_date_jalali"] = _to_jalali(last_dt)
        fee = getattr(last, "Fee_amount", None)
        price = getattr(last, "E48_price_with_tax", None) or getattr(last, "H46_price_before_tax", None)
        if fee is not None:
            ctx["last_order_fee"] = fee
        if price is not None:
            ctx["last_order_price"] = price

    # ---------- 1) GET ----------
    if request.method != "POST":
        initial: dict = {
            "A1_layers": 1, "A2_pieces": 1, "A3_door_type": 1, "A4_door_count": 1,
            "payment_type": "cash",
            "has_print_notes": False,
            "tech_shipping_on_customer": False,
            "open_bottom_door": None,
        }
        if src_order:
            initial.update(_initial_from_order(src_order))
        if lock_initial:
            initial.update(lock_initial)

        form = _build_form_safe(request=request, initial=initial, stage="s1")
        _fill_last_order_context((lock_initial or {}).get("customer"))

        ctx.update({
            "form": form,
            "ui_stage": "s1",
            "show_table": False,
            "show_papers": False,
            "locked_customer": getattr(form, "display_customer", None),
            "locked_phone": form.initial.get("contact_phone") or "",
            "copy_from": copy_from,
            "overheads": _overheads_qs(),
            "overheads_checked": set(),
        })
        return render(request, "carton_pricing/price_form.html", ctx)

    # ---------- 2) POST ----------
    stage_vals = request.POST.getlist("stage")
    stage = (stage_vals[-1] if stage_vals else (request.POST.get("stage") or "s1")).strip().lower()

    form = _build_form_safe(request=request, initial=lock_initial, stage=stage)
    ctx.update({
        "form": form,
        "locked_customer": getattr(form, "display_customer", None),
        "locked_phone": form.initial.get("contact_phone") or "",
        "copy_from": copy_from,
        "overheads": _overheads_qs(),
        "overheads_checked": _selected_overhead_ids(request),
    })

    logger.debug("POST keys: %s", list(request.POST.keys()))
    print(">>> form.is_valid() ?", request.method, form.is_valid())
    if not form.is_valid():
        print(">>> form.errors =", dict(form.errors))
        logger.warning("price_form_view invalid form: %s", dict(form.errors))
        _fill_last_order_context((lock_initial or {}).get("customer"))
        ctx["errors"] = form.errors
        return render(request, "carton_pricing/price_form.html", ctx)

    cd = form.cleaned_data
    obj: PriceQuotation = form.save(commit=False)
    if lock_initial:
        if lock_initial.get("customer"):
            obj.customer_id = lock_initial["customer"]
        if "contact_phone" in lock_initial:
            obj.contact_phone = lock_initial["contact_phone"]

    # ---------- 3) متغیرها + تزریق تنظیمات ----------
    settlement = _settlement_from_post()
    ctx["settlement"] = settlement
    ctx["credit_days"] = int(as_num(request.POST.get("credit_days"), 0))

    var: Dict[str, Any] = _seed_vars(cd)
    obj.A6_sheet_code = var["A6"]
    try:
        SettingsLoader.inject(bs, settlement, var, cd)
    except Exception:
        pass

    # ---------- 4) فرمول‌ها ----------
    def compute_E17(tail: int, g15: float, cd: dict) -> float:
        return float(as_num(cd.get("E17_lip"), 0.0))

    def compute_I17(E15: float, G15: float) -> float:
        return float(E15 + G15 + 3.5)

    def compute_K15(I17: float, round_adjust: float, tail: int) -> float:
        return float(I17 + round_adjust)

    def compute_E20(E15: float, I15: float) -> float:
        return float(E15 + I15 + 3.5)

    def build_rows_for_widths(k15: float, widths: list[float], *, e20_len: float) -> list:
        out = []
        for w in widths:
            try:
                wf = float(w)
                kf = float(k15)
                f24 = int(max(0, math.floor(wf / kf))) if kf > 0 else 0
                i22 = float(wf - f24 * kf) if f24 > 0 else wf
                e28 = float((wf * float(e20_len)) / (f24 if f24 > 0 else 1))
                out.append(SimpleNamespace(sheet_width=wf, f24=f24, I22=i22, E28=e28))
            except Exception as e:
                logger.warning("row calc failed (w=%s): %r", w, e)
        return out

    def pick_best_default(rows: list) -> Optional[Any]:
        greens = [r for r in rows if (r.I22 is not None and 0 < float(r.I22) < 11)]
        if greens:
            return min(greens, key=lambda r: float(r.I22))
        nonnull = [r for r in rows if r.I22 is not None]
        if nonnull:
            return min(nonnull, key=lambda r: float(r.I22))
        return rows[0] if rows else None

    # ---------- محاسبات اولیه ----------
    tail = (var["A6"] % 100) if var["A6"] else 0
    var["E17"] = compute_E17(tail=tail, g15=as_num(var.get("G15"), 0.0), cd=cd)
    try:
        obj.E17_lip = q2(var["E17"], "0.01")
    except Exception:
        pass

    var["I17"] = compute_I17(E15=as_num(var.get("E15"), 0.0), G15=as_num(var.get("G15"), 0.0))
    var["K15"] = compute_K15(I17=as_num(var.get("I17"), 0.0), round_adjust=as_num(var.get("E46"), 0.0), tail=tail)
    e20_preview = compute_E20(E15=as_num(var.get("E15"), 0.0), I15=as_num(var.get("I15"), 0.0))

    logger.debug("DBG E17=%s I17=%s K15=%s E20_preview=%s", var["E17"], var["I17"], var["K15"], e20_preview)
    print(">>> DBG E17=", var["E17"], "I17=", var["I17"], "K15=", var["K15"], "E20_preview=", e20_preview)

    # ---------- 5) جدول مرحله ۱ ----------
    fixed_widths = (
        getattr(bs, "fixed_widths", None)
        or getattr(bs, "sheet_fixed_widths_mm", None)
        or [80, 90, 100, 110, 120, 125, 140]
    )
    fixed_widths = [float(x) for x in fixed_widths]
    rows = build_rows_for_widths(k15=float(var["K15"]), widths=fixed_widths, e20_len=float(e20_preview))

    best_default = pick_best_default(rows)
    default_sheet_choice = float(best_default.sheet_width) if best_default else None

    ctx["best_by_width"] = [r.__dict__ for r in rows]
    ctx["result_preview"] = {
        "K15": q2(as_num(var["K15"], 0.0), "0.01"),
        "E20": q2(as_num(e20_preview, 0.0), "0.01"),
        "K20": q2(0.0, "0.01"),
    }

    posted_choice = request.POST.get("sheet_choice")
    if posted_choice and posted_choice.strip():
        try:
            default_sheet_choice = float(posted_choice)
        except Exception:
            pass
    ctx["default_sheet_choice_str"] = None if default_sheet_choice is None else f"{default_sheet_choice:.2f}"

    _fill_last_order_context((lock_initial or {}).get("customer"))

    # ---------- 6) نمایش مرحله ۱ ----------
    if stage != "final":
        logger.info("render s1: rows=%s", len(rows))
        print(">>> RENDER s1 with rows:", len(rows))
        ctx.update({"ui_stage": "s1", "show_table": True, "show_papers": False})
        return render(request, "carton_pricing/price_form.html", ctx)

    # ---------- 7) مرحله نهایی ----------
    w_try = as_num_or_none((request.POST.get("sheet_choice") or "").strip())
    chosen = None
    if w_try is not None:
        chosen = next((r for r in rows if abs(r.sheet_width - w_try) < 1e-6), None)
    if chosen is None:
        chosen = best_default
    if not chosen or int(chosen.f24 or 0) <= 0:
        messages.error(request, "امکان محاسبۀ نهایی نیست: F24 معتبر انتخاب نشده.")
        ctx.update({"ui_stage": "s1", "show_table": True, "show_papers": False})
        return render(request, "carton_pricing/price_form.html", ctx)

    var["M24"] = float(chosen.sheet_width)
    var["sheet_width"] = float(chosen.sheet_width)
    var["F24"] = float(max(1, int(chosen.f24)))
    var["I22"] = float(chosen.I22 or 0.0)

    obj.chosen_sheet_width = q2(var["M24"], "0.01")
    obj.F24_per_sheet_count = int(var["F24"])
    obj.waste_warning = bool((chosen.I22 is not None) and chosen.I22 >= 11.0)
    obj.note_message = ""

    # K20 و E20
    var["K20"] = float(var["F24"]) * float(var["K15"])
    obj.K20_industrial_wid = q2(var["K20"], "0.01")

    var["E20"] = compute_E20(E15=as_num(var.get("E15"), 0.0), I15=as_num(var.get("I15"), 0.0))
    obj.E20_industrial_len = q2(var["E20"], "0.01")

    # مصرف هر قطعه (cm²)
    var["E28"] = float((var["sheet_width"] * var["E20"]) / (var["F24"] or 1.0))
    obj.E28_carton_consumption = q2(var["E28"], "0.0001")

    # تعداد ورق و متراژ کل
    qty_pcs = int(max(1, as_num(var.get("I8"), 0)))
    sheets_count = int(math.ceil(qty_pcs / var["F24"])) if var["F24"] else qty_pcs
    var["I38"] = sheets_count
    area_per_sheet_m2 = (var["sheet_width"] * var["E20"]) / 10000.0
    total_area_m2 = area_per_sheet_m2 * sheets_count
    var["E38"] = total_area_m2

    logger.debug(
        "FINAL rows: M24=%s F24=%s I22=%s E28=%s K20=%s I38=%s E38=%s",
        var["M24"], var["F24"], var["I22"], var["E28"], var["K20"], var["I38"], var["E38"]
    )
    print(">>> FINAL", "M24=", var["M24"], "F24=", var["F24"], "I22=", var["I22"], "E28=", var["E28"], "K20=", var["K20"])

    # ---------- 8) هزینه‌ها ----------
    def _price_from_choice(val) -> Decimal:
        if not val:
            return Decimal("0")
        try:
            if isinstance(val, Paper):
                return Decimal(val.unit_price or 0)
            p = Paper.objects.only("unit_price").get(pk=val)
            return Decimal(p.unit_price or 0)
        except Exception:
            return Decimal("0")

    fee_per_m2 = (
        _price_from_choice(cd.get("pq_glue_machine")) +
        _price_from_choice(cd.get("pq_be_flute")) +
        _price_from_choice(cd.get("pq_middle_layer")) +
        _price_from_choice(cd.get("pq_c_flute")) +
        _price_from_choice(cd.get("pq_bottom_layer"))
    ).quantize(Decimal("0.01"))
    var["Fee_amount"] = float(fee_per_m2)
    ctx["fee_amount"] = float(fee_per_m2)
    try:
        setattr(obj, "Fee_amount", fee_per_m2)
    except Exception:
        pass

    E38_m2 = Decimal(str(var.get("E38", 0.0)))
    E41_val = (fee_per_m2 * E38_m2).quantize(Decimal("0.01"))
    var["E41"] = float(E41_val)
    obj.E41_sheet_working_cost = E41_val

    selected_ids = ctx.get("overheads_checked") or set()
    oh_total_per_m2 = Decimal("0.00")
    try:
        agg = OverheadItem.objects.filter(is_active=True, id__in=list(selected_ids)).aggregate(sum_cost=Decimal("0.00"))
        oh_total_per_m2 = agg.get("sum_cost") or Decimal("0.00")
    except Exception:
        for it in OverheadItem.objects.filter(is_active=True, id__in=list(selected_ids)):
            oh_total_per_m2 += Decimal(str(it.unit_cost or 0))

    E40_val = (oh_total_per_m2 * E38_m2).quantize(Decimal("0.01"))
    var["E40"] = float(E40_val)
    obj.E40_overhead_cost = E40_val

    M40_final = (E41_val + E40_val).quantize(Decimal("0.01"))
    var["M40"] = float(M40_final)
    obj.M40_total_cost = M40_final

    def _profit_amount(base_amount: Decimal) -> Decimal:
        total = Decimal("0.00")
        for it in OverheadItem.objects.filter(is_active=True, name__icontains=PROFIT_KW):
            rate = Decimal(str(getattr(it, "unit_cost", 0) or 0))
            total += (base_amount * rate / Decimal("100"))
        for ch in ExtraCharge.objects.filter(is_active=True, title__icontains=PROFIT_KW):
            if ch.Percentage:
                rate = Decimal(str((ch.amount_credit if settlement == "credit" else ch.amount_cash) or 0))
                total += (base_amount * rate / Decimal("100"))
            else:
                total += Decimal(str((ch.amount_credit if settlement == "credit" else ch.amount_cash) or 0))
        return total.quantize(Decimal("0.01"))

    M41_val = _profit_amount(M40_final)
    var["M41"] = float(M41_val)
    obj.M41_profit_amount = M41_val

    H46_val = (M40_final + M41_val).quantize(Decimal("0.01"))
    var["H46"] = float(H46_val)
    obj.H46_price_before_tax = H46_val

    tax_percent = Decimal(str((getattr(bs, "custom_vars", {}) or {}).get("tax_percent", 9)))
    J48_val = (H46_val * tax_percent / Decimal("100")).quantize(Decimal("0.01"))
    var["J48"] = float(J48_val)
    obj.J48_tax = J48_val

    E48_val = (H46_val + J48_val).quantize(Decimal("0.01"))
    var["E48"] = float(E48_val)
    obj.E48_price_with_tax = E48_val

    obj.E38_sheet_area_m2 = q2(var.get("E38", 0.0), "0.0001")
    try:
        obj.I38_sheet_count = int(sheets_count)
    except Exception:
        pass

    # ---------- 9) ذخیرهٔ اختیاری ----------
    # 9) ذخیرهٔ اختیاری
    if cd.get("save_record"):
        with transaction.atomic():
            if getattr(obj, "E17_lip", None) in (None, ""):
                obj.E17_lip = q2(var["E17"], "0.01")
            try:
                bot = as_num_or_none(cd.get("open_bottom_door"))
                if bot is not None and hasattr(obj, "E18_lip"):
                    obj.E18_lip = q2(bot, "0.01")
            except Exception:
                pass
            obj.save()
        messages.success(request, "برگه قیمت ذخیره شد.")
        # ⬇️⬇️ اگر تیک خورده بود، مستقیم برو برای گرفتن شماره راهکاران
        return redirect("carton_pricing:link_rahkaran_invoice", pk=obj.pk)

    # ---------- 10) خروجی ----------
    ctx.update({
        "result": obj,
        "vars": var,
        "ui_stage": "final",
        "show_table": True,
        "show_papers": True,
        "result_preview": {
            "E20": obj.E20_industrial_len,
            "K20": obj.K20_industrial_wid,
            "K15": q2(as_num(var.get("K15"), 0.0), "0.01"),
        },
    })
    ctx["default_sheet_choice_str"] = None if default_sheet_choice is None else f"{default_sheet_choice:.2f}"

    logger.info(
        "render final: H46=%s E48=%s sheets=%s m2=%s",
        obj.H46_price_before_tax, obj.E48_price_with_tax, var.get("I38"), var.get("E38")
    )
    return render(request, "carton_pricing/price_form.html", ctx)


# carton_pricing/views_paper.py

# carton_pricing/views.py  (یا هرجایی که paper_* قبلاً بود)
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from .models import Paper
from .forms import PaperForm

def paper_list_view(request):
    papers = Paper.objects.select_related("group").order_by("name_paper")
    return render(request, "papers/paper_list.html", {"papers": papers})

def paper_create_view(request):
    form = PaperForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "کاغذ جدید ذخیره شد.")
        return redirect(reverse("carton_pricing:paper_list"))
    return render(request, "papers/paper_form.html", {"form": form, "mode": "create"})

def paper_update_view(request, pk: int):
    obj = get_object_or_404(Paper, pk=pk)
    form = PaperForm(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "کاغذ به‌روزرسانی شد.")
        return redirect(reverse("carton_pricing:paper_list"))
    return render(request, "papers/paper_form.html", {"form": form, "mode": "update", "object": obj})




from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from .forms import RahkaranInvoiceForm

def link_rahkaran_invoice(request, pk: int):
    quotation = get_object_or_404(PriceQuotation, pk=pk)

    if request.method == "POST":
        form = RahkaranInvoiceForm(request.POST)
        if form.is_valid():
            quotation.rahkaran_invoice_no = form.cleaned_data["invoice_no"].strip()
            quotation.save(update_fields=["rahkaran_invoice_no"])
            messages.success(request, "شماره فاکتور راهکاران ذخیره شد.")
            # مقصد دلخواهت:
            return redirect("/")   # ← روت سایت # یا جزئیات سفارش
    else:
        form = RahkaranInvoiceForm(initial={"invoice_no": quotation.rahkaran_invoice_no or ""})

    return render(request, "carton_pricing/link_rahkaran_invoice.html", {
        "form": form,
        "quotation": quotation,
        "title": "ثبت شماره فاکتور راهکاران",
    })
