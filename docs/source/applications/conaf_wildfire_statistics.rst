CONAF burnt-area statistics (Chile)
===================================

Counts CONAF's seasonal fire reports and sums their published burnt area, by country and
by season, with a total row per country. Writes CSV or a Word document.

Usage
-----

.. code-block:: console

   $ python3 -m src.apps.statistics.wildfires.chile_conaf.wildfire_statistics \
         --csv chile.csv

   # one season, named by its first year
   $ python3 -m src.apps.statistics.wildfires.chile_conaf.wildfire_statistics \
         -y 2016 --docx chile-2016.docx

   # plantations only, and only the fires that published a real start date
   $ python3 -m src.apps.statistics.wildfires.chile_conaf.wildfire_statistics \
         --surface plantation --dated-only --csv plantations.csv

   # only what the forestry brigades reported, not CONAF itself
   $ python3 -m src.apps.statistics.wildfires.chile_conaf.wildfire_statistics \
         --reporter Empresa --csv empresa.csv

Run :doc:`conaf_import_wildfires` first. One of ``--csv`` or ``--docx`` is required.
Settings are read from the environment (``.env``, see :doc:`../setup/configuration`).

The ``Dated`` column
--------------------

.. warning::

   **Half this archive has no published start date.** Eight of the fifteen mainland
   seasons publish none at all, so 49,470 fires carry
   :data:`~src.providers.chile_conaf.PRECISION_SEASON` and start at 1 July midnight
   because that is where the import put them.

   That is why every row of this report carries ``Dated`` beside ``Fires``. Saying which
   half a figure is about is part of the output rather than a footnote, and any
   month-of-year, hour or duration statistic over this dataset is computable on the
   ``Dated`` half only.

``--dated-only`` narrows the whole report to that half. A season with no dated fire then
has no row at all, rather than a row of zeros that would read as *no fires*.

Four surfaces, not one
----------------------

CONAF reports burnt area by what burnt, and the three subtotals are not interchangeable:

``total``
    ``SUPERFICIE``, the whole fire. The default, and the only one that matches the figure
    CONAF itself publishes in its annual statistics.

``plantation``
    ``TOTAL_PLAN`` — pine, eucalyptus and other plantation. The question about the
    forestry industry.

``vegetation``
    ``TOTAL_VEG`` — native forest, scrub and grassland. The question about ecology.

``other``
    ``TOTAL_OTRA`` — agricultural land and debris.

The nine individual components are on the model and a reader who wants *eucalyptus alone*
can ask for it in SQL. Putting nine more choices on this command line would suggest they
are all equally meaningful questions of the archive, and they are not.

``--min-area`` applies to **the surface being measured**. Asking for plantations of 5
hectares or more and getting every fire whose *whole* burn reached 5 hectares would be a
different question with the same command line.

Which country a fire counts towards
-----------------------------------

``--country-source geometry`` (the default) asks the database which country actually
contains the fire's point, against the real boundary polygons. For a single-country
archive its job is not to choose between countries but to catch the fires that are in
**none**: a point mis-keyed into the Pacific keeps its Chilean ``admin_boundary_id`` and
is silently in the total under ``reported``.

``--country-source reported`` trusts what the import stored — a foreign key lookup instead
of a point-in-polygon test per fire, which for 95,865 fires is a difference worth having.

.. note::

   The containment test uses the **ignition's point**, because there is no perimeter:
   :attr:`~src.data_model.wildfire.Wildfire.perimeter` is ``NULL`` on every row of this
   archive. Every other perimeter-bearing provider's version of this report tests
   ``ST_PointOnSurface`` of the polygon; here the point *is* the published location.

API reference
-------------

.. automodule:: src.apps.statistics.wildfires.chile_conaf.wildfire_statistics
   :members:
   :show-inheritance:
