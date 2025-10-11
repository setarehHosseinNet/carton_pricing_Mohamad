# carton_pricing/urls.py
from django.urls import path
from django.views.generic import RedirectView

# صفحات اصلی و تنظیمات
from . import views

# API ها
from . import views_api

# مشتری‌ها (CRUD + فاکتورها)
from . import views_customers

# بندهای اضافی (CRUD)
from . import views_extra_charge as ec

# گروه‌های کاغذ (CRUD + به‌روزرسانی گروهی قیمت)
from .views_paper_groups import (
    PaperGroupListView,
    PaperGroupCreateView,
    PaperGroupUpdateView,
    PaperGroupDeleteView,
    GroupBulkPriceView,
)

# کاغذها (لیست/ایجاد/ویرایش)
from .views_papers import (
    PaperListView,
    paper_create_view,
    paper_update_view,
)
from .views_overheads import (
    OverheadItemListView,
    OverheadItemCreateView,
    OverheadItemUpdateView,
    OverheadItemDeleteView,
)
app_name = "carton_pricing"

urlpatterns = [
    # روت (در صورت تمایل می‌توانید به فرم قیمت ریدایرکت کنید)
    # path("", RedirectView.as_view(pattern_name="carton_pricing:price_form", permanent=False), name="home")
    path("", views_customers.CustomerListView.as_view(), name="customer_list"),

    # ───────── فرم قیمت و تنظیمات ─────────
    path("price-form/",    views.price_form_view,    name="price_form"),
    path("base-settings/", views.base_settings_view, name="base_settings"),

    # ───────── API ها ─────────
    path("api/last-order/",   views_api.api_last_order,   name="api_last_order"),
    path("api/add-customer/", views_api.api_add_customer, name="api_add_customer"),
    path("api/add-phone/",    views_api.api_add_phone,    name="api_add_phone"),

    # ───────── فرمول‌ها ─────────
    path("formulas/", views.formulas_view, name="formulas"),
    # برای سازگاری با نام قدیمی:
    path("formulas/", views.formulas_view, name="formula_list"),

    # ───────── کاغذها ─────────
    path("papers/",               PaperListView.as_view(), name="paper_list"),
    path("papers/new/",           paper_create_view,       name="paper_create"),
    path("papers/<int:pk>/edit/", paper_update_view,       name="paper_update"),

    # ───────── گروه‌های کاغذ ─────────
    path("groups/",                 PaperGroupListView.as_view(),   name="group_list"),
    path("groups/add/",             PaperGroupCreateView.as_view(), name="group_add"),
    path("groups/<int:pk>/edit/",   PaperGroupUpdateView.as_view(), name="group_update"),




    path("groups/<int:pk>/delete/", PaperGroupDeleteView.as_view(), name="group_delete"),
    path("groups/bulk-price/",      GroupBulkPriceView.as_view(),   name="group_bulk_price"),

    # ───────── مشتری‌ها ─────────
    path("customers/",                 views_customers.CustomerListView.as_view(),   name="customer_list"),
    path("customers/new/",             views_customers.CustomerCreateView.as_view(), name="customer_create"),
    path("customers/<int:pk>/edit/",   views_customers.CustomerUpdateView.as_view(), name="customer_update"),
    path("customers/<int:pk>/invoices/", views_customers.CustomerInvoicesView.as_view(), name="customer_invoices"),

    # ───────── بندهای اضافی (Extra Charges) ─────────
    path("extra-charges/",               ec.ExtraChargeList.as_view(),   name="extracharge_list"),
    path("extra-charges/new/",           ec.ExtraChargeCreate.as_view(), name="extracharge_create"),
    path("extra-charges/<int:pk>/edit/", ec.ExtraChargeUpdate.as_view(), name="extracharge_update"),
    path("extra-charges/<int:pk>/delete/", ec.ExtraChargeDelete.as_view(), name="extracharge_delete"),

    # ─────────  هزینه سربار ─────────
    path("overheads/", OverheadItemListView.as_view(), name="overhead_list"),
    path("overheads/new/", OverheadItemCreateView.as_view(), name="overhead_create"),
    path("overheads/<int:pk>/edit/", OverheadItemUpdateView.as_view(), name="overhead_update"),
    path("overheads/<int:pk>/delete/", OverheadItemDeleteView.as_view(), name="overhead_delete"),

    path("quotation/<int:pk>/rahkaran/", views.link_rahkaran_invoice, name="link_rahkaran_invoice"),
]
