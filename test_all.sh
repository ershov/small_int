#!/bin/bash
for f in small_*.py; do ./$f > ${f%.py}.txt; done

if which gnuplot >/dev/null 2>&1 && which perl >/dev/null 2>&1; then
    extract_table() {
        perl -nE '/^$/ and $p=0; print(s/^[^:]++://r =~ s/://gr) if $p>1; /'"$1"'/ ? $p++ : $p && /----------/ ? $p++ : 0' small_int_compare.txt
    }
    plot_graph() {
        local output=$1
        local input=$2
        local bytes=$3
        gnuplot -e '
set terminal pngcairo size 800,600 enhanced font "Verdana,10";
set output "'"$output"'";
set xtics 0,8;
set ytics 0,'"$bytes"';
set grid;
plot [0:64] [0:] floor(0.9999+x/8)*'"$bytes"' title "bytes", "'"$input"'" using 0:1 with lines title "8bit", "" using 0:2 with lines title "4bit", "" using 0:3 with lines title "4rle", "" using 0:4 with lines title "2bit";
'
#         gnuplot -e '
# set terminal pngcairo size 1600,1200 enhanced font "Verdana,10";
# set output "'"$output"'";
# set style data histograms;
# set style fill solid border;
# set xtics 0,8;
# set ytics 0,'"$bytes"';
# set grid;
# plot [0:64] [0:] "'"$input"'" using 1 title "8bit", "" using 2 title "4bit", "" using 3 title "4rle", "" using 4 title "2bit", (x/8+1)*'"$bytes"' title "bytes";
# '
    }
    extract_table "Single numbers exponential" > encoding_sz1.txt
    extract_table "4 numbers exponential" > encoding_sz4.txt
    plot_graph encoding_sz1.png encoding_sz1.txt 1
    plot_graph encoding_sz4.png encoding_sz4.txt 4
fi
