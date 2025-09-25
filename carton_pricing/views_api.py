# carton_pricing/views_api.py
from __future__ import annotations
from decimal import Decimal
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_protect

from .models import Customer, PhoneNumber, PriceQuotation

@require_POST
@csrf_protect
def api_last_order(request):
    """
    آخرین برگه‌قیمت/سفارش مشتری را برمی‌گرداند تا فرم پیش‌فرض شود.
    ورودی: customer=<id>
    خروجی: {ok, found, data}
    """
    cid = (request.POST.get("customer") or "").strip()
    if not cid.isdigit():
        return JsonResponse({"ok": False, "error": "bad_customer"}, status=400)

    last = (
        PriceQuotation.objects
        .filter(customer_id=int(cid))
        .order_by("-id")
        .values(
            "id", "created",
            "product_code", "carton_type", "carton_name",
            "A1_layers","A2_pieces","A3_door_type","A4_door_count",
            "E15_len","G15_wid","I15_hgt",
            "D31_flute","payment_type",
            "I8_qty",
        )
        .first()
    )
    if not last:
        return JsonResponse({"ok": True, "found": False, "data": None}, json_dumps_params={"ensure_ascii": False})
    return JsonResponse({"ok": True, "found": True, "data": last}, json_dumps_params={"ensure_ascii": False})


@require_POST
@csrf_protect
def api_add_customer(request):
    """
    ساخت سریع مشتری. حداقل یکی از first_name یا organization لازم است.
    """
    first = (request.POST.get("first_name") or "").strip()
    last  = (request.POST.get("last_name") or "").strip()
    org   = (request.POST.get("organization") or "").strip()

    if not first and not org:
        return JsonResponse({"ok": False, "error": "نام یا شرکت الزامی است."}, status=400)

    c = Customer.objects.create(
        first_name=first or org,
        last_name=last,
        organization=org,
    )
    return JsonResponse({"ok": True, "id": c.id, "display": str(c)}, json_dumps_params={"ensure_ascii": False})


@require_POST
@csrf_protect
def api_add_phone(request):
    """
    افزودن شماره تماس برای مشتری.
    ورودی: customer=<id>, number, label(اختیاری)
    """
    cid = (request.POST.get("customer") or "").strip()
    number = (request.POST.get("number") or "").strip()
    label  = (request.POST.get("label") or "").strip()

    if not cid.isdigit():
        return JsonResponse({"ok": False, "error": "bad_customer"}, status=400)
    if not number:
        return JsonResponse({"ok": False, "error": "شماره الزامی است."}, status=400)

    try:
        cust = Customer.objects.get(pk=int(cid))
    except Customer.DoesNotExist:
        return JsonResponse({"ok": False, "error": "customer_not_found"}, status=404)

    pn = PhoneNumber.objects.create(customer=cust, number=number, label=label)
    return JsonResponse(
        {"ok": True, "id": pn.id, "display": f"{pn.number} ({pn.label})" if pn.label else pn.number},
        json_dumps_params={"ensure_ascii": False},
    )
