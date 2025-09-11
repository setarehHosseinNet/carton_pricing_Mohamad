# carton_pricing/views.py
# -*- coding: utf-8 -*-


from __future__ import annotations
# ───────────────────────── stdlib ─────────────────────────
from decimal import Decimal
from typing import Any
# ───────────────────────── Django ─────────────────────────
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.db import transaction
from django.shortcuts import render, redirect
from django.contrib import messages
from django.http import HttpRequest, HttpResponse

# فرض: این تابع یک dict از مقادیر پیش‌فرض برمی‌گرداند (نه مدل)
def get_settings_external() -> dict:
    ...

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
        "fixed_widths":       ext.get("fixed_widths", ""),   # اگر TextField/JSONField بسته به مدل
    }

def get_or_create_settings() -> "BaseSettings":
    """
    Singleton pattern: اگر رکورد هست همان را بده؛ وگرنه فقط یک‌بار با defaults بساز.
    هیچ‌وقت در هر درخواست، تنظیمات را از سورس خارجی روی DB overwrite نکن!
    """
    from .models import BaseSettings
    bs = BaseSettings.objects.first()
    if bs:
        return bs
    defaults = seed_defaults_from_external(get_settings_external())
    return BaseSettings.objects.create(**defaults)

def base_settings_view(request: HttpRequest) -> HttpResponse:
    """
    صفحهٔ اطلاعات پایه: رکورد singleton را لود می‌کنیم و همان را آپدیت می‌کنیم.
    """
    from .forms import BaseSettingsForm

    bs = get_or_create_settings()  # نه ensure_settings_model(get_settings_external())

    if request.method == "POST":
        form = BaseSettingsForm(request.POST, instance=bs)
        if form.is_valid():
            with transaction.atomic():
                bs = form.save()  # همان رکورد را آپدیت می‌کند (pk برقرار است)
            messages.success(request, "اطلاعات پایه ذخیره شد.")
            return redirect("carton_pricing:base_settings")
        else:
            # برای دیباگ: ببین دقیقاً کدام فیلد خطاست
            # print(form.errors.as_json())
            messages.error(request, "خطا در ذخیره تنظیمات. لطفاً مقادیر ورودی را بررسی کنید.")
    else:
        form = BaseSettingsForm(instance=bs)

    return render(request, "carton_pricing/base_settings.html", {"form": form})

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
        # اگر settings_api وظیفه را دارد، بگذار انجام بدهد
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
# carton_pricing/views.py





# carton_pricing/views.py



# ---------- کوچک‌های کاربردی ----------
def DBG(*parts: Any) -> None:
    try:
        print(" ".join(str(p) for p in parts))
    except Exception:
        print(" ".join(repr(p) for p in parts))

def q2(val: float | Decimal, places: str) -> Decimal:
    return Decimal(val).quantize(Decimal(places), rounding=ROUND_HALF_UP)

def as_num(x: Any, default: float | None = 0.0) -> float | None:
    """
    تبدیل امن: None/""/"*" → default
    رشتهٔ عددی → float
    عدد → float
    """
    try:
        if x is None:
            return default
        if isinstance(x, str):
            s = x.strip()
            if s in ("", "*"):
                return default
            return float(s.replace(",", ""))
        return float(x)
    except Exception:
        return default




from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict
import math, re

# فرض: این‌ها را قبلاً داری
# from .models import PriceQuotation, CalcFormula, BaseSettings
# from .forms import PriceForm
# from .utils import ensure_settings_model, get_settings_external, to_float, compute_sheet_options, choose_per_sheet_and_width, DBG, build_resolver, render_formula

