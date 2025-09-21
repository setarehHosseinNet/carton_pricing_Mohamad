# carton_pricing/admin.py
from django.contrib import admin
from .models import (
    Product,
    Customer,
    PhoneNumber,
    Order,
    OrderItem,
    BaseSettings,
    Paper,
    FluteStep,
    CalcFormula,
    PriceQuotation,
)

# ---------------- Inlines ----------------
class PhoneInline(admin.TabularInline):
    model = PhoneNumber
    extra = 1


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 1
    autocomplete_fields = ("product",)


# ---------------- Customers / Products / Orders ----------------
@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("id", "first_name", "last_name", "organization", "economic_no")
    search_fields = ("first_name", "last_name", "organization", "economic_no", "phones__number")
    inlines = [PhoneInline]
    ordering = ("id",)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "code", "created_at")
    search_fields = ("name", "code")
    ordering = ("-created_at",)


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("id", "order_no", "customer", "registered_at", "status", "total_price")
    list_filter = ("status", "registered_at")
    search_fields = ("order_no", "customer__first_name", "customer__last_name", "customer__organization")
    inlines = [OrderItemInline]
    autocomplete_fields = ("customer",)
    date_hierarchy = "registered_at"
    list_select_related = ("customer",)
    ordering = ("-registered_at", "-id")


# ---------------- Settings / Catalog ----------------
@admin.register(BaseSettings)
class BaseSettingsAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "overhead_per_meter",
        "sheet_price_cash",
        "sheet_price_credit",
        "profit_rate_percent",
        "updated_at",
    )
    readonly_fields = ("singleton_key",)
    ordering = ("-updated_at", "-id")
    search_fields = ("id",)


@admin.register(Paper)
class PaperAdmin(admin.ModelAdmin):
    list_display = ("id", "name_paper", "updated_at")
    search_fields = ("name_paper",)
    ordering = ("name_paper",)


@admin.register(FluteStep)
class FluteStepAdmin(admin.ModelAdmin):
    # در نسخه‌ی جدید فقط کلید گام را نگه می‌داریم
    list_display = ("key", "updated_at")
    search_fields = ("key",)
    ordering = ("key",)


@admin.register(CalcFormula)
class CalcFormulaAdmin(admin.ModelAdmin):
    list_display = ("key", "description", "updated_at")
    search_fields = ("key", "description", "expression")
    ordering = ("key",)


# ---------------- Price Quotation ----------------
@admin.register(PriceQuotation)
class PriceQuotationAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "customer",
        "carton_name",
        "D31_flute",
        "H46_price_before_tax",
        "E48_price_with_tax",
        "waste_warning",
        "created_at",
    )
    list_filter = ("payment_type", "waste_warning", "created_at", "A1_layers", "A2_pieces")
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
    autocomplete_fields = (
        "customer",
        "D31_flute",
        "pq_glue_machine",
        "pq_be_flute",
        "pq_middle_layer",
        "pq_c_flute",
        "pq_bottom_layer",
    )
    list_select_related = (
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

    # فیلدهای محاسباتی را readonly می‌گذاریم تا از ویرایشِ دستی جلوگیری شود
    readonly_fields = (
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
        ("مشتری و توضیحات", {
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
        ("گزینه‌ها", {
            "fields": (
                "has_print_notes",
                ("dim_customer", "dim_customer_sample", "dim_sample"),
                ("tech_new_cliche", "tech_handle_slot", "tech_punch", "tech_pallet", "tech_shipping_on_customer"),
            )
        }),
        ("پارامترهای اصلی", {
            "fields": (
                "I8_qty",
                ("A1_layers", "A2_pieces", "A3_door_type", "A4_door_count"),
                ("E15_len", "G15_wid", "I15_hgt"),
                "E17_lip",
                "D31_flute",
                "E46_round_adjust",
                ("payment_type",),
            )
        }),
        ("ترکیب کاغذ (مستقل از گام فلوت)", {
            "fields": (
                "pq_glue_machine",
                "pq_be_flute",
                "pq_middle_layer",
                "pq_c_flute",
                "pq_bottom_layer",
            )
        }),
        ("نتایج/اسنپ‌شات محاسبه (فقط‌خواندنی)", {
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
