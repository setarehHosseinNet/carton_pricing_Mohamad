# carton_pricing/models.py
from __future__ import annotations

from decimal import Decimal
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone



# ------------------------- Base mixin -------------------------
class TimeStamped(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        abstract = True


# ------------------------- Core catalog -------------------------
class Product(TimeStamped):
    name = models.CharField("نام محصول", max_length=200)
    code = models.CharField("کد محصول (یکتا)", max_length=64, unique=True)

    class Meta:
        ordering = ("name",)

    def __str__(self) -> str:
        return f"{self.name} — {self.code}"


class Customer(TimeStamped):
    first_name = models.CharField("نام", max_length=100)
    last_name = models.CharField("نام خانوادگی", max_length=100, blank=True)
    organization = models.CharField("نام مجموعه/شرکت", max_length=200, blank=True)
    economic_no = models.CharField("شماره اقتصادی", max_length=100, blank=True)
    address = models.TextField("آدرس", blank=True)
    favorite_products = models.ManyToManyField(Product, verbose_name="محصولات پرمصرف", blank=True)

    class Meta:
        ordering = ("id",)

    def __str__(self) -> str:
        base = f"{self.first_name} {self.last_name}".strip()
        return f"{base} ({self.organization})" if self.organization else base


class PhoneNumber(TimeStamped):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="phones")
    label = models.CharField("برچسب", max_length=50, blank=True)
    number = models.CharField("شماره تماس", max_length=50)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("customer", "number"), name="uniq_customer_phone"),
        ]
        ordering = ("id",)

    def __str__(self) -> str:
        return f"{self.customer} - {self.number}"


# ------------------------- Orders -------------------------
class Order(TimeStamped):
    STATUS_CHOICES = [
        ("pending", "در انتظار"),
        ("confirmed", "تایید شده"),
        ("in_production", "در حال تولید"),
        ("delivered", "تحویل شده"),
        ("cancelled", "لغو شده"),
    ]

    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="orders", verbose_name="مشتری")
    order_no = models.CharField("شماره سفارش", max_length=50, unique=True)
    registered_at = models.DateField("تاریخ ثبت")
    delivery_date = models.DateField("تاریخ تحویل", null=True, blank=True)
    commitment_date = models.DateField("تاریخ تعهدی", null=True, blank=True)
    status = models.CharField("وضعیت", max_length=20, choices=STATUS_CHOICES, default="pending")
    total_price = models.DecimalField("قیمت سفارش", max_digits=18, decimal_places=2, default=0)

    # اسنپ‌شات آخرین نرخ/فی (اختیاری)
    last_unit_rate = models.DecimalField("نرخ واحد", max_digits=18, decimal_places=2, default=0)
    last_fee = models.DecimalField("فی", max_digits=18, decimal_places=2, default=0)

    class Meta:
        ordering = ("-registered_at", "-id")

    def __str__(self) -> str:
        return f"{self.order_no} — {self.customer}"


class OrderItem(TimeStamped):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField("تعداد", validators=[MinValueValidator(1)])
    unit_price = models.DecimalField("فی", max_digits=18, decimal_places=2, default=0)

    class Meta:
        ordering = ("id",)

    @property
    def line_total(self) -> Decimal:
        q = Decimal(self.quantity or 0)
        p = Decimal(self.unit_price or 0)
        return (q * p).quantize(Decimal("0.01"))


# ------------------------- Pricing settings (Singleton) -------------------------
class BaseSettings(TimeStamped):
    """
    تنظیمات پایهٔ قیمت‌گذاری (Singleton)
      M30: overhead_per_meter
      M31: sheet_price_cash
      M33: sheet_price_credit
      I41: profit_rate_percent
      E43: shipping_cost
      H43: pallet_cost
      J43: interface_cost
      E46: custom_vars["E46"]
    """
    singleton_key = models.CharField(max_length=8, default="ONLY", unique=True, editable=False)

    overhead_per_meter = models.DecimalField("هزینه سربار هر متر (M30)", max_digits=18, decimal_places=2, default=0)
    sheet_price_cash = models.DecimalField("فی ورق نقد (M31)", max_digits=18, decimal_places=2, default=0)
    sheet_price_credit = models.DecimalField("فی ورق مدت (M33)", max_digits=18, decimal_places=2, default=0)
    profit_rate_percent = models.DecimalField("نرخ سود ٪ (I41)", max_digits=6, decimal_places=2, default=10)
    shipping_cost = models.DecimalField("کرایه حمل (E43)", max_digits=18, decimal_places=2, default=0)
    pallet_cost = models.DecimalField("هزینه پالت‌بندی (H43)", max_digits=18, decimal_places=2, default=0)
    interface_cost = models.DecimalField("هزینه رابط (J43)", max_digits=18, decimal_places=2, default=0)

    fixed_widths = models.JSONField("عرض‌های ثابت ورق (cm)", default=list)  # e.g. [80, 90, 100, 110, 120, 125, 140]
    custom_vars = models.JSONField("ثابت‌های سفارشی", default=dict, blank=True)

    class Meta:
        verbose_name = "اطلاعات پایه قیمت‌گذاری"
        verbose_name_plural = "اطلاعات پایه قیمت‌گذاری"
        ordering = ("-updated_at", "-id")

    def save(self, *args, **kwargs):
        self.singleton_key = "ONLY"
        if not self.fixed_widths:
            self.fixed_widths = [80, 90, 100, 110, 120, 125, 140]
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return "اطلاعات پایه قیمت‌گذاری"

    @classmethod
    def latest(cls) -> "BaseSettings | None":
        return cls.objects.order_by("-updated_at", "-id").first()


# ------------------------- Paper & Flute -------------------------
# apps/carton_pricing/models.py
from django.db import models


# models.py
class PaperGroup(TimeStamped):
    name = models.CharField("نام گروه", max_length=120, unique=True)
    class Meta:
        ordering = ("name",)
    def __str__(self): return self.name


class Paper(TimeStamped):
    name_paper   = models.CharField("Name_Paper", max_length=120, unique=True)

    group = models.ForeignKey(
        PaperGroup,
        verbose_name="گروه",
        related_name="papers",
        on_delete=models.PROTECT,   # یا SET_NULL
        null=True, blank=True,
    )

    grammage_gsm = models.PositiveIntegerField("گرماژ (gsm)", null=True, blank=True)
    width_cm     = models.DecimalField("عرض (cm)", max_digits=6, decimal_places=2, null=True, blank=True)
    unit_price   = models.DecimalField("قیمت واحد", max_digits=12, decimal_places=2, null=True, blank=True)
    unit_amount  = models.CharField("مقدار واحد", max_length=50, default="1 m²")

    # 👇 فیلد جدید (اختیاری)
    shipping_cost = models.DecimalField(
        "هزینهٔ حمل",
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="اختیاری؛ مبلغ به همان واحد پولی قیمت واحد."
    )

    class Meta:
        ordering = ("name_paper",)

    def __str__(self) -> str:
        return self.name_paper or f"Paper #{self.pk}"

    @property
    def unit_price_total(self) -> Decimal:
        a = self.unit_price or Decimal("0")
        b = self.shipping_cost or Decimal("0")
        return (a + b).quantize(Decimal("0.01"))

class FluteStep(TimeStamped):
    """فقط گام فلوت (کاملاً مستقل از کاغذ)"""
    STEP_CHOICES = [("C", "C"), ("E", "E"), ("B", "B"), ("CB", "CB"), ("CE", "CE"), ("EB", "EB")]
    key = models.CharField("گام فلوت", max_length=2, choices=STEP_CHOICES, unique=True)

    class Meta:
        ordering = ("id",)

    def __str__(self) -> str:
        return self.key


# ------------------------- Formulas -------------------------
class CalcFormula(TimeStamped):
    """فرمول‌های قابل‌ویرایش. کلیدهایی مثل 'E20', 'K20', 'E28', 'E38', ..."""
    key = models.CharField("کلید", max_length=10, unique=True)
    expression = models.TextField("عبارت محاسباتی (Python, امن)")
    description = models.CharField("توضیح", max_length=200, blank=True)

    class Meta:
        ordering = ("key",)
        verbose_name = "فرمول محاسباتی"
        verbose_name_plural = "فرمول‌های محاسباتی"

    def __str__(self) -> str:
        return self.key


