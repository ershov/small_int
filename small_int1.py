#!/usr/bin/env python3

###############################################################################
# Uniform bit-length integer codec (regularized forms 1..8)
#
# Bit pattern summary (LSB-first within stream; shown here MSB->LSB within each
# prefix for readability). Data bits follow the prefix in LSB-first order.
#
#   Form  Prefix (conceptual)         Total bits   Control bits   Data bits   Capacity (values)   Value range (inclusive)
#    1    0                              2              1             1              2            0 .. 1
#    2    10                             4              2             2              4            2 .. 5
#    3    110                            8              3             5             32            6 .. 37
#    4    11111 000 (control byte)      16              8             8            256           38 .. 293
#    5    1110                          16              4            12           4096          294 .. 4389
#    6    11111 001 (control byte)      24              8            16          65536         4390 .. 69925
#    7    11110                         24              5            19         524288        69926 .. 594213
#    8    11111 NNN (N>=2)             8+8*(N+1)        8         8*(N+1)     256*(N+1)       594214 .. 2^64-1
#
# Notes:
#  * Forms 4,6,8 share the 8-bit control-byte family 11111 NNN (low 5 bits all 1s).
#    - N=0 => Form4 (1 data byte)
#    - N=1 => Form6 (2 data bytes)
#    - N>=2 => Form8 (N+1 data bytes)
#  * All fixed forms now use full power-of-two payload capacities (Form4 regularized
#    to 256 values; previous irregular restriction removed). This makes every shift
#    simply the cumulative sum of prior capacities.
#  * Raw (Form8) values encode v' = n - (_MAX_SMALL + 1) in the minimal number of
#    bytes >=3 (since N>=2). We cap at 8 bytes (64 bits total value range).
###############################################################################
#
# Bit order layout:
#    1:  0 x
#    2:  1 0 x x
#    3:  1 1 0 x  x x x x
#    4:  1 1 1 1  1 N N N    x x x x  x x x x    (NNN=0, 1 byte of data)
#    5:  1 1 1 0  x x x x    x x x x  x x x x
#    6:  1 1 1 1  1 N N N    x x x x  x x x x    x x x x  x x x x    (NNN=1, 2 bytes of data)
#    7:  1 1 1 1  0 x x x    x x x x  x x x x    x x x x  x x x x
#    8:  1 1 1 1  1 N N N    (NNN+1 bytes of data, NNN >= 2)
#
# Bytes are in little-endian order. Layout:
#    1:  . . . .  . . x 0
#    2:  . . . .  x x 0 1
#    3:  x x x x  x 0 1 1
#    4:  N N N 1  1 1 1 1    x x x x  x x x x    (NNN=0, 1 byte of data)
#    5:  x x x x  0 1 1 1    x x x x  x x x x
#    6:  N N N 1  1 1 1 1    x x x x  x x x x    x x x x  x x x x    (NNN=1, 2 bytes of data)
#    7:  x x x 0  1 1 1 1    x x x x  x x x x    x x x x  x x x x
#    8:  N N N 1  1 1 1 1    (NNN+1 bytes of data, NNN >= 2)
#
#   Form   Bits   Control Bits    Data Bits    Encoded        Value range
#    1:      2            1            1           2             0 .. 1
#    2:      4            2            2           4             2 .. 5
#    3:      8            3            5          32             6 .. 37
#    4:     16            8            8         256            38 .. 293
#    5:     16            4           12        4096           294 .. 4389
#    6:     24            8           16       65536          4390 .. 69925
#    7:     24            5           19      524288         69926 .. 594213
#    8:      *            8            *           *        594214 .. 2**64-1
#
###############################################################################

from typing import List

# Bit-lengths (excluding control variations for forms with control byte)
_CAP_BITS = (1, 2, 5, 8, 12, 16, 19)  # data bits for forms 1..7
_CAPACITY = tuple(1 << b for b in _CAP_BITS)  # capacities for forms 1..7
# SHIFT[i] = starting value of form i (i from 0..6)
_SHIFT = [0]
for i in range(1, len(_CAPACITY)):
    _SHIFT.append(sum(_CAPACITY[:i]))
_SHIFT = tuple(_SHIFT)
_TOP = tuple(_SHIFT[i] + _CAPACITY[i] - 1 for i in range(len(_CAPACITY)))
_MAX_SMALL = _TOP[-1]  # Top value encodable by forms 1..7
_BIT_MASK = tuple((1 << i) - 1 for i in range(9))

