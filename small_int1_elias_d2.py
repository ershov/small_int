#!/usr/bin/env python3

###############################################################################
# Elias Delta integer codec (modified LSB-first tail variant)
#
# We adapt canonical Elias Delta to emit the variable-length binary fields
# LSB-first (after the unary-delimited sections) to align with an LSB-first
# bit packing inside bytes. Mapping v>=0 -> n=v+1 as usual.
#
# Encoding steps (modified):
#   Small values up to INITIAL_MAX are encoded directly in 1 bit + value:
#   n = v + 1
#   N = bit_length(n)
#   L = bit_length(N) - 1
#   Emit L zero bits (unary prefix)
#   Emit 1 delimiter
#   Emit lower L bits of N (without its leading 1) LSB-first
#   Emit lower (N-1) bits of n (without its leading 1) LSB-first
# Decoding mirrors this.
###############################################################################

from typing import List

INITIAL_BITS = 1  # Initial bits directly encoded (for small values). Reasonable: 1, 2, 3.
INITIAL_MAX = (1 << INITIAL_BITS) - 1  # Max value for initial

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

    def emit_bits_lsb(value: int, n_bits: int):
        for i in range(n_bits):
            emit_bit((value >> i) & 1)

    for v in a:
        if v < 0:
            raise ValueError("Value must be non-negative")
        if v <= INITIAL_MAX:
            emit_bits_lsb((v << 1) | 1, (INITIAL_BITS + 1))  # Directly encode small values
            continue
        v = v - INITIAL_MAX + 1  # Adjust for initial direct encoding
        bitlen = v.bit_length()
        bitlenlen = bitlen.bit_length() - 1
        emit_bits_lsb(1 << bitlenlen, bitlenlen + 1)  # unary zeros and delimiter
        emit_bits_lsb(bitlen, bitlenlen)  # tail of length. length can be zero
        emit_bits_lsb(v, bitlen - 1)  # tail of value. length can be zero

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

    def read_bits_lsb(n_bits: int) -> int:
        ret = 0
        for i in range(n_bits):
            ret |= read_bit() << i
        return ret

    while len(res) < count:
        bitlenlen = 0
        while read_bit() == 0:
            bitlenlen += 1
            if bitlenlen > 64:
                raise ValueError("Unary code too long or malformed")
        if bitlenlen == 0:
            n = read_bits_lsb(INITIAL_BITS)  # Directly encoded small value
        else:
            bitlen = ((1 << bitlenlen) | read_bits_lsb(bitlenlen)) - 1
            n = ((1 << bitlen) | read_bits_lsb(bitlen)) + INITIAL_MAX - 1
        res.append(n)
    return res

###############################################################################
# Tests

from zigzag import encode_signed_as_unsigned, decode_unsigned_as_signed

if __name__ == "__main__":
    import random
    MAX_V = (1 << 64) - 1
    print(f"\n    Unsigned integers (first 200)\n{'Number':<10} {'Hex':<15} {'Bytes':<15} {'Decoded':<10} {'Bin'}")
    for i in range(200):
        enc = bit_encode_small_unsigned([i])
        dec = bit_decode_small_unsigned(enc, 1)[0]
        print(f"{i:<10} {enc.hex(' '):<15} {' '.join(f'{b:02x}' for b in enc):<15} {dec:<10} {' '.join(f'{b:08b}' for b in enc)}")
        assert dec == i

    def logical_bits(v: int) -> int:
        if v <= INITIAL_MAX:
            return INITIAL_BITS + 1
        v = v - INITIAL_MAX + 1
        N = v.bit_length()
        L = N.bit_length() - 1
        return max(4, 2 * L + N)

    print(f"\n    Powers of two boundaries (v=2^k-1)\n{'v':<22} {'logical_bits':<14} {'len(bytes)':<10} {'Bin'}")
    for k in range(0, 65):
        v = (1 << k) - 1
        if v > MAX_V:
            break
        def _print_row(v: int):
            enc = bit_encode_small_unsigned([v])
            dec = bit_decode_small_unsigned(enc, 1)[0]
            print(f"{v:<22} {logical_bits(v):<14} {len(enc):<10} {' '.join(f'{b:08b}' for b in enc)}")
            assert dec == v
        if v >= 3:
            _print_row(v - 1)
        _print_row(v)

    print("\nBoundary length transition spot checks")
    values = []
    for k in range(0, 30):
        base = (1 << k) - 1
        for d in (-2,-1,0,1,2):
            v = base + d
            if v >= 0:
                values.append(v)
    values = sorted(set(v for v in values if v <= MAX_V))
    for v in values:
        enc = bit_encode_small_unsigned([v])
        dec = bit_decode_small_unsigned(enc, 1)[0]
        lb = logical_bits(v)
        assert dec == v, (v, dec, enc.hex())
        assert (len(enc)-1)*8 < lb <= len(enc)*8, ((len(enc)-1)*8 , lb , len(enc)*8, v, lb, len(enc), enc.hex())

    print("Random bulk test")
    random.seed(4321)
    arr = [random.randint(0, (1 << 32) - 1) for _ in range(500)]
    enc = bit_encode_small_unsigned(arr)
    dec = bit_decode_small_unsigned(enc, len(arr))
    assert dec == arr
    print(f"Encoded {len(arr)} values -> {len(enc)} bytes (avg {len(enc)/len(arr):.2f})")

    print("Signed mapping test")
    for i in range(-300,301):
        enc = bit_encode_small_unsigned([encode_signed_as_unsigned(i)])
        dec = decode_unsigned_as_signed(bit_decode_small_unsigned(enc,1)[0])
        assert dec == i

    print("All tests passed (LSB-tail delta variant).")
