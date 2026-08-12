CONAF *incendios de magnitud* perimeter import (Chile)
======================================================

Imports CONAF's mapped perimeters of Chile's large fires — **13 archives, 781 published
features, 743 fires, 2013-2014 to 2024-2025** — into
:doc:`../providers/conaf_magnitud_wildfire`, with their classifications going into
:doc:`../providers/conaf_fire_cause`.

The second of CONAF's two products, and the one that carries the shapes.
:doc:`conaf_import_wildfires` brings in the reports; the two are joined afterwards by
:doc:`conaf_magnitud_bind_wildfires`.

Usage
-----

.. code-block:: console

   $ python3 -m src.apps.imports.wildfires.chile_conaf_magnitud.import_wildfires \
         -d perimetres/

   $ python3 -m src.apps.imports.wildfires.chile_conaf_magnitud.import_wildfires \
         -s perimetres/if_magnitud_2016_2017.rar

   $ python3 -m src.apps.imports.wildfires.chile_conaf_magnitud.import_wildfires \
         -d perimetres/ -y 2016 --dry-run

The two products are independent: this can be run before or after
:doc:`conaf_import_wildfires`, and a perimeter with no report to bind to is still stored.
Import the boundaries and the time zone areas first, for the reason
:doc:`conaf_import_wildfires` gives. Settings are read from the environment (``.env``, see
:doc:`../setup/configuration`).

The dissolve
------------

The one place this import invents structure the file does not have, and therefore the
part worth reading closely.

There is no ``GID``. A fire mapped in pieces is published as several features sharing
``TEMPORADA`` and ``NOM_INCEN``, unmistakably the same fire: same date, same comuna, tens
to a few thousand metres apart. So the import unions them, on the season, the folded name
**and the office's number**.

.. important::

   The number is in the key on measured grounds. ``120_LOS MAITENES`` of 27 November 2016
   and ``388_LOS MAITENES`` of 14 December are two different fires with one name;
   dissolving on the season and the name alone merged four such pairs and turned 743
   fires into 739.

The union is taken with ``ST_CollectionExtract(ST_MakeValid(ST_Force2D(...)), 3)`` —
``ST_Force2D`` because some archives publish 3D polygons, ``ST_MakeValid`` because some
rings self-intersect, and ``ST_CollectionExtract`` because making a bowtie valid can yield
a collection with a stray line in it.

Two areas, because ``SUPERFICIE`` is not what it looks like
-----------------------------------------------------------

It is the **feature's own polygon area** in hectares, not the burnt area the office
reported: the median ratio of computed to declared area is 1.000 in every one of the
thirteen archives. Which makes summing it over the parts wrong wherever the parts overlap
— ``37_TIL TIL`` is six features each declaring 327.50 ha of what is one 327.8 ha fire,
and ``QUEBRADILLA`` of 2015-2016 is the same polygon published twice.

So ``area_ha_mapped`` is computed from the union and ``area_ha_published`` keeps the sum
of the parts beside it. For 724 of the 743 fires they are the same number; for the other
19 the disagreement is the datum, and the run reports every fire whose two areas differ by
more than 5%.

The number prefix
-----------------

Six of the thirteen archives embed the office's running number in the name —
``'402 - SAN GUILLERMO'``, ``'668_CANIHUAL VII'``, ``'37 TIL TIL'`` — and two publish it
as a column instead. Splitting it off is what makes the binder work: ``'402 - SAN
GUILLERMO'`` here and ``'SAN GUILLERMO'`` in the report archive are one fire, and the
number is the strongest signal there is for finding it.

The single ``CAUSA`` column
---------------------------

The reports publish two cause columns and this archive publishes one, used for both:
``'2.1.11. Otros intencionales no clasificados'`` is a *causa específica* and
``'Incendio Intencional'`` is a *causa general*, in the same file. The code's shape
decides — three components is specific, two is general — which settles 730 of the 781.
The other 51 publish no code, and there the rule is *general if the reconciliation table
knows it, specific otherwise*; see
:func:`~src.providers.chile_conaf.fire_cause.resolve_published_cause`.

API reference
-------------

.. automodule:: src.apps.imports.wildfires.chile_conaf_magnitud.import_wildfires
   :members:
   :show-inheritance:
