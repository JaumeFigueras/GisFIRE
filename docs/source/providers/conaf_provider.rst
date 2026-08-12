CONAF provider package
======================

Constants and readers shared by the CONAF report models and the import application: the
provider identity, the **two** published CRSs, the UTM zones ``HUSO`` names, the fire
season and its window, the three date precisions, the two reporting systems, the
plausible extents of each grid, and the null tokens the archive scatters through every
text column.

.. important::

   This is **Chile's CONAF** — *Corporación Nacional Forestal* — and not Mexico's
   **CONAFOR** (:doc:`conafor_provider`). The two agencies' names differ by two letters
   and both are real, so every module in this package opens by saying which country it
   is. The table prefixes are ``conaf_`` and ``conafor_``.

The module docstring is also where the dataset itself is written down: the 23 published
report archives and the 95,868 fires in them, why the fire season runs 1 July to 30 June,
why half the archive has no date at all, why the published ``UTM_E``/``UTM_N``/``HUSO``
triple is provenance rather than a coordinate, why Easter Island needs a second grid, the
two cause taxonomies with their reused numbers, and the three records whose DBF has come
apart.

The functions here are the ones the import calls before anything reaches a model, and
they are tested directly rather than through it:

:func:`~src.providers.chile_conaf.season_start_year`
    ``"2010-2011"`` → ``2010``, and ``None`` for the seven cells that are not a season —
    including the published ``"2023-2025"``, which is a typing error rather than a
    two-year season.

:func:`~src.providers.chile_conaf.season_window`
    1 July to 1 July, exclusive at the end, so consecutive seasons abut exactly. Verified
    against every dated feature of every archive.

:func:`~src.providers.chile_conaf.parse_published_datetime`
    The four published formats, returning the instant **and how much of it is real**.

:func:`~src.providers.chile_conaf.published_utm`
    Reads ``'317709 E'``, ``'19K'`` and ``'12.0'``, and refuses the zeroed pair that
    2013-2014 writes on all 6,297 of its rows.

:func:`~src.providers.chile_conaf.normalise`
    The case, accent and whitespace fold — plus the soft hyphens that two seasons are
    littered with, which are invisible and would otherwise split every spelling they
    touch.

:func:`~src.providers.chile_conaf.admin_code`
    Zero-pads ``'5801'`` to ``'05801'`` and reads ``'6.00000000000'`` as ``'06'``.

:func:`~src.providers.chile_conaf.is_corrupt`
    The control-character test that quarantines the three unreadable records rather than
    letting their mojibake into the cause catalogue.

.. automodule:: src.providers.chile_conaf
   :members:
   :show-inheritance:
