from typing import Tuple


from pyteal import Expr, LeafExpr
from pyteal import Op
from pyteal import TealType, TealOp, TealBlock, TealSimpleBlock
from pyteal import CompileOptions


class ParametrizedLeafExpr(LeafExpr):
    def __init__(self, op: Op, *op_args: [Expr], output_type: TealType, expr_inputs: [Expr] = None):
        super().__init__()
        self.op = op
        self.output_type = output_type
        self.op_args = op_args
        self.expr_inputs = expr_inputs or list()

    def type_of(self) -> TealType:
        return self.output_type

    def __str__(self) -> str:
        return self.op.__str__()

    def __teal__(self, options: CompileOptions) -> Tuple[TealBlock, TealSimpleBlock]:
        op = TealOp(self, self.op, *self.op_args)
        return TealBlock.FromOp(options, op, *self.expr_inputs)
