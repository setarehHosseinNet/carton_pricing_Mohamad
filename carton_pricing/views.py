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

def get_or_create_settings() -> BaseSettings:
    """
    Singleton pattern: اگر رکورد هست همان را بده؛ وگرنه فقط یک‌بار با defaults بساز.
    """
    bs = BaseSettings.objects.first()
    if bs:
        return bs
    defaults = seed_defaults_from_external(get_settings_external())
    return BaseSettings.objects.create(**defaults)

def base_settings_view(request: HttpRequest) -> HttpResponse:
    """
    صفحهٔ اطلاعات پایه: رکورد singleton را لود می‌کنیم و همان را آپدیت می‌کنیم.
    """
    bs = get_or_create_settings()

    if request.method == "POST":
        form = BaseSettingsForm(request.POST, instance=bs)
        if form.is_valid():
            with transaction.atomic():
                form.save()  # همان رکورد را آپدیت می‌کند (pk برقرار است)
            messages.success(request, "اطلاعات پایه ذخیره شد.")
            return redirect("carton_pricing:base_settings")
        messages.error(request, "خطا در ذخیره تنظیمات. لطفاً مقادیر ورودی را بررسی کنید.")
    else:
        form = BaseSettingsForm(instance=bs)

    return render(request, "carton_pricing/base_settings.html", {"form": form})


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


