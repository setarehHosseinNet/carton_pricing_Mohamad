from __future__ import annotations

from django import forms
from django.core.exceptions import ValidationError

from .models import (
    Product,
    Customer,
    PhoneNumber,
    BaseSettings,
    FluteStep,
    PriceQuotation,
    CalcFormula,
)

# ---------- ابزارک کوچک برای نرمال‌سازی اعداد فارسی ----------
_PERSIAN_MAP = str.maketrans("۰۱۲۳۴۵۶۷۸۹٬٫،", "0123456789,.,")
def _normalize_num_str(s):
    if s is None:
        return ""
    return str(s).translate(_PERSIAN_MAP)


# ======================== فرم‌های ساده ========================

class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ["name", "code"]
        labels = {"name": "نام محصول", "code": "کد محصول (یکتا)"}
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "code": forms.TextInput(attrs={"class": "form-control"}),
        }


class CustomerForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = ["first_name", "last_name", "organization", "economic_no", "address", "favorite_products"]
        widgets = {
            "favorite_products": forms.CheckboxSelectMultiple,
            "first_name": forms.TextInput(attrs={"class": "form-control"}),
            "last_name": forms.TextInput(attrs={"class": "form-control"}),
            "organization": forms.TextInput(attrs={"class": "form-control"}),
            "economic_no": forms.TextInput(attrs={"class": "form-control"}),
            "address": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }


class PhoneForm(forms.ModelForm):
    class Meta:
        model = PhoneNumber
        fields = ["customer", "label", "number"]
        widgets = {
            "customer": forms.Select(attrs={"class": "form-select"}),
            "label": forms.TextInput(attrs={"class": "form-control"}),
            "number": forms.TextInput(attrs={"class": "form-control", "inputmode": "tel"}),
        }


class BaseSettingsForm(forms.ModelForm):
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
    widgets = {
        "fixed_widths": forms.TextInput(attrs={"placeholder": "مثلاً: [80,90,100,110,120,125,140]", "class": "form-control"}),
    }


class FluteStepForm(forms.ModelForm):
    class Meta:
        model = FluteStep
        fields = ["key", "glue_machine", "be_flute", "middle_layer", "c_flute", "bottom_layer"]


class CalcFormulaForm(forms.ModelForm):
    class Meta:
        model = CalcFormula
        fields = ["key", "expression", "description"]
        widgets = {
            "key": forms.TextInput(attrs={"class": "form-control"}),
            "expression": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }


# ======================== فرم قیمت ========================

# forms.py
from django import forms
from .models import PriceQuotation

class PriceForm(forms.ModelForm):
    # فقط مخصوص فرم؛ در DB نیست
    save_record = forms.BooleanField(
        required=False,
        initial=False,
        label="ذخیره برگه قیمت بعد از محاسبه؟",
    )

    # UI: چک‌باکس (اختیاری)
    # مدل اما انتظار 'on' یا '' دارد
    has_print_notes = forms.BooleanField(
        required=False,
        label="چاپ و نکات تبدیل",
        widget=forms.CheckboxInput,
    )

    # ورودی ساده و اختیاری
    E46_round_adjust = forms.CharField(
        required=False,
        label="جهت رُند کردن (E46)",
        widget=forms.TextInput(attrs={"placeholder": "مثلاً 25"}),
    )

    class Meta:
        model = PriceQuotation
        fields = [
            "customer", "contact_phone", "prepared_by",
            "product_code", "carton_type", "carton_name",
            "I8_qty",
            "A1_layers", "A2_pieces", "A3_door_type", "A4_door_count",
            "E15_len", "G15_wid", "I15_hgt", "E17_lip",
            "D31_flute", "E46_round_adjust",
            "dim_customer", "dim_customer_sample", "dim_sample",
            "tech_new_cliche", "tech_handle_slot", "tech_punch",
            "tech_pallet", "tech_shipping_on_customer",
            "payment_type",
            "has_print_notes",     # ← همین را نگه دار
            "description",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
        }

    # اینجا بولی UI را به رشتهٔ معتبر برای مدل تبدیل می‌کنیم
    def clean_has_print_notes(self):
        v = self.cleaned_data.get("has_print_notes")
        return "on" if v else ""   # دقیقاً مطابق choices مدل

    # اگر کاربر به‌جای عدد، متنِ «true/false/on/off» در POST فرستاد
    # (مثلاً از JS قدیمی) باز هم درست مپ شود:
    def _coerce_truthy(self, raw):
        if isinstance(raw, bool):
            return raw
        s = (str(raw) or "").strip().lower()
        return s in {"1", "true", "on", "yes"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # اگر مقدار اولیه از مدل 'on' بود، چک‌باکس را تیک بزن
        initial = self.initial.get("has_print_notes", "")
        self.initial["has_print_notes"] = (initial == "on")
        # اگر POST خام مقدار متنی داشت، قبل از clean آن را به بولی تبدیل کن
        data = getattr(self, "data", None)
        if data and "has_print_notes" in data:
            # ساخت یک mutable copy اگر QueryDict باشد
            try:
                mutable = data._mutable
                data._mutable = True
            except Exception:
                mutable = None
            data["has_print_notes"] = self._coerce_truthy(data.get("has_print_notes"))
            if mutable is not None:
                data._mutable = mutable
