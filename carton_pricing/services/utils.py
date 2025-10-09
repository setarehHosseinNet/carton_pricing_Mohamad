
# carton_pricing/services/utils.py
from decimal import Decimal, InvalidOperation

def as_num(val, default=0.0):
    try:
        if val is None or str(val).strip() == "":
            return float(default)
        return float(str(val).replace(",", ""))
    except Exception:
        return float(default)

def as_num_or_none(val):
    try:
        if val is None or str(val).strip() == "":
            return None
        return float(str(val).replace(",", ""))
    except Exception:
        return None

def q2(value, quant="0.01"):
    try:
        return Decimal(str(value)).quantize(Decimal(str(quant)))
    except (InvalidOperation, Exception):
        try:
            return Decimal("0").quantize(Decimal(str(quant)))
        except Exception:
            return Decimal("0.00")
