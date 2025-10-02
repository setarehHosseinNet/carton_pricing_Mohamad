# carton_pricing/forms.py
from __future__ import annotations

from typing import Any

from django import forms
from django.core.exceptions import ValidationError
from django.forms import inlineformset_factory

from .models import (
    Product, Customer, PhoneNumber,
    BaseSettings, FluteStep,
    PaperGroup, Paper,
    CalcFormula, PriceQuotation,
)
from .utils import _normalize_fixed_widths
from decimal import Decimal

# ============================================================================
# ۱) نرمال‌سازی ارقام فارسی/عربی → لاتین برای کل فرم‌ها
# ============================================================================
_PERSIAN_MAP = str.maketrans(
    #  فارسی       عربی        جداکننده‌ها
    "۰۱۲۳۴۵۶۷۸۹"  "٠١٢٣٤٥٦٧٨٩" "٬،٫",
    "0123456789"  "0123456789" ",,."
)
FLAG_FIELD_NAMES = [
    "flag_customer_dims",
    "flag_customer_sample",
    "flag_sample_dims",
    "flag_new_cliche",
    "flag_staple",
    "flag_handle_slot",
    "flag_punch",
    "flag_pallet_wrap",
    "flag_shipping_not_seller",
]

class NormalizeDigitsModelForm(forms.ModelForm):
    """
    هر فرمی که از این کلاس ارث ببرد، در __init__ داده‌های متنی (self.data)
    را از ارقام فارسی/عربی به لاتین تبدیل می‌کند تا اعتبارسنجی عددی درست انجام شود.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        data = getattr(self, "data", None)
        if not data:
            return
        # QueryDict را موقتاً قابل‌ویرایش می‌کنیم
        try:
            was_mutable = data._mutable  # type: ignore[attr-defined]
            data._mutable = True         # type: ignore[attr-defined]
        except Exception:
            was_mutable = None
        for k, v in list(data.items()):
            if isinstance(v, str):
                data[k] = v.translate(_PERSIAN_MAP)
        if was_mutable is not None:
            data._mutable = was_mutable  # type: ignore[attr-defined]


# ============================================================================
# ۲) فرم‌های ساده‌ی دامنه
# ============================================================================

from django import forms
from django.core.exceptions import ValidationError

from .models import PriceQuotation, Customer, Paper



class CustomerForm(NormalizeDigitsModelForm):
    class Meta:
        model = Customer
        fields = ["first_name", "last_name", "organization", "economic_no", "address", "favorite_products"]
        labels = {
            "first_name": "نام",
            "last_name": "نام خانوادگی",
            "organization": "نام مجموعه/شرکت",
            "economic_no": "شماره اقتصادی",
            "address": "آدرس",
            "favorite_products": "محصولات پرمصرف",
        }
        widgets = {
            "first_name": forms.TextInput(attrs={"class": "form-control"}),
            "last_name": forms.TextInput(attrs={"class": "form-control"}),
            "organization": forms.TextInput(attrs={"class": "form-control"}),
            "economic_no": forms.TextInput(attrs={"class": "form-control", "dir": "ltr"}),
            "address": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "favorite_products": forms.CheckboxSelectMultiple(),
        }


class PhoneForm(NormalizeDigitsModelForm):
    class Meta:
        model = PhoneNumber
        fields = ["customer", "label", "number"]
        labels = {"customer": "مشتری", "label": "برچسب", "number": "شماره تماس"}
        widgets = {
            "customer": forms.Select(attrs={"class": "form-select"}),
            "label": forms.TextInput(attrs={"class": "form-control"}),
            "number": forms.TextInput(attrs={"class": "form-control", "inputmode": "tel", "dir": "ltr"}),
        }


class FluteStepForm(NormalizeDigitsModelForm):
    class Meta:
        model = FluteStep
        fields = ["key"]
        labels = {"key": "گام فلوت"}
        widgets = {"key": forms.Select(attrs={"class": "form-select"})}


class CalcFormulaForm(NormalizeDigitsModelForm):
    class Meta:
        model = CalcFormula
        fields = ["key", "expression", "description"]
        labels = {"key": "کلید", "expression": "عبارت محاسباتی", "description": "توضیح"}
        widgets = {
            "key": forms.TextInput(attrs={"class": "form-control", "dir": "ltr"}),
            "expression": forms.Textarea(attrs={"class": "form-control", "rows": 3, "dir": "ltr"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }


# ============================================================================
# ۳) تنظیمات پایه
# ============================================================================
class BaseSettingsForm(NormalizeDigitsModelForm):
    class Meta:
        model = BaseSettings
        fields = [
            "overhead_per_meter",
            "sheet_price_cash",
            "sheet_price_credit",
            "profit_rate_percent",
            "shipping_cost",
            "pallet_cost",
            "interface_cost",
            "fixed_widths",
        ]
        labels = {
            "overhead_per_meter": "هزینهٔ سربار هر متر (M30)",
            "sheet_price_cash": "فی ورق نقد (M31)",
            "sheet_price_credit": "فی ورق مدت (M33)",
            "profit_rate_percent": "نرخ سود ٪ (I41)",
            "shipping_cost": "کرایهٔ حمل (E43)",
            "pallet_cost": "هزینهٔ پالت‌بندی (H43)",
            "interface_cost": "هزینهٔ رابط (J43)",
            "fixed_widths": "عرض‌های ثابت ورق (cm)",
        }
        widgets = {
            "overhead_per_meter":  forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "sheet_price_cash":    forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "sheet_price_credit":  forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "profit_rate_percent": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "shipping_cost":       forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "pallet_cost":         forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "interface_cost":      forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "fixed_widths": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "مثال: 80,90,100,110,120,125,140 یا [80, 90, 100]",
                    "dir": "ltr",
                }
            ),
        }

    def clean_fixed_widths(self) -> list[float]:
        """
        ورودی می‌تواند list/tuple یا رشته (CSV/JSON/space) باشد.
        خروجی: لیست مرتب و یکتا از اعداد مثبت.
        """
        raw: Any = self.cleaned_data.get("fixed_widths")
        return _normalize_fixed_widths(
            raw, dedupe=True, sort_result=True, min_value=1.0, precision=0
        )


# ============================================================================
# ۴) کاغذ و گروه کاغذ
# ============================================================================
class PaperGroupForm(NormalizeDigitsModelForm):
    class Meta:
        model = PaperGroup
        fields = ["name"]
        labels = {"name": "نام گروه"}
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "مثلاً: کرافت‌ها"}),
        }


# carton_pricing/forms.py
from django import forms
from .models import Paper

class PaperForm(forms.ModelForm):
    class Meta:
        model = Paper
        fields = [
            "name_paper", "group", "grammage_gsm", "width_cm",
            "unit_price", "shipping_cost", "unit_amount",
        ]
        widgets = {
            "name_paper":  forms.TextInput(attrs={"class": "form-control"}),
            "group":       forms.Select(attrs={"class": "form-select"}),
            "grammage_gsm":forms.NumberInput(attrs={"class": "form-control", "min": 0, "step": 1}),
            "width_cm":    forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "unit_price":  forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "shipping_cost": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),  # 👈 جدید
            "unit_amount": forms.TextInput(attrs={"class": "form-control"}),
        }


# فرم‌ست کاغذها داخل صفحهٔ گروه کاغذ
PaperFormSet = inlineformset_factory(
    parent_model=PaperGroup,
    model=Paper,
    form=PaperForm,
    fields=["name_paper", "group", "grammage_gsm", "width_cm", "unit_price", "unit_amount"],
    extra=1,         # یک ردیف خالی ابتدایی
    can_delete=True,
)


# ============================================================================
# ۵) فرم اصلی برگه قیمت
# ============================================================================


from typing import Optional
from django import forms
from django.core.exceptions import ValidationError
from django.db import models as dj_models

from .models import (
    PriceQuotation,
    Paper,
    PaperGroup,
    Customer,
)

from django import forms
from django.core.exceptions import ValidationError
from typing import Optional
from .models import PriceQuotation, Paper, Customer
from django.db import models as dj_models

class PriceForm(NormalizeDigitsModelForm):
    # کنترل‌های عمومی فرم
    save_record = forms.BooleanField(required=False, initial=False, label="ذخیرهٔ برگه قیمت بعد از محاسبه؟")
    has_print_notes_bool = forms.BooleanField(required=False, initial=False, label="چاپ و نکات تبدیل")

    # فقط-فرم
    open_bottom_door = forms.DecimalField(
        required=False, min_value=0, max_digits=6, decimal_places=2,
        label="درب باز پایین (cm)",
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "id": "id_open_bottom_door"}),
    )

    # ───── تغییر مهم: نوع کارتن به صورت Select با choices مدل ─────
    carton_type = forms.ChoiceField(
        label="نوع کارتن",
        required=False,  # اگر می‌خواهید اجباری باشد، False را بردارید و در مدل هم default بگذارید
        choices=PriceQuotation.CARTON_TYPE_CHOICES,
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    # چک‌باکس‌های «موارد انتخابی»
    flag_customer_dims       = forms.BooleanField(required=False, label="ابعاد مشتری")
    flag_customer_sample     = forms.BooleanField(required=False, label="نمونه مشتری")
    flag_sample_dims         = forms.BooleanField(required=False, label="ابعاد نمونه")
    flag_new_cliche          = forms.BooleanField(required=False, label="کلیشه جدید")
    flag_staple              = forms.BooleanField(required=False, label="منگنه")
    flag_handle_slot         = forms.BooleanField(required=False, label="جای دسته")
    flag_punch               = forms.BooleanField(required=False, label="پانچ")
    flag_pallet_wrap         = forms.BooleanField(required=False, label="پالت‌کشی")
    flag_shipping_not_seller = forms.BooleanField(required=False, label="هزینه حمل بر عهده فروشنده نیست")

    # فقط برای نمایش در قالب
    display_customer: Optional[str] = None
    display_phone: Optional[str] = None

    class Meta:
        model = PriceQuotation
        fields = [
            # سربرگ
            "customer", "contact_phone", "prepared_by",
            "product_code", "carton_type", "carton_name", "description",
            # پارامترها
            "I8_qty",
            "A1_layers", "A2_pieces", "A3_door_type", "A4_door_count",
            "E15_len", "G15_wid", "I15_hgt",
            "E17_lip", "D31_flute",  # ← payment_type عمداً حذف شد
            "E46_round_adjust",
            # کاغذها
            "pq_glue_machine", "pq_be_flute", "pq_middle_layer", "pq_c_flute", "pq_bottom_layer",
        ]
        widgets = {
            "customer": forms.HiddenInput(),
            "contact_phone": forms.HiddenInput(),
            "prepared_by": forms.TextInput(attrs={"class": "form-control"}),
            "product_code": forms.TextInput(attrs={"class": "form-control", "dir": "ltr"}),
            # "carton_type":  ← قبلاً TextInput بود؛ حذف شد تا همان ChoiceField/Select استفاده شود
            "carton_name": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "I8_qty": forms.NumberInput(attrs={"class": "form-control", "min": 1}),
            "A1_layers": forms.Select(attrs={"class": "form-select"}),
            "A2_pieces": forms.Select(attrs={"class": "form-select"}),
            "A3_door_type": forms.Select(attrs={"class": "form-select", "id": "id_A3_door_type"}),
            "A4_door_count": forms.Select(attrs={"class": "form-select"}),
            "E15_len": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "G15_wid": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "I15_hgt": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "E17_lip": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "id": "id_E17_lip"}),
            "D31_flute": forms.Select(attrs={"class": "form-select"}),
            "E46_round_adjust": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "pq_glue_machine": forms.Select(attrs={"class": "form-select"}),
            "pq_be_flute": forms.Select(attrs={"class": "form-select"}),
            "pq_middle_layer": forms.Select(attrs={"class": "form-select"}),
            "pq_c_flute": forms.Select(attrs={"class": "form-select"}),
            "pq_bottom_layer": forms.Select(attrs={"class": "form-select"}),
        }

    # ---------- init ----------
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # اگر به هر دلیل payment_type هنوز در فرم بود، اختیاری و سپس حذفش کن
        if "payment_type" in self.fields:
            self.fields["payment_type"].required = False
            self.fields.pop("payment_type", None)

        # پایهٔ کوئری‌ست
        from django.db.models import F
        qs = Paper.objects.all()

        # حداقل عرض از انتخاب «عرض ورق» (sheet_choice/M24) اگر وجود دارد
        min_width_cm = None
        try:
            from decimal import Decimal as _D
            raw_candidates = []
            if hasattr(self, "data"):
                raw_candidates.append(self.data.get("sheet_choice"))
            if hasattr(self, "initial"):
                raw_candidates.extend([
                    self.initial.get("sheet_choice"),
                    self.initial.get("chosen_sheet_width"),
                    self.initial.get("M24"),
                ])
            for raw in raw_candidates:
                if raw not in (None, "", "-"):
                    try:
                        min_width_cm = _D(str(raw))
                        break
                    except Exception:
                        pass
        except Exception:
            min_width_cm = None

        if min_width_cm is not None:
            qs = qs.filter(width_cm__gte=min_width_cm)

        qs = qs.order_by(F("width_cm").asc(nulls_last=True), "name_paper")

        def _paper_label(p: Paper) -> str:
            w = f"{p.width_cm:.0f}" if p.width_cm is not None else "—"
            return f"{w} cm — {p.name_paper}"

        for fld in ("pq_glue_machine", "pq_be_flute", "pq_middle_layer", "pq_c_flute", "pq_bottom_layer"):
            if fld in self.fields:
                self.fields[fld].queryset = qs
                if hasattr(self.fields[fld], "label_from_instance"):
                    self.fields[fld].label_from_instance = _paper_label  # type: ignore[attr-defined]

        for fld in ("E17_lip", "open_bottom_door", "E46_round_adjust"):
            if fld in self.fields:
                self.fields[fld].required = False

        # مقدار اولیه‌ی چک‌باکس چاپ
        if self.instance and hasattr(self.instance, "has_print_notes"):
            v = getattr(self.instance, "has_print_notes")
            self.initial["has_print_notes_bool"] = str(v).lower() in {"y", "yes", "true", "1"}

        # مقدار اولیهٔ سایر چک‌باکس‌ها
        for name in FLAG_FIELD_NAMES:
            if self.instance and hasattr(self.instance, name):
                v = getattr(self.instance, name)
                self.initial[name] = str(v).lower() in {"y", "yes", "true", "1"}

        # آماده‌سازی نمایش مشتری/تلفن
        cust_id = self.initial.get("customer") or getattr(self.instance, "customer_id", None)
        phone   = self.initial.get("contact_phone") or getattr(self.instance, "contact_phone", "")
        if cust_id:
            try:
                cust = Customer.objects.only("first_name", "last_name", "organization").get(pk=cust_id)
                self.display_customer = str(cust)
            except Customer.DoesNotExist:
                self.display_customer = None
            self.initial["customer"] = cust_id
        self.display_phone = phone or ""
        if phone is not None:
            self.initial["contact_phone"] = phone

    # ---------- validation ----------
    def clean_E17_lip(self):
        v = self.cleaned_data.get("E17_lip")
        if v is not None and v < 0:
            raise ValidationError("لب درب نمی‌تواند منفی باشد.")
        return v

    def clean_open_bottom_door(self):
        v = self.cleaned_data.get("open_bottom_door")
        if v is not None and v < 0:
            raise ValidationError("درب باز پایین نمی‌تواند منفی باشد.")
        return v

    def clean(self):
        cleaned = super().clean()
        cleaned["has_print_notes"] = "yes" if cleaned.get("has_print_notes_bool") else "no"
        e17_up = cleaned.get("E17_lip") or 0
        e17_dn = cleaned.get("open_bottom_door") or 0
        cleaned["E17_total"] = (e17_up or 0) + (e17_dn or 0)
        return cleaned

    # ---------- save ----------
    def save(self, commit: bool = True) -> PriceQuotation:
        obj: PriceQuotation = super().save(commit=False)

        # نگاشت چاپ
        if hasattr(obj, "has_print_notes"):
            v = self.cleaned_data.get("has_print_notes_bool", False)
            try:
                f = obj._meta.get_field("has_print_notes")
                if isinstance(f, dj_models.BooleanField):
                    obj.has_print_notes = bool(v)
                else:
                    obj.has_print_notes = "yes" if v else "no"
            except Exception:
                obj.has_print_notes = "yes" if v else "no"

        # نگاشت چک‌باکس‌ها
        for name in FLAG_FIELD_NAMES:
            if hasattr(obj, name):
                v = bool(self.cleaned_data.get(name, False))
                try:
                    f = obj._meta.get_field(name)
                    if isinstance(f, dj_models.BooleanField):
                        setattr(obj, name, v)
                    else:
                        setattr(obj, name, "yes" if v else "no")
                except Exception:
                    setattr(obj, name, "yes" if v else "no")

        # تحمیل قفل سروری برای مشتری و تلفن
        if "customer" in self.initial:
            obj.customer_id = self.initial["customer"]
        if "contact_phone" in self.initial:
            obj.contact_phone = self.initial["contact_phone"]

        if commit:
            obj.save()
            self.save_m2m()
        return obj

class GroupPriceUpdateForm(forms.Form):
    """
    فرم اعمال قیمت واحد جدید روی تمام کاغذهای یک گروه.
    """
    group = forms.ModelChoiceField(
        queryset=PaperGroup.objects.order_by("name"),
        label="گروه کاغذ",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    new_price = forms.DecimalField(
        max_digits=12, decimal_places=0, min_value=0,
        label="قیمت واحد جدید",
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
    )
    # 🆕 اختیاری: به‌روزرسانی هزینه حمل
    apply_shipping = forms.BooleanField(required=False, initial=False, label="به‌روزرسانی هزینه حمل؟")
    new_shipping_cost = forms.DecimalField(
        max_digits=12, decimal_places=0, min_value=0, required=False,
        label="هزینه حمل جدید (اختیاری)",
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"})
    )


from django import forms
from .models import ExtraCharge

class ExtraChargeForm(forms.ModelForm):
    class Meta:
        model = ExtraCharge
        fields = [
            "title", "amount_cash", "amount_credit",
            "is_required", "show_on_invoice","priority","Percentage", "is_active",
        ]
        labels = {
            "title": "بندهای اضافی به مبلغ",
            "amount_cash": "مبلغ برای نقد",
            "amount_credit": "مبلغ برای مدت‌دار",
            "priority":"عدد کوچکتر یعنی زودتر محاسبه شود (یکتا)",
            "is_required": "اجبار برای اعمال",
            "show_on_invoice": "نمایش به عنوان یک بند در فاکتور",
            "Percentage":"بصورت درصدی از کل محاسبه شود",
            "is_active": "فعال؟",

        }
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "amount_cash": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "amount_credit": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "priority": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "is_required": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "show_on_invoice": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "Percentage": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }



from django import forms
from .models import OverheadItem

class OverheadItemForm(forms.ModelForm):
    class Meta:
        model = OverheadItem
        fields = ["name", "unit_cost", "is_active"]
        labels = {
            "name": "نام هزینه",
            "unit_cost": "هزینهٔ واحد",
            "is_active": "فعال؟",
        }
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "unit_cost": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }