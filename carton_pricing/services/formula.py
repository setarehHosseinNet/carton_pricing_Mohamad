# carton_pricing/services/formula.py
from __future__ import annotations
import math
from typing import Any, Mapping

class FormulaEngine:
    """
    نسخهٔ مینیمال. بعداً بر اساس نیاز واقعی پروژه گسترش می‌دهیم.
    """

    def __init__(self, env: Any | None = None):
        self.env = env or {}

    def evaluate(self, expr: str, context: Mapping[str, Any] | None = None) -> Any:
        """
        ارزیابی سادهٔ عبارت‌های پایتونیِ امن با یک محیط محدود.
        مثال‌ها:
            engine.evaluate("ceil(I8 / F24)", {"I8": 10, "F24": 3})
            engine.evaluate("A + B * 2", {"A": 5, "B": 4})
        """
        context = dict(context or {})
        # توابع مجاز
        safe_builtins = {
            "abs": abs,
            "min": min,
            "max": max,
            "round": round,
        }
        safe_funcs = {
            "ceil": math.ceil,
            "floor": math.floor,
            "sqrt": math.sqrt,
        }
        # محیط اجرا (بدون builtins خطرناک)
        env = {}
        env.update(safe_builtins)
        env.update(safe_funcs)
        env.update(context)

        # ارزیابی امن با حذف builtins
        return eval(expr, {"__builtins__": {}}, env)


from django import forms

class RahkaranInvoiceForm(forms.Form):
    invoice_no = forms.CharField(
        label="شماره فاکتور راهکاران",
        max_length=100,
        widget=forms.TextInput(attrs={"class": "form-control", "dir": "ltr", "placeholder": "مثلاً FR-1404-00123"})
    )
