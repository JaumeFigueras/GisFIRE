from math import exp
from math import pow

def Alexander(ros, Ue):
    LB = 0.936 * exp(0.2566 * Ue) + 0.461 * exp(-0.1548 * Ue) - 0.397
    HB = (LB + pow(pow(LB, 2) - 1, 0.5)) / (LB - pow(pow(LB, 2) - 1, 0.5))
    a = 0.5 * (ros + ros / HB) / LB
    b = (ros + ros / HB) / 2
    c = b - ros / HB
    return (a, b, c)

def Catchpole(ros, Ue):
    Z = 1 + 0.25 * Ue
    e = pow((Z ** 2 - 1), 0.5) / Z
    Rh = ros
    Rb = Rh * (1 - e) / (1 + e)
    L = Rh + Rb
    W = L / Z
    f = L / 2
    h = W / 2
    g = Rh - f
    return (h, f, g)
