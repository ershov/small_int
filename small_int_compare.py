#!/usr/bin/env python3
"""
Comparison test harness for small integer encodings.

Encoders compared (order fixed):
  1. small_int8.bit_encode_small_unsigned
  2. small_int4.bit_encode_small_unsigned
  3. small_int4_rle1.bit_encode_small_unsigned
  4. small_int1.bit_encode_small_unsigned

Outputs tabular sections with columns:
  Array | For each encoder: <len> <hex-bytes>

Test sections:
  * Single numbers 0..150
  * Single array of 100 numbers with step 50
  * Arrays of small numbers (length 1..10)
  * Arrays of mixed numbers (small + big) up to 10 items
  * Pattern arrays: [0, 0, big, 0, big, medium, medium] (several big/medium variants)
"""
from __future__ import annotations

from small_int8 import bit_encode_small_unsigned as enc8
from small_int4 import bit_encode_small_unsigned as enc4
from small_int4_rle1 import bit_encode_small_unsigned as encrle1
from small_int1 import bit_encode_small_unsigned as enc1

# Keep encoder list in required order
ENCODERS = [
    ("8bit", enc8),
    ("4bit", enc4),
    ("4bit_rle", encrle1),
    ("2bit", enc1),
]

def hex_dump(b: bytes) -> str:
    return b.hex(" ")

def encode_all(arr: list[int]):
    out = []
    for name, fn in ENCODERS:
        data = fn(arr)
        out.append((name, len(data), hex_dump(data)))
    return out

def print_header(title: str):
    print(f"\n=== {title} ===")
    # Dynamic column widths
    encoder_headers = " | ".join(f"   {name:<20} (len: hex)" for name, _ in ENCODERS)
    print(f"{'Array':<40} | {encoder_headers}")
    print("-" * (40 + 3 + len(encoder_headers)))

def print_row(arr: list[int]):
    encs = encode_all(arr)
    # Shorten very long array repr
    arr_repr = str(arr)
    if len(arr_repr) > 38:
        arr_repr = arr_repr[:35] + "..."
    row = f"{arr_repr:<40} | "
    pieces = []
    for name, length, hx in encs:
        pieces.append(f"{length:>3}: {hx}")
    print(row + " | ".join(f"{p:<34}" for p in pieces))

if __name__ == "__main__":
    # 1. Single numbers 0..150
    print_header("Single numbers 0..150")
    for n in range(0, 151):
        print_row([n])

    # 2. Array of 100 numbers with step 50
    print_header("Array: 100 numbers with step 50")
    step_array = [i * 50 for i in range(100)]
    print_row(step_array)

    # 3. Arrays of small numbers up to 10 items (use 0..k-1)
    print_header("Arrays of small numbers (length 1..10)")
    for k in range(1, 11):
        print_row(list(range(k)))

    # 4. Arrays of mixed numbers (small + big) up to 10 items.
    # Define some boundary / larger values that exercise different length tiers.
    BIG_VALUES = [
        293,            # near small_int1 Form4 upper
        4389,           # near Form5 upper
        69925,          # near Form6 upper
        594213,         # near Form7 upper
        594214,         # first Form8/raw value in small_int1
        528967,         # near small_int4_rle1 k=4 upper
        528968,         # small_int4_rle1 raw boundary
        (1 << 32) - 1,  # 32-bit max
        (1 << 40) + 12345,
        (1 << 56) + 7,
    ]
    print_header("Mixed number arrays (length 2..10)")
    # Build arrays by interleaving small and big numbers
    for k in range(2, 11):
        arr = []
        bi = 0
        si = 0
        while len(arr) < k:
            if len(arr) % 2 == 0:
                arr.append(si)
                si += 1
            else:
                arr.append(BIG_VALUES[bi % len(BIG_VALUES)])
                bi += 1
        print_row(arr)

    # 5. Pattern arrays: [0,0,big,0,big,medium,medium]
    print_header("Pattern arrays [0,0,big,0,big,medium,medium]")
    PATTERNS = [
        ( (1<<32) + 123, 50000 ),
        ( (1<<40) + 999, 528968 ),
        ( (1<<56) + 777, 69925 ),
    ]
    for big, med in PATTERNS:
        arr = [0,0,big,0,big,med,med]
        print_row(arr)