# ───────────────────────── the view ─────────────────────────
def price_form_view(request: HttpRequest) -> HttpResponse:
    """
    فرم قیمت: محاسبهٔ فرمول‌ها + پیشنهاد عرض ورق + جدول‌های کمکی
    """

    # نگاشت فیلد فرم → نام متغیر
    FIELD_TO_VAR: Dict[str, str] = {
        "E15_len": "E15",
        "G15_wid": "G15",
        "I15_hgt": "I15",
        "I8_qty":  "I8",
        "E17_lip": "E17",                # فقط fallback دستی
        "E46_round_adjust": "E46",
        "A1_layers": "A1",
        "A2_pieces": "A2",
        "A3_door_type": "A3",
        "A4_door_count": "A4",
    }
    VAR_TO_FIELD = {v: k for (k, v) in FIELD_TO_VAR.items()}

    # settings + context
    bs: BaseSettings = ensure_settings_model(get_settings_external())
    context: Dict[str, Any] = {"settings": bs}

    # ───────── GET ─────────
    if request.method != "POST":
        form = PriceForm(initial={
            "A1_layers": 1, "A2_pieces": 1, "A3_door_type": 1, "A4_door_count": 1,
            "payment_type": "cash",
        })
        form.fields["E17_lip"].required = False
        context["form"] = form
        return render(request, "carton_pricing/price_form.html", context)

    # ───────── POST ─────────
    form = PriceForm(request.POST)
    form.fields["E17_lip"].required = False
    context["form"] = form
    if not form.is_valid():
        context["errors"] = form.errors
        return render(request, "carton_pricing/price_form.html", context)

    obj: PriceQuotation = form.save(commit=False)
    cd = form.cleaned_data

    # ───────── Seed از فرم/ستینگ ─────────
    seed_vars: Dict[str, Any] = {}
    for field, varname in FIELD_TO_VAR.items():
        if field in cd:
            seed_vars[varname] = as_num(cd.get(field), 0.0)

    # اجزای A6 و خود A6
    seed_vars["A1"] = int(cd.get("A1_layers") or 0)
    seed_vars["A2"] = int(cd.get("A2_pieces") or 0)
    seed_vars["A3"] = int(cd.get("A3_door_type") or 0)
    seed_vars["A4"] = int(cd.get("A4_door_count") or 0)
    a6_str = f"{seed_vars['A1']}{seed_vars['A2']}{seed_vars['A3']}{seed_vars['A4']}"
    seed_vars["A6"] = int(a6_str) if a6_str.isdigit() else 0
    context["a6"] = a6_str
    obj.A6_sheet_code = seed_vars["A6"]

    # از ستینگ
    seed_vars["I41"] = as_num(bs.profit_rate_percent, 0.0)
    seed_vars["J43"] = as_num(bs.interface_cost, 0.0)
    seed_vars["H43"] = as_num(bs.pallet_cost, 0.0)
    seed_vars["E43"] = as_num(bs.shipping_cost, 0.0)
    seed_vars["M30"] = as_num(bs.overhead_per_meter, 0.0)
    seed_vars["sheet_price"] = float(
        bs.sheet_price_cash if cd.get("payment_type") == "cash" else bs.sheet_price_credit
    )

    # اسنپ‌شات ستینگ روی مدل
    obj.I41_profit_rate = Decimal(bs.profit_rate_percent or 0)
    obj.E43_shipping    = Decimal(bs.shipping_cost or 0)
    obj.H43_pallet      = Decimal(bs.pallet_cost or 0)
    obj.J43_interface   = Decimal(bs.interface_cost or 0)

    DBG(f"[SEED] A6={seed_vars['A6']} E15={seed_vars.get('E15')} G15={seed_vars.get('G15')} E17(manual)={as_num(cd.get('E17_lip'),0.0)}")

    # ───────── فرمول‌ها و تکمیل seed ─────────
    formulas_qs = CalcFormula.objects.all()
    formulas_raw = {cf.key: str(cf.expression or "") for cf in formulas_qs}

    token_re = re.compile(r"\b([A-Z]+[0-9]+)\b")
    all_tokens: set[str] = set()
    for expr in formulas_raw.values():
        if expr:
            all_tokens.update(token_re.findall(expr))

    for token in all_tokens:
        if token not in seed_vars and token in VAR_TO_FIELD:
            seed_vars[token] = as_num(cd.get(VAR_TO_FIELD[token]), 0.0)

    # پیش‌فرض‌های امن
    for k in ("E17", "I17", "F24", "sheet_width"):
        seed_vars.setdefault(k, 0.0)

    # ساخت Resolver
    resolve, var, formulas_py = build_resolver(formulas_raw, seed_vars)
    var.update(seed_vars)

    context["debug_formulas"] = {k: render_formula(expr, seed_vars) for k, expr in formulas_py.items()}

    def safe_resolve(key: str):
        if key not in formulas_py:
            return None
        try:
            return resolve(key)
        except Exception as ex:
            DBG(f"[EVAL:{key}] error={ex}")
            return None

    # ───────── تثبیت E17 → سپس I17 → سپس K15 ─────────
    tail = seed_vars["A6"] % 100 if seed_vars["A6"] else 0
    g15  = float(seed_vars.get("G15", 0.0))

    if tail in (11, 12):
        e17_manual = _as_num_or_none(cd.get("E17_lip"))
        if not e17_manual or e17_manual == 0.0:
            form.add_error("E17_lip", "این فیلد برای حالت‌های انتهایی 11 یا 12 در A6 الزامی است.")
            context["errors"] = form.errors
            return render(request, "carton_pricing/price_form.html", context)
        var["E17"] = float(e17_manual)
    else:
        raw_e17 = safe_resolve("E17")
        num_e17 = _as_num_or_none(raw_e17)
        if num_e17 not in (None, 0.0):
            var["E17"] = float(num_e17)
        else:
            if g15 > 0 and tail in (21, 22):
                var["E17"] = g15 / 2.0
            elif g15 > 0 and tail in (31, 32):
                var["E17"] = g15
            else:
                var["E17"] = as_num(cd.get("E17_lip"), 0.0)

    seed_vars["E17"] = float(var["E17"])
    var.update(seed_vars)

    if "I17" in formulas_py:
        i17_raw = safe_resolve("I17")
        var["I17"] = as_num(i17_raw, 0.0)
    else:
        var.setdefault("I17", float(seed_vars.get("I17", 0.0)))

    if "K15" in formulas_py:
        k15_raw = safe_resolve("K15")
        var["K15"] = as_num(k15_raw, 0.0)
    else:
        var.setdefault("K15", 0.0)

    # ارزیابی چندمرحله‌ای
    MAX_PASSES = 5
    for _ in range(MAX_PASSES):
        changed = False
        for key in formulas_py.keys():
            if key in ("E17", "K15"):
                continue
            raw = safe_resolve(key)
            num = _as_num_or_none(raw)
            if num is not None:
                prev = var.get(key)
                val = float(num)
                if prev is None or (isinstance(prev, (int, float)) and abs(prev - val) > 1e-9):
                    var[key] = val
                    changed = True
        if not changed:
            break

    # ───────── پیشنهاد عرض ورق + نگاشت ─────────
    try:
        # E20 / K20
        var["E20"] = float(var.get("E20") or as_num(safe_resolve("E20"), 0.0))
        obj.E20_industrial_len = q2(var["E20"], "0.01")

        var["K20"] = float(var.get("K20") or as_num(safe_resolve("K20"), 0.0))
        obj.K20_industrial_wid = q2(var["K20"], "0.01")

        required_w = var["K20"] or 0.0

        # عرض‌های ثابت از تنظیمات (JSONField یا رشته)
        # فقط همین‌ها؛ تنظیمات نادیده گرفته می‌شود
        fixed_widths_all = get_fixed_widths_hard()
        fw_for_k20 = fixed_widths_all  # اگر جایی جدا لازم داری

        # جدول جامع «بهینه برای هر عرض ثابت» (همهٔ عرض‌ها)
        k15_val = float(var.get("K15") or 0.0)
        context["best_by_width"] = best_for_each_width(k15_val, fixed_widths_all, fmax=30)

        # گزینه‌های انتخاب (مثل قبل: دورریز < 11 و محدود به چند مورد)
        options = compute_sheet_options(
            required_width_cm=required_w,
            fixed_widths=fixed_widths_all,
            max_waste_cm=11.0,
            max_options=6,
        )
        context["sheet_options"] = options
        context["fixed_widths_debug"] = fixed_widths_all
        # برای نمایش کوچک «تمام ترکیب‌ها با waste<11»
        def build_f24_candidates_all(
            k15: float,
            fixed_widths: list[float],
            max_waste: float = 11.0,
            f24_min: int = 1,
            f24_max: int = 30,
        ) -> list[dict]:
            rows: list[dict] = []
            if not k15 or k15 <= 0 or not fixed_widths:
                return rows
            for f in range(f24_min, f24_max + 1):
                need = f * k15
                for w in fixed_widths:
                    if w >= need:
                        waste = w - need
                        if 0 <= waste < max_waste:
                            rows.append({
                                "sheet_width": round(float(w), 2),
                                "f24": int(f),
                                "waste": round(float(waste), 2),
                                "req_width": round(float(need), 2),
                            })
            rows.sort(key=lambda r: (r["waste"], r["sheet_width"], -r["f24"]))
            return rows

        # جدول ترکیب‌های ممکن F×K15 (دلخواه/دیباگ)
        context["f24_candidates"] = build_f24_candidates_all(
            k15=k15_val,
            fixed_widths=fixed_widths_all,
            max_waste=11.0,
            f24_min=1,
            f24_max=30,
        )
        # اگر کاربر گزینه‌ای را انتخاب کرده بود
        picked = as_num(request.POST.get("sheet_choice"), 0.0)
        if picked and any(abs(picked - o["width"]) < 1e-6 for o in options):
            chosen_w = picked
            count = int(chosen_w // required_w) if required_w else 1
            waste = chosen_w - count * required_w if required_w else 0.0
            warn = waste >= 11.0
            note = f"طول ورق = {var['E20']:.2f}cm | عرض = {chosen_w:g}cm | دورریز ≈ {waste:.1f}cm"
        else:
            count, chosen_w, waste, warn, note = choose_per_sheet_and_width(
                required_width_cm=required_w,
                fixed_widths=fixed_widths_all,
                max_waste_cm=11.0,
                e20_len_cm=var["E20"],
            )

        obj.F24_per_sheet_count = max(1, int(count))
        obj.chosen_sheet_width  = q2(chosen_w, "0.01")
        obj.waste_warning       = bool(warn)
        obj.note_message        = note

        # تزریق برای فرمول‌های انتهایی
        var["F24"] = float(obj.F24_per_sheet_count)
        var["sheet_width"] = float(chosen_w)

        # پاس نهایی خروجی‌ها
        for key in ["E28","E38","I38","E41","E40","M40","M41","H46","J48","E48"]:
            if key in formulas_py:
                var[key] = as_num(safe_resolve(key), 0.0)
            else:
                var[key] = float(var.get(key, 0.0))

        # نگاشت به مدل
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

        # مقادیر کمکی اختیاری
        if hasattr(obj, "E17_lip_value"):
            obj.E17_lip_value = q2(var["E17"], "0.01")
        if hasattr(obj, "K15_sheet_calc"):
            obj.K15_sheet_calc = q2(float(var.get("K15", 0.0)), "0.01")

    except Exception as e:
        context["errors"] = {"__all__": [str(e)]}
        try:
            context["vars"] = var
        except Exception:
            pass
        return render(request, "carton_pricing/price_form.html", context)

    # ───────── ذخیره در صورت تمایل ─────────
    if form.cleaned_data.get("save_record"):
        with transaction.atomic():
            obj.save()
        messages.success(request, "برگه قیمت ذخیره شد.")

    context.update({"result": obj, "vars": var})
    return render(request, "carton_pricing/price_form.html", context)
