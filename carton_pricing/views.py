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

def best_for_each_width(
    k15: float,
    widths: Iterable[float],
    fmax: int = 30,
    *,
    waste_min: float = 0.0,   # سبز وقتی 0<waste<11
    waste_max: float = 11.0,
    sort_widths: bool = True,
) -> List[Dict]:
    """
    برای هر عرضِ ثابت w، بزرگ‌ترین F (<= fmax) را پیدا می‌کند که F*k15 <= w باشد.
    خروجی برای هر w: dict با کلیدهای sheet_width, f24, need, waste, ok
    """
    try:
        k15_val = float(k15)
    except Exception:
        k15_val = 0.0

    clean_widths: List[float] = []
    for w in widths or []:
        try:
            v = float(w)
            if v > 0:
                clean_widths.append(v)
        except Exception:
            continue
    if sort_widths:
        clean_widths.sort()

    rows: List[Dict] = []
    if k15_val <= 0 or not clean_widths:
        for w in clean_widths:
            rows.append({"sheet_width": float(w), "f24": 0, "need": None, "waste": None, "ok": False})
        return rows

    for w in clean_widths:
        best_f: Optional[int] = None
        best_need: Optional[float] = None
        best_waste: Optional[float] = None

        for f in range(int(fmax), 0, -1):
            need = f * k15_val
            if need <= w + 1e-9:
                best_f = f
                best_need = need
                best_waste = w - need
                break

        if best_f is None:
            rows.append({"sheet_width": float(w), "f24": 0, "need": None, "waste": None, "ok": False})
            continue

        waste = float(best_waste or 0.0)
        ok = (waste > waste_min) and (waste < waste_max)

        rows.append({
            "sheet_width": float(w),
            "f24": int(best_f),
            "need": round(float(best_need or 0.0), 2),
            "waste": round(waste, 2),
            "ok": ok,
        })
    return rows
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

