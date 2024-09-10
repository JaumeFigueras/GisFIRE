# output
set terminal png size 1872, 1080 font "Arial,30"
set output 'number_of_lightnings.png'

# margins
set bmargin at screen 0.30
set tmargin at screen 0.95
set lmargin at screen 0.10
set rmargin at screen 0.90

# ranges
set xrange [-0.5:9.5]
set yrange [0:225]

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
# set xtics ("50-100" 0, "100-200" 1, "200-400" 3.5, "400-800" 4.5, "800-1.6K" 5.5, "1.6K-3.2K" 6.5, "3.2K-6.4K" 7.5, "6.4K-12.8K" 8.5, "12.8K-25.6K" 9.5, "25.6K-51.2K" 10.5)
set xtics border rotate by -45
set ytics 0, 25, 225


# labels
set xlabel "Nombre de llamps per episodi"
set ylabel "Nombre d'episodis"

# begin

plot "number_of_lightnings.dat" using 1:3:xtic(2) with boxes ls 30 notitle


