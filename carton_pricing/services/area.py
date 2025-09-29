# carton_pricing/services/area.py
from __future__ import annotations

from decimal import Decimal
from dataclasses import dataclass

@dataclass
class LayerArea:
    name: str
    width_cm: Decimal
    length_cm: Decimal
    area_m2: Decimal

class CompositionAreaCalculator:
    """
    محاسبه‌ی مساحت هر لایه = (عرض کاغذ بر حسب cm × طول قطعه E20 بر حسب cm) / 10000
    اگر لایه‌ای انتخاب نشده باشد، مساحت آن صفر در نظر گرفته می‌شود.
    """
    def __init__(self, *, glue=None, be=None, mid=None, c=None, bottom=None, e20_cm=None):
        self.glue = glue
        self.be = be
        self.mid = mid
        self.c = c
        self.bottom = bottom
        self.e20_cm = Decimal(str(e20_cm or 0))

    # ---- helpers ----
    @staticmethod
    def _paper_from_val(val):
        # ممکن است مقدار، خود شیء Paper باشد یا صرفاً id آن
        from carton_pricing.models import Paper
        if not val:
            return None
        if isinstance(val, Paper):
            return val
        try:
            return Paper.objects.only("width_cm").get(pk=val)
        except Exception:
            return None

    @staticmethod
    def _area(width_cm, length_cm) -> Decimal:
        try:
            w = Decimal(str(width_cm or 0))
            l = Decimal(str(length_cm or 0))
        except Exception:
            return Decimal("0")
        # m²
        return (w * l / Decimal("10000")).quantize(Decimal("0.0001"))

    def _compute_layer(self, name: str, paper) -> LayerArea:
        if not paper:
            return LayerArea(name=name, width_cm=Decimal("0"), length_cm=self.e20_cm, area_m2=Decimal("0"))
        width = Decimal(str(paper.width_cm or 0))
        area = self._area(width, self.e20_cm)
        return LayerArea(name=name, width_cm=width, length_cm=self.e20_cm, area_m2=area)

    def _compute(self):
        layers = []
        for name, val in [
            ("ماشین چسب", self.glue),
            ("B/E فلوت", self.be),
            ("لایه میانی", self.mid),
            ("C فلوت", self.c),
            ("زیره", self.bottom),
        ]:
            layers.append(self._compute_layer(name, self._paper_from_val(val)))
        total = sum((x.area_m2 for x in layers), Decimal("0")).quantize(Decimal("0.0001"))
        return total, layers

    # ---- public API ----
    @classmethod
    def from_cleaned(cls, cd: dict, *, e20_cm=None) -> "CompositionAreaCalculator":
        return cls(
            glue=cd.get("pq_glue_machine"),
            be=cd.get("pq_be_flute"),
            mid=cd.get("pq_middle_layer"),
            c=cd.get("pq_c_flute"),
            bottom=cd.get("pq_bottom_layer"),
            e20_cm=e20_cm,
        )

    @property
    def total_m2(self) -> Decimal:
        if not hasattr(self, "_total"):
            self._total, self._layers = self._compute()
        return self._total

    @property
    def breakdown(self) -> list[LayerArea]:
        if not hasattr(self, "_layers"):
            self._total, self._layers = self._compute()
        return self._layers
