# legacy_services.py  (قبلاً services.py بود)

import math
from dataclasses import dataclass
from typing import Iterable, Tuple, Any, List, Dict, Optional

# ===== قبلیِ خودت =====
def choose_per_sheet_and_width(required_w: float,
                               fixed_widths: Iterable[float],
                               waste_warn_threshold: float = 0.10
                               ) -> Tuple[int, float, float, bool, str]:
    widths = [float(w) for w in (fixed_widths or []) if w]
    note = ""
    if not widths:
        chosen = float(required_w)
        count = 1
        waste_ratio = 0.0
        warn = False
        note = "عرض استاندارد تعریف نشده؛ از عرض موردنیاز استفاده شد."
        return count, chosen, waste_ratio, warn, note

    widths = sorted(set(widths))
    greater_or_equal = [w for w in widths if w >= required_w]
    chosen = min(greater_or_equal) if greater_or_equal else max(widths)
    if chosen < required_w:
        count = 1
    else:
        count = max(1, int(chosen // required_w))

    used = required_w * count
    waste = max(0.0, chosen - used)
    waste_ratio = (waste / chosen) if chosen else 0.0
    warn = waste_ratio >= waste_warn_threshold

    if not greater_or_equal:
        note = "هیچ عرضی >= نیاز نبود؛ بزرگ‌ترین عرض انتخاب شد."
    elif warn:
        note = f"پرت بالا: {waste_ratio:.1%}"

    return count, float(chosen), float(waste_ratio), bool(warn), note


# ===== استاب‌های مینیمال برای رفع خطای import =====

class CalcFormula:
    """استاب: پیاده‌سازی واقعی را بعداً می‌ریزیم."""
    def __init__(self, context: Optional[Dict[str, Any]] = None):
        self.ctx = context or {}

    def evaluate(self, expr: str, **kwargs) -> Any:
        # فقط پاس می‌دهیم؛ بعداً واقعی می‌شود
        return None

    # اگر در کد شما به اسم run/calc صدا می‌شود:
    def calc(self, expr: str, **kwargs) -> Any:
        return self.evaluate(expr, **kwargs)


class K15Calculator:
    """استاب: محاسبات واقعی K15 را بعداً اضافه می‌کنیم."""
    def compute(self, *args, **kwargs) -> Any:
        return None


@dataclass
class TableRow:
    """استاب: ساختار حداقلی یک ردیف جدول."""
    cells: Dict[str, Any]


class TableBuilder:
    """استاب: جدول ساده برای تجمیع ردیف‌ها."""
    def __init__(self):
        self._rows: List[TableRow] = []

    def add_row(self, row: TableRow) -> None:
        self._rows.append(row)

    def as_list(self) -> List[Dict[str, Any]]:
        return [r.cells for r in self._rows]


class RowCalcs:
    """استاب: توابع کمکی محاسبات سطری."""
    @staticmethod
    def sum(values: Iterable[float]) -> float:
        s = 0.0
        for v in values or []:
            try:
                s += float(v)
            except Exception:
                pass
        return s

    @staticmethod
    def avg(values: Iterable[float]) -> float:
        vals = [float(v) for v in (values or []) if v is not None]
        return (sum(vals) / len(vals)) if vals else 0.0


class E17Calculator:
    """استاب: محاسبهٔ E17 را بعداً واقعی می‌کنیم."""
    def calc(self, *args, **kwargs) -> Any:
        return None
