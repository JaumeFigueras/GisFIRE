INAB provider package
=====================

Constants and readers shared by the INAB models and any reader of the published layer: the
provider identity, the CRS, the single time zone the whole country is in, the definition of
Guatemala's national grid, the four published vocabularies, and the department codes that
make a municipality code checkable.

Three functions live here because both the models and any reader of the download need them:

:func:`~src.providers.guatemala_inab.is_false_alarm`
    Whether a report says there was no fire. 140 of the 4,615 do, and every count has to
    exclude them. Deliberately answers *only* that question — ``no_verificado`` is not a
    false alarm, it is 90 records nobody checked.

:func:`~src.providers.guatemala_inab.parse_municipality`
    Splits ``rio_hondo_1903`` into its name and the INE code 1903, validating the code's
    department against the department column — which is the only way to catch the four
    truncated codes the publication contains.

:func:`~src.providers.guatemala_inab.is_in_guatemala`
    Whether a published coordinate is in the country. Three are not, and the function
    exists to *report* them rather than to repair them.

:func:`~src.providers.guatemala_inab.blank_to_none`
    Turns an unfilled text field into ``None`` whichever way it is unfilled. The source
    marks *not filled* as ``null`` **and** as ``""``, in the same column — ``nombre_ap_1``
    is ``null`` on 80 records and ``""`` on 3,080 — so every text attribute has to go
    through it or a third of the dataset claims to be inside a protected area named ``""``.

.. note::

   :data:`~src.providers.guatemala_inab.GTM_PROJ` is the one constant here that had to be
   discovered rather than looked up. **Guatemala Transverse Mercator has no EPSG code** —
   the registry's Guatemalan projected systems are the Ocotepeque 1935 Lambert zones
   (EPSG:5459, EPSG:5559), which it is not.

   It was verified against the data: reprojecting the published EPSG:4326 point of the 309
   records that carry both a ``GTM`` label and a plausible pair of metres reproduces their
   typed coordinates, **exactly to the metre on the best of them**. A wrong projection
   would be out by hundreds of kilometres.

.. automodule:: src.providers.guatemala_inab
   :members:
   :show-inheritance:
