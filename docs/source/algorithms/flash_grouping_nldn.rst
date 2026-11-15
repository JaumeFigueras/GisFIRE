Flash grouping (NLDN, Cummins et al. 1998)
==========================================

.. contents::
   :local:
   :depth: 1

Groups lightning **strokes** into **flashes**, for a network that publishes strokes
only. A lightning-location network locates strokes, and most group them into flashes and
publish the grouping: MeteoCat and FMI do, and their imports store it as published. The
Alaska Lightning Detection Network does not. Its release has no flash identifier and no
multiplicity, and a flash-based algorithm such as Cellsearch would then count every
stroke as a flash, about 1.3 times too many. So the Alaska import groups the strokes
itself, with this rule.

It lives in :mod:`gisfire_algorithms.thunderstorm.flash_grouping` and is named
``NLDN_CUMMINS_1998`` there. It follows the rule of the U.S. National Lightning
Detection Network in K. L. Cummins, M. J. Murphy, E. A. Bardo, W. L. Hiscox, R. B. Pyle
and A. E. Pifer, *A combined TOA/MDF technology upgrade of the U.S. National Lightning
Detection Network*, J. Geophys. Res. **103** (D8) (1998) 9035–9044.

The rule
--------

The strokes are taken in time order. A stroke joins an open flash when it is, all three
at once:

1. within **1 s** of the flash's **first** stroke (``max_duration_s``);
2. within **0.5 s** of the flash's **previous** stroke (``max_interval_s``);
3. within **10 km** of the flash's **first** stroke (``max_distance_km``).

A stroke that fits no open flash starts a new one. A flash closes once a stroke comes
more than 1 s after its first stroke or 0.5 s after its last. The limits are the three
fields of :class:`~gisfire_algorithms.thunderstorm.flash_grouping.FlashGroupingParameters`,
and the provider package keeps its own copy of them
(:data:`~src.providers.alaska_uswfs.FLASH_MAX_DURATION_S` and the two others).

Choices the rule leaves open
----------------------------

The rule is stated in words; these are the readings the implementation makes, and the
tests pin each one down:

- **The limits are inclusive.** A stroke exactly 1 s after the first, 0.5 s after the
  previous or 10 km from the first joins. A time since the epoch held in a float carries
  a rounding error of about 10⁻⁷ s, so the time limits are compared within
  :data:`~gisfire_algorithms.thunderstorm.flash_grouping.TIME_TOLERANCE_S` (1 µs). That
  is far below the release's millisecond, so a gap published as exactly 500 ms counts as
  0.5 s.
- **Several open flashes:** the stroke joins the one whose first stroke is **nearest**,
  and at equal distance the earlier flash.
- **Kinds apart.** A stroke only joins a flash of its own kind, given as ``kind``. The
  Alaska import passes cloud-to-ground and cloud strokes as two kinds, as FMI groups
  them: July 2018 has 242,537 ground and 467,053 cloud flashes on FMI's own grouping,
  and none mixed.
- **The distance is the plane distance in the caller's CRS**, so it carries that CRS's
  scale error. For Alaska, NAD83 / Alaska Albers (EPSG:3338) is within 1.44 % for 99 %
  of the strokes.
- **Strokes of one instant** are taken in the order given. The Alaska import gives them
  in its content order, so the grouping does not depend on the file's order.

The input must be in time order, with no NaN or infinite value; anything else is refused.
The result is one flash number per stroke, counting from 0 in order of the flashes'
first strokes.

On the Alaska release
---------------------

Over the release of 2026-11-06, grouped by the import within each UTC year (no stroke
falls within a second of a New Year, so no flash is cut):

=======================  ============  ============
                         Ground        Cloud
=======================  ============  ============
Strokes                  2,081,826     144,335
Flashes                  1,621,243     131,274
Strokes per flash        1.28          1.10
Single-stroke flashes    82.4 %        91.4 %
Most strokes in a flash  16            7
=======================  ============  ============

- **By year,** ground strokes per flash run from 1.18 (2024) to 1.34 (2019).
- **Longest flash:** exactly 1.000 s, the first limit.
- **Against the analysis:** counted with spherical distances when the release was
  analysed, the flashes were 1,621,002 and 131,257. The import gives 241 and 17 more,
  for two reasons. It works on Alaska Albers metres, and a pair of strokes right at
  10 km can fall either side of the limit between the two distances. And it takes the
  strokes of one millisecond in its content order, where the analysis used another.

API reference
-------------

.. automodule:: gisfire_algorithms.thunderstorm.flash_grouping
   :members:
   :show-inheritance:
