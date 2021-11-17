# Author:  Giorgio Ciotti
# Date:    11/11/2021
# email:   gciotti.dev@gmail.com

from pyteal import Expr, UnaryExpr, BinaryExpr
from pyteal import Op
from pyteal import TealType
from pyteal import Int, BitwiseXor
from pyteal import If, GetBit
from pyteal import Subroutine
from pyteal import compileTeal, Mode


from parametrizedleafexpr import ParametrizedLeafExpr


# DISCLAIMER: There were a couple of issues when using SInt as a class inheriting from LeafExpr.
#  The methods of the class usually return an object of the same class but it was not the case with SInt.
#  Often it was the case that SInt.__add__(self, other) would return an Expr. This is problematic because
#  a user might expect __add__ to return a python object SInt. For instance, SInt(0) + SInt(12) - SInt(50) wouldn't
#  produce the correct code between signed integers. Much better to be more verbose with subroutines but more explicit.
# Other classes get away with this because they map 1:1 to TEAL opcodes. So even if an operation between two Int
#  returns Expr, they can just sum it again as if it's an uint64.
# Maybe in the future we can integrate directly into PyTeal as an additional type TealType.int64 .
# That way we could have Expr have a .type_of() return TealType.int64 and modify the operations on Expr accordingly.


# TODO: Decide what to do with the most negative representable number. It will cause issues for people that are not
#  aware of this implementation of negative numbers. Potentially exploitable vulnerability and unexpected behavior.
#  Just as we end the contract with an error in overflow/underflow situations, it might be better to "ban" this number.
#  https://en.wikipedia.org/wiki/Two's_complement#Most_negative_number
def SInt(value: int) -> Int:
    if not isinstance(value, int):
        raise TypeError(f"Expected value: int\t\tActual type: {type(value)}.")
    if not (-2 ** 63 <= value <= 2 ** 63 - 1):
        raise ValueError("Value outside of 64bit signed integer using two's complement.")

    if value < 0:
        value = abs(value)
        value = ((value ^ (2 ** 64 - 1)) + 1) % 2 ** 64

    return Int(value)


# Overflow detection will not use internal carries because we don't have access to those and will also not
#  use the trick of doing the addition in 65 bits and then truncating (as exampled in the last sentence of
#  the paragraph here: https://en.wikipedia.org/wiki/Two's_complement#Addition ).
# We will instead say: positive + negative can't overflow, positive + positive overflows if the result is negative,
#  negative + negative overflows if the result is positive.
# Logic gate formula for that will be NOT( (sign_a XNOR sign_b) AND (sign_a XOR sign_c) ).
# Or, equivalently, (sign_a XOR sign_b) OR (sign_a XNOR sign_c). This uses less gates.
# This formula will be true when no overflow occurs.
@Subroutine(TealType.uint64)
def SInt_Add(left: Expr, right: Expr) -> Expr:
    # We use wide addition because there are instances where the result is greater than 2^64.
    #  (Two's complement. Duh.)
    # Of course when adding any two 64bit uint(s) the result can at most be one bit longer.

    # FIXME: If someone smarter than me wants to implement this overflow detection using ScratchVar(s), a shorter
    #  sequence of stack manipulation or branching please be my guest.
    # Addition with overflow detection. It's going to look like a mess but don't worry.
    # I'm here to guide you and I will stay with you all along the way. Let's go, you can do this.

    # 1. Push first operand on the stack, push its sign and duplicate it.
    #   Uncover by 2 so that the first operand is on top of the stack.
    _1 = UnaryExpr(Op.dup, TealType.uint64, TealType.uint64, left)
    _2 = BinaryExpr(Op.getbit, TealType.uint64, TealType.uint64, _1, Int(63))
    _3 = UnaryExpr(Op.dup, TealType.uint64, TealType.uint64, _2)
    _4 = ParametrizedLeafExpr(Op.uncover, 2, output_type=TealType.uint64, expr_inputs=[_3])

    # 2. Push second operand on the stack, get its sign. Cover by 3.
    _5 = BinaryExpr(Op.dup, TealType.uint64, TealType.uint64, _4, right)
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


@Subroutine(TealType.uint64)
def SInt_Sub(left: Expr, right: Expr) -> Expr:
    return SInt_Add(left, SInt_twos_complement(right))


# TODO: other appears two times. If it is a complex expression the Expr will be duplicated.
# TODO: I would have loved to just skip to the end if the operand is positive. Unfortunately if only one branch is
#  present is must evaluate to TealType.none. If both are present they must evaluate to the same TealType.
@Subroutine(TealType.uint64)
def SInt_rshift(left: Expr, right: Expr) -> Expr:
    # Push operand, get its sign. Cover by 1. Push the parameter for the shift. Right shift. Cover by 1.
    # Now operand's sign is on top of the stack.
    _1 = UnaryExpr(Op.dup, TealType.uint64, TealType.uint64, left)
    _2 = GetBit(_1, Int(63))
    _3 = ParametrizedLeafExpr(Op.cover, 1, output_type=TealType.uint64, expr_inputs=[_2])
    _4 = BinaryExpr(Op.shr, TealType.uint64, TealType.uint64, _3, right)
    _5 = ParametrizedLeafExpr(Op.cover, 1, output_type=TealType.uint64, expr_inputs=[_4])

    # If the sign is positive, push Int(0). If the sign is negative push an Int that has "right" ones from MSB.
    # Bitwise Or to add the ones to the shifted negative number.
    _6 = If(_5,
            Int(2**64-1).__lshift__(Int(64) - right),
            Int(0))
    _7 = UnaryExpr(Op.bitwise_or, TealType.uint64, TealType.uint64, _6)

    return _7


@Subroutine(TealType.uint64)
def SInt_twos_complement(operand: Expr) -> Expr:
    # We don't use normal addition between signed integers because we don't care about overflow in this operation.
    xorred = BitwiseXor(operand, Int(2**64-1))
    complemented = BinaryExpr(Op.addw, TealType.uint64, TealType.uint64, xorred, Int(1))
    swapped = UnaryExpr(Op.swap, TealType.anytype, TealType.anytype, complemented)
    popped = UnaryExpr(Op.pop, TealType.uint64, TealType.uint64, swapped)

    return popped


if __name__ == "__main__":
    print(compileTeal(
        SInt_Sub(SInt_Add(SInt(0), SInt(12)), SInt(1)),
        mode=Mode.Signature, version=5))
