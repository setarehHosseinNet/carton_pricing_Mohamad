from django.http import JsonResponse, HttpRequest
from django.shortcuts import render, redirect
from django.views.decorators.http import require_POST
from django.contrib import messages
from decimal import Decimal
from .models import Customer, BaseSettings, CalcFormula, PriceQuotation
from .forms import PriceForm, CustomerForm, PhoneForm, BaseSettingsForm
from .utils import  choose_per_sheet_and_width
import math
from decimal import Decimal, ROUND_HALF_UP
import math, re
from django.contrib import messages
from django.shortcuts import render
from django.http import HttpRequest
from .models import CalcFormula, PriceQuotation
from .forms import PriceForm
from .services import choose_per_sheet_and_width
from .settings_api import get_settings, ensure_default_formulas
from .utils import build_resolver, to_float
from .utils import  safe_eval
# ----- helper to fetch singleton settings -----
def get_settings():
    obj, _ = BaseSettings.objects.get_or_create(singleton_key='ONLY')
    return obj

# ----- default formulas (created if missing) -----
DEFAULT_FORMULAS = {
    'E20': 'E15 + (E17 if A3==1 else 0) + 20',            # طول صنعتی (cm)
    'K20': 'G15 + 20',                                     # عرض صنعتی (cm)
    'E28': 'E20 * K20',                                    # مصرف کارتن (cm^2 placeholder)
    'E38': '(E20/100) * (sheet_width/100)',                # متراژ هر ورق (m^2)
    'I38': 'ceil(I8 / F24)',                               # تعداد ورق
    'E41': 'E38 * sheet_price',                            # مایه کاری ورق
    'E40': 'E38 * M30',                                    # مایه کاری سربار
    'M40': 'E41 + E40',                                    # مایه کاری کلی
    'M41': '(I41/100) * M40',                              # مبلغ سود
    'H46': 'M41 + J43 + H43 + E43 + E46 + M40',            # قیمت نهایی بدون مالیات
    'J48': '(H46/100) * 10',                               # مالیات 10%
    'E48': 'H46 + J48',                                    # قیمت با مالیات
}

def ensure_default_formulas():
    for k, expr in DEFAULT_FORMULAS.items():
        CalcFormula.objects.get_or_create(key=k, defaults={'expression': expr, 'description': k})

# ----- ajax: add customer quickly -----
@require_POST
def api_add_customer(request: HttpRequest):
    form = CustomerForm(request.POST)
    if form.is_valid():
        c = form.save()
        return JsonResponse({'ok': True, 'id': c.id, 'text': str(c)})
    return JsonResponse({'ok': False, 'errors': form.errors}, status=400)

# ----- ajax: add phone quickly -----
@require_POST
def api_add_phone(request: HttpRequest):
    form = PhoneForm(request.POST)
    if form.is_valid():
        p = form.save()
        return JsonResponse({'ok': True, 'id': p.id, 'text': p.number})
    return JsonResponse({'ok': False, 'errors': form.errors}, status=400)

# ----- ajax: last order info for a customer -----
@require_POST
def api_last_order(request: HttpRequest):
    cid = request.POST.get('customer_id')
    try:
        c = Customer.objects.get(id=cid)
    except Customer.DoesNotExist:
        return JsonResponse({'ok': False}, status=404)
    o = c.orders.order_by('-registered_at').first()
    if not o:
        return JsonResponse({'ok': True, 'data': None})
    data = {
        'last_date': o.registered_at.isoformat(),
        'last_fee': float(o.last_fee),
        'last_rate': float(o.last_unit_rate),
    }
    return JsonResponse({'ok': True, 'data': data})

# ----- settings page -----
def base_settings_view(request: HttpRequest):
    bs = get_settings()
    if request.method == 'POST':
        form = BaseSettingsForm(request.POST, instance=bs)
        if form.is_valid():
            form.save()
            messages.success(request, 'اطلاعات پایه ذخیره شد')
            return redirect('base_settings')
    else:
        form = BaseSettingsForm(instance=bs)
    return render(request, 'carton_pricing/base_settings.html', {'form': form})

