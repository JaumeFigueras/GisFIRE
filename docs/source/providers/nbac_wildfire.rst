NBAC wildfire
=============

The burnt area model for the Canadian *National Burned Area Composite*. See
:doc:`../providers` for how provider models relate to the generic ones,
:doc:`../data_model/wildfire` for the columns it inherits, :doc:`nbac_provider` for the
dataset, and :doc:`nfdb_wildfire` for what ``nfdb_wildfire_id`` points at.

Three things about it are worth knowing before using it. **One row is one fire and
several polygons**: the published features are cut at provincial, territorial and national
park boundaries, so the import dissolves them and carries ``part_count``,
``crosses_admin`` and a ``"; "``-joined ``admin_name`` — which is therefore **not a key**
and must not be compared with ``=`` to a province code. **The start date is resolved from
one of three places** — the agency's date, the first satellite hotspot, or the bare year —
and ``date_source`` and ``date_time_precision`` say which and how much of it is real.
And **the perimeter is stored twice**, in EPSG:3978 as published and in EPSG:4326 for
every cross-provider query.

.. automodule:: src.providers.canada_nbac.wildfire
   :members:
   :show-inheritance:
