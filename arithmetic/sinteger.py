from decimal import Decimal


# from pyteal import *


from arithmetic.fprational import BytesRational, UintRational


class BytesSInt(BytesRational):
    def __init__(self, n: int):
        super().__init__(Decimal(n), 0)


class UintSInt(UintRational):
    def __init__(self, n: int):
        super().__init__(Decimal(n), 0)