# ----- formula page -----
from .constants import VARIABLE_LABELS

from .forms import CalcFormulaForm
from .constants import VARIABLE_LABELS

def formulas_view(request: HttpRequest):
    ensure_default_formulas()
    qs = CalcFormula.objects.order_by("key")

    if request.method == "POST":
        if "add_new" in request.POST:
            # حالت افزودن فرمول جدید
            form = CalcFormulaForm(request.POST)
            if form.is_valid():
                form.save()
                messages.success(request, "فرمول جدید اضافه شد.")
                return redirect("formulas")
            else:
                messages.error(request, "خطا در افزودن فرمول.")
        else:
            # حالت بروزرسانی دسته‌ای
            for f in qs:
                new_expr = request.POST.get(f"expr_{f.id}")
                if new_expr is not None:
                    f.expression = new_expr
                    f.save()
            messages.success(request, "فرمول‌ها ذخیره شدند.")
            return redirect("formulas")

    add_form = CalcFormulaForm()
    return render(request, "carton_pricing/formulas.html", {
        "formulas": qs,
        "labels": VARIABLE_LABELS,
        "add_form": add_form,
    })


# ----- price form -----
# def price_form_view(request: HttpRequest):
#     ensure_default_formulas()
#     bs = get_settings()
#     context = {'settings': bs}
#
#     if request.method == 'POST':
#         form = PriceForm(request.POST)
#         if form.is_valid():
#             obj: PriceQuotation = form.save(commit=False)
#             # A6 = int(f"{A1}{A2}{A3}{A4}")
#             obj.A6_sheet_code = int(f"{obj.A1_layers}{obj.A2_pieces}{obj.A3_door_type}{obj.A4_door_count}")
#
#             # load formulas
#             f = {cf.key: cf.expression for cf in CalcFormula.objects.all()}
#             # variables for safe eval
#             # Base settings snapshot
#             obj.I41_profit_rate = Decimal(bs.profit_rate_percent)
#             obj.E43_shipping = Decimal(bs.shipping_cost)
#             obj.H43_pallet = Decimal(bs.pallet_cost)
#             obj.J43_interface = Decimal(bs.interface_cost)
#
#             var = {
#                 'A1': int(obj.A1_layers),
#                 'A2': int(obj.A2_pieces),
#                 'A3': int(obj.A3_door_type),
#                 'A4': int(obj.A4_door_count),
#                 'I8': int(obj.I8_qty),
#                 'E15': float(obj.E15_len),
#                 'G15': float(obj.G15_wid),
#                 'I15': float(obj.I15_hgt),
#                 'E17': float(obj.E17_lip),
#                 'I41': float(bs.profit_rate_percent),
#                 'J43': float(bs.interface_cost),
#                 'H43': float(bs.pallet_cost),
#                 'E43': float(bs.shipping_cost),
#                 'E46': float(obj.E46_round_adjust),
#                 'M30': float(bs.overhead_per_meter),
#             }
#
#             # E20, K20
#             var['E20'] = float(safe_eval(f['E20'], var))
#             obj.E20_industrial_len = Decimal(var['E20']).quantize(Decimal('0.01'))
#             var['K20'] = float(safe_eval(f['K20'], var))
#             obj.K20_industrial_wid = Decimal(var['K20']).quantize(Decimal('0.01'))
#
#             # F24 + choose width
#             required_w = var['K20']
#             fixed_widths = [float(x) for x in (bs.fixed_widths or [])]
#             count, chosen_w, waste, warn, note = choose_per_sheet_and_width(required_w, fixed_widths)
#             obj.F24_per_sheet_count = max(1, int(count))
#             obj.chosen_sheet_width = Decimal(chosen_w)
#             obj.waste_warning = bool(warn)
#             obj.note_message = note
#             var['F24'] = float(obj.F24_per_sheet_count)
#             var['sheet_width'] = float(chosen_w)
#
#             # payment sheet price
#             sheet_price = float(bs.sheet_price_cash if obj.payment_type=='cash' else bs.sheet_price_credit)
#             var['sheet_price'] = sheet_price
#
#             # E28, E38, I38, E41, E40, M40, M41, H46, J48, E48
#             for key in ['E28','E38','I38','E41','E40','M40','M41','H46','J48','E48']:
#                 var[key] = float(safe_eval(f[key], var))
#
#             obj.E28_carton_consumption = Decimal(var['E28']).quantize(Decimal('0.0001'))
#             obj.E38_sheet_area_m2 = Decimal(var['E38']).quantize(Decimal('0.0001'))
#             obj.I38_sheet_count = int(math.ceil(var['I38'])) if isinstance(var['I38'], float) else int(var['I38'])
#             obj.E41_sheet_working_cost = Decimal(var['E41']).quantize(Decimal('0.01'))
#             obj.E40_overhead_cost = Decimal(var['E40']).quantize(Decimal('0.01'))
#             obj.M40_total_cost = Decimal(var['M40']).quantize(Decimal('0.01'))
#             obj.M41_profit_amount = Decimal(var['M41']).quantize(Decimal('0.01'))
#             obj.H46_price_before_tax = Decimal(var['H46']).quantize(Decimal('0.01'))
#             obj.J48_tax = Decimal(var['J48']).quantize(Decimal('0.01'))
#             obj.E48_price_with_tax = Decimal(var['E48']).quantize(Decimal('0.01'))
#
#             if form.cleaned_data.get('save_record'):
#                 obj.save()
#                 messages.success(request, 'برگه قیمت ذخیره شد.')
#             context.update({'result': obj, 'vars': var})
#         else:
#             context['errors'] = form.errors
#         context['form'] = form
#         return render(request, 'carton_pricing/price_form.html', context)
#
#     # GET
#     form = PriceForm(initial={'A1_layers':1,'A2_pieces':1,'A3_door_type':1,'A4_door_count':1,'payment_type':'cash'})
#     context['form'] = form
#     return render(request, 'carton_pricing/price_form.html', context)


