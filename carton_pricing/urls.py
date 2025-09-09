from django.urls import path
from . import views

urlpatterns = [
    path('base-settings/', views.base_settings_view, name='base_settings'),
    path('formulas/', views.formulas_view, name='formulas'),
    path('price-form/', views.price_form_view, name='price_form'),
    path('api/add-customer/', views.api_add_customer, name='api_add_customer'),
    path('api/add-phone/', views.api_add_phone, name='api_add_phone'),
    path('api/last-order/', views.api_last_order, name='api_last_order'),
]