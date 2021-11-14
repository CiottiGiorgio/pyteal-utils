from pyteal import LeafExpr, UnaryExpr, BinaryExpr
from pyteal import TealOp, Op
from pyteal import TealBlock, TealType
from pyteal import Int, BitwiseXor
from pyteal import compileTeal, Mode, CompileOptions


class SInt(LeafExpr):
    def __init__(self, value: int):
        super().__init__()

        if type(value) is not int:
            raise TypeError(f"Expected value: int\t\tActual type: {type(value)}.")
        if not (-2**63 <= value <= 2**63-1):
            raise ValueError("Value outside of 64bit signed integer using two's complement.")

        if value < 0:
            value = abs(value)
            value = ((value ^ 0xFFFFFFFFFFFFFFFF) + 1) % 2**64

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
    def __add__(self, other):
        # We use addition wide because there are instances where the result is greater than 2^64.
        #  (Two's complement. Duh.)
        # Of course when adding any two 64bit uint(s) the result can at most be one bit longer.
        # The overflow is not on top of the stack so we have to swap and pop.
        addition_with_overflow = BinaryExpr(Op.addw, TealType.uint64, TealType.uint64, self, other)
        addition_swapped = UnaryExpr(Op.swap, TealType.anytype, TealType.anytype, addition_with_overflow)
        addition_without_overflow = UnaryExpr(Op.pop, TealType.uint64, TealType.uint64, addition_swapped)

        return addition_without_overflow

    def __sub__(self, other):
        return self + other.two_complement()

    def two_complement(self):
        n_xor = BitwiseXor(self, Int(2**64-1))

        # Looks cursed but it's fine. Look at the disclaimer.
        return SInt.__add__(n_xor, SInt(1))


if __name__ == "__main__":
    print(compileTeal(SInt(100) - SInt(-1), mode=Mode.Signature, version=5))
