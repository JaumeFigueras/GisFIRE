NBAC provider package
=====================

Constants shared by the NBAC model and the import application: the provider identity, the
published CRS, the three ``FIRECAUS`` categories, the two-valued date precision and the
three date sources the import chooses between, the separator that joins the
administrations of a fire that crossed a boundary, and the burned area products a
perimeter can come from.

The module docstring is also where the dataset itself is written down — what a *composite*
is and why ``BASRC`` matters, why a fire is a ``GID`` and not a polygon, the two
independent date pairs and the fires that have neither, why ``Natural`` is not a lightning
category, why the CRS has to be asserted rather than read, and why 1972 is missing.

.. automodule:: src.providers.canada_nbac
   :members:
   :show-inheritance:
