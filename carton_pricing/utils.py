# carton_pricing/utils.py
# -*- coding: utf-8 -*-
"""
ابزارهای محاسباتی:
- موتور فرمول داینامیک (FormulaEngine) با ارزیابی امن و تشخیص حلقه/نام گمشده
- safe_eval مبتنی بر AST با توابع محدود
- تبدیل عبارات اکسل‌مانند به پایتون (IF/AND/OR/NOT/MIN/MAX/ABS/ROUND/CEIL/CEILING/FLOOR/ROUNDUP/INT)
- نرمال‌سازی اعداد فارسی
- انتخاب بهترین عرض ورق با حداقل دورریز + تولید گزینه‌ها
"""

from __future__ import annotations

import ast
import math
import re
import sys
import json
from collections import defaultdict, deque
from typing import Any, Callable, Iterable, List
from decimal import Decimal, ROUND_HALF_UP

# ─────────────────────────────────────────────────────────────────────────────
# دیباگ ساده روی stderr
def UDBG(*a) -> None:
    print(*a, file=sys.stderr, flush=True)

# ─────────────────────────────────────────────────────────────────────────────
# توابع مجاز برای استفاده داخل فرمول‌ها
_SAFE_FUNCS: dict[str, Callable[..., Any]] = {
    "ceil":  math.ceil,
    "floor": math.floor,
    "round": round,
    "max":   max,
    "min":   min,
    "abs":   abs,
    "int":   int,
}

# نودهای مجاز در AST (برای ارزیابی امن)
_ALLOWED_NODES: tuple[type, ...] = (
    ast.Expression, ast.BinOp, ast.UnaryOp, ast.Num, ast.Constant,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod, ast.Pow, ast.FloorDiv,
    ast.USub, ast.UAdd, ast.Compare, ast.Eq, ast.NotEq, ast.Gt, ast.GtE,
    ast.Lt, ast.LtE, ast.BoolOp, ast.And, ast.Or, ast.Name, ast.Load,
    ast.IfExp, ast.Call
)

def _parse(expr: str) -> ast.AST:
    """پارس امن و بررسی نودهای مجاز."""
    tree = ast.parse(expr, mode="eval")
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise ValueError(f"Disallowed expression node: {type(node).__name__}")
    return tree

def extract_names(expr: str) -> list[str]:
    """استخراج همه نام‌های استفاده‌شده در یک عبارت."""
    tree = ast.parse(expr, mode="eval")
    return sorted({n.id for n in ast.walk(tree) if isinstance(n, ast.Name)})

def safe_eval_expr(expr: str, namespace: dict) -> Any:
    """ارزیابی امن یک عبارت با فضای نام داده‌شده (توابع مجاز + namespace)."""
    tree = _parse(expr)
    code = compile(tree, "<formula>", "eval")
    return eval(code, {"__builtins__": {}}, {**_SAFE_FUNCS, **namespace})

# ─────────────────────────────────────────────────────────────────────────────
# نرمال‌سازی ورودی‌ها (اعداد فارسی → لاتین، حذف '=' اکسل و ...)

# توجه: «٪» را مستقیماً به کاراکتر % نگاشت می‌کنیم (در پایتون عملگر باقیمانده است؛
# اگر کسی واقعاً درصدِ عددی می‌خواهد باید در فرمول خودش تقسیم بر 100 کند).
_FA_TO_EN = str.maketrans("۰۱۲۳۴۵۶۷۸۹٬٫،٪؛", "0123456789,.,%;")

def normalize_text(s: Any) -> str:
    """حذف فاصله‌های اضافی، تبدیل اعداد و جداکننده‌های فارسی، حذف '=' اکسل در ابتدای فرمول."""
    if s is None:
        return ""
    text = str(s).strip().translate(_FA_TO_EN)
    if text.startswith("="):
        text = text[1:].strip()
    return text

def to_float(x: Any, default: float = 0.0) -> float:
    """تبدیل امن به float با پشتیبانی از اعداد فارسی و جداکننده هزارگان."""
    s = normalize_text(x)
    if not s:
        return default
    s = s.replace(" ", "").replace(",", "")  # 1,234 -> 1234
    try:
        return float(s)
    except ValueError:
        return default

# ─────────────────────────────────────────────────────────────────────────────
# safe_eval ساده با بررسی نام‌های مجاز (وقتی namespace را خودتان می‌دهید)

