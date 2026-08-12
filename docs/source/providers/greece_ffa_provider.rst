Greek Fire Service provider package
===================================

Constants shared by the Greek Fire Service models and the import application: the
provider identity, the single time zone the whole country is in, the CRS the coordinates
are published in, the στρέμμα-to-hectare factor, the first years that publish a
coordinate and an identifier, and the 2025 incident categories — false alarms included.

Two functions live here because both the models and any reader of the workbooks need
them: :func:`~src.providers.greece_ffa.normalise_column`, which folds the published
headers onto one name each — the line-break hyphens, the inconsistent accents and the
Latin ``A`` the 2025 file writes ``Α/Α ENGAGE`` with — and
:func:`~src.providers.greece_ffa.is_located`, which decides whether a published
``X-ENGAGE``/``Y-ENGAGE`` pair is a location or the ``0``/``0`` the service writes when
it did not record one.

The module docstring is also where the dataset itself is written down — the fifteen
workbooks, the two-row header, the six column arrangements, the twenty years with no
coordinate at all, the absence of any cause, and what the 2025 file is.

.. automodule:: src.providers.greece_ffa
   :members:
   :show-inheritance:
