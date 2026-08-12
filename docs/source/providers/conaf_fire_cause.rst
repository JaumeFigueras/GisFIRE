CONAF fire cause
================

One entry of CONAF's fire cause classification (Chile): the published ``CAUSA_GENE`` and
``CAUSA_ESPE`` pair, the codes in front of them, the canonical Spanish and English, and —
unlike :doc:`conafor_fire_cause`, which needs no such column — **which of the two
numberings the codes belong to**.

.. danger::

   **Never group on the cause code alone.**

   CONAF renumbered the taxonomy in 2023-2024 and reused the numbers. ``4.1`` is
   *incendios de causa desconocida* before the break and *faenas forestales* after it, so
   a fifteen-season series grouped on the code silently merges every fire whose cause was
   unknown with every fire started by forestry work.

   Group on :attr:`~src.providers.chile_conaf.fire_cause.ConafFireCause.cause_normalised`.
   A query that really needs the code must pair it with
   :attr:`~src.providers.chile_conaf.fire_cause.ConafFireCause.scheme`.

Worse than a clean break: the 2023-2024 and 2024-2025 layers publish **both** numberings
in the same file. ``1.1`` and ``4.1`` there are one cause — *faenas forestales*, 83 fires
and 492 — and so are ``1.8`` and ``4.8``, ``1.9`` and ``4.9``, and every other pair. The
group number wobbles inside a single published file; only the name holds still, which is
why :data:`~src.providers.chile_conaf.fire_cause.CAUSE_NORMALISATIONS` is keyed on the
name.

Three things about the table are worth knowing before using it.

**Ten categories were renamed, and are kept apart.** *Accidentes eléctricos* (any
electrical accident) becomes *Líneas eléctricas* (the power line only); *Quema de
desechos* (burning rubbish) becomes *Otras quemas* (any other burning). They are not the
same category, so a series of any of the ten has a break at 2023-2024.
:data:`~src.providers.chile_conaf.fire_cause.SCHEME_SUCCESSORS` is the bridge for a
reader who wants to cross it deliberately, and
:doc:`../applications/conaf_wildfire_causes` offers it behind an explicit option and
reports the break either way.

**2016-2017 publishes the code and no name at all** — ``'01.07'``, ``'04.01'`` — on all
5,234 of its fires. They are resolved through
:data:`~src.providers.chile_conaf.fire_cause.PRE_2023_CODE_NAMES`, which is checkable:
the layer's own ``CAUSA_ESPE`` still carries the old-scheme ``1.7.x`` codes and the two
agree feature for feature. Resolving them through the *new* numbering instead would file
220 unknown-cause fires as forestry work.

**The specific cause is stored but not translated.** CONAFOR's ``CAUSAESP`` is fifty-four
short terms; CONAF's is five hundred descriptive sentences written to be read rather than
joined on. The code in front of them is parsed out, which is the part a query can use.

Both published products share this table. The perimeter archive
(:doc:`conaf_magnitud_wildfire`) publishes a single ``CAUSA`` column that is sometimes a
*causa específica* and sometimes a *causa general*, and
:func:`~src.providers.chile_conaf.fire_cause.resolve_published_cause` decides which by
the shape of its code — falling back, for the 51 features that publish no code, to
*general if the reconciliation table knows it, specific otherwise*.

.. automodule:: src.providers.chile_conaf.fire_cause
   :members:
   :show-inheritance:
