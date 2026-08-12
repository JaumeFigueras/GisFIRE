NFDB wildfire
=============

The fire report model for the *Canadian National Fire Database — Agency Fire Data*. See
:doc:`../providers` for how provider models relate to the generic ones,
:doc:`../data_model/wildfire` for the columns it inherits, :doc:`nfdb_provider` for the
dataset, and :doc:`nfdb_ignition` for the point every report is filed at.

Three things about it are worth knowing before using it. There is **never a perimeter**,
as with :doc:`egif_wildfire` and :doc:`greece_ffa_wildfire`: the agencies publish a
location and a size, and the shapes come from :doc:`nbac_wildfire`, which is a provider of
its own. **Nothing identifies a fire** — ``NFDBFIREID`` has 1,684 duplicates over 448,602
rows — so neither this table nor the ignition constrains an identifier. And
``src_agency`` is the column to read before any other: coverage, accuracy, vocabulary and
start year all vary by it, so a figure computed over the whole archive without regard to it
is a figure about reporting practice as much as about fire.

.. automodule:: src.providers.canada_nfdb.wildfire
   :members:
   :show-inheritance:
