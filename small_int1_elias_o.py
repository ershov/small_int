#!/usr/bin/env python3

###############################################################################
# Elias Omega integer codec (modified LSB-tail variant)
#
# Canonical Elias Omega encodes n>=1 recursively: code(1)="0"; for n>1,
# code(n) = code(len(bin(n))) + bin(n). We extend domain to v>=0 by mapping
# n = v + 1. Canonical form emits each binary block MSB-first. Here we keep
# the block ordering and the leading 1 bit first (so the 0 terminator remains
# distinguishable), but emit the remaining (length-1) bits of each binary
# block LSB-first to align with an LSB-first bit packing within bytes.
#
# Encoding (variant) for n = v+1:
#   segments = []
#   t = n
#   while t > 1:
#       segments.append(t)
#       t = t.bit_length() - 1
#   Emit segments in reverse order:
#       For s in reversed(segments):
#           emit bit 1 (leading MSB of s)
#           emit (bit_length(s)-1) tail bits of s, LSB-first
#   Emit final terminator 0 bit.
#
# Decoding mirrors canonical omega logic with tail bits read LSB-first:
#   n = 1
#   loop:
#       b = next bit
#       if b == 0: output (n - 1)  (since n=v+1) and restart for next value
#       else: read current (n) tail bits LSB-first forming tail value T
#             n = (1 << n) | T
#   (Repeat until requested count reached.)
#
# Not interoperable with canonical Elias Omega due to tail bit order change.
###############################################################################

from typing import List


def bit_encode_small_unsigned(a: List[int]) -> bytes:
    out = bytearray([0])
    bit_pos = 0

    def emit_bit(b: int):
        nonlocal bit_pos
        if b:
            out[-1] |= (1 << bit_pos)
        bit_pos += 1
        if bit_pos == 8:
            out.append(0)
            bit_pos = 0

    def emit_tail_lsb(value: int, n_bits: int):
        for i in range(n_bits):
            emit_bit((value >> i) & 1)

    for v in a:
        if v < 0:
            raise ValueError("Value must be non-negative")
        n = v + 1
        # Collect segments
        segs = []
        t = n
        while t > 1:
            segs.append(t)
            t = t.bit_length() - 1
        # Emit in reverse order
        for s in reversed(segs):
            bl = s.bit_length()
            emit_bit(1)               # leading 1
            if bl > 1:
                tail = s & ((1 << (bl - 1)) - 1)
                emit_tail_lsb(tail, bl - 1)
        # Terminator
        emit_bit(0)

    if bit_pos == 0 and len(out) > 1:
        out.pop()
    return bytes(out)


def bit_decode_small_unsigned(data: bytes, count: int) -> List[int]:
    if count < 0:
        raise ValueError("count must be non-negative")
    res: List[int] = []
    if count == 0:
        return res
    byte_len = len(data)
    byte_index = 0
    bit_pos = 0

    def read_bit() -> int:
        nonlocal byte_index, bit_pos
        if byte_index >= byte_len:
            raise ValueError("Unexpected end of data while reading bit")
        b = (data[byte_index] >> bit_pos) & 1
        bit_pos += 1
        if bit_pos == 8:
            bit_pos = 0
            byte_index += 1
        return b

    current_n = 1  # Tracks length parameter for next segment
    while len(res) < count:
        b = read_bit()
        if b == 0:  # terminator => output value
            res.append(current_n - 1)
            current_n = 1
            continue
        # Leading 1 of next segment; read current_n tail bits LSB-first
        if current_n > 64:  # practical guard for 64-bit domain
            raise ValueError("Omega code length parameter too large")
        tail = 0
        for i in range(current_n):
            tail |= read_bit() << i
        current_n = (1 << current_n) | tail
    return res

###############################################################################
# Tests

from zigzag import encode_signed_as_unsigned, decode_unsigned_as_signed

if __name__ == "__main__":
    import random, math

    def omega_logical_bits(n: int) -> int:
        # n >=1
        L = 1  # terminator 0
        t = n
        while t > 1:
            L += t.bit_length()
            t = t.bit_length() - 1
        return L

    MAX_V = (1 << 64) - 1
    print(f"\n    Unsigned integers (first 200)\n{'Number':<10} {'Hex':<15} {'Bytes':<15} {'Decoded':<10} {'Bin'}")
    for i in range(200):
        enc = bit_encode_small_unsigned([i])
        dec = bit_decode_small_unsigned(enc, 1)[0]
        print(f"{i:<10} {enc.hex(' '):<15} {' '.join(f'{b:02x}' for b in enc):<15} {dec:<10} {' '.join(f'{b:08b}' for b in enc)}")
        assert dec == i

    print("\nBoundary tests around powers of two (v = 2^k - 1 and +/- neighbors)")
    boundary_vals = []
    for k in range(0, 65):
        base = (1 << k) - 1
        for d in (-1,0,1):
            v = base + d
            if 0 <= v <= MAX_V:
                boundary_vals.append(v)
    boundary_vals = sorted(set(boundary_vals))
    print(f"\n    Powers of two boundaries (v=2^k-1)\n{'v':<22} {'logical_bits':<14} {'len(bytes)':<10} {'Bin'}")
    for v in boundary_vals[:100]:  # limit printed output
        enc = bit_encode_small_unsigned([v])
        dec = bit_decode_small_unsigned(enc, 1)[0]
        lb = omega_logical_bits(v + 1)
        print(f"{v:<22} {lb:<14} {len(enc):<10} {' '.join(f'{b:08b}' for b in enc)}")
        assert dec == v
        assert (len(enc)-1)*8 < lb <= len(enc)*8
    print(f"Boundary sample count: {len(boundary_vals)}")

    print("\nRandom spot checks")
    random.seed(2024)
    for _ in range(2000):
        v = random.randint(0, MAX_V)
        enc = bit_encode_small_unsigned([v])
        dec = bit_decode_small_unsigned(enc, 1)[0]
        assert dec == v

    print("Random bulk array test")
    arr = [random.randint(0, (1 << 32) - 1) for _ in range(400)]
    enc = bit_encode_small_unsigned(arr)
    dec = bit_decode_small_unsigned(enc, len(arr))
    assert dec == arr
    print(f"Encoded {len(arr)} values -> {len(enc)} bytes (avg {len(enc)/len(arr):.2f})")

    print("Signed mapping test (zigzag)")
    for i in range(-300,301):
        enc = bit_encode_small_unsigned([encode_signed_as_unsigned(i)])
        dec = decode_unsigned_as_signed(bit_decode_small_unsigned(enc,1)[0])
        assert dec == i

    print("All tests passed (LSB-tail omega variant).")
