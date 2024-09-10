


# output
set terminal png size 1872, 1080 font "Arial,30"
set output 'sensivity.png'

# margins
set bmargin at screen 0.15
set tmargin at screen 0.95
set lmargin at screen 0.10
set rmargin at screen 0.95

# ranges
set xrange [24:240]
set yrange [0:600]

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
set style line 35 lc rgb 'orange' lw 3
set style line 36 lc rgb 'purple' lw 3
set style line 37 lc rgb 'gray' lw 3

# tics
set xtics 24, 24, 240
set ytics 0, 50, 600

# labels
set xlabel "Hores de latència"
set ylabel "Nombre de llamps assignats"

# begin
set multiplot
plot "sensivity_2000.dat" with lines ls 30 notitle
plot "sensivity_3000.dat" with lines ls 31 notitle
plot "sensivity_4000.dat" with lines ls 32 notitle
plot "sensivity_5000.dat" with lines ls 33 notitle
plot "sensivity_7500.dat" with lines ls 34 notitle
plot "sensivity_10000.dat" with lines ls 35 notitle
plot "sensivity_15000.dat" with lines ls 36 notitle
plot "sensivity_20000.dat" with lines ls 37 notitle

# key
set key inside bottom horiz
plot -10000 ls 30 title "r=2000m", -10000 ls 31 title "r=3000m", -10000 ls 32 title "r=4000m", -10000 ls 33 title "r=5000m", -10000 ls 34 title "r=7500m", \
  -10000 ls 35 title "r=10000m", -10000 ls 36 title "r=15000m", -10000 ls 37 title "r=20000m"

unset multiplot


