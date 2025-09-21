# carton_pricing/urls.py
from django.urls import path
from django.views.generic import RedirectView

# ویوهای اصلی در views.py هستند و ویوهای کاغذ در views_paper.py
from . import views

app_name = "carton_pricing"

urlpatterns = [
    # روت → فرم قیمت
    path(
        "",
        RedirectView.as_view(pattern_name="carton_pricing:price_form", permanent=False),
        name="home",
    ),

    # صفحات اصلی
    path("price-form/",    views.price_form_view,   name="price_form"),
    path("base-settings/", views.base_settings_view, name="base_settings"),

    path("formulas/", views.formulas_view, name="formulas"),
    path("formulas/", views.formulas_view, name="formula_list"),  # alias برای سازگاری


    # Paper CRUD (در views_paper.py)
    path("papers/",                 views.paper_list_view,   name="paper_list"),
    path("papers/new/",             views.paper_create_view, name="paper_create"),
    path("papers/<int:pk>/edit/",   views.paper_update_view, name="paper_update"),

    # APIها (نام‌ها با price_form.html هماهنگ است)
    path("api/last-order/",   views.api_last_order,   name="api_last_order"),
    path("api/add-customer/", views.api_add_customer, name="api_add_customer"),
    path("api/add-phone/",    views.api_add_phone,    name="api_add_phone"),
]
