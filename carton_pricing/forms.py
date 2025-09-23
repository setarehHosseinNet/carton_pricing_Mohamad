# carton_pricing/forms.py
from __future__ import annotations

from typing import Any

from django import forms
from django.core.exceptions import ValidationError

from .models import (
    Product,
    Customer,
    PhoneNumber,
    BaseSettings,
    FluteStep,
    Paper,
    CalcFormula,      # در صورت نیاز در ادمین/فرم جدا
    PriceQuotation,
)
from .utils import _normalize_fixed_widths


# ======================== اعداد فارسی/عربی → لاتین ========================

# نگاشت ارقام و جداکننده‌های فارسی/عربی به لاتین
_PERSIAN_MAP = str.maketrans(
    "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩٬،٫",
    "01234567890123456789,,."
)

class _NormalizeDigitsModelForm(forms.ModelForm):
    """
    هر فرمی که از این ارث ببرد، هنگام مقداردهی، ورودی‌های متنی self.data
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


# ======================== فرم‌های ساده ========================

class ProductForm(_NormalizeDigitsModelForm):
    class Meta:
        model = Product
        fields = ["name", "code"]
        labels = {"name": "نام محصول", "code": "کد محصول (یکتا)"}
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "code": forms.TextInput(attrs={"class": "form-control", "dir": "ltr"}),
        }


class CustomerForm(_NormalizeDigitsModelForm):
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


class PhoneForm(_NormalizeDigitsModelForm):
    class Meta:
        model = PhoneNumber
        fields = ["customer", "label", "number"]
        labels = {"customer": "مشتری", "label": "برچسب", "number": "شماره تماس"}
        widgets = {
            "customer": forms.Select(attrs={"class": "form-select"}),
            "label": forms.TextInput(attrs={"class": "form-control"}),
            "number": forms.TextInput(attrs={"class": "form-control", "inputmode": "tel", "dir": "ltr"}),
        }


class PaperForm(_NormalizeDigitsModelForm):
    """
    اگر در مدل Paper فیلدهای بیشتری داری (گروه، گرماژ، عرض و ...)،
    به‌تناسب اضافه کن. اینجا صرفاً name_paper را نگه داشتیم.
    """
    class Meta:
        model = Paper
        fields = ["name_paper"]
        labels = {"name_paper": "نام کاغذ (Name_Paper)"}
        help_texts = {"name_paper": "مثال: «Kraft 140g عرض 120» یا «Testliner 125g»"}
        widgets = {
            "name_paper": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "نام یکتا…", "autofocus": "autofocus"}
            )
        }

    def clean_name_paper(self) -> str:
        name = (self.cleaned_data.get("name_paper") or "").strip()
        if not name:
            raise ValidationError("نام کاغذ الزامی است.")
        return name


class FluteStepForm(_NormalizeDigitsModelForm):
    class Meta:
        model = FluteStep
        fields = ["key"]
        labels = {"key": "گام فلوت"}
        widgets = {"key": forms.Select(attrs={"class": "form-select"})}


class CalcFormulaForm(_NormalizeDigitsModelForm):
    class Meta:
        model = CalcFormula
        fields = ["key", "expression", "description"]
        labels = {"key": "کلید", "expression": "عبارت محاسباتی", "description": "توضیح"}
        widgets = {
            "key": forms.TextInput(attrs={"class": "form-control", "dir": "ltr"}),
            "expression": forms.Textarea(attrs={"class": "form-control", "rows": 3, "dir": "ltr"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }


# ======================== BaseSettings ========================

class BaseSettingsForm(_NormalizeDigitsModelForm):
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
            "overhead_per_meter": "هزینه سربار هر متر (M30)",
            "sheet_price_cash": "فی ورق نقد (M31)",
            "sheet_price_credit": "فی ورق مدت (M33)",
            "profit_rate_percent": "نرخ سود ٪ (I41)",
            "shipping_cost": "کرایه حمل (E43)",
            "pallet_cost": "هزینه پالت‌بندی (H43)",
            "interface_cost": "هزینه رابط (J43)",
            "fixed_widths": "عرض‌های ثابت ورق (cm)",
        }
        widgets = {
            "overhead_per_meter": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "sheet_price_cash": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "sheet_price_credit": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "profit_rate_percent": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "shipping_cost": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "pallet_cost": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "interface_cost": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "fixed_widths": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "مثل: 80,90,100,110,120,125,140 یا [80, 90, 100]",
                    "dir": "ltr",
                }
            ),
        }

    def clean_fixed_widths(self) -> list[float]:
        """
        ورودی می‌تواند list/tuple یا رشته (JSON/CSV/space) باشد.
        خروجی: لیست یکتای مرتب از اعداد مثبت.
        """
        raw: Any = self.cleaned_data.get("fixed_widths")
        values = _normalize_fixed_widths(
            raw, dedupe=True, sort_result=True, min_value=1.0, precision=0
        )
        return values


# ======================== فرم قیمت ========================

class PriceForm(_NormalizeDigitsModelForm):
    """
    فرم اصلی برگه قیمت.
    - save_record فقط برای UI است.
    - has_print_notes در مدل رشته‌ای ('yes'/'no') است؛ اینجا به صورت چک‌باکس بولی است.
    - «open_bottom_door» یک فیلدِ فقط-فرم (غیرمدلی) است تا کنار «E17_lip» (لب درب بالا)
      جمع زده شود. برای مصرف در ویو، مقدار جمع در cleaned_data با کلید 'E17_total' قرار می‌گیرد.
    """

    # کنترل ذخیره‌ی رکورد بعد از محاسبه
    save_record = forms.BooleanField(
        required=False, initial=False, label="ذخیرهٔ برگه قیمت بعد از محاسبه؟"
    )

    # چک‌باکس بولی برای پرچم چاپ/نکات تبدیل
    has_print_notes_bool = forms.BooleanField(
        required=False, initial=False, label="چاپ و نکات تبدیل"
    )

    # فیلدِ فقط-فرم: درب باز پایین (سانتی‌متر)
    open_bottom_door = forms.DecimalField(
        required=False,
        min_value=0,
        max_digits=6,
        decimal_places=2,
        label="درب باز پایین (cm)",
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "id": "id_open_bottom_door"}),
    )

    class Meta:
        model = PriceQuotation
        fields = [
            # اطلاعات پایه
            "customer", "contact_phone", "prepared_by",
            "product_code", "carton_type", "carton_name",
            "description",

            # پارامترها
            "I8_qty",
            "A1_layers", "A2_pieces", "A3_door_type", "A4_door_count",
            "E15_len", "G15_wid", "I15_hgt",
            "E17_lip",               # لب درب بالا (مدلی)
            "D31_flute",
            "payment_type",
            "E46_round_adjust",

            # انتخاب کاغذها (مستقل از گام فلوت)
            "pq_glue_machine", "pq_be_flute", "pq_middle_layer", "pq_c_flute", "pq_bottom_layer",
        ]
        labels = {
            "customer": "مشتری",
            "contact_phone": "شماره تماس",
            "prepared_by": "تنظیم‌کننده",
            "product_code": "کد محصول",
            "carton_type": "نوع کارتن",
            "carton_name": "نام کارتن",
            "description": "توضیحات",

            "I8_qty": "تیراژ کارتن (I8)",

            "A1_layers": "چند لایه (A1)",
            "A2_pieces": "چند تیکه (A2)",
            "A3_door_type": "نوع درب (A3)",
            "A4_door_count": "تعداد درب (A4)",

            "E15_len": "طول (E15, cm)",
            "G15_wid": "عرض (G15, cm)",
            "I15_hgt": "ارتفاع (I15, cm)",

            "E17_lip": "لب درب بالا (E17, cm)",
            "D31_flute": "گام فلوت (D31)",
            "payment_type": "تسویه فاکتور",
            "E46_round_adjust": "جهت رند کردن (E46)",

            "pq_glue_machine": "چسبان",
            "pq_be_flute": "B/E فلوت",
            "pq_middle_layer": "لاینر میانی",
            "pq_c_flute": "C فلوت",
            "pq_bottom_layer": "لاینر زیر",
        }
        widgets = {
            "customer": forms.Select(attrs={"class": "form-select"}),
            "contact_phone": forms.TextInput(attrs={"class": "form-control", "dir": "ltr"}),
            "prepared_by": forms.TextInput(attrs={"class": "form-control"}),

            "product_code": forms.TextInput(attrs={"class": "form-control", "dir": "ltr"}),
            "carton_type": forms.TextInput(attrs={"class": "form-control"}),
            "carton_name": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3}),

            "I8_qty": forms.NumberInput(attrs={"class": "form-control", "min": 1}),

            "A1_layers": forms.Select(attrs={"class": "form-select"}),
            "A2_pieces": forms.Select(attrs={"class": "form-select"}),
            "A3_door_type": forms.Select(attrs={"class": "form-select"}),
            "A4_door_count": forms.Select(attrs={"class": "form-select"}),

            "E15_len": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "G15_wid": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "I15_hgt": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),

            "E17_lip": forms.NumberInput(
                attrs={"class": "form-control", "step": "0.01", "id": "id_E17_lip"}
            ),

            "D31_flute": forms.Select(attrs={"class": "form-select"}),
            "payment_type": forms.Select(attrs={"class": "form-select"}),

            "E46_round_adjust": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),

            "pq_glue_machine": forms.Select(attrs={"class": "form-select"}),
            "pq_be_flute": forms.Select(attrs={"class": "form-select"}),
            "pq_middle_layer": forms.Select(attrs={"class": "form-select"}),
            "pq_c_flute": forms.Select(attrs={"class": "form-select"}),
            "pq_bottom_layer": forms.Select(attrs={"class": "form-select"}),
        }

    # ----------------- init & helpers -----------------
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # لیست کاغذها برای 5 ستون مستقل
        qs = Paper.objects.all().order_by("name_paper")
        for fld in ("pq_glue_machine", "pq_be_flute", "pq_middle_layer", "pq_c_flute", "pq_bottom_layer"):
            self.fields[fld].queryset = qs

        # مقدار اولیهٔ چک‌باکس چاپ از مدل
        if self.instance and getattr(self.instance, "has_print_notes", None):
            self.initial["has_print_notes_bool"] = (self.instance.has_print_notes == "yes")

        # این دو فیلد به‌صورت پیش‌فرض اختیاری هستند
        self.fields["E17_lip"].required = False
        self.fields["open_bottom_door"].required = False

    # ----------------- validation -----------------
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

        # نگاشت چک‌باکس به مقدار رشته‌ای مدل
        cleaned["has_print_notes"] = "yes" if cleaned.get("has_print_notes_bool") else "no"

        # جمع لب‌ها برای مصرف ویو: E17_total = بالا + پایین
        e17_up = cleaned.get("E17_lip") or 0
        e17_down = cleaned.get("open_bottom_door") or 0
        try:
            cleaned["E17_total"] = (e17_up or 0) + (e17_down or 0)
        except Exception:
            cleaned["E17_total"] = e17_up or 0  # در صورت خطا فقط بالایی

        return cleaned

    # ----------------- save -----------------
    def save(self, commit: bool = True) -> PriceQuotation:
        """
        ensure: مقدار رشته‌ای has_print_notes در مدل با چک‌باکس هم‌راستا شود.
        توجه: «open_bottom_door» فیلد مدلی نیست و ذخیره نمی‌شود.
        """
        obj: PriceQuotation = super().save(commit=False)
        obj.has_print_notes = "yes" if self.cleaned_data.get("has_print_notes_bool") else "no"
        if commit:
            obj.save()
            self.save_m2m()
        return obj
