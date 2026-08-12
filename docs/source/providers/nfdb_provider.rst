NFDB provider package
=====================

Constants shared by the NFDB models and the import application: the provider identity —
the same agency name as :doc:`nbac_provider`, a different product — the published CRS, the
three ``CAUSE`` letters and the two ``CAUSE2`` refinements, the year the import starts
from, the ``-999`` year sentinel, and the bounds a published coordinate has to fall in.

Two functions live here because both the models and any reader of the shapefile need them:
:func:`~src.providers.canada_nfdb.is_located`, which decides whether a published
coordinate is a Canadian location, and :func:`~src.providers.canada_nfdb.published_year`,
which reads the sentinel as nothing.

The module docstring is also where the dataset itself is written down — the thirteen
agencies and how unevenly they file, the identifiers that do not identify, the three kinds
of dirt and where each is, and why the import starts in 1973.

.. automodule:: src.providers.canada_nfdb
   :members:
   :show-inheritance:
