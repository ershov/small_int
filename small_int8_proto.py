#!/usr/bin/env python3

###############################################################################
#    Functions for protobuf encoding of small unsigned integers into 8-bit chunks.
#    This is the standard (unbiased) base-128 varint:
#      - Each byte stores 7 data bits (little-endian groups) in bits 0..6.
#      - Bit 7 (0x80) is the continuation flag: set if another byte follows.
#      - No +1 / -1 biasing between bytes (unlike the custom small_int8 scheme).

def bit_encode_small_unsigned(a: list[int]) -> bytes:
    """Encode an array of small non-negative integers (protobuf varint)."""
    out = bytearray()
    for n in a:
        if n < 0:
            raise ValueError("n must be non-negative")
        # Standard base-128 varint emission (LSB 7-bit groups first)
        while True:
            byte = n & 0x7F
            n >>= 7
            if n:
                out.append(byte | 0x80)
            else:
                out.append(byte)
                break
    return bytes(out)


def bit_decode_small_unsigned(data: bytes, count: int) -> list[int]:
    """Decode a byte sequence produced by bit_encode_small_unsigned."""
    result: list[int] = []
    n = 0
    shift = 0
    for b in data:
        n |= (b & 0x7F) << shift
        if not (b & 0x80):  # last byte of this integer
            result.append(n)
            count -= 1
            if count == 0:
                # Ensure no trailing partial data (which would be harmless but unexpected)
                return result
            n = 0
            shift = 0
        else:
            shift += 7
            if shift > 70:  # More than 10 bytes for a 64-bit varint => malformed / overflow
                raise ValueError("Varint too long or overflow")
    if n or shift:
        raise ValueError("Incomplete data: not enough bytes to finish last integer")
    if count > 0:
        raise ValueError(f"Too many integers requested: not enough data to decode all integers ({count} left)")
    return result

###############################################################################
# Tests

from zigzag import encode_signed_as_unsigned, decode_unsigned_as_signed

