#!/bin/bash

# Run all tests and save outputs

cd `dirname -- ${BASH_SOURCE[0]}` || exit $?

for f in small_*.py; do ./$f > output/${f%.py}.txt; done || exit $?

# Plot graphs if gnuplot and perl are available

{ which gnuplot >/dev/null 2>&1 && which perl >/dev/null 2>&1; } || exit 0

set -ueo pipefail

cd output

extract_table() {
    perl -nE '/^$/ and $p=0; print(s/^[^:]++|://gr) if $p>1; /'"$1"'/ ? $p++ : $p && /----------/ && $p++' small_int_compare.txt
}

extract_columns() {
    perl -nE '/\|/ and print(s/^[^|]++|\|//gr),exit' small_int_compare.txt
}

max() {
    perl -nE 'for (split) { $_ > $x and $x=$_ } END { say 0+$x }' "$@"
}

count_items() { echo $#; }

COLUMNS=$(extract_columns)
N_COLS=$(count_items $COLUMNS)

PALETTE="$(perl -E '
sub gamma { $_[0] ** (1/1.6) }
sub adjust { return (gamma($_[0]*0.75), gamma($_[1]*0.5), gamma($_[2])) }
for $c (
  # Vertexes
  # [0, 0, 0],   # black
  # [1, 1, 1],   # white
  [1, 0, 0],  # red
  [0, 1, 0],  # green
  [0, 0, 1],  # blue
  [1, 1, 0],  # yellow
  [1, 0, 1],  # magenta
  [0, 1, 1],  # cyan
  # Edges
  [1/2,   0,   0],
  [  0, 1/2,   0],
  [  0,   0, 1/2],
  [1/2, 1/1,   0],
  [1/1, 1/2,   0],
  [  0, 1/2, 1/1],
  [  0, 1/1, 1/2],
  [1/2,   0, 1/1],
  [1/1,   0, 1/2],
  [1/1, 1/1, 1/2],
  [1/1, 1/2, 1/1],
  [1/2, 1/1, 1/1],
  # Faces
  [1/2, 1/2,   0],
  [1/2,   0, 1/2],
  [  0, 1/2, 1/2],
  [  1, 1/2, 1/2],
  [1/2,   1, 1/2],
  [1/2, 1/2,   1],
  # Middle
  [1/2, 1/2, 1/2],
) {
  printf qq{set style line %d lc rgb "#%02X%02X%02X" lw 2.5;\n},
    ++$n,
    map { $_ = int(256*$_); $_ <= 255 ? $_ : 255 } adjust @$c;
}
')"

plot_graph() {
    local name=$1
    local bytes=$2
    local title="$3"

    if [[ "$bytes" -gt 0 ]]; then
        local PLOT_BYTES=1
        local YTICS="$bytes"
        local XAXIS="(\$0 / 8.0 * $bytes):"
    else
        local PLOT_BYTES=""
        local YTICS=1
        local XAXIS=""
        local bytes=1
    fi
    if [[ -n "$title" ]]; then
        title="set title \"$title\" font \",16\" offset 0,-4;"
    else
        title=""
    fi

    local RANGE=$(max "$name.txt")
    [[ "$RANGE" -gt 40 ]] && RANGE=40

    local PLOTS=""
    local N=1
    for i in $COLUMNS; do
        PLOTS="$PLOTS'$name.txt' using $XAXIS(\$$N-(($N.0-($N_COLS.0+1.0)/2.0)*0.03)*$RANGE.0/10.0) with lines ls $N title '$i', "
        N=$((N+1))
    done

    if [[ -n "$PLOT_BYTES" ]]; then
        PLOTS="$PLOTS"'floor(0.9999+x/'"$bytes"')*'"$bytes"' ls 99 title "minimal whole bytes"'
    else
        PLOTS="${PLOTS%, }"  # remove trailing comma
    fi

    gnuplot -e "$title"'
set xtics 0,1;
set noxlabel;
set ytics 0,'"$YTICS"';
set grid;
set style line 99 lc rgb "#000000" lw 1;
'"$PALETTE"'
set terminal pngcairo size 1200,800 noenhanced font "Verdana,10";
set output "'"$name"'.png";
plot [0:] [0:] '"$PLOTS"';
set terminal svg size 1200,800 noenhanced font "Verdana,10";
set output "'"$name"'.svg";
replot;
'
}

extract_table_and_plot() {
    local bytes=$1
    local name=$2
    local title=$3

    extract_table "$title" > "$name.txt"
    plot_graph "$name" "$bytes" "$title"
}

extract_table_and_plot 1 compare_1 "Single numbers exponential"
extract_table_and_plot 4 compare_4 "4 numbers exponential"
extract_table_and_plot 0 compare_a_pattern "Pattern arrays"
extract_table_and_plot 0 compare_a_mix "Mixed number arrays"
extract_table_and_plot 0 compare_a_small "Array: rather small random numbers"
extract_table_and_plot 0 compare_a_bigger "Array: rather bigger random numbers"
