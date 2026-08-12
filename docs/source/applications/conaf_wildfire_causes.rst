CONAF fire cause statistics (Chile)
===================================

Counts CONAF's fire reports by *causa general* and by season, with each cause's share of
its season's fires and hectares, and a summary block over every season. Writes CSV or a
Word document.

Usage
-----

.. code-block:: console

   $ python3 -m src.apps.statistics.wildfires.chile_conaf.wildfire_causes --csv causes.csv

   $ python3 -m src.apps.statistics.wildfires.chile_conaf.wildfire_causes \
         -y 2016 --docx causes-2016.docx

   # one cause across every season
   $ python3 -m src.apps.statistics.wildfires.chile_conaf.wildfire_causes \
         --cause "Incendios intencionales" --csv intencionales.csv

   # join the renamed categories across the 2023-2024 break, deliberately
   $ python3 -m src.apps.statistics.wildfires.chile_conaf.wildfire_causes \
         --bridge-schemes --csv causes-bridged.csv

Run :doc:`conaf_import_wildfires` first. One of ``--csv`` or ``--docx`` is required.

The break at 2023-2024
----------------------

.. danger::

   **CONAF renumbered its cause taxonomy in 2023-2024 and reused the numbers.** ``4.1``
   is *incendios de causa desconocida* before the break and *faenas forestales* after it.

   This report therefore groups on
   :attr:`~src.providers.chile_conaf.fire_cause.ConafFireCause.cause_normalised` — the
   canonical name — and **never** on the code. A series grouped on the code merges every
   fire whose cause was unknown with every fire started by forestry work, and the numbers
   look perfectly plausible.

Ten categories were also *renamed*, and the renaming is not a pure rename: *Accidentes
eléctricos* (any electrical accident) becomes *Líneas eléctricas* (the power line only),
which is narrower; *Quema de desechos* becomes *Otras quemas*, which is broader. They are
kept apart, so a fifteen-season series of any of the ten stops or starts at 2023-2024.

The report **says where it breaks**, in its own output: a reader looking at a column of
counts that goes to zero needs to know whether the fires stopped or the category did. This
is the same shape as the hole :doc:`conafor_wildfire_causes` documents for Mexico's
*Intencional* / *Actividades ilícitas*.

``--bridge-schemes`` joins each pre-2023 cause to the post-2023 one that took its slot,
under the **post-2023 name** — the one CONAF is publishing now, so that a series ending in
the current vocabulary is easier to extend than one ending in a retired one. It is not the
default, because it asserts a continuity CONAF did not publish, and the break is reported
either way.

The three synthetic rows
------------------------

Fires with no canonical cause are rows in this report rather than fires that vanish from
it — dropping them would make every percentage wrong — and they are **three** rows, not
one, because they mean three different things:

``(specific cause only)``
    The fire publishes a *causa específica* and no *causa general*. 6,221 fires, almost
    all in the seasons whose ``CAUSA_GENE`` column is empty. A fire whose specific cause
    is *1.7.1. Uso de fuego por transeúntes* **is** classified — just not at the level
    this report groups by — and calling that "no cause published" would be false.

``(unreconciled cause)``
    The published *causa general* has no canonical form: ``'TRANSEONTES'``,
    ``'CALDA DE RAYO'``, spellings that lost a letter to a bad decode and cannot be
    guessed back by rule. The row is how a reader finds out the reconciliation tables need
    extending.

``(no cause published)``
    Neither half. 1,012 fires.

All three are printed after the real causes, which are ordered by how many fires they
hold. Sorting them among the causes by count would suggest they were causes.

API reference
-------------

.. automodule:: src.apps.statistics.wildfires.chile_conaf.wildfire_causes
   :members:
   :show-inheritance:
