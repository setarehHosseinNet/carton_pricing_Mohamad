# carton_pricing/urls.py
from django.urls import path
from django.views.generic import RedirectView

# ویوهای فرم قیمت و تنظیمات
from . import views

# گروه کاغذ (CRUD)
from .views_paper_groups import (
    PaperGroupListView,
    PaperGroupCreateView,
    PaperGroupUpdateView,
    PaperGroupDeleteView,
    GroupBulkPriceView,
)

# کاغذها (لیست/ایجاد/ویرایش)  ← این import گم شده بود
from .views_papers import (
    PaperListView,
    paper_create_view,
    paper_update_view,
)

app_name = "carton_pricing"

urlpatterns = [
    # روت
    path("", RedirectView.as_view(pattern_name="carton_pricing:price_form", permanent=False), name="home"),

    # صفحات اصلی
    path("price-form/",    views.price_form_view,    name="price_form"),
    path("base-settings/", views.base_settings_view, name="base_settings"),

    # فرمول‌ها
    path("formulas/", views.formulas_view, name="formulas"),
    path("formulas/", views.formulas_view, name="formula_list"),  # alias

    # کاغذها
    path("papers/",               PaperListView.as_view(), name="paper_list"),
    path("papers/new/",           paper_create_view,       name="paper_create"),
    path("papers/<int:pk>/edit/", paper_update_view,       name="paper_update"),

    # گروه‌های کاغذ
    path("groups/",              PaperGroupListView.as_view(),  name="group_list"),
    path("groups/add/",          PaperGroupCreateView.as_view(), name="group_add"),
    path("groups/<int:pk>/edit/",   PaperGroupUpdateView.as_view(), name="group_update"),
    path("groups/<int:pk>/delete/", PaperGroupDeleteView.as_view(), name="group_delete"),

    path("groups/bulk-price/", GroupBulkPriceView.as_view(), name="group_bulk_price"),
]