# views.py


def q2(val: float | Decimal, places: str) -> Decimal:
    return Decimal(val).quantize(Decimal(places), rounding=ROUND_HALF_UP)

def price_form_view(request: HttpRequest):
    ensure_default_formulas()
    bs = get_settings()
    context = {'settings': bs}

    if request.method == 'POST':
        form = PriceForm(request.POST)
        context['form'] = form

        if not form.is_valid():
            context['errors'] = form.errors
            return render(request, 'carton_pricing/price_form.html', context)

        obj: PriceQuotation = form.save(commit=False)
        obj.A6_sheet_code = int(f"{obj.A1_layers}{obj.A2_pieces}{obj.A3_door_type}{obj.A4_door_count}")

        # فرمول‌ها را از DB بگیر (به سبک اکسل) — در resolver تبدیل می‌کنیم
        formulas_raw = {cf.key: str(cf.expression or '') for cf in CalcFormula.objects.all()}

        cd = form.cleaned_data
        # seed vars (ورودی‌ها و snapshot تنظیمات)
        seed_vars = {
            'A1': int(cd.get('A1_layers') or 0),
            'A2': int(cd.get('A2_pieces') or 0),
            'A3': int(cd.get('A3_door_type') or 0),
            'A4': int(cd.get('A4_door_count') or 0),
            'I8': int(cd.get('I8_qty') or 0),
            'E15': to_float(cd.get('E15_len'), 0.0),
            'G15': to_float(cd.get('G15_wid'), 0.0),
            'I15': to_float(cd.get('I15_hgt'), 0.0),
            'E17': to_float(cd.get('E17_lip'), 0.0),
            'E46': to_float(cd.get('E46_round_adjust'), 0.0),
            'I41': to_float(bs.profit_rate_percent, 0.0),
            'J43': to_float(bs.interface_cost, 0.0),
            'H43': to_float(bs.pallet_cost, 0.0),
            'E43': to_float(bs.shipping_cost, 0.0),
            'M30': to_float(bs.overhead_per_meter, 0.0),
        }

        sheet_price = float(bs.sheet_price_cash if cd.get('payment_type') == 'cash'
                            else bs.sheet_price_credit)
        seed_vars['sheet_price'] = sheet_price

        # snapshot فیلدهای مدل
        obj.I41_profit_rate = Decimal(bs.profit_rate_percent)
        obj.E43_shipping    = Decimal(bs.shipping_cost)
        obj.H43_pallet      = Decimal(bs.pallet_cost)
        obj.J43_interface   = Decimal(bs.interface_cost)

        # Resolver با تبدیل اکسل→پایتون
        resolve, var = build_resolver(formulas_raw, seed_vars)

        try:
            # E20, K20
            var['E20'] = float(resolve('E20'))
            obj.E20_industrial_len = q2(var['E20'], '0.01')

            var['K20'] = float(resolve('K20'))
            obj.K20_industrial_wid = q2(var['K20'], '0.01')

            # انتخاب عرض شیت
            required_w = var['K20']
            fw = bs.fixed_widths or []
            if isinstance(fw, str):
                fw = [w for w in re.split(r'[,\s]+', fw) if w]
            fixed_widths = [to_float(x, 0.0) for x in fw]

            count, chosen_w, waste, warn, note = choose_per_sheet_and_width(required_w, fixed_widths)
            obj.F24_per_sheet_count = max(1, int(count))
            obj.chosen_sheet_width  = q2(chosen_w, '0.01')
            obj.waste_warning       = bool(warn)
            obj.note_message        = note

            var['F24']         = float(obj.F24_per_sheet_count)
            var['sheet_width'] = float(chosen_w)

            # سایر کلیدها
            for key in ['E28','E38','I38','E41','E40','M40','M41','H46','J48','E48']:
                var[key] = float(resolve(key))

            # نگاشت به مدل
            obj.E28_carton_consumption = q2(var['E28'], '0.0001')
            obj.E38_sheet_area_m2      = q2(var['E38'], '0.0001')
            obj.I38_sheet_count        = int(math.ceil(var['I38'])) if isinstance(var['I38'], float) else int(var['I38'])
            obj.E41_sheet_working_cost = q2(var['E41'], '0.01')
            obj.E40_overhead_cost      = q2(var['E40'], '0.01')
            obj.M40_total_cost         = q2(var['M40'], '0.01')
            obj.M41_profit_amount      = q2(var['M41'], '0.01')
            obj.H46_price_before_tax   = q2(var['H46'], '0.01')
            obj.J48_tax                = q2(var['J48'], '0.01')
            obj.E48_price_with_tax     = q2(var['E48'], '0.01')

        except ValueError as e:
            # اگر فرمولی بدسینتکس/ناشناخته بود، پیام ملموس بده
            context['errors'] = {'__all__': [str(e)]}
            context['vars'] = var
            return render(request, 'carton_pricing/price_form.html', context)

        if form.cleaned_data.get('save_record'):
            obj.save()
            messages.success(request, 'برگه قیمت ذخیره شد.')

        context.update({'result': obj, 'vars': var})
        return render(request, 'carton_pricing/price_form.html', context)

    # GET
    form = PriceForm(initial={'A1_layers':1,'A2_pieces':1,'A3_door_type':1,'A4_door_count':1,'payment_type':'cash'})
    context['form'] = form
    return render(request, 'carton_pricing/price_form.html', context)
