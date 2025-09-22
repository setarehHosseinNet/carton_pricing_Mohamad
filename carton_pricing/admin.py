# carton_pricing/admin.py
from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from .models import (
    Product,
    Customer,
    PhoneNumber,
    Order,
    OrderItem,
    BaseSettings,
    PaperGroup,
    Paper,
    FluteStep,
    CalcFormula,
    PriceQuotation,
)

# ───────── helpers: safe inclusion of model fields ─────────
def _model_field_names(model):
    """برمی‌گرداند: مجموعه‌ی نام تمام فیلدهای مدل (Field/Rel/… )"""
    return {f.name for f in model._meta.get_fields()}

def _safe_flat(model, *names):
    """
    فقط نام‌هایی را نگه می‌دارد که واقعاً روی مدل وجود دارند
    (برای list_display / list_filter / readonly_fields و ...).
    """
    avail = _model_field_names(model)
    out = []
    for n in names:
        if n in avail or hasattr(model, n):
            out.append(n)
    return tuple(out)


# ───────── Inlines ─────────
class PhoneInline(admin.TabularInline):
    model = PhoneNumber
    extra = 1


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 1
    autocomplete_fields = ("product",)


# ───────── Customers / Products / Orders ─────────
@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("id", "first_name", "last_name", "organization", "economic_no")
    search_fields = ("first_name", "last_name", "organization", "economic_no", "phones__number")
    inlines = [PhoneInline]
    ordering = ("id",)
    list_per_page = 50


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = _safe_flat(Product, "id", "name", "code", "created_at", "updated_at")
    search_fields = ("name", "code")
    ordering = ("-id",)
    list_per_page = 50


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = _safe_flat(
        Order,
        "id", "order_no", "customer", "registered_at", "status", "total_price", "updated_at"
    )
    list_filter = _safe_flat(Order, "status", "registered_at")
    search_fields = ("order_no", "customer__first_name", "customer__last_name", "customer__organization")
    inlines = [OrderItemInline]
    autocomplete_fields = ("customer",)
    date_hierarchy = "registered_at"
    list_select_related = ("customer",)
    ordering = ("-registered_at", "-id")
    list_per_page = 50


# ───────── Settings / Catalog ─────────
@admin.register(BaseSettings)
class BaseSettingsAdmin(admin.ModelAdmin):
    list_display = _safe_flat(
        BaseSettings,
        "id",
        "overhead_per_meter",
        "sheet_price_cash",
        "sheet_price_credit",
        "profit_rate_percent",
        "updated_at",
    )
    readonly_fields = _safe_flat(BaseSettings, "singleton_key", "created_at", "updated_at")
    ordering = ("-id",)
    search_fields = ("id",)
    list_per_page = 25


@admin.register(PaperGroup)
class PaperGroupAdmin(admin.ModelAdmin):
    list_display = _safe_flat(PaperGroup, "id", "name", "is_active", "description", "updated_at")
    # مهم: list_filter هم ایمن شود تا اگر is_active هنوز در مدل نباشد، خطا ندهد
    list_filter  = _safe_flat(PaperGroup, "is_active", "created_at", "updated_at")
    search_fields = ("name", "description")
    ordering = ("name",)
    list_per_page = 50


@admin.register(Paper)
class PaperAdmin(admin.ModelAdmin):
    # name_paper + فیلدهای جدید: group, grammage_gsm, width_cm, unit, unit_amount, unit_price, is_active
    list_display = _safe_flat(
        Paper,
        "id",
        "name_paper",
        "group",
        "grammage_gsm",
        "width_cm",
        "unit",
        "unit_amount",
        "unit_price",
        "is_active",
        "updated_at",
    )
    list_filter = _safe_flat(Paper, "group", "unit", "is_active")
    search_fields = ("name_paper", "group__name")
    autocomplete_fields = _safe_flat(Paper, "group")
    list_select_related = _safe_flat(Paper, "group")
    ordering = ("name_paper",)
    list_per_page = 50
    readonly_fields = _safe_flat(Paper, "created_at", "updated_at")


@admin.register(FluteStep)
class FluteStepAdmin(admin.ModelAdmin):
    list_display = _safe_flat(FluteStep, "key", "updated_at")
    search_fields = ("key",)
    ordering = ("key",)
    list_per_page = 50


