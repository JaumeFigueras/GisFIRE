Greek Fire Service wildfire
===========================

The fire record model for the Hellenic Fire Service's *Δασικές Πυρκαγιές* statistic.
See :doc:`../providers` for how provider models relate to the generic ones,
:doc:`../data_model/wildfire` for the columns it inherits, :doc:`greece_ffa_provider` for
the dataset, and :doc:`greece_ffa_ignition` for the point the recent years publish.

Three things about it are worth knowing before using it. There is **never a perimeter**,
as with :doc:`egif_wildfire`: this is an administrative statistic and publishes a burnt
area, split eight ways by land cover, in στρέμματα that the import converts to hectares.
**Nothing identifies a fire** — no column is unique, and 201,948 of the 260,194 records
carry no identifier of any kind — so the unit an import replaces is a *year*. And the
2025 file publishes ``Κατηγορία Συμβάντος``, 1,255 rows of which are **false alarms**
that any count of fires has to exclude, with a ``NULL``-safe filter.

.. automodule:: src.providers.greece_ffa.wildfire
   :members:
   :show-inheritance:
