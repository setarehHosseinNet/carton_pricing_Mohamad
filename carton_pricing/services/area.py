# carton_pricing/services/area.py
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, Dict, Iterable, Tuple, List

from carton_pricing.models import Paper

Q4 = Decimal("0.0001")  # برای رُند 4 رقم اعشار

LAYER_FIELDS: Tuple[str, ...] = (
    "pq_glue_machine",   # ماشین چسب
    "pq_be_flute",       # B/E فلوت
    "pq_middle_layer",   # لایه میانی
    "pq_c_flute",        # C فلوت
    "pq_bottom_layer",   # زیره
)

@dataclass(frozen=True)
class LayerArea:
    field: str
    paper_id: Optional[int]
    name: str
    width_cm: Decimal
    e20_cm: Decimal
    area_m2: Decimal  # رند شده به 4 رقم

class CompositionAreaCalculator:
    """
    محاسبه‌ی مساحت کل ترکیب کاغذ برای طول صنعتی E20 (بر حسب سانتی‌متر).
    - لایه‌های انتخاب‌نشده = 0
    - خروجی: جمع کل + جزئیات هر لایه
    """

    def __init__(self, e20_cm: object, layers: Dict[str, Optional[Paper]]):
        self.e20_cm = self._to_decimal(e20_cm)
        self.layers = {k: (v if isinstance(v, Paper) else None) for k, v in (layers or {}).items()}
        # تضمین اینکه همه‌ی فیلدهای شناخته‌شده حاضر باشند
        for f in LAYER_FIELDS:
            self.layers.setdefault(f, None)
        self._breakdown: List[LayerArea] = []
        self._total_m2: Optional[Decimal] = None

    # ---------- API های سازنده ----------
    @classmethod
    def from_cleaned(cls, cleaned_data: dict, e20_cm: object) -> "CompositionAreaCalculator":
        """مستقیماً از cleaned_data فرم مدل (که Paper instance برمی‌گرداند) بساز."""
        return cls(
            e20_cm=e20_cm,
            layers={f: cleaned_data.get(f) for f in LAYER_FIELDS}
        )

    # ---------- Public ----------
    @property
    def breakdown(self) -> List[LayerArea]:
        if self._total_m2 is None:
            self._compute()
        return list(self._breakdown)

    @property
    def total_m2(self) -> Decimal:
        if self._total_m2 is None:
            self._compute()
        return self._total_m2

    # ---------- Internal ----------
    def _compute(self) -> None:
        self._breakdown = []
        total = Decimal("0")
        L = self.e20_cm

        for field in LAYER_FIELDS:
            paper = self.layers.get(field)
            if paper is None:
                la = LayerArea(
                    field=field,
                    paper_id=None,
                    name="—",
                    width_cm=Decimal("0"),
                    e20_cm=L,
                    area_m2=Decimal("0").quantize(Q4, rounding=ROUND_HALF_UP),
                )
            else:
                area = paper.area_for_length_m2(L)
                la = LayerArea(
                    field=field,
                    paper_id=paper.pk,
                    name=str(paper),
                    width_cm=Decimal(str(paper.width_cm or 0)),
                    e20_cm=L,
                    area_m2=area.quantize(Q4, rounding=ROUND_HALF_UP),
                )
                total += la.area_m2

            self._breakdown.append(la)

        self._total_m2 = total.quantize(Q4, rounding=ROUND_HALF_UP)

    @staticmethod
    def _to_decimal(v: object) -> Decimal:
        try:
            return Decimal(str(v or 0))
        except Exception:
            return Decimal("0")
