"""Small, bounded arithmetic evaluator with no Python evaluation."""
import ast
import operator
import math

from pydantic import BaseModel, ConfigDict, Field


class CalculatorArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expression: str = Field(min_length=1, max_length=120)


OPERATORS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
             ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv,
             ast.Mod: operator.mod, ast.Pow: operator.pow,
             ast.UAdd: operator.pos, ast.USub: operator.neg}


def evaluate(expression: str) -> int | float:
    try:
        root = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ValueError("Invalid arithmetic expression.") from exc
    if sum(1 for _ in ast.walk(root)) > 50:
        raise ValueError("Expression is too complex.")

    def visit(node: ast.AST) -> int | float:
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            result = node.value
        elif isinstance(node, ast.UnaryOp) and type(node.op) in OPERATORS:
            result = OPERATORS[type(node.op)](visit(node.operand))
        elif isinstance(node, ast.BinOp) and type(node.op) in OPERATORS:
            left, right = visit(node.left), visit(node.right)
            if isinstance(node.op, ast.Pow) and (abs(right) > 12 or abs(left) > 1_000_000):
                raise ValueError("Exponent is too large.")
            try:
                result = OPERATORS[type(node.op)](left, right)
            except (ZeroDivisionError, OverflowError) as exc:
                raise ValueError("Arithmetic result is invalid.") from exc
        else:
            raise ValueError("Only basic arithmetic is allowed.")
        if not math.isfinite(result) or abs(result) > 1e15:
            raise ValueError("Result is too large.")
        return result

    return visit(root.body)


class Calculator:
    name = "calculator"
    description = "Evaluate a basic arithmetic expression."
    side_effects = False
    args_model = CalculatorArgs

    def execute(self, arguments: CalculatorArgs) -> int | float:
        return evaluate(arguments.expression)
