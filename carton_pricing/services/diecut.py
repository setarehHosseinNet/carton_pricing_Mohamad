# carton_pricing/services/diecut.py
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any, Literal
import json
import math

Flute = Literal["B","C","E"]
Wall  = Literal["singlewall","doublewall"]

@dataclass
class DiecutParams:
    layers: int           # 3 یا 5
    flute: Flute          # B/C/E
    length_cm: float      # طول داخلی جعبه
    width_cm: float       # عرض داخلی
    height_cm: float      # ارتفاع
    door_code: str        # مثل 1211 / 2211 ...
    pieces: int = 1       # چندتکه (اگر در اکسل داشتی)
    machine: str = "default"

class DiecutCalculator:
    def __init__(self, rules_path: Path):
        self.rules = json.loads(Path(rules_path).read_text(encoding="utf-8"))

    # ——— Helpers ———
    def _allowance_mm(self, flute: Flute, layers: int) -> float:
        wall: Wall = "doublewall" if layers>=5 else "singlewall"
        return float(self.rules["flute_allowance_mm"][flute][wall])

    def _glue_mm(self, door_code: str) -> float:
        door_info = self.rules["door_codes"].get(door_code) or {}
        glue_side = door_info.get("glue_side","inside")
        return float(self.rules["glue_seam_mm"][glue_side])

    def _slot_depth_mm(self) -> float:
        return float(self.rules["slot_depth_mm"]["std"])

    def _machine_limits(self, machine: str):
        m = self.rules["machines"].get(machine) or self.rules["machines"]["default"]
        return (m["min_len_cm"], m["max_len_cm"], m["min_wid_cm"], m["max_wid_cm"])

    # ——— Core formulas (بر اساس عرف FEFCO + الهام از اکسل) ———
    def _blank_size_mm(self, p: DiecutParams, allowance_mm: float, glue_mm: float) -> Dict[str,float]:
        """
        برش گستردهٔ جعبه (طول گسترده و عرض گسترده روی شیت)
        برای کارتن چهاردرب استاندارد:
            طول گسترده (wrap) ≈ 2*عرض داخلی + 2*طول داخلی + glue + 4*allowance
            عرض گسترده (depth) ≈ ارتفاع + عرض داخلی/2 + slot_depth + 2*allowance
        این فرمول‌ها را با شیت خودت منطبق کن.
        """
        L = p.length_cm * 10
        W = p.width_cm  * 10
        H = p.height_cm * 10

        wrap_mm  = 2*W + 2*L + glue_mm + 4*allowance_mm
        depth_mm = H + (W/2) + self._slot_depth_mm() + 2*allowance_mm

        return {"wrap_mm": wrap_mm, "depth_mm": depth_mm}

    def _fit_on_sheet(self, blank_mm: Dict[str,float], machine: str) -> Dict[str, Any]:
        minL, maxL, minW, maxW = self._machine_limits(machine)
        wrap_cm  = blank_mm["wrap_mm"]/10.0
        depth_cm = blank_mm["depth_mm"]/10.0

        fit_note = ""
        ok = True
        if not (minL <= wrap_cm <= maxL):
            ok = False
            fit_note += f"طول گسترده خارج از محدودهٔ ماشین ({wrap_cm:.1f}cm). "
        if not (minW <= depth_cm <= maxW):
            ok = False
            fit_note += f"عرض گسترده خارج از محدودهٔ ماشین ({depth_cm:.1f}cm). "

        # چیدمان روی شیت (ساده: 1up؛ اگر نیاز داری n-up و چرخش را هم اضافه کن)
        n_up = 1
        return {"ok": ok, "note": fit_note.strip(), "wrap_cm": wrap_cm, "depth_cm": depth_cm, "n_up": n_up}

    def _sheet_count(self, qty: int, n_up: int, waste_ratio: float) -> int:
        sheets = math.ceil(qty / max(n_up,1))
        sheets = math.ceil(sheets * (1.0 + waste_ratio))
        return sheets

    def calculate(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        inputs نمونه:
        {
          "layers": 3, "flute": "C", "length_cm": 29, "width_cm": 20, "height_cm": 24,
          "door_code": "1211", "pieces": 1, "qty": 1000, "machine": "default"
        }
        """
        p = DiecutParams(
            layers=int(inputs["layers"]),
            flute=inputs["flute"],
            length_cm=float(inputs["length_cm"]),
            width_cm=float(inputs["width_cm"]),
            height_cm=float(inputs["height_cm"]),
            door_code=inputs["door_code"],
            pieces=int(inputs.get("pieces") or 1),
            machine=inputs.get("machine","default"),
        )
        qty = int(inputs.get("qty") or 0)

        allowance_mm = self._allowance_mm(p.flute, p.layers)
        glue_mm = self._glue_mm(p.door_code)

        blank = self._blank_size_mm(p, allowance_mm, glue_mm)
        fit   = self._fit_on_sheet(blank, p.machine)

        waste = float(self.rules["waste_ratio"])
        sheets = self._sheet_count(qty, fit["n_up"], waste) if qty>0 else 0

        # TODO1: این قسمت‌ها را با فرمول‌های کارخانه خودتان تکمیل کن
        # قیمت مواد، چاپ، دایکات، لمینت، خط تا، منگنه/چسب، بسته‌بندی، حمل...
        material_cost = 0.0
        process_cost  = 0.0
        total_cost    = material_cost + process_cost

        return {
            "ok": fit["ok"],
            "note": fit["note"],
            "blank_len_cm": round(fit["wrap_cm"], 2),
            "blank_wid_cm": round(fit["depth_cm"], 2),
            "n_up": fit["n_up"],
            "sheets": sheets,
            "allowance_mm": allowance_mm,
            "glue_mm": glue_mm,
            "material_cost": material_cost,
            "process_cost": process_cost,
            "total_cost": total_cost
        }
