# carton_pricing/tests/test_diecut_calc.py
from pathlib import Path
from carton_pricing.services.diecut import DiecutCalculator

def test_simple_calc():
    calc = DiecutCalculator(Path(__file__).resolve().parents[1]/"config"/"diecut_rules.json")
    out = calc.calculate({
        "layers": 3, "flute": "C", "length_cm": 29, "width_cm": 20, "height_cm": 24,
        "door_code": "1211", "qty": 1000
    })
    assert out["blank_len_cm"] > 0
    assert out["blank_wid_cm"] > 0
    assert out["sheets"] >= 1
