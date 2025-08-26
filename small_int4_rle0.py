#!/usr/bin/env python3

###############################################################################
#    Nibble-oriented variable-length integer codec (small_int2).
#
#    Format overview (LSB-first bit order within the stream):
#      Small forms (k = 0..5) use a unary-style prefix of (k zeros followed by a 1)
#      immediately followed by VALUE_BITS[k] payload bits of the adjusted value
#      (v' = n - SHIFT[k]), all packed LSB-first. The total (prefix + payload)
#      bit length for each k is chosen so it is an exact multiple of 4, so each
#      encoded small value occupies an integral number of nibbles. We then group
#      nibbles little-nibble-first into bytes (low nibble first, then high nibble).
#
#        Pattern (bytes shown high-nibble first; each bracket MSB->LSB)  k  Nibbles Bits  VALUE_BITS  Value range (inclusive)
#        [.... | xxx1]                                                   0    1       4       3       [        0 ..        7]
#        [xxxx | xx10]                                                   1    2       8       6       [        8 ..       71]
#        [xxxx | x100] [.... | xxxx]                                     2    3      12       9       [       72 ..      583]
#        [xxxx | 1000] [xxxx | xxxx]                                     3    4      16      12       [      584 ..     4679]
#        [xxx1 | 0000] [xxxx | xxxx] [xxxx | xxxx]                       4    6      24      19       [     4680 ..   528967]
#        [xx10 | 0000] [xxxx | xxxx] [xxxx | xxxx] [xxxx | xxxx]         5    8      32      26       [   528968 ..  528968+(1<<26)-1 ]
#
#      Legend: Within each bracket bits are shown MSB->LSB (bit3 .. bit0). Nibble order is grouped by bytes, with
#      each byte displayed as [high_nibble | low_nibble] for readability; earlier brackets correspond to later
#      bits in the stream when compared to previous LSB-first depiction (this is a presentation-only reordering).
#
#      For k >= 6 we switch to raw fixed-length forms (no shift, direct value
#      bytes) selected by an 8-bit (two-nibble) control prefix beginning with
#      6 leading zero bits. The mapping (same logical description as original
#      spec) is:
#         11000000 -> raw32 : 4 value bytes (little-endian)
#         10000000 -> raw40 : 5 value bytes
#         01000000 -> raw48 : 6 value bytes
#         00000000 -> raw64 : 8 value bytes
#
#    Storage / ordering conventions:
#      - Nibbles are stored little-nibble-first inside each byte (low nibble is
#        written first). This matches the LSB-first bit packing and allows the
#        decoder to reconstruct values by simple shifting.
#      - Small-form code words are materialized as a single integer whose lower
#        (k+1) bits are the prefix (k zeros then a 1) and whose remaining bits
#        are the value payload (LSB-first). We emit all nibbles of that integer
#        low nibble first.
#
#    Encoder implementation details:
#      - emit_code(code, n_nibbles) writes an entire small-form or control block
#        in bulk, exploiting alignment to append whole bytes when possible.
#      - Raw value bytes are emitted as pairs of nibbles (low then high) for each
#        little-endian byte.
#
#    Decoder implementation details:
#      - peek_two_nibbles() previews up to 8 bits (two nibbles) without consuming.
#      - The first set bit among positions 0..5 in the preview selects small form k.
#        If the lower 6 bits are all zero we treat it as a raw form and use the
#        next two bits (already contained in the second control nibble) to pick
#        the length, or all 8 zero bits for raw64.
#      - read_nibbles(n) bulk-reads n nibbles, consuming whole bytes when aligned.
#      - For small forms we read the fixed nibble count for that k, then shift
#        right by (k+1) to drop the prefix and add SHIFT[k] to reconstruct n.
#      - For raw forms we read two control nibbles (via read_nibbles(2)) then the
#        specified number of value bytes, each as two nibbles (again via read_nibbles(2)).
#
#    NOTE: Only values 0 <= n <= 2^64 - 1 are supported.

from typing import List

# Precomputed constants (capacities & shifts) explained above
_VALUE_BITS = (3, 6, 9, 12, 19, 26)
_CAPACITY = tuple(1 << b for b in _VALUE_BITS)
_SHIFT = (
    0,
    _CAPACITY[0],
    _CAPACITY[0] + _CAPACITY[1],
    _CAPACITY[0] + _CAPACITY[1] + _CAPACITY[2],
    _CAPACITY[0] + _CAPACITY[1] + _CAPACITY[2] + _CAPACITY[3],
    _CAPACITY[0] + _CAPACITY[1] + _CAPACITY[2] + _CAPACITY[3] + _CAPACITY[4],
)
# Top (inclusive) value encodable by small form k
_TOP = tuple(_SHIFT[k] + _CAPACITY[k] - 1 for k in range(6))
_MAX_SMALL = _TOP[5]  # Largest value encodable with small form (k=5)