def bit_encode_small_unsigned(a: List[int]) -> bytes:
    out = bytearray([0])
    bit_pos = 0

    def _emit_bits(value: int, n_bits: int):
        """Emit n_bits (LSB-first) of value into out."""
        nonlocal out, bit_pos

        # Align to byte boundary if needed
        if bit_pos != 8:
            avail = 8 - bit_pos
            if n_bits < avail:
                out[-1] |= (value & _BIT_MASK[n_bits]) << bit_pos
                bit_pos += n_bits
                return
            out[-1] |= (value & _BIT_MASK[avail]) << bit_pos
            value >>= avail
            n_bits -= avail
            bit_pos = 8

        # bit_pos == 8 here: aligned
        # Copy whole bytes
        while n_bits >= 8:
            out.append(value & 0xFF)
            value >>= 8
            n_bits -= 8

        # Remainder bits (<8)
        if n_bits > 0:
            out.append(value & _BIT_MASK[n_bits])
            bit_pos = n_bits

    for n in a:
        if n < 0 or n > 0xFFFFFFFFFFFFFFFF:
            raise ValueError("Value out of supported range (0..2^64-1)")
        if n <= _TOP[0]:  # Form1 (2 bits: prefix 0 + 1 data bit)
            _emit_bits((n - _SHIFT[0]) << 1, 2)
        elif n <= _TOP[1]:  # Form2 (4 bits: 10 + 2 data)
            _emit_bits(((n - _SHIFT[1]) << 2) | 0b01, 4)
        elif n <= _TOP[2]:  # Form3 (8 bits: 110 + 5 data)
            _emit_bits(((n - _SHIFT[2]) << 3) | 0b011, 8)
        elif n <= _TOP[3]:  # Form4 (control 11111 000 + 1 byte payload)
            _emit_bits(0x1F | ((n - _SHIFT[3]) << 8), 16)
        elif n <= _TOP[4]:  # Form5 (16 bits: 1110 + 12 data)
            _emit_bits(((n - _SHIFT[4]) << 4) | 0b0111, 16)
        elif n <= _TOP[5]:  # Form6 (control 11111 001 + 2 bytes)
            _emit_bits(0x3F | ((n - _SHIFT[5]) << 8), 24)
        elif n <= _TOP[6]:  # Form7 (24 bits: 11110 + 19 data)
            _emit_bits(((n - _SHIFT[6]) << 5) | 0b01111, 24)
        else:  # Form8 raw
            adj = n - (_MAX_SMALL + 1)
            nbytes = max(3, (adj.bit_length() + 7) // 8 or 1)
            # if nbytes > 8:
            #     raise ValueError("Value too large (exceeds 64-bit)")
            _emit_bits(0x1F | (((nbytes-1) & 0x7) << 5), 8)
            _emit_bits(adj, 8 * nbytes)
    return bytes(out if bit_pos else out)  # last byte kept even if full

def bit_decode_small_unsigned(data: bytes, count: int) -> List[int]:
    if count < 0:
        raise ValueError("count must be non-negative")
    res: List[int] = []
    byte_len = len(data)
    byte_index = 0
    bit_pos = 0

    def read_bits(n_bits: int) -> int:
        nonlocal byte_index, bit_pos
        if n_bits <= 0:
            return 0

        val = 0
        shift = 0

        # If unaligned, consume bits to reach next byte boundary or finish
        if bit_pos:
            if byte_index >= byte_len:
                raise ValueError("Unexpected end of data while reading bits")
            avail = 8 - bit_pos
            if n_bits < avail:
                val = (data[byte_index] >> bit_pos) & _BIT_MASK[n_bits]
                bit_pos += n_bits
                return val
            # avail <= n_bits
            val = data[byte_index] >> bit_pos
            bit_pos = 0
            byte_index += 1
            shift += avail
            n_bits -= avail

        # Read whole bytes
        while n_bits >= 8:
            if byte_index >= byte_len:
                raise ValueError("Unexpected end of data while reading bits")
            val |= data[byte_index] << shift
            shift += 8
            byte_index += 1
            n_bits -= 8

        # Remainder bits (<8)
        if n_bits:
            if byte_index >= byte_len:
                raise ValueError("Unexpected end of data while reading bits")
            val |= (data[byte_index] & _BIT_MASK[n_bits]) << shift
            bit_pos = n_bits

        return val

    def peek_upto8() -> int:
        # Return next up to 8 bits (LSB-first) without consuming
        if byte_index >= byte_len:
            raise ValueError("Unexpected end of data while reading bits")
        val = data[byte_index] >> bit_pos
        if data[byte_index] >> bit_pos and byte_index + 1 < byte_len:
            val |= (data[byte_index + 1] << (8 - bit_pos)) & 0xFF
        return val

    while len(res) < count:
        if byte_index >= byte_len:
            raise ValueError("Not enough data to decode requested number of integers")
        preview = peek_upto8()
        if (preview & 0x01) == 0:  # Form1
            code = read_bits(2)
            res.append(_SHIFT[0] + (code >> 1))
        elif (preview & 0x03) == 0x01:  # Form2
            code = read_bits(4)
            res.append(_SHIFT[1] + (code >> 2))
        elif (preview & 0x07) == 0x03:  # Form3
            code = read_bits(8)
            res.append(_SHIFT[2] + (code >> 3))
        elif (preview & 0x0F) == 0x07:  # Form5
            code = read_bits(16)
            res.append(_SHIFT[4] + (code >> 4))
        elif (preview & 0x1F) == 0x0F:  # Form7
            code = read_bits(24)
            res.append(_SHIFT[6] + (code >> 5))
        else:  # Control byte forms 4/6/8
            byte_index += 1 # consume control byte
            N = (preview >> 5) & 0x7
            if N == 0:  # Form4
                payload = read_bits(8)
                res.append(_SHIFT[3] + payload)
            elif N == 1:  # Form6
                payload = read_bits(16)
                res.append(_SHIFT[5] + payload)
            else:  # Form8
                payload = read_bits(8 * (N + 1))
                res.append(_MAX_SMALL + 1 + payload)
    return res

###############################################################################
# Tests

from zigzag import encode_signed_as_unsigned, decode_unsigned_as_signed

if __name__ == "__main__":
    print(f"\n    Unsigned integers (first 400)\n{'Number':<10} {'Hex':<40} {'Bin':<64}  {'Decoded'}")
    for i in range(400):
        enc = bit_encode_small_unsigned([i])
        dec = bit_decode_small_unsigned(enc, 1)[0]
        print(f"{i:<10} {enc.hex(' '):<40} {' '.join(f'{b:08b}' for b in enc):<64}  {dec}")
        assert dec == i, (i, dec, enc.hex())

    print("\nBoundary test cases:")
    print(f"{'Value':<22} {'Hex':<40}   {'Bytes':<40} {'Decoded'} {'Len':>4} {'Exp':>4}")
    # Raw (Form8) boundaries for each data byte length (3..8 bytes)
    boundaries = [
        0,1,2,5,6,37,38,293,294,4389,4390,69925,69926,594213,594214,
        _MAX_SMALL,
        _MAX_SMALL + 1,                          # first raw value (3-byte payload start)
        _MAX_SMALL + (1<<24),            # last 3-byte
        _MAX_SMALL + (1<<24) + 1,                # first 4-byte
        _MAX_SMALL + (1<<32),            # last 4-byte
        _MAX_SMALL + (1<<32) + 1,                # first 5-byte
        _MAX_SMALL + (1<<40),            # last 5-byte
        _MAX_SMALL + (1<<40) + 1,                # first 6-byte
        _MAX_SMALL + (1<<48),            # last 6-byte
        _MAX_SMALL + (1<<48) + 1,                # first 7-byte
        _MAX_SMALL + (1<<56),            # last 7-byte
        _MAX_SMALL + (1<<56) + 1,                # first 8-byte
        0xFFFFFFFFFFFFFFFF,                 # last 8-byte (max 64-bit)
    ]
    # Deduplicate & sort
    boundaries = sorted(dict.fromkeys(v for v in boundaries if v <= 0xFFFFFFFFFFFFFFFF))
    def _expected_len_single(n: int) -> int:
        if n <= _TOP[0]: bits = 2
        elif n <= _TOP[1]: bits = 4
        elif n <= _TOP[2]: bits = 8
        elif n <= _TOP[3]: bits = 16
        elif n <= _TOP[4]: bits = 16
        elif n <= _TOP[5]: bits = 24
        elif n <= _TOP[6]: bits = 24
        else:
            adj = n - (_MAX_SMALL + 1)
            nbytes = max(3, (adj.bit_length() + 7)//8 or 1)
            if nbytes > 8:
                raise ValueError("Value too large")
            return 1 + nbytes  # control + payload
        return (bits + 7)//8
    for v in boundaries:
        enc = bit_encode_small_unsigned([v])
        dec = bit_decode_small_unsigned(enc, 1)[0]
        exp_len = _expected_len_single(v)
        print(f"{v:<22} {enc.hex(' '):<40}   {' '.join(f'{b:02x}' for b in enc):<40} {dec} {len(enc):>4} {exp_len:>4}")
        assert dec == v, (v, dec, enc.hex())
        assert len(enc) == exp_len, (v, len(enc), exp_len, enc.hex())

    # Extended boundary tests with ±2 neighbors (including raw length boundaries)
    print("\nExtended boundary tests (each primary boundary with ±2 neighbors):")
    primary = boundaries  # already includes all form boundaries & raw length boundaries
    MAX_U64 = 0xFFFFFFFFFFFFFFFF
    extended_set = set()
    for b in primary:
        for d in (-2,-1,0,1,2):
            v = b + d
            if 0 <= v <= MAX_U64:
                extended_set.add(v)
    extended = sorted(extended_set)
    print(f"Total extended boundary values: {len(extended)}")
    print(f"{'Value':<22} {'Hex':<40}   {'Bytes':<40} {'Decoded'} {'Len':>4} {'Exp':>4}")
    for v in extended:
        enc = bit_encode_small_unsigned([v])
        dec = bit_decode_small_unsigned(enc, 1)[0]
        exp_len = _expected_len_single(v)
        print(f"{v:<22} {enc.hex(' '):<40}   {' '.join(f'{b:02x}' for b in enc):<40} {dec} {len(enc):>4} {exp_len:>4}")
        assert dec == v, (v, dec, enc.hex())
        assert len(enc) == exp_len, (v, len(enc), exp_len, enc.hex())

    print("\nRandom / special spot checks:")
    print(f"{'Value':<22} {'Hex':<40}   {'Bytes':<40} {'Decoded'}")
    spot_values = (12345, 678910, 2**20 - 1, 2**32 - 1, 2**40 - 1, 2**48 - 1, 2**56 - 1, 2**64 - 1)
    for v in spot_values:
        enc = bit_encode_small_unsigned([v])
        dec = bit_decode_small_unsigned(enc, 1)[0]
        print(f"{v:<22} {enc.hex(' '):<40}   {' '.join(f'{b:02x}' for b in enc):<40} {dec}")
        assert dec == v, (v, dec, enc.hex())

    print("\nSequence test values:")
    arr = [0,1,2,3,4,5,6,37,38,39,293,294,4389,4390,69925,69926,594213,594214, 2**56, 2**64 - 1]
    enc = bit_encode_small_unsigned(arr)
    dec = bit_decode_small_unsigned(enc, len(arr))
    print(f"{'Idx':<4} {'Value':<18} {'Decoded'}")
    for i,(v,dv) in enumerate(zip(arr, dec)):
        print(f"{i:<4} {v:<18} {dv}")
    assert dec == arr, (arr, dec, enc.hex())

    print("\nSigned integers test using zigzag mapping")
    print(f"\n    Signed integers\n{'Number':<10} {'Hex':<30} {'Bin':<40} {'Decoded'}")
    for i in range(-150, 151):
        enc = bit_encode_small_unsigned([encode_signed_as_unsigned(i)])
        dec_any = decode_unsigned_as_signed(bit_decode_small_unsigned(enc, 1)[0])
        print(f"{i:<10} {enc.hex(' '):<30} {' '.join(f'{b:08b}' for b in enc):<40} {dec_any}")
        assert dec_any == i, (i, dec_any, enc.hex())

    print("\nPrecomputed constants:")
    print(f"_CAP_BITS: {_CAP_BITS}")
    print(f"_CAPACITY: {_CAPACITY}")
    print(f"_SHIFT: {_SHIFT}")
    print(f"_TOP: {_TOP}")
    print(f"_MAX_SMALL: {_MAX_SMALL}")
