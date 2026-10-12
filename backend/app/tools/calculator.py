"""Exact arithmetic without eval(): only numbers, operators, and math functions."""

import ast
import math
import operator

MAX_EXPONENT = 10_000
MAX_RESULT_DIGITS = 500

BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
UNARY_OPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}
FUNCTIONS = {
    "sqrt": math.sqrt,
    "abs": abs,
    "round": round,
    "floor": math.floor,
    "ceil": math.ceil,
    "exp": math.exp,
    "log": math.log,  # log(x) natural, log(x, base)
    "ln": math.log,
    "log10": math.log10,
    "log2": math.log2,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "asin": math.asin,
    "acos": math.acos,
    "atan": math.atan,
    "radians": math.radians,
    "degrees": math.degrees,
    "factorial": math.factorial,
    "min": min,
    "max": max,
}
CONSTANTS = {"pi": math.pi, "e": math.e, "tau": math.tau}


class CalculatorError(ValueError):
    pass


def _eval(node: ast.AST) -> float | int:
    if isinstance(node, ast.Expression):
        return _eval(node.body)
    if (
        isinstance(node, ast.Constant)
        and isinstance(node.value, int | float)
        and not isinstance(node.value, bool)
    ):
        return node.value
    if isinstance(node, ast.Name) and node.id in CONSTANTS:
        return CONSTANTS[node.id]
    if isinstance(node, ast.UnaryOp) and type(node.op) in UNARY_OPS:
        return UNARY_OPS[type(node.op)](_eval(node.operand))
    if isinstance(node, ast.BinOp) and type(node.op) in BIN_OPS:
        left, right = _eval(node.left), _eval(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > MAX_EXPONENT:
            raise CalculatorError("Exponent too large")
        result = BIN_OPS[type(node.op)](left, right)
        if isinstance(result, int) and abs(result).bit_length() > MAX_RESULT_DIGITS * 3.33:
            raise CalculatorError("Result too large")
        return result
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in FUNCTIONS
        and not node.keywords
    ):
        args = [_eval(a) for a in node.args]
        if node.func.id == "factorial" and (not args or args[0] > 500):
            raise CalculatorError("factorial() only up to 500")
        return FUNCTIONS[node.func.id](*args)
    raise CalculatorError(
        f"Unsupported expression: {ast.unparse(node) if hasattr(ast, 'unparse') else node}"
    )


def calculate(expression: str) -> str:
    text = expression.strip().replace("^", "**").replace("×", "*").replace("÷", "/")
    if not text or len(text) > 500:
        raise CalculatorError("Expression is empty or too long")
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError as exc:
        raise CalculatorError("That isn't a valid math expression") from exc
    try:
        value = _eval(tree)
    except ZeroDivisionError as exc:
        raise CalculatorError("Division by zero") from exc
    except (OverflowError, ValueError, TypeError) as exc:
        if isinstance(exc, CalculatorError):
            raise
        raise CalculatorError(str(exc) or "Math error") from exc
    if isinstance(value, float):
        # Round away float noise first (log(1000, 10) is 2.9999999999999996).
        value = round(value, 12)
        if value.is_integer() and abs(value) < 1e15:
            return str(int(value))
        return repr(value)
    return str(value)
