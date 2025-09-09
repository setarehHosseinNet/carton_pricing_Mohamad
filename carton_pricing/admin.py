from django.contrib import admin
from .models import Product, Customer, PhoneNumber, Order, OrderItem, BaseSettings, FluteStep, CalcFormula, PriceQuotation

class PhoneInline(admin.TabularInline):
    model = PhoneNumber
    extra = 1

@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('first_name','last_name','organization','economic_no')
    search_fields = ('first_name','last_name','organization','economic_no')
    inlines = [PhoneInline]

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name','code','created_at')
    search_fields = ('name','code')

class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 1

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('order_no','customer','registered_at','status','total_price')
    list_filter = ('status',)
    search_fields = ('order_no','customer__first_name','customer__last_name','customer__organization')
    inlines = [OrderItemInline]

@admin.register(BaseSettings)
class BaseSettingsAdmin(admin.ModelAdmin):
    list_display = ('overhead_per_meter','sheet_price_cash','sheet_price_credit','profit_rate_percent')

@admin.register(FluteStep)
class FluteStepAdmin(admin.ModelAdmin):
    list_display = ('key','glue_machine','be_flute','middle_layer','c_flute','bottom_layer')

@admin.register(CalcFormula)
class CalcFormulaAdmin(admin.ModelAdmin):
    list_display = ('key','description')
    search_fields = ('key','description','expression')

@admin.register(PriceQuotation)
class PriceQuotationAdmin(admin.ModelAdmin):
    list_display = ('id','customer','created_at','H46_price_before_tax','E48_price_with_tax','waste_warning')
    list_filter = ('payment_type','waste_warning')
    search_fields = ('customer__first_name','customer__last_name','product_code','carton_name')