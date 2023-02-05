set terminal postscript "Times, 20" eps color dashed size 3.5,2
set loadpath '~/gnuplot-palettes'
load "blues.pal"
set output "unstructured.ps"

set xlabel "Density %" font "Times, 24"

unset key
set datafile missing '-'
set xtics border in scale 0,0 nomirror norotate left autojustify font "Times, 18"
set ytics border in scale 1,0.5 nomirror norotate left autojustify
set key top font "Helvetica, 15"
set key autotitle columnhead
set format x '2^{%L}'  #<- enhanced text.

set xrange 
set yrange [0.125: 8]
set xrange [0.0047: 0.19]
set logscale y 2
set logscale x 2
set border 15
set origin 0, 0
set size 1, 1

set ylabel "Normalized Speedup(x)" font "Times, 24"
set xtics border in scale 0,0 nomirror norotate left autojustify

to_str_1(x) = sprintf("%.1f%", x)
to_str_2(x) = sprintf("%.1fms", x)
ypos(x) = (x < 30) ? x - 3: x + 3

NO_ANIMATION = 1
plot 'unstructured.dat' using ($1):($3) w points pt 7 ps 1 lc "#2166AC", \
    '' u ($1):($2) with points pt 7 ps 1 lc "#92C5DE", \
    '' u ($1):($4) with points pt 7 ps 1 lc "#D6604D", \
    '' u ($1):($5) with lp pt 0 lw 2 lc "#000000"
