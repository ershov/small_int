#!/usr/bin/env python3

###############################################################################
# WiredTiger's Variable-length integer encoding.
# We need up to 64 bits, signed and unsigned.  Further, we want the packed
# representation to have the same lexicographic ordering as the integer
# values.  This avoids the need for special-purpose comparison code.
#
# Try hard to keep small values small (up to ~2 bytes): that gives the biggest
# benefit for common cases storing small values.  After that, just encode the
# length in the first byte: we could squeeze in a couple of extra bits, but
# the marginal benefit is small, and we want this code to be relatively
# easy to implement in client code or scripting APIs.
#
# First byte  | Next |                        |
# byte        | bytes| Min Value              | Max Value
# ------------+------+------------------------+--------------------------------
# [00 00xxxx] | free | N/A                    | N/A
# [00 01llll] | llll | -2^64                  | -2^13 - 2^6
# [00 1xxxxx] | 1    | -2^13 - 2^6            | -2^6 - 1
# [01 xxxxxx] | 0    | -2^6                   | -1
# [10 xxxxxx] | 0    | 0                      | 2^6 - 1
# [11 0xxxxx] | 1    | 2^6                    | 2^13 + 2^6 - 1
# [11 10llll] | llll | 2^13 + 2^6             | 2^64 - 1
# [11 11xxxx] | free | N/A                    | N/A

# Added marker constants for negative ranges
NEG_MULTI_MARKER = 0x10
NEG_2BYTE_MARKER = 0x20
NEG_1BYTE_MARKER = 0x40
POS_1BYTE_MARKER = 0x80
POS_2BYTE_MARKER = 0xC0
POS_MULTI_MARKER = 0xE0

# Range limits (signed & unsigned boundaries)
NEG_1BYTE_MIN = -(1 << 6)                # -64
NEG_2BYTE_MIN = -(1 << 13) + NEG_1BYTE_MIN  # -(8192 + 64) = -8256
POS_1BYTE_MAX = (1 << 6) - 1             # 63
POS_2BYTE_MAX = (1 << 13) + POS_1BYTE_MAX  # 8192 + 63 = 8255

