# carton_pricing/views.py
# -*- coding: utf-8 -*-
from __future__ import annotations

# ───────────────────────── stdlib ─────────────────────────
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict
import math
import re

# ───────────────────────── Django ─────────────────────────
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.db import transaction
from django.shortcuts import render, redirect
from django.contrib import messages
from django.http import HttpRequest, HttpResponse

# ─────────────────────── App Imports ──────────────────────
from .models import BaseSettings, CalcFormula, Customer, PriceQuotation
from .forms import (
    BaseSettingsForm,
    CalcFormulaForm,
    CustomerForm,
    PhoneForm,
    PriceForm,
)
from .constants import VARIABLE_LABELS

# ابزارهای محاسباتی/فرمول
from .utils import (
    build_resolver,
    to_float,
    render_formula,
    compute_sheet_options,
    choose_per_sheet_and_width,
)

# تنظیمات/آداپتر (مصون‌سازی خروجی get_settings)
from .settings_api import get_settings as get_settings_external
from .helpers.settings_adapter import ensure_settings_model
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.core.paginator import Paginator
from django.db.models import Q

from .models import Paper
from .forms import PaperForm
# ─────────────────────── Helpers / Logger ─────────────────
def DBG(*parts: Any) -> None:
    """لاگ سبک برای توسعه."""
    try:
        msg = " ".join(str(p) for p in parts)
    except Exception:
        msg = " ".join(repr(p) for p in parts)
    print(msg)


def q2(val: float | Decimal, places: str) -> Decimal:
    """گرد کردن با ROUND_HALF_UP بر اساس قالب اعشاری places مثل '0.01'."""
    return Decimal(val).quantize(Decimal(places), rounding=ROUND_HALF_UP)


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

def as_num(x: Any, default: float = 0.0) -> float:
    v = as_num_or_none(x)
    return default if v is None else v


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
import math, re
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, Iterable, List, Optional

from django.contrib import messages
from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from .forms import PriceForm
from .models import BaseSettings, CalcFormula, PriceQuotation
from .settings_api import get_settings as get_settings_external
from .helpers.settings_adapter import ensure_settings_model
from .utils import (
    build_resolver,
    compute_sheet_options,
    choose_per_sheet_and_width,
    render_formula,
)

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

