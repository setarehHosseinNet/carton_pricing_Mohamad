from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse, reverse_lazy
from django.views.generic import ListView
from .models import Paper
from .forms import PaperForm
from decimal import Decimal
from django.db.models import (
    F, Q, Value, DecimalField, ExpressionWrapper
)
from django.db.models.functions import Coalesce
from django.views.generic import ListView
from .models import Paper
class PaperListView(ListView):
    """
       لیست کاغذها با:
         - سورت روی تمام ستون‌ها (با پارامتر o=)
         - جست‌وجوی داینامیک (پارامتر q=)
         - ستون «قیمت واحد (+حمل)» = unit_price + shipping_cost
       """
    model = Paper
    template_name = "papers/paper_list.html"
    context_object_name = "papers"
    paginate_by = 50
    ORDER_MAP = {
        "name": "name_paper",
        "group": "group__name",
        "gsm": "grammage_gsm",
        "width": "width_cm",
        "unit": "unit_price",
        "ship": "shipping_cost",
        "total": "total_price",  # ← annotate شده
    }

    def get_queryset(self):
        # مجموع قیمت = unit_price + shipping_cost (برای نمایش/سورت)
        qs = (
            Paper.objects.select_related("group")
            .annotate(
                total_price=ExpressionWrapper(
                    Coalesce(F("unit_price"), Value(0)) + Coalesce(F("shipping_cost"), Value(0)),
                    output_field=DecimalField(max_digits=12, decimal_places=2),
                )
            )
        )

        # --- جست‌وجوی داینامیک ---
        self.q = (self.request.GET.get("q") or "").strip()
        if self.q:
            base_q = Q(name_paper__icontains=self.q) | Q(group__name__icontains=self.q)
            # اگر عدد بود، روی فیلدهای عددی هم فیلتر مساوی بزن
            num_q = Q()
            try:
                n = Decimal(self.q.replace(",", "."))
                num_q |= Q(grammage_gsm=n)
                num_q |= Q(width_cm=n)
                num_q |= Q(unit_price=n)
                num_q |= Q(shipping_cost=n)
                num_q |= Q(total_price=n)
            except Exception:
                pass
            qs = qs.filter(base_q | num_q)

        # --- سورت ---
        self.o = (self.request.GET.get("o") or "name").strip()  # پیش‌فرض: نام
        desc = self.o.startswith("-")
        key = self.o[1:] if desc else self.o
        db_field = self.ORDER_MAP.get(key, "name_paper")
        order_by = f"-{db_field}" if desc else db_field
        qs = qs.order_by(order_by, "pk")

        # نگه‌دار برای template
        self.order_key = key
        self.order_desc = desc
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update({
            "q": self.q,
            "o": self.o,
            "order_key": self.order_key,
            "order_desc": self.order_desc,
        })
        return ctx
def paper_create_view(request):
    form = PaperForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "کاغذ با موفقیت ایجاد شد.")
        return redirect(reverse("carton_pricing:paper_list"))
    return render(request, "papers/paper_form.html", {"form": form, "mode": "create"})

def paper_update_view(request, pk: int):
    obj = get_object_or_404(Paper, pk=pk)
    form = PaperForm(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "کاغذ به‌روزرسانی شد.")
        return redirect(reverse("carton_pricing:paper_list"))
    return render(request, "papers/paper_form.html", {"form": form, "mode": "update"})
