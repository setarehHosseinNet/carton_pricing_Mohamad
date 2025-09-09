# carton_pricing/views.py
# -*- coding: utf-8 -*-

from __future__ import annotations

# ───────────────────────────── stdlib ─────────────────────────────
import math
import re
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

# ───────────────────────────── Django ─────────────────────────────
from django.contrib import messages
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

# ─────────────────────── app imports (models/forms) ───────────────
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
from .utils import build_resolver, to_float
# (safe_eval را نگه می‌داریم اگر جایی لازم شد؛ فعلاً از resolver استفاده می‌کنیم)
from .utils import safe_eval  # noqa: F401

# انتخاب عرض ورق (ترجیح از utils؛ اگر services موجود بود، همان را هم می‌پذیریم)
try:
    from .services import choose_per_sheet_and_width  # type: ignore
except Exception:  # pragma: no cover
    from .utils import choose_per_sheet_and_width

# ───────────────────── helpers: settings & defaults ───────────────
# ترجیح می‌دهیم از settings_api ایمپورت کنیم؛ در صورت نبود، fallback داخلی داریم.
try:
    from .settings_api import get_settings, ensure_default_formulas  # type: ignore
except Exception:  # pragma: no cover
    # ---- fallback: ساخت تنظیمات و فرمول‌های پیش‌فرض همین‌جا ----
    def get_settings() -> BaseSettings:
        obj, _ = BaseSettings.objects.get_or_create(singleton_key="ONLY")
        return obj

    DEFAULT_FORMULAS = {
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

    def ensure_default_formulas() -> None:
        for k, expr in DEFAULT_FORMULAS.items():
            CalcFormula.objects.get_or_create(
                key=k, defaults={"expression": expr, "description": k}
            )

# ───────────────────────────── debug logger ───────────────────────
def DBG(*parts: Any) -> None:
    """لاگ کنسولی سبک برای توسعه."""
    try:
        msg = " ".join(str(p) for p in parts)
    except Exception:
        msg = " ".join(repr(p) for p in parts)
    print(msg)




# ───────────────────────────── API (Ajax) ─────────────────────────
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
    try:
        c = Customer.objects.get(id=cid)
    except Customer.DoesNotExist:
        return JsonResponse({"ok": False}, status=404)

    o = c.orders.order_by("-registered_at").first()
    if not o:
        return JsonResponse({"ok": True, "data": None})

    data = {
        "last_date": o.registered_at.isoformat() if o.registered_at else None,
        "last_fee": float(getattr(o, "last_fee", 0) or 0),
        "last_rate": float(getattr(o, "last_unit_rate", 0) or 0),
    }
    return JsonResponse({"ok": True, "data": data})


# ───────────────────────────── pages: settings & formulas ─────────
def base_settings_view(request: HttpRequest) -> HttpResponse:
    """صفحه اطلاعات پایه؛ ذخیره M30، قیمت‌ها، هزینه‌ها و…"""
    bs = get_settings()
    if request.method == "POST":
        form = BaseSettingsForm(request.POST, instance=bs)
        if form.is_valid():
            form.save()
            messages.success(request, "اطلاعات پایه ذخیره شد")
            return redirect("base_settings")
    else:
        form = BaseSettingsForm(instance=bs)
    return render(request, "carton_pricing/base_settings.html", {"form": form})


def formulas_view(request: HttpRequest) -> HttpResponse:
    """صفحه فرمول‌ها (ایجاد پیش‌فرض‌ها، افزودن و ویرایش گروهی)."""
    ensure_default_formulas()
    qs = CalcFormula.objects.order_by("key")

    if request.method == "POST":
        if "add_new" in request.POST:
            form = CalcFormulaForm(request.POST)
            if form.is_valid():
                form.save()
                messages.success(request, "فرمول جدید اضافه شد.")
                return redirect("formulas")
            messages.error(request, "خطا در افزودن فرمول.")
        else:
            for f in qs:
                new_expr = request.POST.get(f"expr_{f.id}")
                if new_expr is not None:
                    f.expression = new_expr
                    f.save()
            messages.success(request, "فرمول‌ها ذخیره شدند.")
            return redirect("formulas")

    add_form = CalcFormulaForm()
    return render(
        request,
        "carton_pricing/formulas.html",
        {"formulas": qs, "labels": VARIABLE_LABELS, "add_form": add_form},
    )


# ───────────────────────────── price form view ────────────────────
from typing import Any
from decimal import Decimal, ROUND_HALF_UP
import math, re
from django.contrib import messages
from django.shortcuts import render
from django.http import HttpRequest, HttpResponse

from .models import CalcFormula, PriceQuotation
from .forms import PriceForm
from .settings_api import get_settings, ensure_default_formulas
from .utils import (
    build_resolver, to_float,
    choose_per_sheet_and_width, compute_sheet_options, render_formula
)

def q2(val: float | Decimal, places: str) -> Decimal:
    return Decimal(val).quantize(Decimal(places), rounding=ROUND_HALF_UP)

def _as_number(x: Any, fallback: float) -> float:
    """هر چیزی که بشود به عدد تبدیل کرد را برگردان؛ در غیر این صورت fallback."""
    try:
        if x is None:
            return fallback
        if isinstance(x, str):
            s = x.strip()
            if s == "":
                return fallback
            return float(s.replace(",", ""))
        return float(x)
    except Exception:
        return fallback

from typing import Any
import math, re
from decimal import Decimal
from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from .forms import PriceForm
from .models import CalcFormula, PriceQuotation
from .settings_api import get_settings, ensure_default_formulas
from .utils import (
    to_float, build_resolver, render_formula,
    compute_sheet_options, choose_per_sheet_and_width
)

# گرد کردن کمکی
def q2(val: float | Decimal, places: str) -> Decimal:
    return Decimal(val).quantize(Decimal(places))

def price_form_view(request: HttpRequest) -> HttpResponse:
    """
    فرم قیمت:
    - ورودی‌ها از فرم
    - محاسبه E20/K20 (+ پشتیبانی از فرمول‌های E17, I17, K15 در صورت وجود)
    - پیشنهاد عرض ورق از بزرگ‌ترین به کوچک‌ترین (waste<11) + انتخاب کاربر
    - ارزیابی سایر فرمول‌ها و نگاشت به مدل
    """
    ensure_default_formulas()
    bs = get_settings()
    context: dict[str, Any] = {"settings": bs}

    if request.method == "POST":
        form = PriceForm(request.POST)
        context["form"] = form

        if not form.is_valid():
            context["errors"] = form.errors
            return render(request, "carton_pricing/price_form.html", context)

        obj: PriceQuotation = form.save(commit=False)

        # A6 کُد چهارتایی
        obj.A6_sheet_code = int(f"{obj.A1_layers}{obj.A2_pieces}{obj.A3_door_type}{obj.A4_door_count}")

        # فرمول‌های خام (اکسل‌طور) از DB
        formulas_raw = {cf.key: str(cf.expression or "") for cf in CalcFormula.objects.all()}

        cd = form.cleaned_data
        # seed vars: ورودی‌های فرم + snapshot تنظیمات
        seed_vars = {
            "A1": int(cd.get("A1_layers") or 0),
            "A2": int(cd.get("A2_pieces") or 0),
            "A3": int(cd.get("A3_door_type") or 0),
            "A4": int(cd.get("A4_door_count") or 0),
            "I8": int(cd.get("I8_qty") or 0),
            "E15": to_float(cd.get("E15_len"), 0.0),
            "G15": to_float(cd.get("G15_wid"), 0.0),
            "I15": to_float(cd.get("I15_hgt"), 0.0),
            "E17": to_float(cd.get("E17_lip"), 0.0),   # ورودی فرم برای لب درب
            "E46": to_float(cd.get("E46_round_adjust"), 0.0),
            "I41": to_float(bs.profit_rate_percent, 0.0),
            "J43": to_float(bs.interface_cost, 0.0),
            "H43": to_float(bs.pallet_cost, 0.0),
            "E43": to_float(bs.shipping_cost, 0.0),
            "M30": to_float(bs.overhead_per_meter, 0.0),
        }
        seed_vars["A6"] = int(f"{seed_vars['A1']}{seed_vars['A2']}{seed_vars['A3']}{seed_vars['A4']}")

        # قیمت ورق بر اساس شیوه پرداخت
        sheet_price = float(bs.sheet_price_cash if cd.get("payment_type") == "cash"
                            else bs.sheet_price_credit)
        seed_vars["sheet_price"] = sheet_price

        # اسنپ‌شات تنظیمات داخل آبجکت خروجی
        obj.I41_profit_rate = Decimal(bs.profit_rate_percent)
        obj.E43_shipping    = Decimal(bs.shipping_cost)
        obj.H43_pallet      = Decimal(bs.pallet_cost)
        obj.J43_interface   = Decimal(bs.interface_cost)

        # Resolver (اکسل→پایتون) + فرمول‌های پایتونی برای دیباگ
        resolve, var, formulas_py = build_resolver(formulas_raw, seed_vars)
        context["debug_formulas"] = {k: render_formula(expr, seed_vars) for k, expr in formulas_py.items()}

        try:
            # --- E17: اگر فرمول تعریف شده و خروجی‌اش ""/None نبود، همان را بگیر؛
            #          در غیر این صورت از ورودی فرم (seed_vars['E17']) استفاده کن.
            if "E17" in formulas_py:
                v_e17 = resolve("E17")
                if v_e17 is None or (isinstance(v_e17, str) and v_e17.strip() == ""):
                    var["E17"] = seed_vars["E17"]
                else:
                    var["E17"] = float(v_e17)
            else:
                var["E17"] = seed_vars["E17"]

            # --- I17: در صورت وجود فرمول
            if "I17" in formulas_py:
                try:
                    var["I17"] = float(resolve("I17"))
                except Exception:
                    var["I17"] = 0.0
            else:
                var["I17"] = 0.0

            # --- K15: در صورت وجود فرمول
            if "K15" in formulas_py:
                try:
                    var["K15"] = float(resolve("K15"))
                except Exception:
                    var["K15"] = 0.0
            else:
                var["K15"] = 0.0

            # --- E20 / K20
            var["E20"] = float(resolve("E20"))
            obj.E20_industrial_len = q2(var["E20"], "0.01")

            var["K20"] = float(resolve("K20"))
            obj.K20_industrial_wid = q2(var["K20"], "0.01")

            # --- پیشنهاد عرض شیت: از بزرگ‌ترین به کوچک‌ترین + فقط waste<11
            required_w = var["K20"]
            fw = bs.fixed_widths or []
            if isinstance(fw, str):
                fw = [w for w in re.split(r"[,\s]+", fw) if w]
            fixed_widths = [to_float(x, 0.0) for x in fw if to_float(x, 0.0) > 0]

            options = compute_sheet_options(required_width_cm=required_w,
                                            fixed_widths=fixed_widths,
                                            max_waste_cm=11.0,
                                            max_options=6)
            context["sheet_options"] = options
            context["result_preview"] = {
                "E20": q2(var["E20"], "0.01"),
                "K20": q2(required_w, "0.01"),
            }

            # اگر کاربر یکی از گزینه‌های جدول را انتخاب کرده باشد همان را اعمال کن
            picked = to_float(request.POST.get("sheet_choice"), 0.0)
            if picked and any(abs(picked - o["width"]) < 1e-6 for o in options):
                chosen_w = picked
                count = int(chosen_w // required_w)
                waste = chosen_w - count * required_w
                warn = waste >= 11.0
                note = f"طول ورق (E20) = {var['E20']:.2f}cm ، عرض ورق = {chosen_w:g}cm ، دورریز ≈ {waste:.1f}cm"
            else:
                # انتخاب خودکار بهترین
                count, chosen_w, waste, warn, note = choose_per_sheet_and_width(
                    required_width_cm=required_w,
                    fixed_widths=fixed_widths,
                    max_waste_cm=11.0,
                    e20_len_cm=var["E20"],
                )

            obj.F24_per_sheet_count = max(1, int(count))
            obj.chosen_sheet_width  = q2(chosen_w, "0.01")
            obj.waste_warning       = bool(warn)
            obj.note_message        = note

            # برای ادامهٔ فرمول‌ها
            var["F24"] = float(obj.F24_per_sheet_count)
            var["sheet_width"] = float(chosen_w)

            # سایر خروجی‌ها
            for key in ["E28", "E38", "I38", "E41", "E40", "M40", "M41", "H46", "J48", "E48"]:
                var[key] = float(resolve(key))

            # نگاشت به مدل (نمایش نتایج)
            obj.E28_carton_consumption = q2(var["E28"], "0.0001")
            obj.E38_sheet_area_m2      = q2(var["E38"], "0.0001")
            obj.I38_sheet_count        = int(math.ceil(var["I38"])) if isinstance(var["I38"], float) else int(var["I38"])
            obj.E41_sheet_working_cost = q2(var["E41"], "0.01")
            obj.E40_overhead_cost      = q2(var["E40"], "0.01")
            obj.M40_total_cost         = q2(var["M40"], "0.01")
            obj.M41_profit_amount      = q2(var["M41"], "0.01")
            obj.H46_price_before_tax   = q2(var["H46"], "0.01")
            obj.J48_tax                = q2(var["J48"], "0.01")
            obj.E48_price_with_tax     = q2(var["E48"], "0.01")

            # اگر مدل فیلدی برای ذخیرهٔ E17/K15 داری، اینجا می‌توانی ست کنی:
            obj.E17_lip_value  = q2(var["E17"], "0.01")
            obj.K15_sheet_calc = q2(var["K15"], "0.01")

        except ValueError as e:
            context["errors"] = {"__all__": [str(e)]}
            context["vars"] = var
            return render(request, "carton_pricing/price_form.html", context)

        if form.cleaned_data.get("save_record"):
            obj.save()
            messages.success(request, "برگه قیمت ذخیره شد.")

        # vars را برای نمایش/دیباگ به قالب بده (E17/K15 هم داخلش هستند)
        context.update({"result": obj, "vars": var})
        return render(request, "carton_pricing/price_form.html", context)

    # GET
    form = PriceForm(initial={
        "A1_layers": 1,
        "A2_pieces": 1,
        "A3_door_type": 1,
        "A4_door_count": 1,
        "payment_type": "cash",
    })
    context["form"] = form
    return render(request, "carton_pricing/price_form.html", context)