def safe_eval(expr: str, variables: dict) -> Any:
    """
    ارزیابی امن (فقط عملگرها، مقادیر و نام‌ها + توابع _SAFE_FUNCS).
    اگر نام ناشناخته باشد، خطا می‌دهد.
    """
    expr = str(expr or "").strip()
    tree = ast.parse(expr, mode="eval")
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise ValueError(f"Disallowed expression node: {type(node).__name__}")
        if isinstance(node, ast.Name) and node.id not in variables and node.id not in _SAFE_FUNCS:
            raise ValueError(f"Unknown name in expression: {node.id}")
    code = compile(tree, "<formula>", "eval")
    return eval(code, {"__builtins__": {}}, {**_SAFE_FUNCS, **variables})

# ─────────────────────────────────────────────────────────────────────────────
# تبدیل عبارات اکسل‌مانند به پایتون

def _split_args(s: str) -> list[str]:
    """
    جداسازی آرگومان‌ها برای توابع اکسل‌طور (IF/AND/OR/...) با رعایت:
    - پرانتزهای تو در تو
    - کوتیشن‌های داخل رشته‌ها
    - پشتیبانی از هر دو جداکننده: ',' و ';'
    """
    args: list[str] = []
    buf: list[str] = []
    lvl = 0
    in_str = False
    quote = ""

    i = 0
    while i < len(s):
        ch = s[i]

        # مدیریت رشته‌ها
        if ch in ("'", '"'):
            if not in_str:
                in_str = True
                quote = ch
            elif quote == ch:
                in_str = False
                quote = ""
            buf.append(ch)
            i += 1
            continue

        if not in_str:
            if ch == "(":
                lvl += 1
                buf.append(ch); i += 1; continue
            if ch == ")":
                lvl -= 1
                buf.append(ch); i += 1; continue
            # جداکننده آرگومان‌ها در سطح صفر
            if lvl == 0 and (ch == "," or ch == ";"):
                arg = "".join(buf).strip()
                if arg != "":
                    args.append(arg)
                buf = []
                i += 1
                continue

        buf.append(ch)
        i += 1

    tail = "".join(buf).strip()
    if tail != "":
        args.append(tail)
    return args


def _replace_fn(name: str, text: str, conv: Callable[[list[str]], str], flags: int = 0) -> str:
    """
    جایگزینی بازگشتی NAME(…)، فقط برای توابع ساختاری (IF/AND/OR/NOT).
    """
    pat = re.compile(rf"\b{name}\s*\(", flags=flags)
    guard = 0
    while True:
        if guard > 2000:
            UDBG(f"[UTIL] _replace_fn guard hit for {name}")
            break
        m = pat.search(text)
        if not m:
            break
        i = m.end() - 1
        lvl, j = 1, i
        while j + 1 < len(text) and lvl > 0:
            j += 1
            if text[j] == "(":
                lvl += 1
            elif text[j] == ")":
                lvl -= 1
        inner = text[i + 1 : j]
        args = _split_args(inner)
        rep = conv(args)
        orig = text[m.start() : j + 1]
        if rep == orig:  # جلوگیری از لوپ
            break
        text = text[: m.start()] + rep + text[j + 1 :]
        guard += 1
    return text


