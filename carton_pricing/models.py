from __future__ import annotations
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone

class TimeStamped(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        abstract = True

class Product(TimeStamped):
    name = models.CharField('نام محصول', max_length=200)
    code = models.CharField('کد محصول (یکتا)', max_length=64, unique=True)
    def __str__(self):
        return f"{self.name} — {self.code}"

class Customer(TimeStamped):
    first_name = models.CharField('نام', max_length=100)
    last_name  = models.CharField('نام خانوادگی', max_length=100, blank=True)
    organization = models.CharField('نام مجموعه/شرکت', max_length=200, blank=True)
    economic_no = models.CharField('شماره اقتصادی', max_length=100, blank=True)
    address = models.TextField('آدرس', blank=True)
    favorite_products = models.ManyToManyField(Product, verbose_name='محصولات پرمصرف', blank=True)
    def __str__(self):
        base = f"{self.first_name} {self.last_name}".strip()
        return f"{base} ({self.organization})" if self.organization else base

class PhoneNumber(TimeStamped):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='phones')
    label = models.CharField('برچسب', max_length=50, blank=True)
    number = models.CharField('شماره تماس', max_length=50)
    def __str__(self):
        return f"{self.customer} - {self.number}"

class Order(TimeStamped):
    STATUS_CHOICES = [
        ('pending', 'در انتظار'),
        ('confirmed', 'تایید شده'),
        ('in_production', 'در حال تولید'),
        ('delivered', 'تحویل شده'),
        ('cancelled', 'لغو شده'),
    ]
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name='orders', verbose_name='مشتری')
    order_no = models.CharField('شماره سفارش', max_length=50, unique=True)
    registered_at = models.DateField('تاریخ ثبت')
    delivery_date = models.DateField('تاریخ تحویل', null=True, blank=True)
    commitment_date = models.DateField('تاریخ تعهدی', null=True, blank=True)
    status = models.CharField('وضعیت', max_length=20, choices=STATUS_CHOICES, default='pending')
    total_price = models.DecimalField('قیمت سفارش', max_digits=18, decimal_places=2, default=0)
    # latest rate/fee fields (optional, used for "آخرین سفارش")
    last_unit_rate = models.DecimalField('نرخ واحد', max_digits=18, decimal_places=2, default=0)
    last_fee = models.DecimalField('فی', max_digits=18, decimal_places=2, default=0)
    def __str__(self):
        return f"{self.order_no} — {self.customer}"

class OrderItem(TimeStamped):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField('تعداد', validators=[MinValueValidator(1)])
    unit_price = models.DecimalField('فی', max_digits=18, decimal_places=2, default=0)
    def line_total(self):
        return self.quantity * self.unit_price

class BaseSettings(TimeStamped):
    """Singleton-style settings for pricing."""
    singleton_key = models.CharField(max_length=8, default='ONLY', unique=True, editable=False)
    overhead_per_meter = models.DecimalField('هزینه سربار هر متر (M30)', max_digits=18, decimal_places=2, default=0)  # M30
    sheet_price_cash = models.DecimalField('فی ورق نقد (M31)', max_digits=18, decimal_places=2, default=0)  # M31
    sheet_price_credit = models.DecimalField('فی ورق مدت (M33)', max_digits=18, decimal_places=2, default=0)  # M33
    profit_rate_percent = models.DecimalField('نرخ سود ٪ (I41)', max_digits=6, decimal_places=2, default=10)  # I41
    shipping_cost = models.DecimalField('کرایه حمل (E43)', max_digits=18, decimal_places=2, default=0)
    pallet_cost = models.DecimalField('هزینه پالت‌بندی (H43)', max_digits=18, decimal_places=2, default=0)
    interface_cost = models.DecimalField('هزینه رابط (J43)', max_digits=18, decimal_places=2, default=0)
    fixed_widths = models.JSONField('عرض‌های ثابت ورق (cm)', default=list)  # e.g. [80,90,100,110,120,125,140]
    custom_vars = models.JSONField('ثابت‌های سفارشی', default=dict, blank=True)
    def save(self, *args, **kwargs):
        self.singleton_key = 'ONLY'
        if not self.fixed_widths:
            self.fixed_widths = [80, 90, 100, 110, 120, 125, 140]
        super().save(*args, **kwargs)
    def __str__(self):
        return 'اطلاعات پایه قیمت‌گذاری'

class FluteStep(TimeStamped):
    STEP_CHOICES = [('C','C'),('E','E'),('B','B'),('CB','CB'),('CE','CE'),('EB','EB')]
    key = models.CharField('گام فلوت', max_length=2, choices=STEP_CHOICES, unique=True)
    glue_machine = models.CharField('ماشین چسب', max_length=100, blank=True)
    be_flute = models.CharField('B/E فلوت', max_length=100, blank=True)
    middle_layer = models.CharField('لایه میانی', max_length=100, blank=True)
    c_flute = models.CharField('C فلوت', max_length=100, blank=True)
    bottom_layer = models.CharField('زیره', max_length=100, blank=True)
    def __str__(self):
        return self.key

class CalcFormula(TimeStamped):
    """Editable formulas (safe-eval). key names like 'E20', 'K20', 'E28', 'E38', ..."""
    key = models.CharField('کلید', max_length=10, unique=True)
    expression = models.TextField('عبارت محاسباتی (Python, امن)')
    description = models.CharField('توضیح', max_length=200, blank=True)
    def __str__(self):
        return f"{self.key}"