def price_form_view(request: HttpRequest) -> HttpResponse:
    """
    s1   : گرفتن A1..A4 و E15,G15,I15 ⇒ جدول (انتخاب | M24 | F24 | I22 | E28)
    final: بعد از انتخاب ردیف ⇒ محاسبات نهایی
    """
    # ───────── helpers ─────────
    PERSIAN_MAP = str.maketrans("۰۱۲۳۴۵۶۷۸۹٬٫،", "0123456789,,.")
    def _norm_num(x: Any) -> str:
        s = "" if x is None else str(x)
        return s.translate(PERSIAN_MAP).replace(",", "")
    def as_num_or_none(x: Any) -> float | None:
        try:
            if x is None: return None
            if isinstance(x, (int, float, Decimal)): return float(x)
            s = _norm_num(x).strip()
            if s in ("", "*"): return None
            return float(s)
        except Exception:
            return None
    def as_num(x: Any, default: float = 0.0) -> float:
        v = as_num_or_none(x)
        return default if v is None else v
    def q2(val: float | Decimal, places: str) -> Decimal:
        return Decimal(val).quantize(Decimal(places), rounding=ROUND_HALF_UP)

    # ───────── per-row calculators ─────────
    def _calc_e20_row(env_row: dict, formulas_raw: dict) -> float:
        env_local = dict(env_row)
        env_local.pop("E20", None)
        try:
            r, _e, f = build_resolver(formulas_raw, env_local)
            if "E20" in f:
                v = as_num_or_none(r("E20"))
                if v is not None:
                    return float(v)
        except Exception:
            pass
        A6  = int(as_num(env_local.get("A6"), 0))
        E15 = as_num(env_local.get("E15"), 0.0)
        G15 = as_num(env_local.get("G15"), 0.0)
        if E15 == 0 and G15 == 0: return 0.0
        if A6 == 2211:            return E15 + G15 + 3.5
        return (E15 + G15) * 2 + 3.5

    def _calc_e28_row(env_row: dict, formulas_raw: dict) -> float:
        env_local = dict(env_row)
        e20_row = _calc_e20_row(env_local, formulas_raw)
        env_local["E20"] = e20_row
        env_local.pop("E28", None)
        try:
            r, _e, f = build_resolver(formulas_raw, env_local)
            if "E28" in f:
                v = as_num_or_none(r("E28"))
                if v is not None:
                    return float(v)
        except Exception:
            pass
        F24 = as_num(env_local.get("F24"), 0.0)   # ← fix
        M24 = as_num(env_local.get("M24"), 0.0)
        return (e20_row * M24 / F24 / 10000.0) if (e20_row and F24) else 0.0

    # ───────── settings ─────────
    bs = BaseSettings.objects.order_by("-id").first() or BaseSettings.objects.create()
    ctx: Dict[str, Any] = {"settings": bs}

    # ───────── GET ─────────
    if request.method != "POST":
        form = PriceForm(initial={
            "A1_layers": 1, "A2_pieces": 1, "A3_door_type": 1, "A4_door_count": 1,
            "payment_type": "cash", "has_print_notes": False, "tech_shipping_on_customer": False,
        })
        form.fields["E17_lip"].required = False
        if "open_bottom_door" in form.fields:
            form.fields["open_bottom_door"].required = False
        ctx.update({"form": form, "ui_stage": "s1", "show_table": False, "show_papers": False})
        return render(request, "carton_pricing/price_form.html", ctx)

    # ───────── POST ─────────
    stage = (request.POST.get("stage") or "s1").strip().lower()
    form = PriceForm(request.POST)
    form.fields["E17_lip"].required = False
    if "open_bottom_door" in form.fields:
        form.fields["open_bottom_door"].required = False
    ctx["form"] = form
    if not form.is_valid():
        ctx["errors"] = form.errors
        return render(request, "carton_pricing/price_form.html", ctx)

    cd  = form.cleaned_data
    obj: PriceQuotation = form.save(commit=False)

    # ───────── settlement ─────────
    settlement = ("credit" if (request.POST.get("settlement") or cd.get("payment_type") or "cash").strip().lower() == "credit" else "cash")
    credit_days = int(as_num(request.POST.get("credit_days"), 0))
    ctx["settlement"]  = settlement
    ctx["credit_days"] = credit_days

    # ───────── seed vars ─────────
    FIELD_TO_VAR = {
        "E15_len": "E15", "G15_wid": "G15", "I15_hgt": "I15",
        "I8_qty": "I8", "E17_lip": "E17", "E46_round_adjust": "E46",
        "A1_layers": "A1", "A2_pieces": "A2", "A3_door_type": "A3", "A4_door_count": "A4",
    }
    VAR_TO_FIELD = {v: k for k, v in FIELD_TO_VAR.items()}

    MIN_REQUIRED = ["A1_layers","A2_pieces","A3_door_type","A4_door_count","E15_len","G15_wid","I15_hgt"]
    if any(as_num(cd.get(f), 0) <= 0 for f in MIN_REQUIRED):
        messages.warning(request, "برای ساخت جدول، مقادیر A1,A2,A3,A4 و E15,G15,I15 را کامل وارد کنید.")
        ctx.update({"ui_stage": "s1", "show_table": False, "show_papers": False})
        return render(request, "carton_pricing/price_form.html", ctx)

    var: Dict[str, Any] = {v: as_num(cd.get(f), 0.0) for f, v in FIELD_TO_VAR.items() if f in cd}
    var["A1"] = int(cd.get("A1_layers") or 0)
    var["A2"] = int(cd.get("A2_pieces") or 0)
    var["A3"] = int(cd.get("A3_door_type") or 0)
    var["A4"] = int(cd.get("A4_door_count") or 0)
    a6_str    = f'{var["A1"]}{var["A2"]}{var["A3"]}{var["A4"]}'
    var["A6"] = int(a6_str) if a6_str.isdigit() else 0
    ctx["a6"] = a6_str
    obj.A6_sheet_code = var["A6"]

    # ───────── inject settings ─────────
    def _fill_from_settings(bs: BaseSettings, settlement: str, var: dict, cd: dict|None=None):
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
            try: e46 = as_num((bs.custom_vars or {}).get("E46"), 0.0)
            except Exception: e46 = 0.0
        var["E46"] = e46

        fee = var["M33"] if settlement == "credit" else var["M31"]
        if fee <= 0:
            try: fee = as_num((bs.custom_vars or {}).get("Fee_amount"), 0.0)
            except Exception: fee = 0.0
        if fee <= 0: fee = 1.0
        var["sheet_price"] = fee
        var["Fee_amount"]  = fee

    _fill_from_settings(bs, settlement, var, cd)

    obj.I41_profit_rate = Decimal(str(var["I41"]))
    obj.E43_shipping    = Decimal(str(var["E43"]))
    obj.H43_pallet      = Decimal(str(var["H43"]))
    obj.J43_interface   = Decimal(str(var["J43"]))

    # ───────── resolver ─────────
    formulas_raw = {cf.key: str(cf.expression or "") for cf in CalcFormula.objects.all()}
    token_re = re.compile(r"\b([A-Z]+[0-9]+)\b")
    for t in {tok for e in formulas_raw.values() for tok in token_re.findall(e or "")}:
        if t not in var and t in VAR_TO_FIELD:
            var[t] = as_num(cd.get(VAR_TO_FIELD[t]), 0.0)
    for k in ("E17","I17","K15","E20","K20","F24","M24","sheet_width","I22","E28"):
        var.setdefault(k, 0.0)

    resolve, env, formulas_py = build_resolver(formulas_raw, var)
    def _sr(key: str):
        if key not in formulas_py: return None
        try: return resolve(key)
        except Exception: return None

    # ───────── E17 ─────────
    tail      = (var["A6"] % 100) if var["A6"] else 0
    g15_val   = as_num(cd.get("G15_wid"), 0.0)
    e17_top   = as_num_or_none(cd.get("E17_lip"))
    e17_bot   = as_num_or_none(cd.get("open_bottom_door"))

    if tail in (11, 12):  # باز/نامتوازن
        top_v = 0.0 if e17_top is None else float(e17_top)
        bot_v = 0.0 if e17_bot is None else float(e17_bot)
        if stage == "final" and (e17_top is None or e17_bot is None):
            if e17_top is None: form.add_error("E17_lip", "لب درب بالا برای این حالت الزامی است.")
            if e17_bot is None: form.add_error("open_bottom_door", "درب باز پایین برای این حالت الزامی است.")
            ctx["errors"] = form.errors
            ctx.update({"ui_stage": "s1", "show_table": False, "show_papers": False})
            return render(request, "carton_pricing/price_form.html", ctx)
        var["E17"] = top_v + bot_v
    elif tail in (21, 22):
        var["E17"] = g15_val / 2.0
    elif tail in (31, 32):
        var["E17"] = g15_val
    else:
        e17_calc = _sr("E17")
        var["E17"] = as_num(e17_calc, 0.0)

    # جلوگیری از NOT NULL
    try: obj.E17_lip = q2(var["E17"], "0.01")
    except Exception: pass

    # ───────── K15 / I17 ─────────
    resolve, env, formulas_py = build_resolver(formulas_raw, {**env, **var})
    var["I17"] = as_num(_sr("I17"), 0.0) if "I17" in formulas_py else as_num(var.get("E15"),0.0) + as_num(var.get("G15"),0.0) + 3.5

    # 1) خروجی فرمول DB
    k15_val = as_num(_sr("K15"), 0.0)

    # 2) منطق دستی مطمئن (fallback)
    coef = 2 if (tail % 10) == 1 else 1
    if tail in (11, 12):
        k15_logic = max(0.0, var["I17"] * coef + as_num(var.get("I15"), 0.0))
    elif tail in (21, 22, 31, 32):
        k15_logic = max(0.0, as_num(var.get("E17"), 0.0) * coef + as_num(var.get("I15"), 0.0))
    else:
        k15_logic = max(
            as_num(var.get("E17"), 0.0) * 2 + as_num(var.get("I15"), 0.0),
            var["I17"] * 2 + as_num(var.get("I15"), 0.0),
        )

    # 3) اگر K15 فرمولی نامعتبر/خیلی بزرگ بود، از fallback استفاده کن و در نهایت clamp
    fixed_widths = bs.fixed_widths or [80, 90, 100, 110, 120, 125, 140]
    try:
        max_w = float(max(float(w) for w in fixed_widths))
    except Exception:
        max_w = 140.0

    if (not math.isfinite(k15_val)) or k15_val <= 0 or k15_val > max_w:
        k15_val = k15_logic

    # clamp نهایی
    k15_val = min(k15_val, max_w)
    var["K15"] = k15_val

    # پیش‌نمایش E20
    var["E20"] = as_num(var.get("E20") or _sr("E20"), 0.0)

    # ───────── جدول مرحله ۱ ─────────
    def _rows_for_table(k15: float, widths: list[float], base_env: dict) -> list[dict]:
        rows: list[dict] = []
        k15v = float(k15 or 0.0)

        ws: list[float] = []
        for w in widths or []:
            try:
                v = float(w)
                if v > 0: ws.append(v)
            except Exception:
                pass
        ws = sorted(set(ws))

        if k15v <= 0:
            for w in ws:
                rows.append({"sheet_width": float(w), "f24": 0, "I22": None, "E28": None})
            return rows

        for w in ws:
            f = int(min(30, math.floor((w + 1e-9) / k15v)))
            if f <= 0:
                rows.append({"sheet_width": float(w), "f24": 0, "I22": None, "E28": None})
                continue

            waste   = w - (k15v * f)
            row_env = {**base_env, "M24": float(w), "sheet_width": float(w), "F24": float(f)}

            e20_row = _calc_e20_row(row_env, formulas_raw)
            row_env["E20"] = e20_row
            e28_row = _calc_e28_row(row_env, formulas_raw)

            rows.append({
                "sheet_width": float(w),
                "f24": int(f),
                "I22": round(float(waste), 2),
                "E28": round(float(e28_row), 4),
            })
        return rows

    base_env = {**env, **var}
    rows = _rows_for_table(k15=float(var["K15"]), widths=fixed_widths, base_env=base_env)
    ctx["best_by_width"] = rows

    # پیش‌نمایش
    e20_preview = _calc_e20_row(base_env, formulas_raw)
    k20_preview = as_num(_sr("K20"), 0.0)
    if k20_preview <= 0 and rows:
        k20_preview = as_num(var.get("K15"), 0.0) * float(rows[0]["f24"])
    ctx["result_preview"] = {
        "K15": q2(as_num(var.get("K15"), 0.0), "0.01"),
        "E20": q2(as_num(e20_preview, 0.0), "0.01"),
        "K20": q2(k20_preview, "0.01"),
    }

    if stage != "final":
        ctx.update({"ui_stage": "s1", "show_table": True, "show_papers": False})
        return render(request, "carton_pricing/price_form.html", ctx)

    # ───────── مرحله ۲ ─────────
    picked_raw = (request.POST.get("sheet_choice") or "").strip()
    chosen = None
    w_try = as_num_or_none(picked_raw)
    if w_try is not None:
        chosen = next((r for r in rows if abs(r["sheet_width"] - w_try) < 1e-6), None)
    if chosen is None and rows:
        chosen = rows[0]
    if not chosen or int(chosen.get("f24") or 0) <= 0:
        messages.error(request, "امکان محاسبۀ نهایی نیست: F24 معتبر انتخاب نشده.")
        ctx.update({"ui_stage": "s1", "show_table": True, "show_papers": False})
        return render(request, "carton_pricing/price_form.html", ctx)

    var["M24"]         = float(chosen["sheet_width"])
    var["sheet_width"] = float(chosen["sheet_width"])
    var["F24"]         = float(max(1, int(chosen["f24"])))
    var["I22"]         = float(chosen["I22"] or 0.0)
    var["E28"]         = float(chosen["E28"] or 0.0)

    obj.chosen_sheet_width  = q2(var["M24"], "0.01")
    obj.F24_per_sheet_count = int(var["F24"])
    obj.waste_warning       = bool((chosen.get("I22") is not None) and chosen["I22"] >= 11.0)
    obj.note_message        = ""

    for k in ("F24","M24","sheet_width","I22","E28"):
        formulas_py.pop(k, None)

    resolve, env, formulas_py = build_resolver(formulas_raw, {**env, **var})
    def _sr2(key: str):
        if key not in formulas_py: return None
        try: return resolve(key)
        except Exception: return None

    k20_val = as_num(_sr2("K20"), 0.0) if "K20" in formulas_py else 0.0
    if k20_val <= 0:
        k20_val = as_num(var.get("F24"), 0.0) * as_num(var.get("K15"), 0.0)
    var["K20"] = k20_val
    obj.K20_industrial_wid = q2(k20_val, "0.01")
    formulas_py.pop("K20", None)

    BLOCK = {"E17","K15","F24","M24","sheet_width","I22","E28","K20"}
    for _ in range(8):
        changed = False
        for key in list(formulas_py.keys()):
            if key in BLOCK: continue
            v = _sr2(key); num = as_num_or_none(v)
            if num is not None and abs(num - as_num(var.get(key), 0.0)) > 1e-9:
                var[key] = num; changed = True
        if not changed: break

    var["E20"] = as_num(var.get("E20") or _sr2("E20"), 0.0)
    obj.E20_industrial_len = q2(var["E20"], "0.01")

    base_fee = as_num(var.get("sheet_price"), 0.0)
    if base_fee <= 0:
        base_fee = as_num(bs.sheet_price_credit if settlement == "credit" else bs.sheet_price_cash, 0.0)
        if base_fee <= 0:
            try: base_fee = as_num((bs.custom_vars or {}).get("Fee_amount"), 1.0)
            except Exception: base_fee = 1.0
    var["Fee_amount"] = float(base_fee)
    ctx["fee_amount"] = float(base_fee)
    try: setattr(obj, "Fee_amount", Decimal(str(var["Fee_amount"])))
    except Exception: pass

    obj.E28_carton_consumption = q2(var.get("E28", 0.0), "0.0001")
    obj.E38_sheet_area_m2      = q2(var.get("E38", 0.0), "0.0001")
    obj.I38_sheet_count        = int(math.ceil(var.get("I38", 0.0)))
    obj.E41_sheet_working_cost = q2(var.get("E41", 0.0), "0.01")
    obj.E40_overhead_cost      = q2(var.get("E40", 0.0), "0.01")
    obj.M40_total_cost         = q2(var.get("M40", 0.0), "0.01")
    obj.M41_profit_amount      = q2(var.get("M41", 0.0), "0.01")
    obj.H46_price_before_tax   = q2(var.get("H46", 0.0), "0.01")
    obj.J48_tax                = q2(var.get("J48", 0.0), "0.01")
    obj.E48_price_with_tax     = q2(var.get("E48", 0.0), "0.01")

    if cd.get("save_record"):
        with transaction.atomic():
            if getattr(obj, "E17_lip", None) in (None, ""):
                obj.E17_lip = q2(var["E17"], "0.01")
            if hasattr(obj, "open_bottom_door") and e17_bot is not None:
                try: obj.open_bottom_door = q2(float(e17_bot), "0.01")
                except Exception: pass
            obj.save()
        messages.success(request, "برگه قیمت ذخیره شد.")

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
    return render(request, "carton_pricing/price_form.html", ctx)