# ───────────────────────── the view ─────────────────────────
# ───────────────────────── the view ─────────────────────────
# def price_form_view(request: HttpRequest) -> HttpResponse:
#     """
#     فرم قیمت: محاسبهٔ فرمول‌ها + پیشنهاد/انتخاب عرض ورق
#     """
#
#     # ── Helpers ─────────────────────────────────────────
#     def as_num_or_none(x: Any) -> float | None:
#         if x is None:
#             return None
#         if isinstance(x, (int, float, Decimal)):
#             return float(x)
#         s = _normalize_num_text(x)
#         if s in ("", "*"):
#             return None
#         try:
#             return float(s)
#         except Exception:
#             return None
#
#     def as_num(x: Any, default: float = 0.0) -> float:
#         v = as_num_or_none(x)
#         return default if v is None else v
#
#     def best_for_each_width(k15: float, widths: list[float], fmax: int = 30) -> list[dict]:
#         """
#         برای هر عرضِ w، بزرگ‌ترین F<=fmax که F*k15 <= w باشد را می‌یابد.
#         خروجی: [{sheet_width, f24, need, waste, ok}]
#         """
#         ws = sorted({float(w) for w in widths if w and float(w) > 0})
#         try:
#             k15v = float(k15)
#         except Exception:
#             k15v = 0.0
#
#         rows: list[dict] = []
#         if k15v <= 0:
#             for w in ws:
#                 rows.append({"sheet_width": w, "f24": 0, "need": None, "waste": None, "ok": False})
#             return rows
#
#         for w in ws:
#             best_f = None; best_need = None; best_waste = None
#             for f in range(int(fmax), 0, -1):
#                 need = f * k15v
#                 if need <= w + 1e-9:
#                     best_f, best_need, best_waste = f, need, w - need
#                     break
#             if best_f is None:
#                 rows.append({"sheet_width": w, "f24": 0, "need": None, "waste": None, "ok": False})
#             else:
#                 waste = float(best_waste or 0.0)
#                 rows.append({
#                     "sheet_width": w,
#                     "f24": int(best_f),
#                     "need": round(float(best_need or 0.0), 2),
#                     "waste": round(waste, 2),
#                     "ok": (0.0 < waste < 11.0),
#                 })
#         return rows
#
#     # ── Mapping fields ↔ variables ─────────────────────
#     FIELD_TO_VAR: Dict[str, str] = {
#         "E15_len": "E15",
#         "G15_wid": "G15",
#         "I15_hgt": "I15",
#         "I8_qty":  "I8",
#         "E17_lip": "E17",             # فقط fallback
#         "E46_round_adjust": "E46",
#         "A1_layers": "A1",
#         "A2_pieces": "A2",
#         "A3_door_type": "A3",
#         "A4_door_count": "A4",
#     }
#     VAR_TO_FIELD = {v: k for k, v in FIELD_TO_VAR.items()}
#
#     # ── Settings & context ─────────────────────────────
#     bs: BaseSettings = ensure_settings_model(get_settings_external())
#     context: Dict[str, Any] = {"settings": bs}
#
#     # ── GET ────────────────────────────────────────────
#     if request.method != "POST":
#         form = PriceForm(initial={
#             "A1_layers": 1, "A2_pieces": 1, "A3_door_type": 1, "A4_door_count": 1,
#             "payment_type": "cash",
#         })
#         form.fields["E17_lip"].required = False
#         context["form"] = form
#         return render(request, "carton_pricing/price_form.html", context)
#
#     # ── POST ───────────────────────────────────────────
#     form = PriceForm(request.POST)
#     form.fields["E17_lip"].required = False
#     context["form"] = form
#     if not form.is_valid():
#         context["errors"] = form.errors
#         return render(request, "carton_pricing/price_form.html", context)
#
#     obj: PriceQuotation = form.save(commit=False)
#     cd = form.cleaned_data
#
#     # ── Seed vars از فرم/ستینگ ─────────────────────────
#     seed_vars: Dict[str, Any] = {}
#     for field, varname in FIELD_TO_VAR.items():
#         if field in cd:
#             seed_vars[varname] = as_num(cd.get(field), 0.0)
#
#     seed_vars["A1"] = int(cd.get("A1_layers") or 0)
#     seed_vars["A2"] = int(cd.get("A2_pieces") or 0)
#     seed_vars["A3"] = int(cd.get("A3_door_type") or 0)
#     seed_vars["A4"] = int(cd.get("A4_door_count") or 0)
#     a6_str = f"{seed_vars['A1']}{seed_vars['A2']}{seed_vars['A3']}{seed_vars['A4']}"
#     seed_vars["A6"] = int(a6_str) if a6_str.isdigit() else 0
#     context["a6"] = a6_str
#     obj.A6_sheet_code = seed_vars["A6"]
#
#     seed_vars["I41"] = as_num(bs.profit_rate_percent, 0.0)
#     seed_vars["J43"] = as_num(bs.interface_cost, 0.0)
#     seed_vars["H43"] = as_num(bs.pallet_cost, 0.0)
#     seed_vars["E43"] = as_num(bs.shipping_cost, 0.0)
#     seed_vars["M30"] = as_num(bs.overhead_per_meter, 0.0)
#     seed_vars["sheet_price"] = float(
#         bs.sheet_price_cash if cd.get("payment_type") == "cash" else bs.sheet_price_credit
#     )
#     obj.I41_profit_rate = Decimal(bs.profit_rate_percent or 0)
#     obj.E43_shipping    = Decimal(bs.shipping_cost or 0)
#     obj.H43_pallet      = Decimal(bs.pallet_cost or 0)
#     obj.J43_interface   = Decimal(bs.interface_cost or 0)
#
#     # ── ساخت Resolver ─────────────────────────────────
#     formulas_raw = {cf.key: str(cf.expression or "") for cf in CalcFormula.objects.all()}
#     token_re = re.compile(r"\b([A-Z]+[0-9]+)\b")
#     for token in {t for expr in formulas_raw.values() for t in token_re.findall(expr or "")}:
#         if token not in seed_vars and token in VAR_TO_FIELD:
#             seed_vars[token] = as_num(cd.get(VAR_TO_FIELD[token]), 0.0)
#
#     for k in ("E17", "I17", "F24", "sheet_width", "M24"):
#         seed_vars.setdefault(k, 0.0)
#
#     resolve, var, formulas_py = build_resolver(formulas_raw, seed_vars)
#     var.update(seed_vars)
#     context["debug_formulas"] = {k: render_formula(expr, seed_vars) for k, expr in formulas_py.items()}
#
#     def safe_resolve(key: str):
#         if key not in formulas_py:
#             return None
#         try:
#             return resolve(key)
#         except Exception as ex:
#             DBG(f"[EVAL:{key}] error={ex}")
#             return None
#
#     # ── تثبیت E17 → I17 → K15 ─────────────────────────
#     tail = seed_vars["A6"] % 100 if seed_vars["A6"] else 0
#     g15  = float(seed_vars.get("G15", 0.0))
#
#     if tail in (11, 12):
#         e17_manual = as_num_or_none(cd.get("E17_lip"))
#         if not e17_manual:
#             form.add_error("E17_lip", "این فیلد برای حالت‌های انتهایی 11 یا 12 در A6 الزامی است.")
#             context["errors"] = form.errors
#             return render(request, "carton_pricing/price_form.html", context)
#         var["E17"] = float(e17_manual)
#     else:
#         num_e17 = as_num_or_none(safe_resolve("E17"))
#         if num_e17:
#             var["E17"] = float(num_e17)
#         elif g15 > 0 and tail in (21, 22):
#             var["E17"] = g15 / 2.0
#         elif g15 > 0 and tail in (31, 32):
#             var["E17"] = g15
#         else:
#             var["E17"] = as_num(cd.get("E17_lip"), 0.0)
#
#     seed_vars["E17"] = float(var["E17"])
#     var.update(seed_vars)
#     if "I17" in formulas_py:
#         var["I17"] = as_num(safe_resolve("I17"), 0.0)
#     if "K15" in formulas_py:
#         var["K15"] = as_num(safe_resolve("K15"), 0.0)
#
#     # ارزیابی چندمرحله‌ای
#     for _ in range(5):
#         changed = False
#         for key in formulas_py.keys():
#             if key in ("E17", "K15"):
#                 continue
#             num = as_num_or_none(safe_resolve(key))
#             if num is not None and abs(var.get(key, 0.0) - num) > 1e-9:
#                 var[key] = num
#                 changed = True
#         if not changed:
#             break
#
#     # ── پیشنهاد/انتخاب عرض ورق ─────────────────────────
#     try:
#         var["E20"] = as_num(var.get("E20") or safe_resolve("E20"), 0.0)
#         var["K20"] = as_num(var.get("K20") or safe_resolve("K20"), 0.0)
#         obj.E20_industrial_len = q2(var["E20"], "0.01")
#         obj.K20_industrial_wid = q2(var["K20"], "0.01")
#
#         required_w = var["K20"]
#         fixed_widths_all = [80, 90, 100, 110, 120, 125, 140]
#
#         k15_val = float(var.get("K15", 0.0))
#         context["best_by_width"] = best_for_each_width(k15_val, fixed_widths_all)
#         context["result_preview"] = {
#             "E20": q2(var["E20"], "0.01"),
#             "K20": q2(required_w, "0.01"),
#             "K15": q2(k15_val, "0.01"),
#         }
#
#         picked = as_num(request.POST.get("sheet_choice"), 0.0)
#         if picked and any(abs(picked - w) < 1e-6 for w in fixed_widths_all):
#             # ردیف انتخابی کاربر از جدول best_by_width
#             chosen_row = next((r for r in context["best_by_width"]
#                                if abs(r["sheet_width"] - picked) < 1e-6), None)
#
#             chosen_w = picked
#             var["M24"] = float(chosen_w)              # ← M24 = عرض انتخابی
#
#             if chosen_row:
#                 # ← F24 را دقیقاً از ستون جدول بگیر
#                 obj.F24_per_sheet_count = int(chosen_row["f24"])
#                 var["F24"] = float(chosen_row["f24"])  # ← F24 = مقدار ستون F24 (≤30)
#
#                 waste_txt = "—" if chosen_row["waste"] is None else f"{chosen_row['waste']:.2f}cm"
#                 need_txt  = "—" if chosen_row["need"]  is None else f"{chosen_row['need']:.2f}cm"
#                 context["chosen_summary"] = (
#                     f"عرض ورق انتخابی: {int(round(chosen_row['sheet_width']))}cm | "
#                     f"F24: {chosen_row['f24']} | نیاز = F×K15: {need_txt} | دورریز: {waste_txt}"
#                 )
#                 obj.waste_warning = (chosen_row["waste"] is not None and chosen_row["waste"] >= 11.0)
#                 obj.note_message = ""
#             else:
#                 # اگر به هر دلیل ردیف پیدا نشد، به الگوریتم fallback برگرد
#                 count, chosen_w, waste, warn, note = choose_per_sheet_and_width(
#                     required_width_cm=required_w,
#                     fixed_widths=fixed_widths_all,
#                     max_waste_cm=11.0,
#                     e20_len_cm=var["E20"],
#                 )
#                 obj.F24_per_sheet_count = max(1, int(count))
#                 var["F24"] = float(obj.F24_per_sheet_count)
#                 obj.waste_warning = bool(warn)
#                 obj.note_message = note
#
#             obj.chosen_sheet_width = q2(chosen_w, "0.01")
#
#         else:
#             # انتخاب نشده → بهترین حالت خودکار
#             count, chosen_w, waste, warn, note = choose_per_sheet_and_width(
#                 required_width_cm=required_w,
#                 fixed_widths=fixed_widths_all,
#                 max_waste_cm=11.0,
#                 e20_len_cm=var["E20"],
#             )
#             obj.F24_per_sheet_count = max(1, int(count))
#             obj.chosen_sheet_width  = q2(chosen_w, "0.01")
#             obj.waste_warning       = bool(warn)
#             obj.note_message        = note
#             var["M24"] = float(chosen_w)              # ← M24
#             var["F24"] = float(obj.F24_per_sheet_count)  # ← F24
#
#         var["sheet_width"] = float(obj.chosen_sheet_width)
#
#         # ── خروجی‌های نهایی فرمول‌ها ─────────────────────
#         for key in ["E28","E38","I38","E41","E40","M40","M41","H46","J48","E48"]:
#             var[key] = as_num(safe_resolve(key), 0.0)
#
#         # نگاشت به مدل
#         obj.E28_carton_consumption = q2(var["E28"], "0.0001")
#         obj.E38_sheet_area_m2      = q2(var["E38"], "0.0001")
#         obj.I38_sheet_count        = int(math.ceil(var["I38"] or 0.0))
#         obj.E41_sheet_working_cost = q2(var["E41"], "0.01")
#         obj.E40_overhead_cost      = q2(var["E40"], "0.01")
#         obj.M40_total_cost         = q2(var["M40"], "0.01")
#         obj.M41_profit_amount      = q2(var["M41"], "0.01")
#         obj.H46_price_before_tax   = q2(var["H46"], "0.01")
#         obj.J48_tax                = q2(var["J48"], "0.01")
#         obj.E48_price_with_tax     = q2(var["E48"], "0.01")
#
#     except Exception as e:
#         context["errors"] = {"__all__": [str(e)]}
#         try:
#             context["vars"] = var
#         except Exception:
#             pass
#         return render(request, "carton_pricing/price_form.html", context)
#
#     # ── Save if requested ──────────────────────────────
#     if form.cleaned_data.get("save_record"):
#         with transaction.atomic():
#             obj.save()
#         messages.success(request, "برگه قیمت ذخیره شد.")
#
#     context.update({"result": obj, "vars": var})
#     return render(request, "carton_pricing/price_form.html", context)
def price_form_view(request: HttpRequest) -> HttpResponse:
    """
    فرم قیمت: محاسبه فرمول‌ها + پیشنهاد/انتخاب عرض ورق
    تعیین Fee_amount:
      - مستقیم از BaseSettings (M31 برای نقد، M33 برای مدت)
      - اگر صفر بود ⇒ fallback از آخرین BaseSettings غیرصفر
    """
    # ---------- Helpers ----------
    def _norm_num(x: Any) -> str:
        s = "" if x is None else str(x)
        return s.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٬٫،", "0123456789,.,")).replace(",", "")

    def as_num_or_none(x: Any) -> float | None:
        if x is None:
            return None
        if isinstance(x, (int, float, Decimal)):
            return float(x)
        s = _norm_num(x).strip()
        if s in ("", "*"):
            return None
        try:
            return float(s)
        except Exception:
            return None

    def as_num(x: Any, default: float = 0.0) -> float:
        v = as_num_or_none(x)
        return default if v is None else v

    def best_for_each_width(k15: float, widths: list[float], fmax: int = 30) -> list[dict]:
        ws = sorted({float(w) for w in widths if w and float(w) > 0})
        try:
            k15v = float(k15)
        except Exception:
            k15v = 0.0

        out: list[dict] = []
        if k15v <= 0:
            for w in ws:
                out.append({"sheet_width": w, "f24": 0, "need": None, "waste": None, "ok": False})
            return out

        for w in ws:
            best_f = None
            need = waste = None
            for f in range(int(fmax), 0, -1):
                need_f = f * k15v
                if need_f <= w + 1e-9:
                    best_f, need, waste = f, need_f, w - need_f
                    break
            out.append({
                "sheet_width": w,
                "f24": int(best_f or 0),
                "need": None if best_f is None else round(float(need), 2),
                "waste": None if best_f is None else round(float(waste), 2),
                "ok": (best_f is not None and 0.0 < float(waste) < 11.0),
            })
        return out

    # --- گرفتن آخرین فی معتبر از BaseSettings (fallback) ---
    def _get_latest_fee_amount(settlement: str, *, fallback_cash: float = 0.0, fallback_credit: float = 0.0) -> float:
        qs = BaseSettings.objects.all()
        fns = {f.name for f in BaseSettings._meta.fields}
        if "updated_at" in fns:
            qs = qs.order_by("-updated_at", "-id")
        elif "created_at" in fns:
            qs = qs.order_by("-created_at", "-id")
        else:
            qs = qs.order_by("-id")

        for row in qs:
            v = row.sheet_price_credit if settlement == "credit" else row.sheet_price_cash
            try:
                v = float(v or 0)
            except Exception:
                v = float(Decimal(v or 0))
            if v > 0:
                return v
        return float(fallback_credit if settlement == "credit" else fallback_cash)

    # --- تزریق مستقیم مقادیر تنظیمات به var (M30/M31/M33/I41/E43/H43/J43/E46 + sheet_price/Fee_amount) ---
    def fill_vars_from_settings(bs: BaseSettings, settlement: str, var: dict, cd: dict | None = None):
        def _f(x):
            if x is None:
                return 0.0
            try:
                return float(x)
            except Exception:
                return float(Decimal(str(x)) or 0)

        var["M30"] = _f(bs.overhead_per_meter)
        var["M31"] = _f(bs.sheet_price_cash)
        var["M33"] = _f(bs.sheet_price_credit)
        var["I41"] = _f(bs.profit_rate_percent)
        var["E43"] = _f(bs.shipping_cost)
        var["H43"] = _f(bs.pallet_cost)
        var["J43"] = _f(bs.interface_cost)

        # E46: اولویت با فرم، بعد custom_vars["E46"]
        e46 = None
        if cd:
            e46 = cd.get("E46") or cd.get("E46_round_adjust")
            try:
                e46 = float(e46)
            except Exception:
                e46 = None
        if e46 is None:
            try:
                e46 = float((bs.custom_vars or {}).get("E46", 0))
            except Exception:
                e46 = 0.0
        var["E46"] = 0.0 if e46 is None else e46

        var["sheet_price"] = var["M33"] if settlement == "credit" else var["M31"]
        var["Fee_amount"]  = var["sheet_price"]

    # --- مپ فرم ↔ توکن‌ها ---
    FIELD_TO_VAR = {
        "E15_len": "E15", "G15_wid": "G15", "I15_hgt": "I15",
        "I8_qty": "I8", "E17_lip": "E17", "E46_round_adjust": "E46",
        "A1_layers": "A1", "A2_pieces": "A2", "A3_door_type": "A3", "A4_door_count": "A4",
    }
    VAR_TO_FIELD = {v: k for k, v in FIELD_TO_VAR.items()}

    # ---------- Load settings (بدون همگام‌سازی خارجی) ----------
    bs: BaseSettings | None = BaseSettings.objects.order_by("-id").first()
    if bs is None:
        bs = BaseSettings.objects.create()
    context: Dict[str, Any] = {"settings": bs}

    # ---------- GET ----------
    if request.method != "POST":
        form = PriceForm(initial={
            "A1_layers": 1, "A2_pieces": 1, "A3_door_type": 1, "A4_door_count": 1,
            "payment_type": "cash",
            "has_print_notes": False,
            "tech_shipping_on_customer": False,
        })
        form.fields["E17_lip"].required = False
        context["form"] = form
        return render(request, "carton_pricing/price_form.html", context)

    # ---------- POST ----------
    form = PriceForm(request.POST)
    form.fields["E17_lip"].required = False
    context["form"] = form
    if not form.is_valid():
        context["errors"] = form.errors
        return render(request, "carton_pricing/price_form.html", context)

    obj: PriceQuotation = form.save(commit=False)
    cd = form.cleaned_data

    settlement_in = (request.POST.get("settlement") or cd.get("payment_type") or "cash").strip().lower()
    settlement = "credit" if settlement_in == "credit" else "cash"
    credit_days = int(as_num(request.POST.get("credit_days"), 0))

    # ---------- Seed vars ----------
    seed_vars: Dict[str, Any] = {}
    for f, v in FIELD_TO_VAR.items():
        if f in cd:
            seed_vars[v] = as_num(cd.get(f), 0.0)

    # A6
    seed_vars["A1"] = int(cd.get("A1_layers") or 0)
    seed_vars["A2"] = int(cd.get("A2_pieces") or 0)
    seed_vars["A3"] = int(cd.get("A3_door_type") or 0)
    seed_vars["A4"] = int(cd.get("A4_door_count") or 0)
    a6_str = f"{seed_vars['A1']}{seed_vars['A2']}{seed_vars['A3']}{seed_vars['A4']}"
    seed_vars["A6"] = int(a6_str) if a6_str.isdigit() else 0
    context["a6"] = a6_str
    obj.A6_sheet_code = seed_vars["A6"]

    # پر کردن مستقیم سلول‌ها و قیمت‌ها از تنظیمات
    fill_vars_from_settings(bs, settlement, seed_vars, cd)

    # کپی برخی ثابت‌ها به آبجکت
    obj.I41_profit_rate = Decimal(str(seed_vars["I41"]))
    obj.E43_shipping    = Decimal(str(seed_vars["E43"]))
    obj.H43_pallet      = Decimal(str(seed_vars["H43"]))
    obj.J43_interface   = Decimal(str(seed_vars["J43"]))

    # ---------- فرمول‌ها ----------
    formulas_raw = {cf.key: str(cf.expression or "") for cf in CalcFormula.objects.all()}
    token_re = re.compile(r"\b([A-Z]+[0-9]+)\b")
    for token in {t for e in formulas_raw.values() for t in token_re.findall(e or "")}:
        if token not in seed_vars and token in VAR_TO_FIELD:
            seed_vars[token] = as_num(cd.get(VAR_TO_FIELD[token]), 0.0)
    for k in ("E17", "I17", "F24", "sheet_width", "M24"):
        seed_vars.setdefault(k, 0.0)

    resolve, var, formulas_py = build_resolver(formulas_raw, seed_vars)
    var.update(seed_vars)

    # دوباره تنظیمات را داخل var هم می‌ریزیم تا حتماً override شود
    fill_vars_from_settings(bs, settlement, var, cd)

    context["debug_formulas"] = {k: render_formula(expr, seed_vars) for k, expr in formulas_py.items()}

    def safe_resolve(key: str):
        if key not in formulas_py:
            return None
        try:
            return resolve(key)
        except Exception as ex:
            DBG(f"[EVAL:{key}] {ex}")
            return None

    # تثبیت E17 → I17 → K15
    tail = seed_vars["A6"] % 100 if seed_vars["A6"] else 0
    g15 = float(seed_vars.get("G15", 0.0))
    if tail in (11, 12):
        e17_manual = as_num_or_none(cd.get("E17_lip"))
        if not e17_manual:
            form.add_error("E17_lip", "این فیلد برای حالت‌های 11/12 الزامی است.")
            context["errors"] = form.errors
            return render(request, "carton_pricing/price_form.html", context)
        var["E17"] = float(e17_manual)
    else:
        v_e17 = as_num_or_none(safe_resolve("E17"))
        if v_e17 is not None and v_e17 != 0:
            var["E17"] = float(v_e17)
        elif g15 > 0 and tail in (21, 22):
            var["E17"] = g15 / 2.0
        elif g15 > 0 and tail in (31, 32):
            var["E17"] = g15
        else:
            var["E17"] = as_num(cd.get("E17_lip"), 0.0)

    var["I17"] = as_num(safe_resolve("I17"), 0.0) if "I17" in formulas_py else var.get("I17", 0.0)
    var["K15"] = as_num(safe_resolve("K15"), 0.0) if "K15" in formulas_py else var.get("K15", 0.0)

    # چند پاس برای پایدارسازی
    for _ in range(5):
        changed = False
        for key in formulas_py.keys():
            if key in ("E17", "K15"):
                continue
            num = as_num_or_none(safe_resolve(key))
            if num is not None and abs(var.get(key, 0.0) - num) > 1e-9:
                var[key] = num
                changed = True
        if not changed:
            break

    # ---------- پیشنهاد/انتخاب عرض ورق ----------
    try:
        var["E20"] = as_num(var.get("E20") or safe_resolve("E20"), 0.0)
        var["K20"] = as_num(var.get("K20") or safe_resolve("K20"), 0.0)
        obj.E20_industrial_len = q2(var["E20"], "0.01")
        obj.K20_industrial_wid = q2(var["K20"], "0.01")

        required_w = var["K20"]
        fixed_widths = bs.fixed_widths or [80, 90, 100, 110, 120, 125, 140]

        k15_val = float(var.get("K15", 0.0))
        context["best_by_width"] = best_for_each_width(k15_val, fixed_widths)
        context["result_preview"] = {
            "E20": q2(var["E20"], "0.01"),
            "K20": q2(required_w, "0.01"),
            "K15": q2(k15_val, "0.01"),
        }

        picked = as_num(request.POST.get("sheet_choice"), 0.0)
        if picked and any(abs(picked - w) < 1e-6 for w in fixed_widths):
            chosen_row = next((r for r in context["best_by_width"] if abs(r["sheet_width"] - picked) < 1e-6), None)
            chosen_w = picked
            var["M24"] = float(chosen_w)

            if chosen_row:
                obj.F24_per_sheet_count = int(chosen_row["f24"])
                var["F24"] = float(chosen_row["f24"])
                need_txt = "—" if chosen_row["need"] is None else f"{chosen_row['need']:.2f}cm"
                waste_txt = "—" if chosen_row["waste"] is None else f"{chosen_row['waste']:.2f}cm"
                context["chosen_summary"] = (
                    f"عرض ورق انتخابی: {int(round(chosen_row['sheet_width']))}cm | "
                    f"F24: {chosen_row['f24']} | نیاز = F×K15: {need_txt} | دورریز: {waste_txt}"
                )
                obj.waste_warning = (chosen_row["waste"] is not None and chosen_row["waste"] >= 11.0)
                obj.note_message = ""
            else:
                count, chosen_w, waste, warn, note = choose_per_sheet_and_width(required_w, fixed_widths, 11.0, var["E20"])
                obj.F24_per_sheet_count = max(1, int(count))
                var["F24"] = float(obj.F24_per_sheet_count)
                obj.waste_warning = bool(warn)
                obj.note_message = note

            obj.chosen_sheet_width = q2(chosen_w, "0.01")
        else:
            count, chosen_w, waste, warn, note = choose_per_sheet_and_width(required_w, fixed_widths, 11.0, var["E20"])
            obj.F24_per_sheet_count = max(1, int(count))
            obj.chosen_sheet_width = q2(chosen_w, "0.01")
            obj.waste_warning = bool(warn)
            obj.note_message = note
            var["M24"] = float(chosen_w)
            var["F24"] = float(obj.F24_per_sheet_count)

        var["sheet_width"] = float(obj.chosen_sheet_width)

        # ---------- خروجی‌های محاسباتی ----------
        # توجه: M31 و M33 را resolve نمی‌کنیم (مقادیر مستقیم از تنظیمات هستند)
        for key in ["E28", "E38", "I38", "E41", "E40", "M40", "M41", "H46", "J48", "E48"]:
            var[key] = as_num(safe_resolve(key), 0.0)

        # ---------- تعیین Fee_amount ----------
        base_fee = var["sheet_price"]  # از fill_vars_from_settings
        if base_fee <= 0:
            base_fee = _get_latest_fee_amount(
                settlement=settlement,
                fallback_cash=float(bs.sheet_price_cash or 0),
                fallback_credit=float(bs.sheet_price_credit or 0),
            )
        var["Fee_amount"] = float(base_fee)
        context["settlement"] = settlement
        context["fee_amount"] = float(base_fee)
        context["credit_days"] = credit_days

        # اگر فیلدی برای Fee در مدل داری، این‌جا ست کن (try/except بی‌خطر)
        try:
            setattr(obj, "Fee_amount", Decimal(str(var["Fee_amount"])))
        except Exception:
            pass

        # نگاشت خروجی‌ها به مدل
        obj.E28_carton_consumption = q2(var["E28"], "0.0001")
        obj.E38_sheet_area_m2      = q2(var["E38"], "0.0001")
        obj.I38_sheet_count        = int(math.ceil(var["I38"] or 0.0))
        obj.E41_sheet_working_cost = q2(var["E41"], "0.01")
        obj.E40_overhead_cost      = q2(var["E40"], "0.01")
        obj.M40_total_cost         = q2(var["M40"], "0.01")
        obj.M41_profit_amount      = q2(var["M41"], "0.01")
        obj.H46_price_before_tax   = q2(var["H46"], "0.01")
        obj.J48_tax                = q2(var["J48"], "0.01")
        obj.E48_price_with_tax     = q2(var["E48"], "0.01")

    except Exception as e:
        context["errors"] = {"__all__": [str(e)]}
        context["vars"] = locals().get("var", {})
        return render(request, "carton_pricing/price_form.html", context)

    # ---------- ذخیره در صورت درخواست ----------
    if form.cleaned_data.get("save_record"):
        with transaction.atomic():
            obj.save()
        messages.success(request, "برگه قیمت ذخیره شد.")

    context.update({"result": obj, "vars": var})
    return render(request, "carton_pricing/price_form.html", context)

# carton_pricing/views_paper.py
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.core.paginator import Paginator
from django.db.models import Q

from .models import Paper
from .forms import PaperForm

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
