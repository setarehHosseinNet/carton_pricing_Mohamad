# carton_pricing/utils.py
# -*- coding: utf-8 -*-
"""
ابزارهای محاسباتی:
- موتور فرمول داینامیک (FormulaEngine) با ارزیابی امن و تشخیص حلقه/نام گمشده
- safe_eval مبتنی بر AST با توابع محدود
- تبدیل عبارات اکسل‌مانند به پایتون (IF/AND/OR/NOT/MIN/MAX/ABS/ROUND/CEIL/CEILING/FLOOR/ROUNDUP/INT)
- نرمال‌سازی اعداد فارسی
- انتخاب بهترین عرض ورق با حداقل دورریز
"""

from __future__ import annotations

import ast
import math
import re
from collections import defaultdict, deque
from typing import Any, Callable
import sys
def UDBG(*a):  # util debug
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

# نکته: «٪» را عمداً مپ نمی‌کنیم چون در پایتون % عملگر باقیمانده است.
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
    args, buf = [], []
    lvl = 0
    in_str = False
    quote = ""

    i = 0
    while i < len(s):
        ch = s[i]

        # مدیریت رشته‌ها "..."
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
            if ch == '(':
                lvl += 1
                buf.append(ch)
                i += 1
                continue
            if ch == ')':
                lvl -= 1
                buf.append(ch)
                i += 1
                continue
            # جداکننده آرگومان‌ها در سطح صفر: کاما یا سمی‌کالن
            if lvl == 0 and (ch == ',' or ch == ';'):
                arg = ''.join(buf).strip()
                if arg != '':
                    args.append(arg)
                buf = []
                i += 1
                continue

        buf.append(ch)
        i += 1

    tail = ''.join(buf).strip()
    if tail != '':
        args.append(tail)
    return args


def _replace_fn(name: str, text: str, conv, flags=0):
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
        inner = text[i+1:j]
        args = _split_args(inner)
        rep = conv(args)
        # اگر خروجی هیچ تغییری نداد، از حلقه خارج شو تا لوپ نشود
        orig = text[m.start():j+1]
        if rep == orig:
            break
        text = text[:m.start()] + rep + text[j+1:]
        guard += 1
    return text