def bit_encode_small_unsigned(a: List[int]) -> bytes:
    """Encode a list of non-negative integers into bytes."""
    out = bytearray()
    nibble_phase = 0  # 0 -> next nibble goes to low 4 bits (new byte), 1 -> high 4 bits of last byte

    def emit_nibble(nib: int):
        nonlocal nibble_phase
        if nibble_phase == 0:
            out.append(nib & 0x0F)
        else:
            out[-1] |= (nib & 0x0F) << 4
        nibble_phase ^= 1

    def emit_code(code: int, n_nibbles: int):
        """Emit 'n_nibbles' from code, lowest nibble first."""
        nonlocal nibble_phase

        if n_nibbles <= 1:
            emit_nibble(code & 0x0F)
            return

        if nibble_phase == 1:
            # If we are in high nibble phase, emit a low nibble first to complete the byte
            emit_nibble(code & 0x0F)
            code >>= 4
            n_nibbles -= 1

        # Now we are guaranteed to be in low nibble phase
        while n_nibbles > 1:
            out.append(code & 0xFF)
            code >>= 8
            n_nibbles -= 2

        # Emit the last nibble (if any)
        if n_nibbles == 1:
            emit_nibble(code & 0x0F)

    for n in a:
        if n < 0 or n > 0xFFFFFFFFFFFFFFFF:
            raise ValueError("Value out of supported range (0..2^64-1)")
        # Small forms via explicit if/elif chain with emit_code helper
        if n <= _TOP[0]:  # k=0 (1 nibble)
            emit_code((n << 1) | 0x01, 1)
        elif n <= _TOP[1]:  # k=1 (2 nibbles)
            emit_code(((n - _SHIFT[1]) << 2) | 0x02, 2)
        elif n <= _TOP[2]:  # k=2 (3 nibbles)
            emit_code(((n - _SHIFT[2]) << 3) | 0x04, 3)
        elif n <= _TOP[3]:  # k=3 (4 nibbles)
            emit_code(((n - _SHIFT[3]) << 4) | 0x08, 4)
        elif n <= _TOP[4]:  # k=4 (6 nibbles)
            emit_code(((n - _SHIFT[4]) << 5) | 0x10, 6)
        elif n <= _TOP[5]:  # k=5 (8 nibbles)
            emit_code(((n - _SHIFT[5]) << 6) | 0x20, 8)
        else:
            # Raw forms: adjust so _MAX_SMALL+1 maps to 0
            n = n - _MAX_SMALL - 1
            if n <= 0xFFFFFFFF:  # raw32 (4 bytes)
                emit_code(0xC0, 2)
                emit_code(n, 8)
            elif n <= 0xFFFFFFFFFF:  # raw40 (5 bytes)
                emit_code(0x40, 2)
                emit_code(n, 10)
            elif n <= 0xFFFFFFFFFFFF:  # raw48 (6 bytes)
                emit_code(0x80, 2)
                emit_code(n, 12)
            else:  # raw64 (8 bytes)
                emit_code(0, 2)
                emit_code(n, 16)
    # If we ended on half byte (nibble_phase==1) that's fine (stream ends at a nibble boundary). No padding needed.
    return bytes(out)


