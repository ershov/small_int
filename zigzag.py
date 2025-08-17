#!/usr/bin/env python3

###############################################################################
#   Functions for encoding and decoding small unsigned and signed integers to/from unsigned integers.
#   The encoding is as follows:
#   - The absolute value is multiplied by 2 and the sign is encoded in the lowest bit.
#   - If the number is negative, it's incremented by 1 before encoding.
#   It's similar to "zigzag" encoding.

def encode_signed_as_unsigned(n: int) -> int:
    if n < 0:
        return ((-n - 1) << 1) | 1
    return n << 1

def decode_unsigned_as_signed(n: int) -> int:
    if n & 1:
        return -(n >> 1) - 1
    return n >> 1
