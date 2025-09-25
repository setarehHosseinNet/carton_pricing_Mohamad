# carton_pricing/views_customers.py
from __future__ import annotations
from typing import Any, Dict
from django.contrib import messages
from django.db.models import Q
from django.http import HttpRequest
from django.urls import reverse, reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView

from .models import Customer
from .forms import CustomerForm


class CustomerListView(ListView):
    """
    لیست مشتری‌ها با جستجو/صفحه‌بندی.
    اگر پارامتر select=1 باشد، ستون «انتخاب» نمایش داده می‌شود.
    با پارامترهای:
      - ?q=...       → جستجو روی نام/شرکت/شماره اقتصادی/آدرس
      - ?select=1    → نمایش دکمهٔ «انتخاب»
      - ?next=/price-form/  → مقصد پس از انتخاب (پیش‌فرض: price_form)
      - ?param=customer     → نام پارامتر مقصد (پیش‌فرض: customer)
    """
    model = Customer
    template_name = "customers/list.html"
    context_object_name = "customers"
    paginate_by = 20

    def get_queryset(self):
        qs = super().get_queryset().order_by("id")
        q = (self.request.GET.get("q") or "").strip()
        if q:
            qs = qs.filter(
                Q(first_name__icontains=q) |
                Q(last_name__icontains=q) |
                Q(organization__icontains=q) |
                Q(economic_no__icontains=q) |
                Q(address__icontains=q)
            )
        return qs

    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        ctx = super().get_context_data(**kwargs)
        select_mode = (self.request.GET.get("select") == "1")
        next_url    = self.request.GET.get("next") or reverse("carton_pricing:price_form")
        param_name  = self.request.GET.get("param") or "customer"

        ctx.update({
            "q": self.request.GET.get("q", ""),
            "select_mode": select_mode,
            "next_url": next_url,
            "param_name": param_name,
        })
        return ctx


class CustomerCreateView(CreateView):
    """
    ساخت مشتری جدید. پس از ذخیره، به لیست برمی‌گردد
    و در صورت وجود پارامترهای select/next/param آن‌ها را نگه می‌دارد.
    """
    model = Customer
    form_class = CustomerForm
    template_name = "customers/form.html"

    def get_success_url(self):
        base = reverse("carton_pricing:customer_list")
        # حالت انتخاب را نگه می‌داریم تا کاربر بعد از ساخت، بتواند انتخاب کند
        qs = []
        for key in ("select", "next", "param", "q"):
            val = self.request.GET.get(key)
            if val:
                qs.append(f"{key}={val}")
        return base + (("?" + "&".join(qs)) if qs else "")

    def form_valid(self, form):
        messages.success(self.request, "مشتری با موفقیت ثبت شد.")
        return super().form_valid(form)


class CustomerUpdateView(UpdateView):
    model = Customer
    form_class = CustomerForm
    template_name = "customers/form.html"

    def get_success_url(self):
        messages.success(self.request, "اطلاعات مشتری به‌روزرسانی شد.")
        base = reverse("carton_pricing:customer_list")
        qs = []
        for key in ("select", "next", "param", "q", "page"):
            val = self.request.GET.get(key)
            if val:
                qs.append(f"{key}={val}")
        return base + (("?" + "&".join(qs)) if qs else "")

# carton_pricing/views_customers.py
from django.views.generic import ListView
from django.shortcuts import get_object_or_404
from .models import Customer, PriceQuotation

class CustomerInvoicesView(ListView):
    """
    لیست برگه‌های قیمت/فاکتورهای مشتری انتخاب‌شده.
    """
    model = PriceQuotation
    template_name = "customers/customer_invoices.html"
    context_object_name = "invoices"
    paginate_by = 20

    def dispatch(self, request, *args, **kwargs):
        self.customer = get_object_or_404(Customer, pk=kwargs.get("pk"))
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        # اگر TimeStamped دارید، بر اساس آخرین‌ها مرتب می‌کنیم
        qs = PriceQuotation.objects.filter(customer=self.customer).order_by("-id")
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["customer"] = self.customer
        return ctx
