#!/usr/bin/env python3
"""
Comparison test harness for small integer encodings.
"""
from __future__ import annotations

from small_int8 import bit_encode_small_unsigned as enc8
from small_int8_proto import bit_encode_small_unsigned as enc8proto
from small_int8_wt import bit_encode_small as enc8wt
from small_int4 import bit_encode_small_unsigned as enc4
from small_int4_rle1 import bit_encode_small_unsigned as enc4rle1
from small_int2 import bit_encode_small_unsigned as enc2
from small_int1_elias_g import bit_encode_small_unsigned as enc1eg
from small_int1_elias_d import bit_encode_small_unsigned as enc1ed
from small_int1_elias_d2 import bit_encode_small_unsigned as enc1ed2
from small_int1_elias_o import bit_encode_small_unsigned as enc1eo

# Keep encoder list in required order
ENCODERS = [
    ("8wt", enc8wt),
    ("8proto", enc8proto),
    ("8bit", enc8),
    ("4rle", enc4rle1),
    ("4bit", enc4),
    ("2bit", enc2),
    ("1eliasG", enc1eg),
    ("1eliasD", enc1ed),
    ("1eliasD2", enc1ed2),
    ("1eliasO", enc1eo),
]

def truncate(s: str, max_len: int) -> str:
    if len(s) <= max_len:
        return s
    if max_len < 4:
        return s[:max_len]
    return s[: max_len - 3] + "..."

def hex_dump(b: bytes) -> str:
    return b.hex(" ")

def encode_all(arr: list[int]):
    out = []
    for name, fn in ENCODERS:
        data = fn(arr)
        out.append((name, len(data), hex_dump(data)))
    return out

def print_header(title: str):
    # print(f"\n=== {title} ===")
    # encoder_headers = " | ".join(f"   {name:<20} (len: hex)" for name, _ in ENCODERS)
    # print(f"{'Array':<40} | {encoder_headers}")
    # print("-" * (40 + 3 + len(encoder_headers)))
    encoder_headers = " | ".join(f" {name:<9}" for name, _ in ENCODERS)
    title = f"=== {title} ==="
    print(f"\n{title:<80} | {encoder_headers}")
    print("-" * (80 + 3 + len(encoder_headers)))

def print_row(arr: list[int], full: bool = True):
    # encs = encode_all(arr)
    # row = str(arr)
    # if full and len(row) > 38:
    #     print(arr)
    #     row = ""
    # else:
    #     row = truncate(row, 38)
    # row = f"{row:<40} | "
    # pieces = []
    # for name, length, hx in encs:
    #     pieces.append(f"{length:>3}: {truncate(hx, 29)}")
    # print(row + " | ".join(f"{p:<34}" for p in pieces))
    encs = encode_all(arr)
    row = str(arr)
    if full and len(row) > 78:
        print(arr)
        row = ""
    else:
        row = truncate(row, 78)
    row = f"{row:<80} : "
    pieces = []
    for name, length, hx in encs:
        pieces.append(f"{length:>5}")
    print(row + " : ".join(f"{p:<10}" for p in pieces))

if __name__ == "__main__":
    import random
    random.seed(876543)

    # Sort arrays by expected comptessed size.
    def sort_arrays(arr: list[list[int]]) -> list[list[int]]:
        return sorted(arr, key=lambda x: (len(x), sum([n.bit_length() for n in x]), sum(x), x))

    print_header("Single numbers")
    for n in range(0, 151):
        print_row([n])

    print_header("Single numbers exponential")
    for n in range(0, 65):
        print_row([(1 << n)-1])
    # print_row([(1 << 64) - 1])

    print_header("4 numbers exponential")
    for n in range(0, 65):
        print_row([(1 << n)-1]*4, full=False)
    # print_row([(1 << 64) - 1]*4, full=False)

    print_header("Array: rather small random numbers")
    for row in sort_arrays([
            [random.randint(0, 1 << random.randint(0, 1 << random.randint(0, 5))) for _ in range(10)]
            for _ in range(20)]):
        print_row(row, full=True)

    print_header("Array: rather bigger random numbers")
    for row in sort_arrays([
            [random.randint(0, 1 << random.randint(0, 32)) for _ in range(10)]
            for _ in range(20)]):
        print_row(row, full=True)

    print_header("Arrays of small numbers")
    for k in range(1, 21):
        print_row(list(range(k)))

    print_header("Arrays of mixed numbers")
    for k in range(1, 16):
        row = [*sum(zip(
                list(range(k)),
                [((1 << 19)-1) * (n+1) for n in range(k)]), ())]
        print_row(row, full=True)

    print_header("Mixed random number arrays")
    for row in sort_arrays([
            [*sum(zip(
                [int(random.paretovariate(2)) for _ in range(k)],
                [random.randint(0, random.getrandbits(random.randint(0, 32))) for _ in range(k)]), ())]
            for k in range(1, 11)] + [
            [*sum(zip(
                [int(random.paretovariate(2)) for _ in range(k)],
                [random.getrandbits(random.randint(0, 32)) for _ in range(k)]), ())]
            for k in range(1, 11)]):
        print_row(row, full=True)

    print_header("Pattern random arrays0 [0,0,big,small,big,mediumsmall,medium]")
    for row in sort_arrays([
            [0,
               0,
               abs(int(random.gauss(mu=100000, sigma=100000))),
               random.randint(0, 8),
               abs(int(random.gauss(mu=100000, sigma=100000))),
               int(random.expovariate(0.05)),
               int(4096 * random.paretovariate(2)),
               ]
            for _ in range(30)]):
        print_row(row, full=True)

    print_header("Pattern random arrays1 [1,1,big,small,big,mediumsmall,medium]")
    for row in sort_arrays([
            [1,
               1,
               abs(int(random.gauss(mu=100000, sigma=100000))),
               random.randint(0, 8),
               abs(int(random.gauss(mu=100000, sigma=100000))),
               int(random.expovariate(0.05)),
               int(4096 * random.paretovariate(2)),
               ]
            for _ in range(30)]):
        print_row(row, full=True)
