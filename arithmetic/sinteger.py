# Author:  Giorgio Ciotti
# Date:    11/11/2021
# email:   gciotti.dev@gmail.com
from typing import Tuple

from pyteal import Expr, LeafExpr, UnaryExpr, BinaryExpr, TealSimpleBlock
from pyteal import TealOp, Op
from pyteal import TealBlock, TealType
from pyteal import Or, Assert
from pyteal import Int, BitwiseXor
from pyteal import compileTeal, Mode, CompileOptions


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


# TODO: Decide what to do with the most negative representable number. It will cause issues for people that are not
#  aware of this implementation of negative numbers. Potentially exploitable vulnerability and unexpected behavior.
#  Just as we end the contract with an error in overflow/underflow situations, it might be better to "ban" this number.
#  https://en.wikipedia.org/wiki/Two's_complement#Most_negative_number
class SInt(LeafExpr):
    def __init__(self, value: int):
        super().__init__()

        if type(value) is not int:
            raise TypeError(f"Expected value: int\t\tActual type: {type(value)}.")
        if not (-2**63 <= value <= 2**63-1):
            raise ValueError("Value outside of 64bit signed integer using two's complement.")

        if value < 0:
            value = abs(value)
            value = ((value ^ (2**64-1)) + 1) % 2**64

        self.value = value

    def __teal__(self, options: CompileOptions):
        op = TealOp(self, Op.int, self.value)
        return TealBlock.FromOp(options, op)

    def __str__(self):
        return f"(SInt: {self.value})"

    def type_of(self) -> TealType:
        return TealType.uint64

    # DISCLAIMER: We override a bunch of operators for this class because we need to do more than just call
    #  the underlying TEAL operator.
    # Other classes just inherit their operators from Expr so they can pass other Expr. When we do the same
    #  the syntax interpreter might call the police because it doesn't understand that we are not doing any actual
    #  operation. We are just building our syntax tree.

    # Overflow detection will not use internal carries because we don't have access to those and will also not
    #  use the trick of doing the addition in 65 bits and then truncating (as exampled in the last sentence of
    #  the paragraph here: https://en.wikipedia.org/wiki/Two's_complement#Addition ).
    # We will instead say: positive + negative can't overflow, positive + positive overflows if the result is negative,
    #  negative + negative overflows if the result is positive.
    # Logic gate formula for that will be NOT( (sign_a XNOR sign_b) AND (sign_a XOR sign_c) ).
    # Or, equivalently, (sign_a XOR sign_b) OR (sign_a XNOR sign_c). This uses less gates.
    # This formula will be true when no overflow occurs.
    def __add__(self, other):
        # We use wide addition because there are instances where the result is greater than 2^64.
        #  (Two's complement. Duh.)
        # Of course when adding any two 64bit uint(s) the result can at most be one bit longer.

        # FIXME: If someone smarter than me wants to implement this overflow detection using ScratchVar(s), a shorter
        #  sequence of stack manipulation or branching please be my guest.
        # Addition with overflow detection. It's going to look like a mess but don't worry.
        # I'm here to guide you and I will stay with you all along the way. Let's go, you can do this.

        # 1. Push first operand on the stack, push its sign and duplicate it.
        #   Uncover by 2 so that the first operand is on top of the stack.
        _1 = UnaryExpr(Op.dup, TealType.uint64, TealType.uint64, self)
        _2 = BinaryExpr(Op.getbit, TealType.uint64, TealType.uint64, _1, Int(63))
        _3 = UnaryExpr(Op.dup, TealType.uint64, TealType.uint64, _2)
        _4 = ParametrizedLeafExpr(Op.uncover, 2, output_type=TealType.uint64, expr_inputs=[_3])

        # 2. Push second operand on the stack, get its sign. Cover by 3.
        _5 = BinaryExpr(Op.dup, TealType.uint64, TealType.uint64, _4, other)
        _6 = BinaryExpr(Op.getbit, TealType.uint64, TealType.uint64, _5, Int(63))
        _7 = ParametrizedLeafExpr(Op.cover, 3, output_type=TealType.uint64, expr_inputs=[_6])

        # 3. Wide addition on the operand (that should be on top of the stack now). Get result sign, cover it by 5.
        #   Cover lower result by 5. Pop higher result.
        _8 = UnaryExpr(Op.addw, TealType.uint64, TealType.uint64, _7)
        _9 = UnaryExpr(Op.dup, TealType.uint64, TealType.uint64, _8)
        _10 = BinaryExpr(Op.getbit, TealType.uint64, TealType.uint64, _9, Int(63))
        _11 = ParametrizedLeafExpr(Op.cover, 5, output_type=TealType.uint64, expr_inputs=[_10])
        _12 = ParametrizedLeafExpr(Op.cover, 5, output_type=TealType.uint64, expr_inputs=[_11])
        _13 = UnaryExpr(Op.pop, TealType.uint64, TealType.uint64, _12)

        # 4. XOR on the operands sign bit. Cover it by 2.
        _14 = UnaryExpr(Op.bitwise_xor, TealType.uint64, TealType.uint64, _13)
        _15 = ParametrizedLeafExpr(Op.cover, 2, output_type=TealType.uint64, expr_inputs=[_14])

        # 5. XNOR on one operand and result sign bit. OR those mofos, assert.
        _16 = UnaryExpr(Op.bitwise_xor, TealType.uint64, TealType.uint64, _15)
        _17 = UnaryExpr(Op.logic_not, TealType.uint64, TealType.uint64, _16)
        _18 = UnaryExpr(Op.logic_or, TealType.uint64, TealType.uint64, _17)
        _19 = UnaryExpr(Op.assert_, TealType.uint64, TealType.uint64, _18)

        return _19

    def __sub__(self, other):
        return self + other.two_complement()

    # TODO: Right shift must preserve sign. Change the current implementation.
    def __rshift__(self, other):
        super().__rshift__(other)

    def two_complement(self):
        # We don't use normal addition between signed integers because we don't care about overflow in this operation.
        xorred = BitwiseXor(self, Int(2**64-1))
        complemented = BinaryExpr(Op.addw, TealType.uint64, TealType.uint64, xorred, Int(1))
        swapped = UnaryExpr(Op.swap, TealType.anytype, TealType.anytype, complemented)
        popped = UnaryExpr(Op.pop, TealType.uint64, TealType.uint64, swapped)

        return popped


if __name__ == "__main__":
    print(compileTeal(SInt(2**63-1) + SInt(1), mode=Mode.Signature, version=5))
