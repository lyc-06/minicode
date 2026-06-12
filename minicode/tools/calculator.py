"""Calculator tool — safe arithmetic evaluation for the agent."""

from __future__ import annotations

import ast
import operator

from . import ToolContext, ToolDefinition, ToolResult

# Safe operators mapping
_SAFE_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _safe_eval(expr: str) -> str:
    """Evaluate a mathematical expression safely without using eval()."""
    try:
        tree = ast.parse(expr.strip(), mode='eval')
    except SyntaxError as e:
        return f"Syntax error: {e}"

    if not _is_safe(tree):
        return "Error: expression contains unsafe operations. Only arithmetic expressions are allowed."

    try:
        result = _eval_node(tree.body)
        return str(result)
    except ZeroDivisionError:
        return "Error: division by zero"
    except OverflowError:
        return "Error: numeric overflow"
    except Exception as e:
        return f"Error: {e}"


def _is_safe(node: ast.AST, top_level: bool = True) -> bool:
    """Check that the AST only contains safe nodes."""
    allowed = (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant,
               ast.Num,  # Python < 3.8
               )
    if isinstance(node, ast.Expression):
        return _is_safe(node.body, False)
    if isinstance(node, ast.BinOp):
        return (isinstance(node.op, tuple(_SAFE_OPS.keys()))
                and _is_safe(node.left, False)
                and _is_safe(node.right, False))
    if isinstance(node, ast.UnaryOp):
        return (isinstance(node.op, tuple(_SAFE_OPS.keys()))
                and _is_safe(node.operand, False))
    if isinstance(node, (ast.Constant, ast.Num)):
        return True
    return False


def _eval_node(node: ast.AST):
    """Recursively evaluate a safe AST node."""
    if isinstance(node, ast.Constant):
        return node.n if hasattr(node, 'n') else node.value
    if isinstance(node, ast.Num):  # Python < 3.8
        return node.n
    if isinstance(node, ast.BinOp):
        op_func = _SAFE_OPS[type(node.op)]
        return op_func(_eval_node(node.left), _eval_node(node.right))
    if isinstance(node, ast.UnaryOp):
        op_func = _SAFE_OPS[type(node.op)]
        return op_func(_eval_node(node.operand))
    raise ValueError(f"Unsupported node: {type(node).__name__}")


def _run(input_data: dict, _context: ToolContext) -> ToolResult:
    expression = input_data.get('expression', '')
    if not expression:
        return ToolResult(ok=False, output="Expression is required")

    result = _safe_eval(expression)
    if result.startswith("Error"):
        return ToolResult(ok=False, output=result)
    return ToolResult(ok=True, output=f"{expression} = {result}")


calculator_tool = ToolDefinition(
    name='calculator',
    description='Evaluate a mathematical expression. Supports +, -, *, /, //, %%, **. Example: "2 + 3 * 4"',
    input_schema={
        'type': 'object',
        'properties': {
            'expression': {
                'type': 'string',
                'description': 'Mathematical expression to evaluate, e.g. "2 + 3 * 4" or "2 ** 10"',
            },
        },
        'required': ['expression'],
    },
    run=_run,
)