def excel_to_python(expr: str) -> str:
    """
    تبدیل فرمول اکسل‌مانند به پایتون امن.
    فقط IF/AND/OR/NOT با _replace_fn بازنویسی می‌شوند (ساختاری).
    بقیه توابع اکسل صرفاً به معادلِ پایتون lowercase می‌شوند تا لوپ ایجاد نشود.
    """
    s = normalize_text(expr)

    # TRUE/FALSE
    s = re.sub(r"\bTRUE\b", "True", s, flags=re.I)
    s = re.sub(r"\bFALSE\b", "False", s, flags=re.I)

    # عملگرها
    s = s.replace("<>", "!=").replace("^", "**")
    # '=' مقایسه‌ای → '==' (به‌جز >=, <=, !=, ==)
    s = re.sub(r"(?<![<>!=])=(?!=)", "==", s)

    # ── 1) فقط توابع ساختاری با _replace_fn ───────────────────────────────
    def conv_if(args):
        if len(args) != 3:
            return f"({args[1]} if ({args[0]}) else {args[2]})" if len(args) >= 3 else "(" + ",".join(args) + ")"
        c, a, b = args
        return f"({a} if ({c}) else {b})"

    def conv_and(args): return "(" + " and ".join(args) + ")"
    def conv_or(args):  return "(" + " or ".join(args) + ")"
    def conv_not(args):
        x = args[0] if args else ""
        return f"(not ({x}))"

    # ── فقط توابع ساختاری با replace ساختاری و case-sensitive ──
    for name, conv in [("IF", conv_if), ("AND", conv_and), ("OR", conv_or), ("NOT", conv_not)]:
        s = _replace_fn(name, s, conv, flags=0)  # مهم: بدون re.I

    # ── بقیه توابع با نگاشت ساده و re.I ──
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

    # ── 2) مپِ ساده‌ی بقیه توابع (بدون replace بازگشتی) ──────────────────
    #     فقط به lowercase یا معادل مستقیم پایتون تبدیل می‌کنیم تا لوپ نشود.
    SIMPLE_MAP = {
        # اکسل → پایتون
        r"\bMIN\s*\(": "min(",
        r"\bMAX\s*\(": "max(",
        r"\bABS\s*\(": "abs(",
        r"\bROUND\s*\(": "round(",
        r"\bCEIL\s*\(": "ceil(",
        r"\bCEILING\s*\(": "ceil(",
        r"\bFLOOR\s*\(": "floor(",
        r"\bINT\s*\(": "int(",
        # ROUNDUP را به ceil نگاشت می‌کنیم (ساده‌شده)
        r"\bROUNDUP\s*\(": "ceil(",
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
    def __init__(self, formulas: dict, base_vars: dict):
        self.formulas = dict(formulas or {})
        self.vars = dict(base_vars or {})
        self.cache: dict[str, Any] = {}

        # گراف وابستگی‌ها برای تشخیص حلقه و ترتیب محاسبه
        self.deps: dict[str, list[str]] = {k: [n for n in extract_names(expr) if n != k]
                                           for k, expr in self.formulas.items()}
        UDBG("[ENG] init formulas=", list(self.formulas.keys()))
        UDBG("[ENG] base_vars keys=", list(self.vars.keys()))

    def topo_order(self) -> list[str]:
        UDBG("[ENG] topo_order start")
        """محاسبه ترتیب توپولوژیک. در صورت حلقه، خطا می‌دهد."""
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
        _ = self.topo_order()  # حلقه؟ اگر باشد خطا می‌دهد
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
        """ارزیابی یک کلید با حل وابستگی‌ها و کش."""
        if key in self.cache:
            UDBG(f"[ENG]  cache-hit {key} =", self.cache[key])
            return self.cache[key]
        if key in self.vars:
            UDBG(f"[ENG]  undefined key {key}")
            val = self.vars[key]
            try:
                val = float(val)
            except Exception:
                pass
            self.cache[key] = val
            return val
        if key not in self.formulas:
            UDBG(f"[ENG]  undefined key {key}")
            raise ValueError(f"Undefined variable or formula: {key}")
        # ابتدا وابستگی‌هایی که خودشان فرمول هستند را حل کن
        for n in self.deps[key]:
            UDBG(f"[ENG]  dep {key} -> {n}")
            if n in self.formulas and n not in self.cache and n not in self.vars:
                self.eval(n)
        ns = {**self.vars, **self.cache}
        UDBG(f"[ENG]  eval expr[{key}] =", self.formulas[key], " with ns-keys=", list(ns.keys()))
        val = float(safe_eval_expr(self.formulas[key], ns))
        UDBG(f"[ENG]  result {key} =", val)
        self.cache[key] = val
        return val

    def eval_many(self, keys: list[str]) -> dict[str, float]:
        """ارزیابی چند کلید. اگر ترتیب اهمیت داشته باشد، topo_order کمک می‌کند."""
        _ = self.topo_order()  # تأیید عدم حلقه
        out: dict[str, float] = {}
        for k in keys:
            out[k] = self.eval(k)
        return out

# ─────────────────────────────────────────────────────────────────────────────
# انتخاب بهترین عرض ورق با کمترین دورریز

def choose_per_sheet_and_width(required_width_cm: float, fixed_widths: list[int],
                               max_waste_cm: float = 11.0,
                               e20_len_cm: float | None = None):
    """
    ورودی: عرض صنعتی لازم (K20) و لیست عرض‌های ثابت.
    خروجی: (best_count, chosen_width, waste, warning, note)
    - اگر دورریز < max_waste باشد بهترین را برمی‌گرداند.
    - در غیر این‌صورت نزدیک‌ترین را با هشدار برمی‌گرداند.
    """
    UDBG("[UTIL] choose_per_sheet_and_width: required=", required_width_cm, "fixed=", fixed_widths, "max_waste=",
         max_waste_cm)

    best: tuple[float, int, float] | None = None  # (waste, count, W)
    for W in fixed_widths:
        W = float(W)
        if required_width_cm <= 0:
            continue
        count = int(W // required_width_cm)
        if count < 1:
            continue
        waste = W - count * required_width_cm
        candidate = (waste, count, W)
        if waste < max_waste_cm:
            if best is None or candidate < best:  # کمینه‌سازی دورریز، سپس بیشینه‌سازی count
                best = candidate
    if best:
        waste, count, W = best
        note = (f"طول ورق (E20) = {e20_len_cm:.2f}cm ، عرض ورق = {W}cm ، "
                f"دورریز ≈ {waste:.1f}cm") if e20_len_cm is not None else \
            (f"عرض ورق = {W}cm ، دورریز ≈ {waste:.1f}cm")
        return count, W, waste, False, note

    # هیچ گزینه‌ای با دورریز < آستانه پیدا نشد → نزدیک‌ترین را با هشدار انتخاب کن
    fallback: tuple[float, int, float] | None = None
    for W in fixed_widths:
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
        UDBG("[UTIL] best choice:", count, W, waste, "warn=", False)  # یا True در fallback

        return count, W, waste, True, note

    # هیچ چیز جا نمی‌شود
    UDBG("[UTIL] best choice:", count, W, waste, "warn=", False)  # یا True در fallback

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
    """
    ارزیابی سریع فرمول‌ها بر اساس request.POST (برای کاربردهای سبک).
    formulas: {'C16_Calc': '...', 'E20': '...'}
    خروجی: دیکشنری cache از مقادیر.
    """
    cache: dict[str, float] = {}

    def resolve(name: str):
        if name in cache:
            return cache[name]
        val = find_post_value_like(name, post)
        if val is not None:
            cache[name] = val
            return val
        if name in formulas:
            deps = extract_names(formulas[name])
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
    خروجی: (resolve, cache)
    """
    # تبدیل همه فرمول‌ها به پایتون
    formulas = {k: excel_to_python(v) for k, v in formulas_raw.items()}

    # اعتبارسنجی اولیه سینتکس تا خطا واضح باشد
    for k, expr in formulas.items():
        try:
            ast.parse(str(expr or ""), mode="eval")
        except SyntaxError as e:
            raise ValueError(f"Syntax error in formula '{k}': {expr!r} -> {e}") from e

    cache: dict[str, Any] = dict(seed_vars)

    def _extract(expr: str) -> set[str]:
        out: set[str] = set()
        try:
            tree = ast.parse(str(expr or ""), mode="eval")
        except SyntaxError:
            return out
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                out.add(node.id)
        return out

    def resolve(name: str):
        if name in cache:
            return cache[name]
        if name in formulas:
            expr = formulas[name]
            deps = _extract(expr)
            scope = {d: resolve(d) for d in deps}
            val = safe_eval(expr, scope)
            cache[name] = val
            return val
        raise ValueError(f"Unknown name in expression: {name}")

    return resolve, cache, formulas
# جایگذاری نام متغیرها با مقدارشان برای دیباگ
import re as _re_dbg

def render_formula(expr: str, vars_dict: dict) -> str:
    out = expr
    # نام‌های طولانی‌تر اول تا جایگذاری اشتباه نشود (مثلاً E20 قبل از E2)
    for name, val in sorted(vars_dict.items(), key=lambda x: -len(x[0])):
        out = _re_dbg.sub(rf"\b{name}\b", str(val), out)
    return out

# utils.py
def compute_sheet_options(required_width_cm: float,
                          fixed_widths: list[float],
                          max_waste_cm: float = 11.0,
                          max_options: int = 6):
    """
    از بزرگ‌ترین عرض به کوچک‌تر می‌گردد و گزینه‌هایی که دورریزشان 0 تا کمتر از max_waste_cm باشد را
    برمی‌گرداند. خروجی: لیست دیکشنری‌ها {'width', 'count', 'waste'} مرتب‌شده به ترتیب
    عرض نزولی و سپس دورریز صعودی.
    """
    if not fixed_widths or required_width_cm <= 0:
        return []

    options = []
    for W in sorted(fixed_widths, reverse=True):  # از بزرگ‌ترین شروع کن
        count = int(W // required_width_cm)
        if count < 1:
            continue
        waste = W - count * required_width_cm
        if 0 <= waste < max_waste_cm:
            options.append({'width': float(W), 'count': int(count), 'waste': float(waste)})

    options.sort(key=lambda o: (-o['width'], o['waste']))
    return options[:max_options]
