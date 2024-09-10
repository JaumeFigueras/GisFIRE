# output
set terminal png size 1872, 1080 font "Arial,30"
set output 'probability_error_detection.png'

# margins
set bmargin at screen 0.15
set tmargin at screen 0.95
set lmargin at screen 0.10
set rmargin at screen 0.95

# ranges
set xrange [0:1]
set yrange [0:150]

# styles
set style line 11 lc rgb 'blue' lw 1 lt 0
set style line 12 lc rgb 'red' lw 1 lt 0
set style line 13 lc rgb 'green' lw 1 lt 0
set style line 20 lc rgb 'black' lw 1 lt 0
set style line 30 lc rgb 'black' lw 3
set style line 31 lc rgb 'red' lw 3
set style line 32 lc rgb 'blue' lw 3
set style line 33 lc rgb 'green' lw 3
set style line 34 lc rgb 'yellow' lw 3

# tics
set xtics 0, .1, 1
set ytics 0, 25, 150
set format x "%1.2f"
set format y "%3.0f"

# labels
set xlabel "Probabilitat llindar"
set ylabel "Ignicions descartades"

# begin
set multiplot
plot "probability_error_detection_20000.dat" with lines ls 30 notitle
plot "probability_error_detection_15000.dat" with lines ls 31 notitle

# key
set key top horiz
plot -10000 ls 30 title "20 Km", -10000 ls 31 title "15 Km"

unset multiplot