# ------------------------- Price Quotation -------------------------
class PriceQuotation(TimeStamped):
    PAYMENT_CHOICES = [("cash", "نقد"), ("credit", "اعتباری")]
    PRINT_CHOICES = [("yes", "دارد"), ("no", "ندارد")]
    LAYERS_CHOICES = [(1, "3 لایه"), (2, "5 لایه")]                   # A1
    PIECE_CHOICES = [(1, "یک تیکه"), (2, "نیم کارتن"), (3, "چهار تیکه")]  # A2
    DOOR_TYPE_CHOICES = [(1, "باز/نامتوازن "), (2, "درب بسته"), (3, "درب دوبل")] # A3
    DOOR_COUNT_CHOICES = [(1, "دو درب"), (2, "تک درب")]                 # A4

    # اطلاعات پایه فرم
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, verbose_name="سفارش‌دهنده")
    contact_phone = models.CharField("شماره تماس", max_length=50, blank=True)
    prepared_by = models.CharField("نام تنظیم‌کننده", max_length=100)

    has_print_notes = models.CharField("چاپ و نکات تبدیل", max_length=3, choices=PRINT_CHOICES, default="no")

    dim_customer = models.BooleanField("ابعاد مشتری", default=False)
    dim_customer_sample = models.BooleanField("نمونه مشتری", default=False)
    dim_sample = models.BooleanField("ابعاد نمونه", default=False)

    tech_new_cliche = models.BooleanField("کلیشه جدید", default=False)
    tech_handle_slot = models.BooleanField("جای دسته", default=False)
    tech_punch = models.BooleanField("پانچ", default=False)
    tech_pallet = models.BooleanField("پالت‌کشی", default=False)
    tech_shipping_on_customer = models.BooleanField("هزینه حمل با مشتری", default=False)

    product_code = models.CharField("کد محصول", max_length=64, blank=True)
    CARTON_NORMAL = "معمولی"
    CARTON_DIECUT = "دایکات"
    CARTON_TRAY = "کفی"

    CARTON_TYPE_CHOICES = [
        (CARTON_NORMAL, "معمولی"),
        (CARTON_DIECUT, "دایکات"),
        (CARTON_TRAY, "کفی"),
    ]

    carton_type = models.CharField(
        "نوع کارتن",
        max_length=10,
        choices=CARTON_TYPE_CHOICES,
        blank=True,  # اگر می‌خوای انتخاب اجباری باشد، این خط را حذف کن و یک default بگذار:

        # default=CARTON_NORMAL,
    )
    carton_name = models.CharField("نام کارتن", max_length=150, blank=True)
    description = models.TextField("توضیحات", blank=True)

    I8_qty = models.PositiveIntegerField("تیراژ کارتن (I8)", default=1)

    A1_layers = models.IntegerField("چند لایه (A1)", choices=LAYERS_CHOICES)
    A2_pieces = models.IntegerField("چند تیکه (A2)", choices=PIECE_CHOICES)
    A3_door_type = models.IntegerField("نوع درب (A3)", choices=DOOR_TYPE_CHOICES)
    A4_door_count = models.IntegerField("تعداد درب (A4)", choices=DOOR_COUNT_CHOICES)

    E15_len = models.DecimalField("طول (E15, cm)", max_digits=10, decimal_places=2)
    G15_wid = models.DecimalField("عرض (G15, cm)", max_digits=10, decimal_places=2)
    I15_hgt = models.DecimalField("ارتفاع (I15, cm)", max_digits=10, decimal_places=2)

    E17_lip = models.DecimalField("لب درب بالا(E17, cm)", max_digits=10, decimal_places=2, default=0)
    E18_lip = models.DecimalField("لب درب پایین(E18, cm)", max_digits=10, decimal_places=2, default=0)

    # گام فلوت (مستقل)
    D31_flute = models.ForeignKey(
        FluteStep, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="گام فلوت (D31)"
    )

    payment_type = models.CharField("بازپرداخت", max_length=6, choices=PAYMENT_CHOICES, default="cash")
    E46_round_adjust = models.DecimalField("جهت رند کردن (E46)", max_digits=12, decimal_places=2, default=0)

    # انتخاب کاغذها (برای همین برگه – مستقل از گام فلوت)
    pq_glue_machine = models.ForeignKey(
        Paper, on_delete=models.PROTECT, null=True, blank=True,
        related_name="pq_as_glue_machine", verbose_name="ماشین چسب"
    )
    pq_be_flute = models.ForeignKey(
        Paper, on_delete=models.PROTECT, null=True, blank=True,
        related_name="pq_as_be_flute", verbose_name="B/E فلوت"
    )
    pq_middle_layer = models.ForeignKey(
        Paper, on_delete=models.PROTECT, null=True, blank=True,
        related_name="pq_as_middle_layer", verbose_name="لایه میانی"
    )
    pq_c_flute = models.ForeignKey(
        Paper, on_delete=models.PROTECT, null=True, blank=True,
        related_name="pq_as_c_flute", verbose_name="C فلوت"
    )
    pq_bottom_layer = models.ForeignKey(
        Paper, on_delete=models.PROTECT, null=True, blank=True,
        related_name="pq_as_bottom_layer", verbose_name="زیره"
    )

    # اسنپ‌شات خروجی محاسبات
    A6_sheet_code = models.IntegerField("A6 کد شیت", default=0)
    E20_industrial_len = models.DecimalField("طول صنعتی (E20, cm)", max_digits=12, decimal_places=2, default=0)
    K20_industrial_wid = models.DecimalField("عرض صنعتی (K20, cm)", max_digits=12, decimal_places=2, default=0)
    F24_per_sheet_count = models.PositiveIntegerField("تعداد هر ورق (F24)", default=1)
    chosen_sheet_width = models.DecimalField("عرض ورق انتخابی (cm)", max_digits=10, decimal_places=2, default=0)
    E28_carton_consumption = models.DecimalField("مصرف کارتن (E28)", max_digits=18, decimal_places=4, default=0)
    E38_sheet_area_m2 = models.DecimalField("متراژ ورق (E38, m²)", max_digits=18, decimal_places=4, default=0)
    I38_sheet_count = models.PositiveIntegerField("تعداد ورق (I38)", default=0)
    E41_sheet_working_cost = models.DecimalField("مایه کاری ورق (E41)", max_digits=18, decimal_places=2, default=0)
    E40_overhead_cost = models.DecimalField("مایه کاری سربار (E40)", max_digits=18, decimal_places=2, default=0)
    M40_total_cost = models.DecimalField("مایه کاری کلی (M40)", max_digits=18, decimal_places=2, default=0)
    M41_profit_amount = models.DecimalField("مبلغ سود (M41)", max_digits=18, decimal_places=2, default=0)
    I41_profit_rate = models.DecimalField("نرخ سود ٪ (I41)", max_digits=6, decimal_places=2, default=0)
    E43_shipping = models.DecimalField("کرایه حمل (E43)", max_digits=18, decimal_places=2, default=0)
    H43_pallet = models.DecimalField("هزینه پالت‌بندی (H43)", max_digits=18, decimal_places=2, default=0)
    J43_interface = models.DecimalField("هزینه رابط (J43)", max_digits=18, decimal_places=2, default=0)
    H46_price_before_tax = models.DecimalField("قیمت نهایی بدون مالیات (H46)", max_digits=18, decimal_places=2, default=0)
    J48_tax = models.DecimalField("مالیات (J48)", max_digits=18, decimal_places=2, default=0)
    E48_price_with_tax = models.DecimalField("قیمت نهایی با مالیات (E48)", max_digits=18, decimal_places=2, default=0)

    waste_warning = models.BooleanField("هشدار دورریز ≥ 11؟", default=False)
    note_message = models.CharField("پیغام/یادداشت F24", max_length=300, blank=True)
    rahkaran_invoice_no = models.CharField(
        max_length=100, blank=True, null=True, db_index=True,
        verbose_name="شماره فاکتور راهکاران"
    )
    class Meta:
        ordering = ("-created_at", "-id")

    def __str__(self) -> str:
        date = timezone.localdate(self.created_at) if self.created_at else ""
        return f"برگه قیمت #{self.id} — {self.customer} — {date}"