class PriceQuotation(TimeStamped):
    PAYMENT_CHOICES = [('cash','نقد'), ('credit','اعتباری')]
    PRINT_CHOICES = [('yes','دارد'), ('no','ندارد')]
    LAYERS_CHOICES = [(1,'3 لایه'), (2,'5 لایه')]           # A1
    PIECE_CHOICES = [(1,'یک تیکه'), (2,'نیم کارتن'), (3,'چهار تیکه')]  # A2
    DOOR_TYPE_CHOICES = [(1,'درب باز'), (2,'درب بسته'), (3,'درب دوبل')] # A3
    DOOR_COUNT_CHOICES = [(1,'دو درب'), (2,'تک درب')]        # A4

    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, verbose_name='سفارش‌دهنده')
    contact_phone = models.CharField('شماره تماس', max_length=50, blank=True)
    prepared_by = models.CharField('نام تنظیم‌کننده', max_length=100)

    has_print_notes = models.CharField('چاپ و نکات تبدیل', max_length=3, choices=PRINT_CHOICES, default='no')

    dim_customer = models.BooleanField('ابعاد مشتری', default=False)
    dim_customer_sample = models.BooleanField('نمونه مشتری', default=False)
    dim_sample = models.BooleanField('ابعاد نمونه', default=False)

    tech_new_cliche = models.BooleanField('کلیشه جدید', default=False)
    tech_handle_slot = models.BooleanField('جای دسته', default=False)
    tech_punch = models.BooleanField('پانچ', default=False)
    tech_pallet = models.BooleanField('پالت‌کشی', default=False)
    tech_shipping_on_customer = models.BooleanField('هزینه حمل با مشتری', default=False)

    product_code = models.CharField('کد محصول', max_length=64, blank=True)
    carton_type = models.CharField('نوع کارتن', max_length=100, blank=True)
    carton_name = models.CharField('نام کارتن', max_length=150, blank=True)
    description = models.TextField('توضیحات', blank=True)

    I8_qty = models.PositiveIntegerField('تیراژ کارتن (I8)', default=1)

    A1_layers = models.IntegerField('چند لایه (A1)', choices=LAYERS_CHOICES)
    A2_pieces = models.IntegerField('چند تیکه (A2)', choices=PIECE_CHOICES)
    A3_door_type = models.IntegerField('نوع درب (A3)', choices=DOOR_TYPE_CHOICES)
    A4_door_count = models.IntegerField('تعداد درب (A4)', choices=DOOR_COUNT_CHOICES)

    E15_len = models.DecimalField('طول (E15, cm)', max_digits=10, decimal_places=2)
    G15_wid = models.DecimalField('عرض (G15, cm)', max_digits=10, decimal_places=2)
    I15_hgt = models.DecimalField('ارتفاع (I15, cm)', max_digits=10, decimal_places=2)

    E17_lip = models.DecimalField('لب درب (E17, cm)', max_digits=10, decimal_places=2, default=0)  # only if A3==1

    D31_flute = models.ForeignKey(FluteStep, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='گام فلوت (D31)')

    payment_type = models.CharField('بازپرداخت', max_length=6, choices=PAYMENT_CHOICES, default='cash')

    E46_round_adjust = models.DecimalField('جهت رند کردن (E46)', max_digits=12, decimal_places=2, default=0)

    # computed snapshot fields
    A6_sheet_code = models.IntegerField('A6 کد شیت', default=0)
    E20_industrial_len = models.DecimalField('طول صنعتی (E20, cm)', max_digits=12, decimal_places=2, default=0)
    K20_industrial_wid = models.DecimalField('عرض صنعتی (K20, cm)', max_digits=12, decimal_places=2, default=0)
    F24_per_sheet_count = models.PositiveIntegerField('تعداد هر ورق (F24)', default=1)
    chosen_sheet_width = models.DecimalField('عرض ورق انتخابی (cm)', max_digits=10, decimal_places=2, default=0)
    E28_carton_consumption = models.DecimalField('مصرف کارتن (E28)', max_digits=18, decimal_places=4, default=0)
    E38_sheet_area_m2 = models.DecimalField('متراژ ورق (E38, m²)', max_digits=18, decimal_places=4, default=0)
    I38_sheet_count = models.PositiveIntegerField('تعداد ورق (I38)', default=0)
    E41_sheet_working_cost = models.DecimalField('مایه کاری ورق (E41)', max_digits=18, decimal_places=2, default=0)
    E40_overhead_cost = models.DecimalField('مایه کاری سربار (E40)', max_digits=18, decimal_places=2, default=0)
    M40_total_cost = models.DecimalField('مایه کاری کلی (M40)', max_digits=18, decimal_places=2, default=0)
    M41_profit_amount = models.DecimalField('مبلغ سود (M41)', max_digits=18, decimal_places=2, default=0)
    I41_profit_rate = models.DecimalField('نرخ سود ٪ (I41)', max_digits=6, decimal_places=2, default=0)
    E43_shipping = models.DecimalField('کرایه حمل (E43)', max_digits=18, decimal_places=2, default=0)
    H43_pallet = models.DecimalField('هزینه پالت‌بندی (H43)', max_digits=18, decimal_places=2, default=0)
    J43_interface = models.DecimalField('هزینه رابط (J43)', max_digits=18, decimal_places=2, default=0)
    H46_price_before_tax = models.DecimalField('قیمت نهایی بدون مالیات (H46)', max_digits=18, decimal_places=2, default=0)
    J48_tax = models.DecimalField('مالیات (J48)', max_digits=18, decimal_places=2, default=0)
    E48_price_with_tax = models.DecimalField('قیمت نهایی با مالیات (E48)', max_digits=18, decimal_places=2, default=0)

    waste_warning = models.BooleanField('هشدار دورریز ≥ 11؟', default=False)
    note_message = models.CharField('پیغام/یادداشت F24', max_length=300, blank=True)

    def __str__(self):
        return f"برگه قیمت #{self.id} — {self.customer} — {timezone.localdate(self.created_at)}"
