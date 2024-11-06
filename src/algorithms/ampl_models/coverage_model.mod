reset;

set DK;  									# Disks
set PT;  									# Points
set COVERAGE within (DK cross PT);  		# Coverage matrix (set of points PT covered by disk DK)

var decision{DK} binary;  					# 1 if the disk j is chosen to cover the point set

# Objective function
minimize total_cliques: sum {cl in CL} decision[cl];

# All
subject to point_coverage {pt in PT}:
    sum{(dk,pt) in DK} decision[dk] >= 1;
    