if __name__ == "__main__":
    import random
    random.seed(876543)

    print(f"\n    Unsigned integers\n{'Number':<10} {'Hex':<20} {'Bin':<30}  {'Decoded Value':<20}")
    for ii in range(201):
        i = ii * 10
        encoded = bit_encode_small_unsigned([i])
        decoded = bit_decode_small_unsigned(encoded, 1)[0]
        print(f"{i:<10} {encoded.hex(' '):<20} {' '.join(f'{b:08b}' for b in encoded):<30}  {decoded:<20}")
        assert decoded == i, f"Decoded value {decoded} does not match original {i}"
    for ii in range(3, 30):
        i = (200 + ii * (2 ** ii) // 3)*10
        encoded = bit_encode_small_unsigned([i])
        decoded = bit_decode_small_unsigned(encoded, 1)[0]
        print(f"{i:<10} {encoded.hex(' '):<20} {' '.join(f'{b:08b}' for b in encoded):<30}  {decoded:<20}")
        assert decoded == i, f"Decoded value {decoded} does not match original {i}"

    print(f"\n    Signed integers\n{'Number':<10} {'Hex':<20} {'Bin':<20} {'Decoded Value':<20}")
    for ii in range(-100, 101):
        i = ii * 10
        encoded = bit_encode_small_unsigned([encode_signed_as_unsigned(i)])
        decoded = decode_unsigned_as_signed(bit_decode_small_unsigned(encoded, 1)[0])
        print(f"{i:<10} {encoded.hex(' '):<20} {' '.join(f'{b:08b}' for b in encoded):<20} {decoded:<20}")
        assert decoded == i, f"Decoded value {decoded} does not match original {i}"

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

    print(f"\n    Pairs of integers\n{'Array':<15} {'Decoded':<15} {'Len':<8} {'Hex':<10} {'Bin':<16}")
    for ii in range(0, 11):
        i = ii * 10
        arr = [i * (i + 1) // 2, i]
        encoded = bit_encode_small_unsigned(arr)
        decoded = bit_decode_small_unsigned(encoded, 2)
        print(f"{str(arr):<15} {str(decoded):<15} {len(encoded):<8} {encoded.hex(' '):<10} {' '.join(f'{b:08b}' for b in encoded):<16}")
        assert decoded == arr, f"Decoded value {decoded} does not match original {arr}"

    print(f"\n    Array of small integers")
    for i in range(1, 11):
        arr = [x*50 for x in range(i)]
        encoded = bit_encode_small_unsigned(arr)
        decoded = bit_decode_small_unsigned(encoded, i)
        print(f"""
Array:    {str(arr):<10}\t({len(arr)} elements)
Decoded:  {str(decoded)}
Hex dump: {encoded.hex(' ')}\t({len(encoded)} bytes)
Bin dump: {' '.join(f'{b:08b}' for b in encoded)}""")
        assert decoded == arr, f"Decoded value {decoded} does not match original {arr}"

    print(f"\n    Array of bigger integers")
    for i in range(2, 11):
        arr = [x * x * 50 for x in range(i)]
        encoded = bit_encode_small_unsigned(arr)
        decoded = bit_decode_small_unsigned(encoded, i)
        print(f"""
Array:    {str(arr):<10}\t({len(arr)} elements)
Decoded:  {str(decoded)}
Hex dump: {encoded.hex(' ')}\t({len(encoded)} bytes)
Bin dump: {' '.join(f'{b:08b}' for b in encoded)}""")
        assert decoded == arr, f"Decoded value {decoded} does not match original {arr}"

    ###########################################################################
    # Boundary values for unbiased protobuf varint (length transitions)
    print("\n    Boundary values (protobuf varint length transitions)")

    def compute_min_values(max_len: int):
        # mins[L] minimal value requiring exactly L bytes; index 0 -> L=1.
        mins = [0]
        for L in range(2, max_len + 1):
            mins.append(1 << (7 * (L - 1)))
        return mins

    max_len = 10  # up to 10 bytes for 64-bit values
    mins = compute_min_values(max_len)

    def max_for_length(L: int):
        return (1 << (7 * L)) - 1

    test_values = []
    for L in range(1, max_len + 1):
        min_v = mins[L - 1]
        max_v = max_for_length(L)
        if L < max_len:
            next_min = mins[L] if L < max_len else None
        prev_max = (1 << (7 * (L - 1))) - 1 if L > 1 else None
        candidates = [
            prev_max,
            min_v - 1 if L > 1 else None,
            min_v,
            min_v + 1,
            max_v - 1,
            max_v,
            max_v + 1 if L < max_len else None,
        ]
        for v in candidates:
            if v is not None and v >= 0:
                if v < (1 << 64):  # keep within 64-bit test domain
                    test_values.append(v)

    test_values = sorted(set(test_values))

    for v in test_values:
        enc = bit_encode_small_unsigned([v])
        dec = bit_decode_small_unsigned(enc, 1)[0]
        L = len(enc)
        assert dec == v, f"Boundary decode mismatch: got {dec} expected {v}"
        expected_L = 1 if v == 0 else (v.bit_length() + 6) // 7
        assert L == expected_L, f"Length mismatch for {v}: got {L}, expected {expected_L}"
        print(f"v={v:<22} bytes={L} hex={enc.hex(' '):<25} bin={' '.join(f'{b:08b}' for b in enc)}")

    # Random stress test
    print("\n    Random stress test (1000 integers)")
    random_values = [random.randint(0, (1 << 56) - 1) for _ in range(1000)]
    enc = bit_encode_small_unsigned(random_values)
    dec = bit_decode_small_unsigned(enc, len(random_values))
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
        enc = bit_encode_small_unsigned(arr)
        dec = bit_decode_small_unsigned(enc, len(arr)) if arr else []
        assert dec == arr, f"Mixed array mismatch: {dec} != {arr}"
        print(f"len={len(arr):<3} bytes={len(enc):<4} arr_head={arr[:5]}")

    # Error: truncated data
    print("\n    Error handling: truncated data")
    big_value = (1 << 35) + 12345
    enc_big = bit_encode_small_unsigned([big_value])
    assert len(enc_big) > 1
    truncated = enc_big[:-1]
    try:
        bit_decode_small_unsigned(truncated, 1)
        assert False, "Expected ValueError for truncated data"
    except ValueError as e:
        print(f"Truncated data correctly raised: {e}")

    # Error: requesting too many integers
    print("\n    Error handling: over-request count")
    enc_two = bit_encode_small_unsigned([10, 20])
    try:
        bit_decode_small_unsigned(enc_two, 3)
        assert False, "Expected ValueError for over-request count"
    except ValueError as e:
        print(f"Over-request correctly raised: {e}")

    # Large single value extremes (near 2^63)
    print("\n    Large value tests")
    for v in [(1 << 62) - 1, 1 << 62, (1 << 62) + 1]:
        enc = bit_encode_small_unsigned([v])
        dec = bit_decode_small_unsigned(enc, 1)[0]
        print(f"v={v} bytes={len(enc)}")
        assert dec == v, f"Large value mismatch {dec} != {v}"

    # Edge and max 64-bit related values
    for v in [(1 << 63) - 1, 1 << 63, (1 << 64) - 1]:
        enc = bit_encode_small_unsigned([v])
        dec = bit_decode_small_unsigned(enc, 1)[0]
        print(f"v={v} bytes={len(enc)}")
        assert dec == v, f"Value mismatch {dec} != {v}"
