USWFS (Alaska) lightning
========================

The stroke model for the Alaska Lightning Detection Network, released by the U.S.
Wildland Fire Service. See :doc:`../providers` for how provider models relate to the
generic ones, :doc:`../data_model/lightning` for the columns it inherits, and
:doc:`alaska_uswfs_provider` for the release.

Four things about it are worth knowing before using it:

- **The point is stored once.** The release is in WGS 84, so the published point *is*
  the parent's EPSG:4326 ``geometry``, and there is no second point as MeteoCat and FMI
  have. The EPSG:3338 point is never stored, only indexed. Because the point lives on
  ``lightning``, its index does too: a partial expression index over this provider's
  strokes only.
- **The flashes are GisFIRE's, not the network's.** The release has no flash id, so the
  import groups the strokes (see :doc:`../algorithms/flash_grouping_nldn`).
  ``flash_id`` is the identifier of the flash's first stroke. ``multiplicity`` and
  ``stroke_index`` mean what they mean for the other two providers, so ``stroke_index =
  1`` selects one stroke per flash, its first.
- **The ellipse is two semi-axes, in metres** (``ellipse_semi_major_axis``,
  ``ellipse_semi_minor_axis``), converted from the whole kilometres published. A
  semi-major axis published as 0 (599 strokes) is ``NULL``: not known.
- **A cloud stroke has no peak current.** The release gives it an amplitude of 0, which
  is how it marks a cloud stroke, not a measurement, so ``peak_current`` is ``NULL``.

.. automodule:: src.providers.alaska_uswfs.lightning
   :members:
   :show-inheritance:
