#!/usr/bin/env python3

###############################################################################
# Elias Delta integer codec (modified LSB-first tail variant)
#
# We adapt canonical Elias Delta to emit the variable-length binary fields
# LSB-first (after the unary-delimited sections) to align with an LSB-first
# bit packing inside bytes. Mapping v>=0 -> n=v+1 as usual.
#
# Encoding steps (modified):
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
        n = v + 1
        N = n.bit_length()
        L = N.bit_length() - 1
        for _ in range(L):  # unary zeros
            emit_bit(0)
        emit_bit(1)  # delimiter for N
        if L:
            emit_bits_lsb(N & ((1 << L) - 1), L)  # tail of N LSB-first
        if N > 1:
            emit_bits_lsb(n & ((1 << (N - 1)) - 1), N - 1)  # tail of n

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

    while len(res) < count:
        L = 0
        while True:  # unary zeros for L
            bit = read_bit()
            if bit == 0:
                L += 1
                if L > 64:
                    raise ValueError("Delta code too long or malformed")
            else:
                break
        if L == 0:
            N = 1
        else:
            tailN = 0
            for i in range(L):  # LSB-first bits of N's tail
                tailN |= read_bit() << i
            N = (1 << L) | tailN
        if N == 1:
            n = 1
        else:
            tail = 0
            for i in range(N - 1):  # LSB-first bits of n's tail
                tail |= read_bit() << i
            n = (1 << (N - 1)) | tail
        res.append(n - 1)
    return res

###############################################################################
# Tests (similar structure, lengths still 2*L + N logical bits)

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

    print(f"\n    Powers of two boundaries (v=2^k-1)\n{'v':<22} {'logical_bits':<14} {'len(bytes)':<10} {'Bin'}")
    for k in range(0, 65):
        v = (1 << k) - 1
        if v > MAX_V:
            break
        def _print_row(v: int):
            n = v + 1
            N = n.bit_length()
            L = N.bit_length() - 1
            bits = 2 * L + N
            enc = bit_encode_small_unsigned([v])
            dec = bit_decode_small_unsigned(enc, 1)[0]
            print(f"{v:<22} {bits:<14} {len(enc):<10} {' '.join(f'{b:08b}' for b in enc)}")
            assert dec == v
        if v >= 3:
            _print_row(v - 1)
        _print_row(v)

    print("\nBoundary length transition spot checks")
    def logical_bits(v: int) -> int:
        n = v + 1
        N = n.bit_length()
        L = N.bit_length() - 1
        return 2 * L + N
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
        assert dec == v
        assert (len(enc)-1)*8 < lb <= len(enc)*8

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
