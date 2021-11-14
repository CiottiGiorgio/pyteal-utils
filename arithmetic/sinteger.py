from pyteal import *


# FIXME: Probably we shouldn't import directly from Int but rather from the parent of Int (seen as SInt is a different
#  "type".
class SInt(Int):
    def __init__(self, value: int):
        if type(value) != int:
            raise TypeError
        if not(-2**63 <= value <= 2**63-1):
            raise ValueError

        if value < 0:
            value = abs(value)
            value = ((value ^ 0xFFFFFFFFFFFFFFFF) + 1) % 2**64

        super().__init__(value)

    def __sub__(self, other) -> Expr:
        return SInt.__add_modulo__(self, SInt.two_complement(other))

    @staticmethod
    def __add_modulo__(left, right) -> Expr:
        # We use addition wide because there are instances where the result is greater than 2^64.
        #  (Two's complement. Duh.)
        # Of course when adding any two 64bit uint(s) the result can at most be one bit longer.
        # The overflow is not on top of the stack so we have to swap and pop.
        addition_with_overflow = BinaryExpr(Op.addw, TealType.uint64, TealType.uint64, left, right)
        addition_swapped = UnaryExpr(Op.swap, TealType.anytype, TealType.anytype, addition_with_overflow)
        addition_without_overflow = UnaryExpr(Op.pop, TealType.uint64, TealType.uint64, addition_swapped)

        return addition_without_overflow

    @staticmethod
    def two_complement(n) -> Expr:
        n_xor = BitwiseXor(n, Int(0xFFFFFFFFFFFFFFFF))

        return SInt.__add_modulo__(n_xor, Int(1))


if __name__ == "__main__":
    print(compileTeal(SInt(100) - SInt(101), mode=Mode.Signature, version=5))
