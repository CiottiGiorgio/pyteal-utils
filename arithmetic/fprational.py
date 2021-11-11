"""
@Author: Giorgio Ciotti
@Date: 11/11/2021

This file should contain fixed point rational numbers.
Ideally we would offer the possibility of building them on top of uint64 or bytes,
 since the TEAL bitwise opcodes have different costs depending on the type.

If we are really smart people we should be able to write signed integers as a special case of fixed point rationals
 where the bits allocated for the fractional part are 0.
"""


from decimal import Decimal
from abc import abstractmethod


# from pyteal import *


# from arithmetic.exceptions import OutsideValidRange


class FixedPointRational:
    @abstractmethod
    def __add__(self, other):
        pass

    @abstractmethod
    def __sub__(self, other):
        pass

    @abstractmethod
    def __mul__(self, other):
        pass

    @abstractmethod
    def __truediv__(self, other):       # /
        pass

    # TODO: Check if this list is 1:1 to the operations for the native types.


class BytesRational(FixedPointRational):
    def __init__(self, n: Decimal, fractional_bits: int = 10):
        pass


class UintRational(FixedPointRational):
    def __init__(self, n: Decimal, fractional_bits: int = 5):
        pass