def bit_encode_small(a: list[int]) -> bytes:
    """Encode a list of 64-bit signed/unsigned integers (WiredTiger format)."""
    out = bytearray()
    for n in a:
        # Normalize to 64-bit signed range for checks
        if n < -(1 << 63) or n > (1 << 64) - 1:
            raise ValueError(f"value out of supported 64-bit range: {n}")
        # Negative cases
        if n < NEG_2BYTE_MIN:
            # Multi-byte negative: mirror positive logic (derive payload length, then slice)
            mask64 = (1 << 64) - 1
            n = n & mask64  # two's complement 64-bit
            inv = (~n) & mask64
            lead_zero_bits = 64 - inv.bit_length() if inv else 64
            lz = min(7, lead_zero_bits // 8) # clamp (-1 would yield 8, but isn't in this branch)
            full = n.to_bytes(8, 'big')
            payload = full[lz - 8:]
            out.append(NEG_MULTI_MARKER | (lz & 0x0F))
            out.extend(payload)
            continue
        if n < NEG_1BYTE_MIN:  # 2-byte negative
            x2 = n - NEG_2BYTE_MIN  # 0 .. (2^13 - 1)
            out.append(NEG_2BYTE_MARKER | ((x2 >> 8) & 0x1F))
            out.append(x2 & 0xFF)
            continue
        if n < 0:  # 1-byte negative
            x3 = n - NEG_1BYTE_MIN  # 0..63
            out.append(NEG_1BYTE_MARKER | (x3 & 0x3F))
            continue
        # Non-negative (unsigned) path
        if n <= POS_1BYTE_MAX:
            out.append(POS_1BYTE_MARKER | (n & 0x3F))
        elif n <= POS_2BYTE_MAX:
            v = n - (POS_1BYTE_MAX + 1)
            out.append(POS_2BYTE_MARKER | ((v >> 8) & 0x1F))
            out.append(v & 0xFF)
        elif n == POS_2BYTE_MAX + 1:
            # Special case per WT: keep monotonic length growth
            out.extend([POS_MULTI_MARKER | 0x1, 0x00])
        else:
            v = n - (POS_2BYTE_MAX + 1)
            length = max(1, (v.bit_length() + 7) // 8)  # 1..8
            if length > 8:
                raise ValueError("multi-byte positive length overflow")
            out.append(POS_MULTI_MARKER | length)
            out.extend(v.to_bytes(length, 'big'))
    return bytes(out)


def bit_decode_small(data: bytes, count: int) -> list[int]:
    """Decode 'count' signed/unsigned integers (WiredTiger format)."""
    res: list[int] = []
    i = 0
    while count > 0:
        if i >= len(data):
            raise ValueError("insufficient data to decode value")
        b0 = data[i]
        top = b0 & 0xF0
        # Negative multi
        if top == NEG_MULTI_MARKER:
            lz = b0 & 0x0F
            length = 8 - lz
            if length <= 0 or length > 8:
                raise ValueError("invalid negative multi length header")
            end = i + 1 + length
            if end > len(data):
                raise ValueError("truncated negative multi value")
            payload = data[i + 1:end]
            u_bytes = b'\xff' * lz + payload
            u = int.from_bytes(u_bytes, 'big')
            val = u - (1 << 64) if u & (1 << 63) else u
            i = end
        # Negative 2-byte
        elif top in (NEG_2BYTE_MARKER, NEG_2BYTE_MARKER | 0x10):
            if i + 1 >= len(data):
                raise ValueError("truncated 2-byte negative value")
            high5 = b0 & 0x1F
            b1 = data[i + 1]
            v = (high5 << 8) | b1
            val = v + NEG_2BYTE_MIN
            i += 2
        # Negative 1-byte
        elif top in (NEG_1BYTE_MARKER, NEG_1BYTE_MARKER | 0x10, NEG_1BYTE_MARKER | 0x20, NEG_1BYTE_MARKER | 0x30):
            val = NEG_1BYTE_MIN + (b0 & 0x3F)
            i += 1
        # Positive 1-byte
        elif top in (0x80, 0x90, 0xA0, 0xB0):
            val = b0 & 0x3F
            i += 1
        # Positive 2-byte
        elif top in (0xC0, 0xD0):
            if i + 1 >= len(data):
                raise ValueError("truncated 2-byte positive value")
            v = (b0 & 0x1F) << 8 | data[i + 1]
            val = v + POS_1BYTE_MAX + 1
            i += 2
        # Positive multi
        elif top == POS_MULTI_MARKER:
            length = b0 & 0x0F
            if length == 0 or length > 8:
                raise ValueError("invalid multi-byte positive length")
            end = i + 1 + length
            if end > len(data):
                raise ValueError("truncated multi-byte positive value")
            v = int.from_bytes(data[i + 1:end], 'big')
            val = v + POS_2BYTE_MAX + 1
            i = end
        else:
            raise ValueError(f"invalid marker byte 0x{b0:02x}")
        res.append(val)
        count -= 1
    return res

###############################################################################
# Tests

if __name__ == "__main__":
    import random
    random.seed(876543)

    print(f"\n    Unsigned integers\n{'Number':<10} {'Hex':<20} {'Bin':<30}  {'Decoded Value':<20}")
    for ii in range(201):
        i = ii * 10
        encoded = bit_encode_small([i])
        decoded = bit_decode_small(encoded, 1)[0]
        print(f"{i:<10} {encoded.hex(' '):<20} {' '.join(f'{b:08b}' for b in encoded):<30}  {decoded:<20}")
        assert decoded == i, f"Decoded value {decoded} does not match original {i}"
    for ii in range(3, 30):
        i = (200 + ii * (2 ** ii) // 3)*10
        encoded = bit_encode_small([i])
        decoded = bit_decode_small(encoded, 1)[0]
        print(f"{i:<10} {encoded.hex(' '):<20} {' '.join(f'{b:08b}' for b in encoded):<30}  {decoded:<20}")
        assert decoded == i, f"Decoded value {decoded} does not match original {i}"

    print(f"\n    Signed integers\n{'Number':<10} {'Hex':<20} {'Bin':<20} {'Decoded Value':<20}")
    for ii in range(-100, 101):
        i = ii * 10
        encoded = bit_encode_small([i])
        decoded = bit_decode_small(encoded, 1)[0]
        print(f"{i:<10} {encoded.hex(' '):<20} {' '.join(f'{b:08b}' for b in encoded):<20} {decoded:<20}")
        assert decoded == i, f"Decoded value {decoded} does not match original {i}"

    print(f"\n    Unsigned integers (exponent)\n{'Number':<10} {'Hex':<40} {'Bin':<64}  {'Decoded'}")
    for ii in range(64):
        i = 1 << ii
        enc = bit_encode_small([i])
        dec = bit_decode_small(enc, 1)[0]
        print(f"{i:<10} {enc.hex(' '):<40} {' '.join(f'{b:08b}' for b in enc):<64}  {dec}")
        assert dec == i, (i, dec, enc.hex())
    i = (1 << 64) - 1
    enc = bit_encode_small([i])
    dec = bit_decode_small(enc, 1)[0]
    print(f"{i:<10} {enc.hex(' '):<40} {' '.join(f'{b:08b}' for b in enc):<64}  {dec}")
    assert dec == i, (i, dec, enc.hex())

    print(f"\n    Pairs of integers\n{'Array':<15} {'Decoded':<15} {'Len':<8} {'Hex':<10} {'Bin':<16}")
    for ii in range(0, 11):
        i = ii * 10
        arr = [i * (i + 1) // 2, i]
        encoded = bit_encode_small(arr)
        decoded = bit_decode_small(encoded, 2)
        print(f"{str(arr):<15} {str(decoded):<15} {len(encoded):<8} {encoded.hex(' '):<10} {' '.join(f'{b:08b}' for b in encoded):<16}")
        assert decoded == arr, f"Decoded value {decoded} does not match original {arr}"

    print(f"\n    Array of small integers")
    for i in range(1, 11):
        arr = [x*50 for x in range(i)]
        encoded = bit_encode_small(arr)
        decoded = bit_decode_small(encoded, i)
        print(f"""
Array:    {str(arr):<10}\t({len(arr)} elements)
Decoded:  {str(decoded)}
Hex dump: {encoded.hex(' ')}\t({len(encoded)} bytes)
Bin dump: {' '.join(f'{b:08b}' for b in encoded)}""")
        assert decoded == arr, f"Decoded value {decoded} does not match original {arr}"

    print(f"\n    Array of bigger integers")
    for i in range(2, 11):
        arr = [x * x * 50 for x in range(i)]
        encoded = bit_encode_small(arr)
        decoded = bit_decode_small(encoded, i)
        print(f"""
Array:    {str(arr):<10}\t({len(arr)} elements)
Decoded:  {str(decoded)}
Hex dump: {encoded.hex(' ')}\t({len(encoded)} bytes)
Bin dump: {' '.join(f'{b:08b}' for b in encoded)}""")
        assert decoded == arr, f"Decoded value {decoded} does not match original {arr}"

    ###########################################################################
    # WiredTiger format boundary tests (length transitions)

    print("\n    Boundary values (WiredTiger length transitions)")

    def wt_encoded_len(v: int) -> int:
        return len(bit_encode_small([v]))

    boundary_values = [
        0, 1, 62, 63, 64, 65,  # 1-byte -> 2-byte
        POS_1BYTE_MAX, POS_1BYTE_MAX + 1,
        POS_2BYTE_MAX - 1, POS_2BYTE_MAX, POS_2BYTE_MAX + 1, POS_2BYTE_MAX + 2,
        POS_2BYTE_MAX + 255, POS_2BYTE_MAX + 256, POS_2BYTE_MAX + 257,
        (1 << 16) - 1 + (POS_2BYTE_MAX + 1), (1 << 16) + (POS_2BYTE_MAX + 1),  # 1-byte remainder vs 2-byte remainder
        (1 << 24) - 1 + (POS_2BYTE_MAX + 1), (1 << 24) + (POS_2BYTE_MAX + 1),
        (1 << 32) - 1 + (POS_2BYTE_MAX + 1), (1 << 32) + (POS_2BYTE_MAX + 1),
        (1 << 40) - 1 + (POS_2BYTE_MAX + 1), (1 << 40) + (POS_2BYTE_MAX + 1),
        (1 << 48) - 1 + (POS_2BYTE_MAX + 1), (1 << 48) + (POS_2BYTE_MAX + 1),
        (1 << 56) - 1 + (POS_2BYTE_MAX + 1), (1 << 56) + (POS_2BYTE_MAX + 1),
        (1 << 63) - 1  # near signed max
    ]

    # Expected length calculator per spec
    def expected_len(v: int) -> int:
        if v <= POS_1BYTE_MAX:
            return 1
        if v <= POS_2BYTE_MAX + 1:  # includes special 8256
            return 2
        r = v - (POS_2BYTE_MAX + 1)
        # remainder length (1..8)
        rem_len = max(1, (r.bit_length() + 7) // 8)
        return 1 + rem_len

    for v in boundary_values:
        enc = bit_encode_small([v])
        dec = bit_decode_small(enc, 1)[0]
        L = len(enc)
        exp = expected_len(v)
        assert dec == v, f"decode mismatch {dec}!={v}"
        assert L == exp, f"length mismatch v={v} got {L} expected {exp}"
        print(f"v={v:<22} bytes={L} hex={enc.hex(' '):<25} bin={' '.join(f'{b:08b}' for b in enc)}")

    # Random sampling length verification
    for _ in range(500):
        v = random.randint(0, (1 << 63) - 1)
        L = len(bit_encode_small([v]))
        assert L == expected_len(v), f"random length mismatch for {v}"  # sanity

    print("Boundary tests passed.")

    # Random stress test
    print("\n    Random stress test (1000 integers)")
    random_values = [random.randint(0, (1 << 56) - 1) for _ in range(1000)]
    enc = bit_encode_small(random_values)
    dec = bit_decode_small(enc, len(random_values))
    assert dec == random_values, "Random stress test failed"
    print(f"Encoded 1000 values into {len(enc)} bytes (avg {len(enc)/len(random_values):.2f} bytes/value)")

    # Mixed length arrays and incremental decoding
    print("\n    Mixed arrays incremental decoding")
    mixed_arrays = [
        [],
        [0],
        [0, 1, 2, 3, 4],
        [127, 128, 129],
        [1, (1 << 14) - 1, 1 << 14, (1 << 14) + 1],
        [random.randint(0, 10_000) for _ in range(50)],
    ]
    for arr in mixed_arrays:
        enc = bit_encode_small(arr)
        dec = bit_decode_small(enc, len(arr)) if arr else []
        assert dec == arr, f"Mixed array mismatch: {dec} != {arr}"
        print(f"len={len(arr):<3} bytes={len(enc):<4} arr_head={arr[:5]}")

    # Error: truncated data
    print("\n    Error handling: truncated data")
    big_value = (1 << 35) + 12345
    enc_big = bit_encode_small([big_value])
    assert len(enc_big) > 1
    truncated = enc_big[:-1]
    try:
        bit_decode_small(truncated, 1)
        assert False, "Expected ValueError for truncated data"
    except ValueError as e:
        print(f"Truncated data correctly raised: {e}")

    # Error: requesting too many integers
    print("\n    Error handling: over-request count")
    enc_two = bit_encode_small([10, 20])
    try:
        bit_decode_small(enc_two, 3)
        assert False, "Expected ValueError for over-request count"
    except ValueError as e:
        print(f"Over-request correctly raised: {e}")

    # Large single value extremes (near 2^63)
    print("\n    Large value tests")
    for v in [ (1 << 62) - 1, 1 << 62, (1 << 62) + 1 ]:
        enc = bit_encode_small([v])
        dec = bit_decode_small(enc, 1)[0]
        print(f"v={v} bytes={len(enc)}")
        assert dec == v, f"Large value mismatch {dec} != {v}"

    # Special case: exact 9-byte value (2^63-1)
    enc = bit_encode_small([(1 << 63) - 1])
    dec = bit_decode_small(enc, 1)[0]
    print(f"v=4611686018427387905 bytes=9")
