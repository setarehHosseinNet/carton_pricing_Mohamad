# carton_pricing/views_paper_groups.py
from __future__ import annotations

from typing import Any, Dict, Optional

from django import forms
from django.contrib import messages
from django.db import transaction
from django.db.models import Count
from django.db.models.deletion import ProtectedError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import DeleteView, ListView

from .models import Paper, PaperGroup


# ============================================================
#  فرم‌ها
# ============================================================
# ... بالای فایل همان است ...
from django.forms import inlineformset_factory, NumberInput, TextInput

# ویجت name_paper → list="paper-name-list"
PaperFormSet = inlineformset_factory(
    parent_model=PaperGroup,
    model=Paper,
    fields=["name_paper", "grammage_gsm", "width_cm", "unit_price","shipping_cost", "unit_amount"],
    extra=0,
    can_delete=True,
    widgets={
        "name_paper":  TextInput(attrs={
            "class": "form-control",
            "placeholder": "نام کاغذ",
            "list": "paper-name-list",   # ← این مهم است
        }),
        "grammage_gsm": NumberInput(attrs={"class": "form-control", "min": 0}),
        "width_cm":     NumberInput(attrs={"class": "form-control", "step": "0.01", "min": 0}),
        "unit_price":   NumberInput(attrs={"class": "form-control", "step": "0.01", "min": 0}),
        "shipping_cost": NumberInput(attrs={"class": "form-control", "step": "0.01", "min": 0}),
        "unit_amount":  TextInput(attrs={"class": "form-control", "placeholder": "مثلاً 1 m²"}),
    },
)

class GroupWithFormsetBase(View):
    template_name = "papers/group_form.html"
    success_url = reverse_lazy("carton_pricing:group_list")
    mode: str = "create"
    form_prefix: str = "paper_set"

    # ... بقیه کد همان است ...

    def _render(self, request, form, formset):
        # نام‌های موجود برای datalist
        paper_name_choices = list(
            Paper.objects.order_by("name_paper")
            .values_list("name_paper", flat=True)
            .distinct()
        )
        return render(request, self.template_name, {
            "form": form,
            "formset": formset,
            "mode": self.mode,
            "paper_name_choices": paper_name_choices,   # ← به قالب بده
        })

class PaperGroupForm(forms.ModelForm):
    """فرم ساده‌ی گروه کاغذ."""
    class Meta:
        model = PaperGroup
        fields = ["name"]
        labels = {"name": "نام گروه"}
        widgets = {"name": forms.TextInput(attrs={"class": "form-control"})}


# فرم‌ست درون‌خطی برای مدیریت کاغذهایِ یک گروه
from django.forms import inlineformset_factory, NumberInput, TextInput

PaperFormSet = inlineformset_factory(
    parent_model=PaperGroup,
    model=Paper,
    fields=["name_paper", "grammage_gsm", "width_cm", "unit_price","shipping_cost", "unit_amount"],
    extra=0,                # ردیف اضافه اولیه (می‌توانید 1 بگذارید)
    can_delete=True,        # امکان حذف ردیف‌ها
    widgets={
        "name_paper":   TextInput(attrs={"class": "form-control", "placeholder": "نام کاغذ"}),
        "grammage_gsm": NumberInput(attrs={"class": "form-control", "min": 0}),
        "width_cm":     NumberInput(attrs={"class": "form-control", "step": "0.01", "min": 0}),
        "unit_price":   NumberInput(attrs={"class": "form-control", "step": "0.01", "min": 0}),
        "shipping_cost":   NumberInput(attrs={"class": "form-control", "step": "0.01", "min": 0}),
        "unit_amount":  TextInput(attrs={"class": "form-control", "placeholder": "مثلاً 1 m²"}),
    },
)


# ============================================================
#  لیست گروه‌ها
# ============================================================

class PaperGroupListView(ListView):
    """
    نمایش لیست گروه‌ها به‌همراه تعداد کاغذهای هر گروه.
    """
    model = PaperGroup
    template_name = "papers/group_list.html"
    context_object_name = "groups"
    paginate_by = 25

    def get_queryset(self):
        return (
            PaperGroup.objects
            .annotate(papers_count=Count("papers"))
            .order_by("name")
        )


# ============================================================
#  کلاس پایه‌ی ساخت/ویرایش گروه به همراه فرم‌ست کاغذها
# ============================================================