def bit_decode_small_unsigned(data: bytes, count: int) -> List[int]:
    """Decode 'count' integers from the given byte stream (nibble-based reader)."""
    if count < 0:
        raise ValueError("count must be non-negative")

    res: List[int] = []
    byte_len = len(data)
    byte_index = 0
    nibble_phase = 0  # 0 -> low nibble next, 1 -> high nibble next

    def peek_two_nibbles() -> int:
        """Return next two nibbles (low-first) packed into one byte without advancing.
        If only one nibble remains, second nibble bits are zero."""
        if byte_index >= byte_len:
            raise ValueError("Unexpected end of data while reading nibble")

        if nibble_phase == 0:
            return data[byte_index]

        ret = (data[byte_index] >> 4) & 0x0F
        if byte_index + 1 < byte_len:
            ret |= (data[byte_index + 1] << 4) & 0xF0
        return ret

    def read_nibble() -> int:
        nonlocal byte_index, nibble_phase
        if byte_index >= byte_len:
            raise ValueError("Unexpected end of data while reading nibble")
        b = data[byte_index]
        if nibble_phase == 0:
            nib = b & 0x0F
            nibble_phase = 1
        else:
            nib = (b >> 4) & 0x0F
            nibble_phase = 0
            byte_index += 1
        return nib

    def read_nibbles(n: int) -> int:
        """Read n nibbles and pack them (low nibble first) into an integer.
        Optimized to read whole bytes when aligned (nibble_phase==0)."""
        nonlocal byte_index, nibble_phase

        if n <= 1:
            return read_nibble()

        val = 0
        shift = 0

        # If misaligned (high nibble next), read one nibble to realign
        if nibble_phase == 1 and n > 0:
            # Read the high nibble first
            val = read_nibble()
            shift = 4
            n -= 1

        # Now aligned (low nibble first)
        while n >= 2:
            if byte_index >= byte_len:
                raise ValueError("Unexpected end of data while reading byte")
            b = data[byte_index]
            byte_index += 1
            # low nibble
            val |= b << shift
            shift += 8
            n -= 2

        # If odd nibbles left, read the last low nibble
        if n == 1:
            val |= read_nibble() << shift

        return val

    while len(res) < count:
        if byte_index >= byte_len:
            raise ValueError("Not enough data to decode requested number of integers")
        preview = peek_two_nibbles()
        if preview & 0x01:  # k=0 (1 nibble)
            res.append(_SHIFT[0] + (read_nibbles(1) >> 1))
        elif preview & 0x02:  # k=1 (2 nibbles)
            res.append(_SHIFT[1] + (read_nibbles(2) >> 2))
        elif preview & 0x04:  # k=2 (3 nibbles)
            res.append(_SHIFT[2] + (read_nibbles(3) >> 3))
        elif preview & 0x08:  # k=3 (4 nibbles)
            res.append(_SHIFT[3] + (read_nibbles(4) >> 4))
        elif preview & 0x10:  # k=4 (6 nibbles)
            res.append(_SHIFT[4] + (read_nibbles(6) >> 5))
        elif preview & 0x20:  # k=5 (8 nibbles)
            res.append(_SHIFT[5] + (read_nibbles(8) >> 6))
        else:  # raw (payload is adjusted value)
            byte_index += 1  # consume control byte already previewed
            if preview == 0xC0:  # raw32
                res.append(_MAX_SMALL + 1 + read_nibbles(8))
            elif preview == 0x40:  # raw40
                res.append(_MAX_SMALL + 1 + read_nibbles(10))
            elif preview == 0x80:  # raw48
                res.append(_MAX_SMALL + 1 + read_nibbles(12))
            elif preview == 0x00:  # raw64
                res.append(_MAX_SMALL + 1 + read_nibbles(16))
            else:
                raise ValueError(f"Invalid prefix: {preview:02X}")
    return res

###############################################################################
# Tests

from zigzag import encode_signed_as_unsigned, decode_unsigned_as_signed

