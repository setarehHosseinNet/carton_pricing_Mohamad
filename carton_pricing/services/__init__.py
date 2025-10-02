# carton_pricing/services/__init__.py
from importlib import import_module

BASE = __package__.rsplit(".", 1)[0]   # 'carton_pricing'

def _grab(candidates: list[str], names: tuple[str, ...]):
    last_err = None
    for modpath in candidates:
        try:
            m = import_module(modpath)
            return tuple(getattr(m, n) for n in names)
        except Exception as e:
            last_err = e
    missing = ", ".join(names)
    tried   = " , ".join(candidates)
    raise ImportError(f"Cannot import {missing}. Tried: {tried}") from last_err

# هر گروه چند مسیرِ محتمل دارد؛ یکی جواب بدهد کافیست
Env, SettingsLoader = _grab(
    [f"{BASE}.services.env", f"{BASE}.env", f"{BASE}.helpers.env"],
    ("Env", "SettingsLoader"),
)

FormulaEngine, CalcFormula = _grab(
    [f"{BASE}.services.formula", f"{BASE}.formula", f"{BASE}.helpers.formula"],
    ("FormulaEngine", "CalcFormula"),
)

K15Calculator, = _grab(
    [f"{BASE}.services.k15", f"{BASE}.k15", f"{BASE}.helpers.k15"],
    ("K15Calculator",),
)

TableBuilder, TableRow, RowCalcs = _grab(
    [f"{BASE}.services.rowbuilder", f"{BASE}.rowbuilder", f"{BASE}.helpers.rowbuilder"],
    ("TableBuilder", "TableRow", "RowCalcs"),
)

E17Calculator, = _grab(
    [f"{BASE}.services.e17", f"{BASE}.e17", f"{BASE}.helpers.e17"],
    ("E17Calculator",),
)

# این یکی در پوشه‌ی services شما هست
from .area import CompositionAreaCalculator

__all__ = [
    "Env", "SettingsLoader",
    "FormulaEngine", "CalcFormula",
    "K15Calculator",
    "TableBuilder", "TableRow", "RowCalcs",
    "E17Calculator",
    "CompositionAreaCalculator",
]