def price_form_view(request: HttpRequest) -> HttpResponse:
    """
    فرم قیمت (نسخهٔ پایدار برای فرمول‌های داینامیک و وابسته):
      1) کشیدن فرمول‌ها از DB
      2) seeding سیستماتیک متغیرها از فرم/ستینگ (+ پیش‌فرض‌های امن)
      3) تثبیت E17 و سپس محاسبهٔ I17 و K15
      4) ارزیابی چندمرحله‌ای تا همگرایی
      5) پیشنهاد عرض ورق، تزریق F24/sheet_width و پاس نهایی
      6) نگاشت نتایج به مدل + پیش‌نمایش K15
    """

    # ───────── Helpers ─────────
    def q2(val: float | Decimal, places: str) -> Decimal:
        return Decimal(val).quantize(Decimal(places), rounding=ROUND_HALF_UP)

    def as_num_or_none(x: Any) -> float | None:
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
        v = as_num_or_none(x)
        return default if v is None else v

    # نگاشت فیلد فرم → نام متغیر
    FIELD_TO_VAR: Dict[str, str] = {
        "E15_len": "E15",
        "G15_wid": "G15",
        "I15_hgt": "I15",
        "I8_qty":  "I8",
        "E17_lip": "E17",            # فقط fallback دستی
        "E46_round_adjust": "E46",
        "A1_layers": "A1",
        "A2_pieces": "A2",
        "A3_door_type": "A3",
        "A4_door_count": "A4",
    }
    VAR_TO_FIELD = {v: k for (k, v) in FIELD_TO_VAR.items()}

    # ───────── Settings & Context ─────────
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

    # از فرم
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

    # اگر توکنی در seed نیست ولی از فرم می‌آید → از فرم مقدار بده
    for token in all_tokens:
        if token not in seed_vars and token in VAR_TO_FIELD:
            seed_vars[token] = as_num(cd.get(VAR_TO_FIELD[token]), 0.0)

    # پیش‌فرض‌های «امن» برای نام‌های حساس (تا Unknown name نخوریم)
    for k in ("E17", "I17", "F24", "sheet_width"):
        seed_vars.setdefault(k, 0.0)

    # ───────── Resolver ─────────
    resolve, var, formulas_py = build_resolver(formulas_raw, seed_vars)
    var.update(seed_vars)  # فضای ارزیابی همان seed را ببیند

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
    DBG(f"[TRACE:E17] tail={tail} expr={formulas_py.get('E17')}")

    if tail in (11, 12):
        e17_manual = as_num_or_none(cd.get("E17_lip"))
        if not e17_manual or e17_manual == 0.0:
            form.add_error("E17_lip", "این فیلد برای حالت‌های انتهایی 11 یا 12 در A6 الزامی است.")
            context["errors"] = form.errors
            return render(request, "carton_pricing/price_form.html", context)
        var["E17"] = float(e17_manual)
    else:
        raw_e17 = safe_resolve("E17")
        num_e17 = as_num_or_none(raw_e17)
        if num_e17 not in (None, 0.0):
            var["E17"] = float(num_e17)
        else:
            # fail-safe مبتنی بر tail و G15
            if g15 > 0 and tail in (21, 22):
                var["E17"] = g15 / 2.0
            elif g15 > 0 and tail in (31, 32):
                var["E17"] = g15
            else:
                var["E17"] = as_num(cd.get("E17_lip"), 0.0)

    seed_vars["E17"] = float(var["E17"])
    var.update(seed_vars)
    DBG(f"[TRACE:E17] final={var['E17']} (G15={g15})")

    # I17 (اگر فرمول دارد) ــ قبل از K15
    if "I17" in formulas_py:
        i17_raw = safe_resolve("I17")
        var["I17"] = as_num(i17_raw, 0.0)
    else:
        var.setdefault("I17", float(seed_vars.get("I17", 0.0)))

    # K15 اکنون محاسبه شود تا صفر نشود
    if "K15" in formulas_py:
        k15_raw = safe_resolve("K15")
        var["K15"] = as_num(k15_raw, 0.0)
    else:
        var.setdefault("K15", 0.0)

    # ───────── ارزیابی چندمرحله‌ای تا همگرایی ─────────
    MAX_PASSES = 5
    for p in range(1, MAX_PASSES + 1):
        changed = False
        for key in formulas_py.keys():
            if key in ("E17", "K15"):  # همین‌ها را قبلاً تثبیت کرده‌ایم
                continue
            raw = safe_resolve(key)
            num = as_num_or_none(raw)
            if num is not None:
                prev = var.get(key)
                val = float(num)
                if prev is None or (isinstance(prev, (int, float)) and abs(prev - val) > 1e-9):
                    var[key] = val
                    changed = True
        DBG(f"[PASS {p}] changed={changed}")
        if not changed:
            break

    # ───────── پیشنهاد عرض ورق و نگاشت ─────────
    try:
        # E20 / K20
        var["E20"] = float(var.get("E20") or as_num(safe_resolve("E20"), 0.0))
        obj.E20_industrial_len = q2(var["E20"], "0.01")

        var["K20"] = float(var.get("K20") or as_num(safe_resolve("K20"), 0.0))
        obj.K20_industrial_wid = q2(var["K20"], "0.01")

        required_w = var["K20"] or 0.0
        fw = bs.fixed_widths or []
        if isinstance(fw, str):
            fw = [w for w in re.split(r"[,\s\[\]]+", fw) if w]
        fixed_widths = [as_num(x, 0.0) for x in fw if as_num(x, 0.0) > 0]

        # --- پیشنهادهای عرض ورق بر اساس F24 از 30 تا 2 (F24 * K15) ---
        # --- پیشنهادهای عرض ورق بر اساس تمام ترکیب‌های F24×K15 و همه‌ی عرض‌های ثابت ---
        def _parse_fixed_widths(raw_fw):
            if raw_fw is None or raw_fw == "":
                return []
            if isinstance(raw_fw, (list, tuple)):
                return [as_num(x, 0.0) for x in raw_fw if as_num(x, 0.0) > 0]
            parts = re.split(r"[,\s\[\]]+", str(raw_fw))  # مانند "80,90,100"
            return [as_num(x, 0.0) for x in parts if as_num(x, 0.0) > 0]

        fixed_from_settings = _parse_fixed_widths(getattr(bs, "fixed_widths", None))
        fixed_widths_all = fixed_from_settings or [80, 90, 100, 110, 120, 125, 140]
        fixed_widths_all = sorted(set(w for w in fixed_widths_all if w > 0))

        def build_f24_candidates_all(
                k15: float,
                fixed_widths: list[float],
                max_waste: float = 11.0,
                f24_min: int = 1,
                f24_max: int = 30,
        ) -> list[dict]:
            """
            تمام ترکیب‌های (F24=f24_min..f24_max) × (تمام fixed_widths) را می‌سنجد.
            اگر w >= need = F24*K15 و waste = w-need بین [0, max_waste) بود، در خروجی می‌آید.
            خروجی: لیستی از دیکشنری‌ها برای نمایش در تمپلیت.
            """
            rows: list[dict] = []
            if not k15 or k15 <= 0 or not fixed_widths:
                return rows

            for f in range(f24_min, f24_max + 1):  # 1 .. 30
                need = f * k15  # عرض لازم
                for w in fixed_widths:  # همه عرض‌های ثابت
                    if w >= need:
                        waste = w - need
                        if 0 <= waste < max_waste:
                            rows.append({
                                "sheet_width": round(float(w), 2),
                                "f24": int(f),
                                "waste": round(float(waste), 2),
                                "req_width": round(float(need), 2),  # F24*K15
                            })
            # مرتب‌سازی: کمترین دورریز، سپس عرض ورق صعودی، سپس F24 نزولی (دلخواه)
            rows.sort(key=lambda r: (r["waste"], r["sheet_width"], -r["f24"]))
            return rows

        k15_val = float(var.get("K15") or 0.0)
        context["f24_candidates"] = build_f24_candidates_all(
            k15=k15_val,
            fixed_widths=fixed_widths_all,
            max_waste=11.0,
            f24_min=1,
            f24_max=30,
        )

        # اگر در settings چیزی نبود، پیش‌فرض‌هایی که گفتی:
        fixed_from_settings = _parse_fixed_widths(getattr(bs, "fixed_widths", None))
        fixed_widths_f24 = fixed_from_settings or [80, 90, 100, 110, 120, 125, 140]
        fixed_widths_f24 = sorted(set(w for w in fixed_widths_f24 if w > 0))

        def build_f24_candidates(k15: float,
                                 fixed_widths: list[float],
                                 max_waste: float = 11.0,
                                 f24_start: int = 30,
                                 f24_stop: int = 2) -> list[dict]:
            """
            برای F24 از f24_start تا f24_stop (کاهشی) مقدار لازمِ عرض = F24*K15 را می‌سازد
            و کوچک‌ترین عرض ثابتِ >= آن را که دورریز بین 0..max_waste داشته باشد، انتخاب می‌کند.
            خروجی: [{width, f24, waste, need}]  (need=F24*K15)
            """

            rows: list[dict] = []
            if not k15 or k15 <= 0 or not fixed_widths:
                return rows

            fws = sorted(fixed_widths)
            for f in range(f24_start, f24_stop - 1, -1):
                need = f * k15  # عرض موردنیاز
                # کوچک‌ترین عرض ثابت ≥ need
                chosen = None
                for w in fws:
                    if w >= need:
                        waste = w - need
                        if 0 <= waste < max_waste:
                            chosen = (w, waste)
                        break
                if chosen:
                    w, waste = chosen
                    rows.append({
                        "width": round(float(w), 2),
                        "f24": int(f),
                        "waste": round(float(waste), 2),
                        "need": round(float(need), 2),
                    })
            return rows

        k15_val = float(var.get("K15") or 0.0)
        context["f24_candidates"] = build_f24_candidates(
            k15=k15_val,
            fixed_widths=fixed_widths_f24,
            max_waste=11.0,
            f24_start=30,
            f24_stop=2,
        )

        options = compute_sheet_options(
            required_width_cm=required_w,
            fixed_widths=fixed_widths,
            max_waste_cm=11.0,
            max_options=6,
        )
        context["sheet_options"] = options
        context["result_preview"] = {
            "E20": q2(var["E20"], "0.01"),
            "K20": q2(required_w, "0.01"),
            "K15": q2(var.get("K15", 0.0), "0.01"),
        }

        # --- سری ضرب‌های K15 در 1..30 + نزدیک‌ترین عرضِ ثابت و دورریز ---
        def _pick_smallest_fixed(width_needed: float, fixed_widths: list[float]):
            """کوچک‌ترین عرض ثابتِ >= نیاز را برمی‌گرداند؛ اگر نبود، None."""
            for w in sorted(fixed_widths):
                if w >= width_needed:
                    return float(w), float(w - width_needed)
            return None, None

        k15_val = float(var.get("K15") or 0.0)  # اگر قبلاً داری، تکراری نیست
        k15_multiples = []
        for f in range(1, 31):
            need = round(f * k15_val, 2)
            bw, waste = _pick_smallest_fixed(need, fixed_widths_f24)
            k15_multiples.append({
                "f": f,  # همان F24 فرضی
                "need": need,  # F * K15
                "best_width": bw,  # کوچک‌ترین عرض ثابت که جواب می‌دهد
                "waste": None if waste is None else round(waste, 2),
                "ok": (waste is not None) and (0 <= waste < 11.0),  # معیار قبلی تو
            })

        context["k15_multiples"] = k15_multiples

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
                fixed_widths=fixed_widths,
                max_waste_cm=11.0,
                e20_len_cm=var["E20"],
            )

        obj.F24_per_sheet_count = max(1, int(count))
        obj.chosen_sheet_width  = q2(chosen_w, "0.01")
        obj.waste_warning       = bool(warn)
        obj.note_message        = note

        # تزریق به محیط برای فرمول‌های پایین‌دستی
        var["F24"] = float(obj.F24_per_sheet_count)
        var["sheet_width"] = float(chosen_w)

        # پاس نهایی برای خروجی‌های انتهایی
        for key in ["E28","E38","I38","E41","E40","M40","M41","H46","J48","E48"]:
            if key in formulas_py:
                var[key] = as_num(safe_resolve(key), 0.0)
            else:
                var[key] = float(var.get(key, 0.0))

        # ───────── نگاشت به مدل ─────────
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

        # ذخیرهٔ اختیاری
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