# carton_pricing/views_paper.py


def paper_list_view(request):
    q = (request.GET.get("q") or "").strip()
    qs = Paper.objects.all()
    if q:
        qs = qs.filter(Q(name_paper__icontains=q))
    qs = qs.order_by("name_paper")

    paginator = Paginator(qs, 20)
    page = request.GET.get("page")
    page_obj = paginator.get_page(page)

    return render(request, "carton_pricing/paper_list.html", {
        "page_obj": page_obj,
        "q": q,
    })

def paper_create_view(request):
    if request.method == "POST":
        form = PaperForm(request.POST)
        if form.is_valid():
            obj = form.save()
            messages.success(request, f"کاغذ «{obj.name_paper}» با موفقیت ثبت شد.")
            return redirect(reverse("carton_pricing:paper_list"))
    else:
        form = PaperForm()
    return render(request, "carton_pricing/paper_form.html", {"form": form, "mode": "create"})

def paper_update_view(request, pk: int):
    obj = get_object_or_404(Paper, pk=pk)
    if request.method == "POST":
        form = PaperForm(request.POST, instance=obj)
        if form.is_valid():
            obj = form.save()
            messages.success(request, f"کاغذ «{obj.name_paper}» به‌روزرسانی شد.")
            return redirect(reverse("carton_pricing:paper_list"))
    else:
        form = PaperForm(instance=obj)
    return render(request, "carton_pricing/paper_form.html", {"form": form, "mode": "edit", "obj": obj})
