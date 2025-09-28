# carton_pricing/views_overheads.py
from __future__ import annotations

from typing import Any, Dict
from django.contrib import messages
from django.db.models import Q
from django.http import HttpRequest
from django.urls import reverse, reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView, DeleteView

from .models import OverheadItem
from .forms import OverheadItemForm


class OverheadItemListView(ListView):
    """
    لیست موارد هزینهٔ سربار با جستجو و فیلتر وضعیت.
    GET پارامترها:
      - q     : جستجو در نام
      - state : 'active' (پیش‌فرض) یا 'all' یا 'inactive'
    """
    model = OverheadItem
    template_name = "overheads/list.html"
    context_object_name = "items"
    paginate_by = 25
    ordering = ("name",)

    def get_queryset(self):
        qs = OverheadItem.objects.all().order_by(*self.ordering)
        q = (self.request.GET.get("q") or "").strip()
        state = (self.request.GET.get("state") or "active").strip().lower()

        if state == "active":
            qs = qs.filter(is_active=True)
        elif state == "inactive":
            qs = qs.filter(is_active=False)
        # state == "all" → بدون فیلتر

        if q:
            qs = qs.filter(Q(name__icontains=q))
        return qs

    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        ctx = super().get_context_data(**kwargs)
        ctx["q"] = self.request.GET.get("q", "")
        ctx["state"] = self.request.GET.get("state", "active")
        ctx["total_count"] = OverheadItem.objects.count()
        ctx["active_count"] = OverheadItem.objects.filter(is_active=True).count()
        ctx["inactive_count"] = OverheadItem.objects.filter(is_active=False).count()
        return ctx


class OverheadItemCreateView(CreateView):
    """
    ایجاد آیتم جدید هزینهٔ سربار
    """
    model = OverheadItem
    form_class = OverheadItemForm
    template_name = "overheads/form.html"

    def get_success_url(self):
        messages.success(self.request, "آیتم هزینهٔ سربار با موفقیت ساخته شد.")
        # بعد از ساخت، به لیست برگرد
        return reverse("carton_pricing:overhead_list")


class OverheadItemUpdateView(UpdateView):
    """
    ویرایش آیتم هزینهٔ سربار
    """
    model = OverheadItem
    form_class = OverheadItemForm
    template_name = "overheads/form.html"

    def get_success_url(self):
        messages.success(self.request, "تغییرات آیتم هزینهٔ سربار ذخیره شد.")
        return reverse("carton_pricing:overhead_list")


class OverheadItemDeleteView(DeleteView):
    """
    حذف آیتم هزینهٔ سربار
    """
    model = OverheadItem
    template_name = "overheads/confirm_delete.html"
    success_url = reverse_lazy("carton_pricing:overhead_list")

    def delete(self, request: HttpRequest, *args, **kwargs):
        messages.success(request, "آیتم هزینهٔ سربار حذف شد.")
        return super().delete(request, *args, **kwargs)