@admin.register(CalcFormula)
class CalcFormulaAdmin(admin.ModelAdmin):
    list_display = _safe_flat(CalcFormula, "key", "description", "updated_at")
    search_fields = ("key", "description", "expression")
    ordering = ("key",)
    list_per_page = 100


# ───────── Price Quotation ─────────
@admin.register(PriceQuotation)
class PriceQuotationAdmin(admin.ModelAdmin):
    list_display = _safe_flat(
        PriceQuotation,
        "id",
        "customer",
        "carton_name",
        "D31_flute",
        "H46_price_before_tax",
        "E48_price_with_tax",
        "waste_warning",
        "created_at",
    )
    list_filter = _safe_flat(
        PriceQuotation, "payment_type", "waste_warning", "created_at", "A1_layers", "A2_pieces"
    )
    search_fields = (
        "carton_name",
        "product_code",
        "customer__first_name",
        "customer__last_name",
        "customer__organization",
        "pq_glue_machine__name_paper",
        "pq_be_flute__name_paper",
        "pq_middle_layer__name_paper",
        "pq_c_flute__name_paper",
        "pq_bottom_layer__name_paper",
    )
    autocomplete_fields = _safe_flat(
        PriceQuotation,
        "customer",
        "D31_flute",
        "pq_glue_machine",
        "pq_be_flute",
        "pq_middle_layer",
        "pq_c_flute",
        "pq_bottom_layer",
    )
    list_select_related = _safe_flat(
        PriceQuotation,
        "customer",
        "D31_flute",
        "pq_glue_machine",
        "pq_be_flute",
        "pq_middle_layer",
        "pq_c_flute",
        "pq_bottom_layer",
    )
    date_hierarchy = "created_at"
    ordering = ("-created_at", "-id")
    list_per_page = 50

    readonly_fields = _safe_flat(
        PriceQuotation,
        "A6_sheet_code",
        "E20_industrial_len",
        "K20_industrial_wid",
        "F24_per_sheet_count",
        "chosen_sheet_width",
        "E28_carton_consumption",
        "E38_sheet_area_m2",
        "I38_sheet_count",
        "E41_sheet_working_cost",
        "E40_overhead_cost",
        "M40_total_cost",
        "M41_profit_amount",
        "I41_profit_rate",
        "E43_shipping",
        "H43_pallet",
        "J43_interface",
        "H46_price_before_tax",
        "J48_tax",
        "E48_price_with_tax",
        "waste_warning",
        "note_message",
        "created_at",
        "updated_at",
    )

    fieldsets = (
        (_("مشتری و توضیحات"), {
            "fields": (
                "customer",
                "contact_phone",
                "prepared_by",
                "product_code",
                "carton_type",
                "carton_name",
                "description",
            )
        }),
        (_("گزینه‌ها"), {
            "fields": (
                "has_print_notes",
                ("dim_customer", "dim_customer_sample", "dim_sample"),
                ("tech_new_cliche", "tech_handle_slot", "tech_punch", "tech_pallet", "tech_shipping_on_customer"),
            )
        }),
        (_("پارامترهای اصلی"), {
            "fields": (
                "I8_qty",
                ("A1_layers", "A2_pieces", "A3_door_type", "A4_door_count"),
                ("E15_len", "G15_wid", "I15_hgt"),
                "E17_lip",
                "D31_flute",
                "E46_round_adjust",
                "payment_type",
            )
        }),
        (_("ترکیب کاغذ (مستقل از گام فلوت)"), {
            "fields": (
                "pq_glue_machine",
                "pq_be_flute",
                "pq_middle_layer",
                "pq_c_flute",
                "pq_bottom_layer",
            )
        }),
        (_("نتایج/اسنپ‌شات محاسبه (فقط‌خواندنی)"), {
            "classes": ("collapse",),
            "fields": (
                "A6_sheet_code",
                ("E20_industrial_len", "K20_industrial_wid"),
                "F24_per_sheet_count",
                "chosen_sheet_width",
                "E28_carton_consumption",
                "E38_sheet_area_m2",
                "I38_sheet_count",
                ("E41_sheet_working_cost", "E40_overhead_cost"),
                ("M40_total_cost", "M41_profit_amount", "I41_profit_rate"),
                ("E43_shipping", "H43_pallet", "J43_interface"),
                ("H46_price_before_tax", "J48_tax", "E48_price_with_tax"),
                "waste_warning",
                "note_message",
                ("created_at", "updated_at"),
            )
        }),
    )