class GroupWithFormsetBase(View):
    """
    کنترلر مشترک برای «ایجاد» و «ویرایش» PaperGroup به‌همراه PaperFormSet.

    زیرکلاس‌ها باید:
      - `mode` را ("create" یا "update") تعیین کنند.
      - `get_object()` را در حالت update پیاده‌سازی کنند.
    """
    template_name = "papers/group_form.html"
    success_url = reverse_lazy("carton_pricing:group_list")
    mode: str = "create"      # یا "update"
    form_prefix: str = "paper_set"

    # ----- helpers -----
    def get_object(self) -> Optional[PaperGroup]:
        """در حالت ویرایش، شیء گروه را برگردانید."""
        return None

    def _build_forms(self, request: HttpRequest, instance: Optional[PaperGroup] = None):
        """
        ساخت فرم گروه و فرم‌ست کاغذها (POST یا GET).
        """
        if request.method == "POST":
            form = PaperGroupForm(request.POST, instance=instance)
            formset = PaperFormSet(request.POST, instance=instance, prefix=self.form_prefix)
        else:
            form = PaperGroupForm(instance=instance)
            formset = PaperFormSet(instance=instance, prefix=self.form_prefix)
        return form, formset

    def _render(self, request: HttpRequest, form, formset) -> HttpResponse:
        """
        رندر کردن قالب با کانتکست منسجم.
        """
        ctx: Dict[str, Any] = {
            "form": form,
            "formset": formset,
            "mode": self.mode,
        }
        return render(request, self.template_name, ctx)

    # ----- HTTP verbs -----
    def get(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        obj = self.get_object()
        form, formset = self._build_forms(request, instance=obj)
        return self._render(request, form, formset)

    def post(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        obj = self.get_object()
        form, formset = self._build_forms(request, instance=obj)

        if not (form.is_valid() and formset.is_valid()):
            # نمایش دوباره‌ی فرم با خطاها
            return self._render(request, form, formset)

        # ذخیره‌ی اتمیک گروه و کاغذها
        with transaction.atomic():
            obj = form.save()
            formset.instance = obj
            formset.save()

        messages.success(
            request,
            "گروه و کاغذها ذخیره شد." if self.mode == "create" else "گروه و کاغذها به‌روزرسانی شد.",
        )
        return redirect(self.success_url)


# ============================================================
#  ایجاد / ویرایش / حذف
# ============================================================

class PaperGroupCreateView(GroupWithFormsetBase):
    """ایجاد گروه جدید به‌همراه ردیف‌های کاغذ (فرم‌ست)."""
    mode = "create"


class PaperGroupUpdateView(GroupWithFormsetBase):
    """ویرایش گروه موجود + فرم‌ست کاغذها."""
    mode = "update"

    def get_object(self) -> Optional[PaperGroup]:
        return get_object_or_404(PaperGroup, pk=self.kwargs.get("pk"))


class PaperGroupDeleteView(DeleteView):
    """
    حذف گروه. چون ForeignKey کاغذ → گروه روی PROTECT است،
    اگر گروه هنوز کاغذ داشته باشد، حذف ممنوع و پیام مناسب نمایش داده می‌شود.
    """
    model = PaperGroup
    template_name = "papers/group_confirm_delete.html"
    success_url = reverse_lazy("carton_pricing:group_list")

    def delete(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        self.object = self.get_object()
        try:
            response = super().delete(request, *args, **kwargs)
            messages.success(request, "گروه حذف شد.")
            return response
        except ProtectedError:
            messages.error(request, "ابتدا کاغذهای این گروه را حذف/منتقل کنید (وابستگی وجود دارد).")
            return redirect(reverse("carton_pricing:group_update", kwargs={"pk": self.object.pk}))



# carton_pricing/views_paper_groups.py
from decimal import Decimal, ROUND_HALF_UP
from django.views.generic.edit import FormView
from django.urls import reverse, reverse_lazy
from django.contrib import messages
from django.db import transaction
from .forms import GroupPriceUpdateForm
from .models import PaperGroup, Paper

class GroupBulkPriceView(FormView):
    """
    اعمال یک/چند مقدار جدید (قیمت واحد و/یا هزینه حمل) روی تمام Paperهای یک گروه.
    """
    template_name = "carton_pricing/groups/bulk_price.html"  # اگر مسیر دیگری داری، هماهنگش کن
    form_class = GroupPriceUpdateForm
    success_url = reverse_lazy("carton_pricing:group_bulk_price")

    # گروه انتخاب‌شده از querystring را داخل فرم initial می‌گذاریم
    def get_initial(self):
        initial = super().get_initial()
        gid = self.request.GET.get("group")
        if gid:
            try:
                initial["group"] = PaperGroup.objects.get(pk=gid)
            except PaperGroup.DoesNotExist:
                pass
        return initial

    # برای پیش‌نمایش لیست کاغذهای گروه
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        gid = self.request.POST.get("group") or self.request.GET.get("group")
        ctx["selected_group"] = None
        ctx["papers"] = []
        if gid:
            try:
                grp = PaperGroup.objects.get(pk=gid)
                ctx["selected_group"] = grp
                ctx["papers"] = Paper.objects.filter(group=grp).order_by("name_paper")
            except PaperGroup.DoesNotExist:
                pass
        return ctx

    def form_valid(self, form):
        group = form.cleaned_data["group"]
        new_price = form.cleaned_data.get("new_price")
        new_ship  = form.cleaned_data.get("new_shipping_cost")

        updates = {}
        if new_price not in (None, ""):
            updates["unit_price"] = Decimal(new_price).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if new_ship not in (None, ""):
            updates["shipping_cost"] = Decimal(new_ship).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        if not updates:
            messages.warning(self.request, "مقداری برای به‌روزرسانی ارسال نشد.")
            return super().form_valid(form)

        with transaction.atomic():
            qs = Paper.objects.select_for_update().filter(group=group)
            updated = qs.update(**updates)

        # پیام موفقیت شفاف
        parts = []
        if "unit_price" in updates:
            parts.append(f"قیمت واحد = {updates['unit_price']}")
        if "shipping_cost" in updates:
            parts.append(f"هزینه حمل = {updates['shipping_cost']}")
        msg = " و ".join(parts)

        messages.success(self.request, f"{updated} کاغذ در گروه «{group.name}» به‌روزرسانی شد: {msg}")

        # بعد از موفقیت، گروه انتخاب‌شده در آدرس باقی بماند تا پیش‌نمایش بماند
        self.success_url = f"{reverse('carton_pricing:group_bulk_price')}?group={group.pk}"
        return super().form_valid(form)
