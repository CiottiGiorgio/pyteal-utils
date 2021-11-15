# Author:  Giorgio Ciotti
# Date:    11/11/2021
# email:   gciotti.dev@gmail.com
from typing import Tuple

from pyteal import Expr, LeafExpr, UnaryExpr, BinaryExpr, TealSimpleBlock
from pyteal import TealOp, Op
from pyteal import TealBlock, TealType
from pyteal import Int, BitwiseXor
from pyteal import compileTeal, Mode, CompileOptions


class Uncover(LeafExpr):
    def __init__(self, n, arg: Expr):
        super().__init__()
        self.n = n
        self.arg = arg

    def type_of(self) -> TealType:
        return TealType.anytype

    def __str__(self) -> str:
        return "(uncover)"

    def __teal__(self, options: CompileOptions) -> Tuple[TealBlock, TealSimpleBlock]:
        op = TealOp(self, Op.uncover, self.n)
        return TealBlock.FromOp(options, op, self.arg)


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
    # TODO: Add overflow detection.
    #  https://en.wikipedia.org/wiki/Two's_complement#Addition
    #  Since we don't have access to the internal carries of the addition we must resort to the last paragraph of that
    #   section.
    #  We have to "add" a bit to both operands (being careful to respect the sign), do the sum in 65bit and then
    #   truncate to 64bit if and only if 65th and 64th bit are the same.
    #  I doubt we can do operation in 65bit without resorting to bytes. What a shame.
    #  As a last resort we can always say: positive + negative can't overflow, positive + positive overflows if
    #   the result is negative, negative + negative overflows if the result is positive.
    def __add__(self, other):
        # We use wide addition because there are instances where the result is greater than 2^64.
        #  (Two's complement. Duh.)
        # Of course when adding any two 64bit uint(s) the result can at most be one bit longer.
        addition_with_overflow = BinaryExpr(Op.addw, TealType.uint64, TealType.uint64, self, other)
        swapped = UnaryExpr(Op.swap, TealType.anytype, TealType.anytype, addition_with_overflow)
        popped = UnaryExpr(Op.pop, TealType.uint64, TealType.uint64, swapped)

        # Overflow detection (doesn't work)
        # dup_sign = UnaryExpr(Op.dup, TealType.anytype, TealType.anytype, addition_with_overflow)
        # result_sign = BinaryExpr(Op.getbit, TealType.anytype, TealType.uint64, dup_sign, Int(63))
        # uncover_overflow = Uncover(2, result_sign)
        # check_overflow = UnaryExpr(Op.eq, TealType.uint64, TealType.uint64, uncover_overflow)
        # assert_overflow = UnaryExpr(Op.assert_, TealType.uint64, TealType.uint64, check_overflow)

        return popped

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
    print(compileTeal(SInt(100) - SInt(101), mode=Mode.Signature, version=5))