def excel_to_python(expr: str) -> str:
    """
    تبدیل فرمول اکسل‌مانند به پایتون امن.
    - عملگرها: <> → != ، ^ → ** ، = مقایسه‌ای → ==
    - TRUE/FALSE → True/False
    - توابع ساختاری (IF/AND/OR/NOT) به‌صورت بازنویسی ساختاری
    - سایر توابع با نگاشت ساده به معادل‌های پایتون
    """
    s = normalize_text(expr)

    # TRUE/FALSE
    s = re.sub(r"\bTRUE\b", "True", s, flags=re.I)
    s = re.sub(r"\bFALSE\b", "False", s, flags=re.I)

    # عملگرها
    s = s.replace("<>", "!=").replace("^", "**")
    # '=' مقایسه‌ای → '==' (به‌جز >=, <=, !=, ==)
    s = re.sub(r"(?<![<>!=])=(?!=)", "==", s)

    # ── توابع ساختاری ───────────────────────────────────────────────
    def conv_if(args: list[str]) -> str:
        if len(args) != 3:
            # تحمل خطا
            return (
                f"({args[1]} if ({args[0]}) else {args[2]})"
                if len(args) >= 3 else
                "(" + ",".join(args) + ")"
            )
        c, a, b = args
        return f"({a} if ({c}) else {b})"

    def conv_and(args: list[str]) -> str: return "(" + " and ".join(args) + ")"
    def conv_or(args: list[str])  -> str: return "(" + " or ".join(args) + ")"
    def conv_not(args: list[str]) -> str:
        x = args[0] if args else ""
        return f"(not ({x}))"

    for name, conv in [("IF", conv_if), ("AND", conv_and), ("OR", conv_or), ("NOT", conv_not)]:
        s = _replace_fn(name, s, conv, flags=0)  # عمدی: case-sensitive

    # ── نگاشت سادهٔ باقی توابع ──────────────────────────────────────
    SIMPLE_MAP = {
        r"\bMIN\s*\(": "min(",
        r"\bMAX\s*\(": "max(",
        r"\bABS\s*\(": "abs(",
        r"\bROUND\s*\(": "round(",
        r"\bCEIL(ING)?\s*\(": "ceil(",
        r"\bFLOOR\s*\(": "floor(",
        r"\bROUNDUP\s*\(": "ceil(",
        r"\bINT\s*\(": "int(",
    }
    for pat, repl in SIMPLE_MAP.items():
        s = re.sub(pat, repl, s, flags=re.I)

    UDBG("[UTIL] excel_to_python:", repr(expr), "->", repr(s))
    return s

# ─────────────────────────────────────────────────────────────────────────────
# موتور فرمول داینامیک با تشخیص وابستگی و ترتیب توپولوژیک

class FormulaEngine:
    """
    formulas: dict[str, str]  →  {'E20': 'E15 + ...', 'K20': '...', 'X1':'...'}
    base_vars: dict[str, Any] →  ورودی‌ها/ثابت‌ها/اعداد اولیه
    """
    def __init__(self, formulas: dict[str, str], base_vars: dict[str, Any]):
        self.formulas = dict(formulas or {})
        self.vars     = dict(base_vars or {})
        self.cache: dict[str, Any] = {}

        # گراف وابستگی‌ها
        self.deps: dict[str, list[str]] = {
            k: [n for n in extract_names(expr) if n != k]
            for k, expr in self.formulas.items()
        }
        UDBG("[ENG] init formulas=", list(self.formulas.keys()))
        UDBG("[ENG] base_vars keys=", list(self.vars.keys()))

    def topo_order(self) -> list[str]:
        UDBG("[ENG] topo_order start")
        indeg = {k: 0 for k in self.formulas}
        graph: dict[str, list[str]] = defaultdict(list)
        for k, ns in self.deps.items():
            for n in ns:
                if n in self.formulas:
                    graph[n].append(k)
                    indeg[k] += 1
        q = deque([k for k, d in indeg.items() if d == 0])
        order: list[str] = []
        while q:
            u = q.popleft()
            order.append(u)
            for v in graph[u]:
                indeg[v] -= 1
                if indeg[v] == 0:
                    q.append(v)
        if len(order) != len(self.formulas):
            UDBG("[ENG] topo_order CYCLE indeg>0:", {k: d for k, d in indeg.items() if d > 0})
            cyc = [k for k, d in indeg.items() if d > 0]
            raise ValueError(f"Cycle detected among formulas: {', '.join(cyc)}")
        UDBG("[ENG] topo_order ok:", order)
        return order

    def validate(self) -> dict[str, list[str]]:
        """
        گزارش نام‌های گمشده و حلقه‌ها را برمی‌گرداند (قبل از ارزیابی).
        خروجی: dict[key] = [missing names]
        """
        _ = self.topo_order()  # اگر حلقه باشد، همینجا خطا می‌دهد
        missing: dict[str, list[str]] = {}
        for k, expr in self.formulas.items():
            names = extract_names(expr)
            for n in names:
                if n in self.formulas or n in self.vars or n in _SAFE_FUNCS:
                    continue
                missing.setdefault(k, []).append(n)
        return missing

    def eval(self, key: str) -> float:
        UDBG(f"[ENG] eval({key})")
        if key in self.cache:
            UDBG(f"[ENG]  cache-hit {key} =", self.cache[key])
            return self.cache[key]
        if key in self.vars:
            val = self.vars[key]
            try:
                val = float(val)
            except Exception:
                pass
            self.cache[key] = val
            return val
        if key not in self.formulas:
            raise ValueError(f"Undefined variable or formula: {key}")

        # وابستگی‌ها
        for n in self.deps[key]:
            UDBG(f"[ENG]  dep {key} -> {n}")
            if n in self.formulas and n not in self.cache and n not in self.vars:
                self.eval(n)

        ns = {**self.vars, **self.cache}
        UDBG(f"[ENG]  eval expr[{key}] = {self.formulas[key]}  with ns-keys=", list(ns.keys()))
        val = float(safe_eval_expr(self.formulas[key], ns))
        UDBG(f"[ENG]  result {key} =", val)
        self.cache[key] = val
        return val

    def eval_many(self, keys: list[str]) -> dict[str, float]:
        _ = self.topo_order()  # تأیید عدم حلقه
        return {k: self.eval(k) for k in keys}