if __name__ == "__main__":
    # Unsigned integer basic set
    print(f"\n    Unsigned integers (first 300)\n{'Number':<10} {'Hex':<20} {'Bin':<30}  {'Decoded'}")
    for i in range(300):
        enc = bit_encode_small_unsigned([i])
        dec = bit_decode_small_unsigned(enc, 1)[0]
        print(f"{i:<10} {enc.hex(' '):<20} {' '.join(f'{b:08b}' for b in enc):<30}  {dec}")
        assert dec == i, (i, dec, enc.hex())

    print(f"\n    Unsigned integers (exponent)\n{'Number':<10} {'Hex':<40} {'Bin':<64}  {'Decoded'}")
    for ii in range(64):
        i = 1 << ii
        enc = bit_encode_small_unsigned([i])
        dec = bit_decode_small_unsigned(enc, 1)[0]
        print(f"{i:<10} {enc.hex(' '):<40} {' '.join(f'{b:08b}' for b in enc):<64}  {dec}")
        assert dec == i, (i, dec, enc.hex())
    i = (1 << 64) - 1
    enc = bit_encode_small_unsigned([i])
    dec = bit_decode_small_unsigned(enc, 1)[0]
    print(f"{i:<10} {enc.hex(' '):<40} {' '.join(f'{b:08b}' for b in enc):<64}  {dec}")
    assert dec == i, (i, dec, enc.hex())

    # Boundary tests around each shift
    print("\nBoundary test cases:")
    print(f"{'Value':<22} {'Hex':<30}   {'Bytes':<30} {'Decoded'}")
    boundaries = [
        0,7,8,71,72,583,584,4679,4680,528967,528968,_MAX_SMALL,
        _MAX_SMALL+1,
        _MAX_SMALL+1 + 0xFFFFFFFF,
        _MAX_SMALL+1 + 0xFFFFFFFF + 1,
        _MAX_SMALL+1 + 0xFFFFFFFFFF,
        _MAX_SMALL+1 + 0xFFFFFFFFFF + 1,
        _MAX_SMALL+1 + 0xFFFFFFFFFFFF,
        _MAX_SMALL+1 + 0xFFFFFFFFFFFF + 1,
        0xFFFFFFFFFFFFFFFF,
    ]
    for v in boundaries:
        enc = bit_encode_small_unsigned([v])
        dec = bit_decode_small_unsigned(enc, 1)[0]
        print(f"{v:<22} {enc.hex(' '):<30}   {' '.join(f'{b:02x}' for b in enc):<30} {dec}")
        assert dec == v, (v, dec, enc.hex())

    # Random spot checks
    print("\nRandom / special spot checks:")
    print(f"{'Value':<22} {'Hex':<30}   {'Bytes':<30} {'Decoded'}")
    spot_values = (12345, 678910, 2**26 - 1, 2**26, 2**32 - 1, 2**32, 2**40 - 1, 2**48 - 1, 2**56 - 1, 2**64 - 1)
    for v in spot_values:
        enc = bit_encode_small_unsigned([v])
        dec = bit_decode_small_unsigned(enc, 1)[0]
        print(f"{v:<22} {enc.hex(' '):<30}   {' '.join(f'{b:02x}' for b in enc):<30} {dec}")
        assert dec == v, (v, dec, enc.hex())

    # Sequence test
    print("\nSequence test values:")
    arr = [0,7,8,9,71,72,528967,528968, _MAX_SMALL, _MAX_SMALL+1, 2**40 - 1, 2**64 - 1]
    enc = bit_encode_small_unsigned(arr)
    dec = bit_decode_small_unsigned(enc, len(arr))
    # Print each value with cumulative offset into encoded buffer
    print(f"{'Idx':<4} {'Value':<12} {'Decoded'}")
    for i,(v,dv) in enumerate(zip(arr, dec)):
        print(f"{i:<4} {v:<12} {dv}")
    assert dec == arr, (arr, dec, enc.hex())

    # Signed integers test using zigzag mapping
    print(f"\n    Signed integers\n{'Number':<10} {'Hex':<20} {'Bin':<20} {'Decoded'}")
    for i in range(-100, 101):
        enc = bit_encode_small_unsigned([encode_signed_as_unsigned(i)])
        dec_any = decode_unsigned_as_signed(bit_decode_small_unsigned(enc, 1)[0])
        print(f"{i:<10} {enc.hex(' '):<20} {' '.join(f'{b:08b}' for b in enc):<20} {dec_any}")
        assert dec_any == i, (i, dec_any, enc.hex())

    # Pairs of integers
    print(f"\n    Pairs of integers\n{'Array':<18} {'Decoded':<18} {'Len':<6} {'Hex':<20} {'Bin'}")
    for i in range(0, 11):
        arr = [i * (i + 1) // 2, i]
        enc = bit_encode_small_unsigned(arr)
        dec = bit_decode_small_unsigned(enc, 2)
        print(f"{str(arr):<18} {str(dec):<18} {len(enc):<6} {enc.hex(' '):<20} {' '.join(f'{b:08b}' for b in enc)}")
        assert dec == arr, (i, dec, enc.hex())

    # Arrays of small consecutive integers
    print(f"\n    Arrays of consecutive integers")
    for i in range(1, 11):
        arr = list(range(i))
        enc = bit_encode_small_unsigned(arr)
        dec = bit_decode_small_unsigned(enc, i)
        print(f"Array: {arr} -> bytes={len(enc)} hex={enc.hex(' ')}")
        assert dec == arr, (i, dec, enc.hex())

    # Arrays of squared integers
    print(f"\n    Arrays of squared integers")
    for i in range(2, 11):
        arr = [x * x for x in range(i)]
        enc = bit_encode_small_unsigned(arr)
        dec = bit_decode_small_unsigned(enc, i)
        print(f"Array: {arr} -> bytes={len(enc)} hex={enc.hex(' ')}")
        assert dec == arr, (i, dec, enc.hex())

    # Print out precomputed constants for reference
    print("\nPrecomputed constants:")
    print(f"_VALUE_BITS: {_VALUE_BITS}")
    print(f"_CAPACITY: {_CAPACITY}")
    print(f"_SHIFT: {_SHIFT}")
    print(f"_TOP: {_TOP}")
    print(f"_MAX_SMALL: {_MAX_SMALL}")