from decimal import Decimal
from django.db import models, transaction
from django.core.validators import MinValueValidator


class ExtraCharge(models.Model):
    """بندهای اضافی که می‌خواهیم روی برگه/فاکتور اعمال شوند."""
    title = models.CharField(
        max_length=120,
        verbose_name="بندهای اضافی به مبلغ",
    )

    amount_cash = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        validators=[MinValueValidator(0)],
        verbose_name="مبلغ برای نقد",
    )
    amount_credit = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        validators=[MinValueValidator(0)],
        verbose_name="مبلغ برای مدت‌دار",
    )

    is_required = models.BooleanField(
        default=False,
        verbose_name="اجبار برای اعمال",
    )

    priority = models.PositiveIntegerField(
        "اولویت محاسبه",
        unique=True,
        null=True, blank=True,            # اگر خالی باشد، خودکار پر می‌شود
        validators=[MinValueValidator(1)],
        db_index=True,
        help_text="عدد کوچکتر یعنی زودتر محاسبه شود (یکتا).",
    )

    show_on_invoice = models.BooleanField(
        default=True,
        verbose_name="نمایش به عنوان یک بند در فاکتور",
    )

    # توجه: به درخواست شما نام فیلد عیناً حفظ شده است (با P بزرگ)
    Percentage = models.BooleanField(
        default=False,
        verbose_name="محاسبه درصد",
        help_text="اگر فعال باشد، مقدار نقد/مدت به‌عنوان درصد از مبلغ پایه در نظر گرفته می‌شود.",
    )

    is_active = models.BooleanField(
        default=True,
        verbose_name="فعال؟",
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="ایجاد")
    updated_at = models.DateTimeField(auto_now=True,  verbose_name="ویرایش")

    class Meta:
        verbose_name = "بند اضافی"
        verbose_name_plural = "بندهای اضافی"
        # ابتدا بر اساس اولویت (صعودی)، سپس فعال بودن، بعد عنوان
        ordering = ("priority", "-is_active", "title")
        constraints = [
            models.CheckConstraint(
                check=models.Q(amount_cash__gte=0),
                name="extracharge_amount_cash_gte_0",
            ),
            models.CheckConstraint(
                check=models.Q(amount_credit__gte=0),
                name="extracharge_amount_credit_gte_0",
            ),
        ]

    def __str__(self) -> str:
        return self.title

    # ---------- اولویت خودکار یکتا ----------
    @classmethod
    def next_priority(cls) -> int:
        """اولویت بعدی را با گام 10 تولید می‌کند (برای درج‌های میان‌راهی جا بماند)."""
        last = (
            cls.objects
            .exclude(priority__isnull=True)
            .order_by("-priority")
            .first()
        )
        return (last.priority if last and last.priority else 0) + 10

    def save(self, *args, **kwargs):
        # اگر کاربر چیزی وارد نکرد، خودکار مقدار یکتا تعیین کن
        if self.priority is None:
            with transaction.atomic():
                self.priority = type(self).next_priority()
        super().save(*args, **kwargs)

    # ---------- محاسبه مبلغ بر اساس نوع تسویه ----------
    def amount_for(self, settlement: str, base_amount: Decimal | float | int | None = None) -> Decimal:
        """
        settlement: 'cash' یا 'credit'
        اگر Percentage روشن باشد، amount_* به‌عنوان درصد از base_amount اعمال می‌شود.
        """
        is_credit = (settlement or "").lower() == "credit"
        raw = self.amount_credit if is_credit else self.amount_cash

        if self.Percentage:
            base = Decimal(str(base_amount or 0))
            rate = Decimal(str(raw or 0))  # درصد
            return (base * rate / Decimal("100")).quantize(Decimal("0.01"))
        else:
            return Decimal(str(raw or 0))




class OverheadItem(models.Model):
    name = models.CharField(
        "نام هزینه",
        max_length=120,
        unique=True,
        help_text="سلفون،تسمه پالت،تسمه کارت،مرکب،منگنه"
    )
    unit_cost = models.DecimalField(
        "هزینهٔ واحد",
        max_digits=12,
        decimal_places=0,
        default=0,
        validators=[MinValueValidator(0)],
        help_text="مبلغ به واحد پولی سیستم؛ نمی‌تواند منفی باشد."
    )
    is_active = models.BooleanField("فعال؟", default=True)

    created_at = models.DateTimeField("ایجاد", auto_now_add=True)
    updated_at = models.DateTimeField("ویرایش", auto_now=True)

    class Meta:
        verbose_name = "آیتم هزینهٔ سربار"
        verbose_name_plural = "موارد هزینهٔ سربار"
        ordering = ("-is_active", "name")

    def __str__(self) -> str:
        return f"{self.name} — {self.unit_cost}"