# ─────────────────────────────────────────────────────────────────────────────
# انتخاب بهترین عرض ورق با کمترین دورریز

def choose_per_sheet_and_width(required_width_cm: float,
                               fixed_widths: list[float],
                               max_waste_cm: float = 11.0,
                               e20_len_cm: float | None = None):
    """
    ورودی: عرض صنعتی لازم (K20) و لیست عرض‌های ثابت.
    خروجی: (best_count, chosen_width, waste, warning, note)
    - اگر دورریز < max_waste باشد بهترین را برمی‌گرداند.
    - در غیر این‌صورت نزدیک‌ترین را با هشدار برمی‌گرداند.
    """
    UDBG("[UTIL] choose_per_sheet_and_width: required=", required_width_cm,
         "fixed=", fixed_widths, "max_waste=", max_waste_cm)

    best: tuple[float, int, float] | None = None  # (waste, count, W)
    for W in fixed_widths or []:
        W = float(W)
        if required_width_cm <= 0:
            continue
        count = int(W // required_width_cm)
        if count < 1:
            continue
        waste = W - count * required_width_cm
        candidate = (waste, count, W)
        if waste < max_waste_cm:
            if best is None or candidate < best:
                best = candidate

    if best:
        waste, count, W = best
        note = (
            f"طول ورق (E20) = {e20_len_cm:.2f}cm ، عرض ورق = {W}cm ، دورریز ≈ {waste:.1f}cm"
            if e20_len_cm is not None
            else f"عرض ورق = {W}cm ، دورریز ≈ {waste:.1f}cm"
        )
        return count, W, waste, False, note

    # fallback: نزدیک‌ترین (بیشترین چیدمان و کمترین دورریز)
    fallback: tuple[float, int, float] | None = None
    for W in fixed_widths or []:
        W = float(W)
        if required_width_cm <= 0:
            continue
        count = int(W // required_width_cm)
        if count < 1:
            continue
        waste = W - count * required_width_cm
        candidate = (waste, count, W)
        if fallback is None or candidate < fallback:
            fallback = candidate

    if fallback:
        waste, count, W = fallback
        note = "هشدار دور ریز زیاد می باشد"
        return count, W, waste, True, note

    return 0, 0, 0, True, "ابعاد انتخابی در هیچ عرض ثابتی قابل چیدمان نیست"

# ─────────────────────────────────────────────────────────────────────────────
# رزولور/ارزیابی سبک برای POST (اختیاری)

def find_post_value_like(name: str, post) -> float | None:
    """
    تلاش می‌کند مقدار name را از POST پیدا کند.
    اول کلید دقیق، بعد هر کلیدی که با 'name' شروع شود مثل E15_len.
    """
    if name in post:
        return to_float(post.get(name))
    prefix = f"{name}_"
    for k in post.keys():
        if k.startswith(prefix):
            return to_float(post.get(k))
    return None


def evaluate_formulas_dynamic(formulas: dict[str, str], post) -> dict[str, float]:
    cache: dict[str, float] = {}

    def resolve(name: str):
        if name in cache:
            return cache[name]
        val = find_post_value_like(name, post)
        if val is not None:
            cache[name] = val
            return val
        if name in formulas:
            deps = [n for n in extract_names(formulas[name]) if n not in _SAFE_FUNCS]  # 👈 فیلتر توابع
            scope = {dep: resolve(dep) for dep in deps}
            val2 = safe_eval(formulas[name], scope)
            cache[name] = float(val2)
            return val2
        raise ValueError(f"Unknown name in expression: {name}")

    for key in list(formulas.keys()):
        resolve(key)
    return cache

# ─────────────────────────────────────────────────────────────────────────────
# ساخت رزولور با پشتیبانی از اکسل→پایتون (برای سناریوهای پیشرفته‌تر)

def build_resolver(formulas_raw: dict[str, str], seed_vars: dict[str, Any]):
    """
    formulas_raw: {key: excel_like_expr}
    seed_vars: مقادیر اولیه/ثابت‌ها
    خروجی: (resolve, cache, formulas_py)
    """
    # تبدیل همه فرمول‌ها به پایتون
    formulas_py = {k: excel_to_python(v) for k, v in formulas_raw.items()}

    # اعتبارسنجی اولیه سینتکس
    for k, expr in formulas_py.items():
        try:
            ast.parse(str(expr or ""), mode="eval")
        except SyntaxError as e:
            raise ValueError(f"Syntax error in formula '{k}': {expr!r} -> {e}") from e

    cache: dict[str, Any] = dict(seed_vars)

    def _extract(expr: str) -> set[str]:
        """فقط متغیّرها را برگردان؛ توابعِ امن را حذف کن."""
        out: set[str] = set()
        try:
            tree = ast.parse(str(expr or ""), mode="eval")
        except SyntaxError:
            return out
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                if node.id not in _SAFE_FUNCS:   # 👈 مهم: توابع را حذف کن
                    out.add(node.id)
        return out

    def resolve(name: str):
        if name in cache:
            return cache[name]
        if name in formulas_py:
            expr = formulas_py[name]
            deps = _extract(expr)
            scope = {d: resolve(d) for d in deps}  # فقط متغیّرها
            val = safe_eval(expr, scope)           # safe_eval خودش _SAFE_FUNCS را دارد
            cache[name] = val
            return val
        raise ValueError(f"Unknown name in expression: {name}")

    return resolve, cache, formulas_py


# ─────────────────────────────────────────────────────────────────────────────
# جایگذاری نام متغیرها با مقدارشان برای دیباگ

import re as _re_dbg

def render_formula(expr: str, vars_dict: dict) -> str:
    """
    صرفاً برای دیباگ: نام متغیرها را با مقدارشان درون رشتهٔ فرمول جایگزین می‌کند.
    """
    out = expr
    # نام‌های طولانی‌تر اول تا جایگذاری اشتباه نشود (مثلاً E20 قبل از E2)
    for name, val in sorted(vars_dict.items(), key=lambda x: -len(x[0])):
        out = _re_dbg.sub(rf"\b{name}\b", str(val), out)
    return out

# ─────────────────────────────────────────────────────────────────────────────
# تولید گزینه‌ّهای چیدمان بر اساس عرض‌های ثابت

def compute_sheet_options(required_width_cm: float,
                          fixed_widths: list[float],
                          max_waste_cm: float = 11.0,
                          max_options: int = 6):
    """
    از بزرگ‌ترین عرض به کوچک‌تر می‌گردد و گزینه‌هایی که دورریزشان
    بین 0 و کمتر از max_waste_cm است را برمی‌گرداند.
    خروجی: [{'width': ..., 'count': ..., 'waste': ...}, ...]
    """
    if not fixed_widths or required_width_cm <= 0:
        return []

    opts = []
    for W in sorted(fixed_widths, reverse=True):  # 👈 از بزرگ‌ترین شروع
        count = int(W // required_width_cm)
        if count < 1:
            continue
        waste = W - count * required_width_cm
        if 0 <= waste < max_waste_cm:
            opts.append({'width': float(W), 'count': int(count), 'waste': float(waste)})

    # مرتب‌سازی: عرض نزولی، بعد دورریز صعودی
    opts.sort(key=lambda o: (-o['width'], o['waste']))
    return opts[:max_options]

# ─────────────────────────────────────────────────────────────────────────────
# نرمال‌سازی عرض‌های ثابت (fix widths) با پشتیبانی از ارقام فارسی/عربی

_PERSIAN_MAP = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩٬،٫", "01234567890123456789,,.")

def _normalize_fixed_widths(
    value: Any,
    *,
    dedupe: bool = True,
    sort_result: bool = True,
    min_value: float = 1.0,
    precision: int = 0,
) -> List[float]:
    """
    ورودی‌های قابل قبول برای fixed_widths:
      - list/tuple/set از اعداد یا رشته‌ها
      - رشته JSON شبیه "[80, 90, 100]"
      - رشته CSV/space مثل "80,90,100" یا "80 90 100"
      - شامل ارقام فارسی هم باشد اوکی است
    خروجی: لیست اعداد مثبت (unique & sorted).
    """
    if value is None or value == "":
        return []

    # اگر iterable باشد
    if isinstance(value, (list, tuple, set)):
        tokens: Iterable[Any] = value
    else:
        # به رشته تبدیل و نرمال‌سازی
        s = str(value).translate(_PERSIAN_MAP).strip()
        if not s:
            return []
        # JSON array؟
        if s.startswith("[") and s.endswith("]"):
            try:
                parsed = json.loads(s)
                return _normalize_fixed_widths(parsed,
                                               dedupe=dedupe,
                                               sort_result=sort_result,
                                               min_value=min_value,
                                               precision=precision)
            except Exception:
                pass
        # CSV / فاصله / ; / | / /
        tokens = (t for t in re.split(r"[,\s;|/]+", s) if t)

    # تبدیل به عدد + فیلتر
    out: List[float] = []
    for t in tokens:
        try:
            num = float(str(t).translate(_PERSIAN_MAP))
        except Exception:
            continue
        if num >= min_value:
            out.append(round(num, precision) if precision is not None and precision >= 0 else num)

    if dedupe:
        seen = set()
        out = [x for x in out if not (x in seen or seen.add(x))]
    if sort_result:
        out.sort()
    return out

# ─────────────────────────────────────────────────────────────────────────────
# گرد کردن به عدد صحیح (برای خروجی‌های integer)

def q_int(v, default="0") -> Decimal:
    """
    گرد کردن به عدد صحیح (ROUND_HALF_UP) و برگرداندن Decimal('…')
    """
    try:
        return Decimal(str(v)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    except Exception:
        return Decimal(default)

# ─────────────────────────────────────────────────────────────────────────────
# کمکی‌های عددی عمومی که در views/forms استفاده می‌شوند
# (برای حل ImportError: as_num, as_num_or_none, q2)

# مبدّل جامع ارقام فارسی/عربی و جداکننده‌ها به لاتین
_PERSIAN_ARABIC_NUM_MAP = str.maketrans(
    "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩٬،٫",  # ارقام فارسی + عربی + جداکننده‌های رایج
    "01234567890123456789,,."    # ارقام لاتین + کاما (هزارگان) + نقطه (اعشار)
)

def _normalize_num_str(x) -> str:
    """
    رشتهٔ عددی را نرمال می‌کند:
    - ارقام فارسی/عربی → لاتین
    - حذف فاصله و کاما (هزارگان)
    - نگه داشتن نقطه اعشار
    """
    s = str(x).strip()
    s = s.translate(_PERSIAN_ARABIC_NUM_MAP)
    # حذف جداکننده‌های هزارگان و فاصله
    s = s.replace(",", "").replace(" ", "")
    return s

def as_num(value, default: float = 0.0) -> float:
    """
    تبدیل ورودی به float با تحمل فرمت‌های فارسی/عربی.
    اگر نتوانست، default برمی‌گرداند.
    """
    if value is None or value == "":
        return float(default)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, Decimal):
        return float(value)
    try:
        s = _normalize_num_str(value)
        if s in {"", ".", "+", "-", "+.", "-."}:
            return float(default)
        return float(s)
    except Exception:
        try:
            return float(Decimal(_normalize_num_str(value)))
        except Exception:
            return float(default)

def as_num_or_none(value):
    """
    تلاش برای تبدیل به float؛ اگر نشد، None برمی‌گرداند.
    (برای تمایز «نامعتبر» از «۰» مفید است)
    """
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, Decimal):
        return float(value)
    s = _normalize_num_str(value)
    if s in {"", ".", "+", "-", "+.", "-."}:
        return None
    try:
        return float(s)
    except Exception:
        try:
            return float(Decimal(s))
        except Exception:
            return None

def q2(value, step: str = "0.01") -> Decimal:
    """
    مقدار ورودی را به Decimal تبدیل و با گام دلخواه (پیش‌فرض دو رقم اعشار) رُند می‌کند.
    همیشه Decimal برمی‌گرداند (برای ذخیره در DecimalField مناسب است).
    """
    try:
        d = Decimal(str(value if value is not None and value != "" else 0))
    except Exception:
        d = Decimal("0")
    try:
        quant = Decimal(step)
    except Exception:
        quant = Decimal("0.01")
    return d.quantize(quant, rounding=ROUND_HALF_UP)
