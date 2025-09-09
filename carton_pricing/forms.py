from django import forms
from .models import Product, Customer, PhoneNumber, BaseSettings, FluteStep, PriceQuotation, CalcFormula

class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ['name','code']
        labels = {'name':'نام محصول','code':'کد محصول (یکتا)'}

class CustomerForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = ['first_name','last_name','organization','economic_no','address','favorite_products']
        widgets = {'favorite_products': forms.CheckboxSelectMultiple}

class PhoneForm(forms.ModelForm):
    class Meta:
        model = PhoneNumber
        fields = ['customer','label','number']

class BaseSettingsForm(forms.ModelForm):
    class Meta:
        model = BaseSettings
        fields = ['overhead_per_meter','sheet_price_cash','sheet_price_credit','profit_rate_percent','shipping_cost','pallet_cost','interface_cost','fixed_widths']
        widgets = {'fixed_widths': forms.TextInput(attrs={'placeholder':'مثلاً: [80,90,100,110,120,125,140]'})}

class FluteStepForm(forms.ModelForm):
    class Meta:
        model = FluteStep
        fields = ['key','glue_machine','be_flute','middle_layer','c_flute','bottom_layer']

class CalcFormulaForm(forms.ModelForm):
    class Meta:
        model = CalcFormula
        fields = ['key','expression','description']

class PriceForm(forms.ModelForm):
    save_record = forms.BooleanField(label='ذخیره برگه قیمت بعد از محاسبه؟', required=False, initial=True)
    class Meta:
        model = PriceQuotation
        fields = [
            'customer','contact_phone','prepared_by',
            'has_print_notes','dim_customer','dim_customer_sample','dim_sample',
            'tech_new_cliche','tech_handle_slot','tech_punch','tech_pallet','tech_shipping_on_customer',
            'product_code','carton_type','carton_name','description',
            'I8_qty','A1_layers','A2_pieces','A3_door_type','A4_door_count',
            'E15_len','G15_wid','I15_hgt','E17_lip','D31_flute','payment_type','E46_round_adjust',
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows':3}),
        }
