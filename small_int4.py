#!/usr/bin/env python3

###############################################################################
#    Functions for golomb-like small integer encoding into 4-bit chunks.
#
#    The packing format is:
#    - The encoded data is split into 4-bit chunks: F v v v.
#    - If the first bit (MSB) is 0, this is the last chunk.
#    - If the MSB is 1, the next chunk is a part of the same number.
#    - The remaining 3 bits encode the value.
#    - For chunks beyond the first, the actual value is one greater than what's decoded.
#    - The sequence is LSB-first, meaning the least significant chunk comes first.
#      * Rationale: simplifies encoding and decoding.
#    - The low half of the byte holds the first chunk, the high half holds the second.
#      * Rationale: small integers encode to their own value making debugging easier.

def bit_encode_small_unsigned(a: list[int]) -> bytes:
    """
    Encode an array of small unsigned integers into a single byte sequence.
    """
    result = bytes()
    nibble = 0 # 0 : first nibble, 1 : second nibble

    def bit_encode_one(n: int) -> bytes:
        nonlocal result, nibble
        if n < 0:
            raise ValueError("n must be a non-negative integer")
        while True:
            chunk = n & 0b0111  # Get the last 3 bits
            n >>= 3  # Shift right by 3 bits to process the next chunk
            if n:
                # If there are more bits to process, set the first bit to 1
                chunk |= 0b1000

            if nibble == 0:
                result += bytes([chunk])  # Store in the low half of the byte
            else:
                result = result[:-1] + bytes([result[-1] | (chunk << 4)])
            nibble = 1 - nibble  # Toggle nibble for next iteration

            if n <= 0:
                break

            n -= 1  # Save one bit for encoding since we know the value is not zero

    for n in a:
        if n < 0:
            raise ValueError("All integers must be non-negative")
        bit_encode_one(n)

    return result

def bit_decode_small_unsigned(data: bytes, count: int) -> list[int]:
    """
    Decode a byte sequence into an array of small unsigned integers.
    """
    result = []
    n = 0
    shift = 0

    def decode_chunk(chunk: int) -> bool:
        """Process the next chunk and return the value."""
        nonlocal n, shift
        val = chunk & 0b0111  # Get the last 3 bits
        if shift:
            val = (val + 1) << shift
        n += val  # Use "+" rather than "|", since we can carry bits from "+1"
        shift += 3
        return bool(chunk & 0b1000)

    for byte in data:
        for chunk in (byte & 0b1111, byte >> 4):
            if not decode_chunk(chunk):
                result.append(n)
                if (count := count - 1) <= 0:
                    return result
                n, shift = 0, 0

    if n or shift:
        raise ValueError("Incomplete data: not enough bits to decode the last integer")
    if count > 0:
        raise ValueError(f"Too many integers requested: not enough data to decode all integers ({count} left)")

    return result

###############################################################################
# Tests

from zigzag import encode_signed_as_unsigned, decode_unsigned_as_signed

if __name__ == "__main__":
    print(f"\n    Unsigned integers\n{'Number':<10} {'Hex':<20} {'Bin':<30}  {'Decoded Value':<20}")
    for i in range(201):
        encoded = bit_encode_small_unsigned([i])
        decoded = bit_decode_small_unsigned(encoded, 1)[0]
        print(f"{i:<10} {encoded.hex(' '):<20} {' '.join(f'{b:08b}' for b in encoded):<30}  {decoded:<20}")
        assert decoded == i, f"Decoded value {decoded} does not match original {i}"
    for ii in range(3, 30):
        i = 200 + ii * (2 ** ii) // 3
        encoded = bit_encode_small_unsigned([i])
        decoded = bit_decode_small_unsigned(encoded, 1)[0]
        print(f"{i:<10} {encoded.hex(' '):<20} {' '.join(f'{b:08b}' for b in encoded):<30}  {decoded:<20}")
        assert decoded == i, f"Decoded value {decoded} does not match original {i}"

    # Signed integer
    print(f"\n    Signed integers\n{'Number':<10} {'Hex':<20} {'Bin':<20} {'Decoded Value':<20}")
    for i in range(-100, 101):
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

    # Two small unsigned integers
    print(f"\n    Pairs of integers\n{'Array':<15} {'Decoded':<15} {'Len':<8} {'Hex':<10} {'Bin':<16}")
    for i in range(0, 11):
        arr = [i*(i+1)//2, i]
        encoded = bit_encode_small_unsigned(arr)
        decoded = bit_decode_small_unsigned(encoded, 2)
        print(f"{str(arr):<15} {str(decoded):<15} {len(encoded):<8} {encoded.hex(' '):<10} {' '.join(f'{b:08b}' for b in encoded):<16}")
        assert decoded == arr, f"Decoded value {decoded} does not match original {arr}"

    # Array of small unsigned integers
    print(f"\n    Array of small integers")
    for i in range(1, 11):
        arr = list(range(i))
        encoded = bit_encode_small_unsigned(arr)
        decoded = bit_decode_small_unsigned(encoded, i)
        print(f"""
Array:    {str(arr):<10}\t({len(arr)} elements)
Decoded:  {str(decoded)}
Hex dump: {encoded.hex(' ')}\t({len(encoded)} bytes)
Bin dump: {' '.join(f'{b:08b}' for b in encoded)}""")
        assert decoded == arr, f"Decoded value {decoded} does not match original {arr}"

    # Array of medium unsigned integers
    print(f"\n    Array of bigger integers")
    for i in range(2, 11):
        arr = [x*x for x in range(i)]
        encoded = bit_encode_small_unsigned(arr)
        decoded = bit_decode_small_unsigned(encoded, i)
        print(f"""
Array:    {str(arr):<10}\t({len(arr)} elements)
Decoded:  {str(decoded)}
Hex dump: {encoded.hex(' ')}\t({len(encoded)} bytes)
Bin dump: {' '.join(f'{b:08b}' for b in encoded)}""")
        assert decoded == arr, f"Decoded value {decoded} does not match original {arr}"

