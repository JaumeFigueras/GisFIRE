#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""IGN — Instituto Geográfico Nacional (Spain).

Data model for the *Base de Datos de Divisiones Administrativas de España*
(BDDAE), the national administrative map, published by the IGN through the CNIG
download centre. GisFIRE imports its three polygon levels — the ``recintos``
layers — as :class:`~src.providers.ign.admin_boundary.IgnAdminBoundary` rows:

=====================  ======================  ===============================
Level                  ``NATLEVNAME``          Count (2026, territories out)
=====================  ======================  ===============================
*Comunidad autónoma*   ``Comunidad autónoma``  19
*Provincia*            ``Provincia``           52
*Municipio*            ``Municipio``           8 213
=====================  ======================  ===============================

The published layers come in INSPIRE form, which is why the fields are named
``NATCODE``, ``NAMEUNIT`` and ``CODNUT1``/``2``/``3`` rather than in Spanish. The
companion ``ll_*`` layers hold the boundary *lines* rather than the areas and are
not imported: an area is what a wildfire is attributed to.

``NATCODE`` is a padded hierarchy
---------------------------------

Every unit at every level has an 11-digit ``NATCODE``, zero-padded on the right::

    34170000000   La Rioja                (comunidad autónoma)
    34172600000   La Rioja                (provincia)
    34172626145   Sotés                   (municipio, INE code 26145)

which is ``34`` (Spain) + *comunidad* (2) + *provincia* (2) + the INE municipal
code (5). A child's code therefore begins with its parent's, and the tree is built
from the codes rather than from a spatial containment test — but the padding has
to be put back, so the parent of a *municipio* is
``left(natcode, 6) || '00000'`` and not simply a prefix. Checked over the whole
dataset: no unit at any level fails to find its parent that way.

.. note::

   The last five digits are the **INE** municipal code, a different numbering
   system that happens to be embedded in ``NATCODE``. It is what Spanish
   statistical sources join on, so it is stored in its own column
   (:attr:`~src.providers.ign.admin_boundary.IgnAdminBoundary.ine_code`) rather
   than left to be sliced out of the code.

NUTS nests inside the administrative hierarchy
----------------------------------------------

Unlike Portugal's, where the two hierarchies cross and only one could be the tree
(see :mod:`src.providers.caop`), Spain's agree:

* ``CODNUT2`` maps one-to-one onto the *comunidad autónoma*.
* **No NUTS 3 region spans more than one province.** It equals the province
  everywhere except three island provinces, where it splits further — Illes
  Balears into three, Las Palmas into three, Santa Cruz de Tenerife into four,
  one per island.

So NUTS 3 is a refinement of the administrative tree, not a rival to it, and the
codes are carried as plain columns with nothing to reconcile. They are the full
Eurostat codes (``ES230``), not the national short form the CAOP publishes.

One asymmetry to know about: the IGN fills ``CODNUT3`` on *municipios* only. It is
empty on every *provincia* and every *comunidad autónoma*, even though NUTS 3 is a
province-level concept.

Two datums, no shift
--------------------

The data is published twice, once per datum: the peninsula and the Balearics in
ETRS89 (EPSG:4258) and the Canaries in REGCAN95 (EPSG:4081). Both are
**geographic** CRSs on the GRS80 ellipsoid and both declare a null transformation
to WGS84, so reprojecting to EPSG:4326 does not move a coordinate. The import
still forces it, so nothing depends on the source never changing.

What is left out
----------------

The IGN maps seven areas as ``NATLEVNAME = 'Territorio'`` rather than
``'Municipio'`` — Gibraltar, the *plazas de soberanía* off the Moroccan coast and
the Franco-Spanish condominium of the Isla de los Faisanes — under a pseudo
*comunidad autónoma* and a pseudo *provincia* that exist only to hold them. They
are **excluded by default**: they are not Spanish administrative divisions in the
sense the rest of the dataset is, the IGN's own level name says as much, and
Gibraltar is a separate country in the OCHA boundaries GisFIRE already imports.
:data:`EXCLUDED_CODE_PREFIX` is the whole branch, and ``--include-territories``
brings it back.
"""

#: Identity of the :class:`~src.data_model.data_provider.DataProvider` row every
#: IGN boundary hangs off, kept beside the model for the same reason as OCHA's
#: (see :mod:`src.providers.ocha`). The product carries the **edition**, which is
#: what keeps successive publications of the same codes apart — Spanish
#: municipalities merge and split, so the codes are not stable for ever.
PROVIDER_NAME = "IGN"
PROVIDER_FULL_NAME = "Instituto Geográfico Nacional"
PROVIDER_PRODUCT_TEMPLATE = "Base de Datos de Divisiones Administrativas de España {edition}"
PROVIDER_URL = "https://centrodedescargas.cnig.es"

#: Edition imported when none is given.
#:
#: Unlike the CAOP, nothing in the published files names the edition — not the
#: file names, not the DBFs, not the ``Leeme`` document — so this cannot be
#: checked against the data and is simply what the operator says it is.
DEFAULT_EDITION = "2026"

#: The two datums the data is published in, one file set each. Both are
#: geographic and both transform to EPSG:4326 without moving a coordinate.
SOURCE_SRIDS = {
    "Península y Baleares": 4258,   # ETRS89
    "Canarias": 4081,               # REGCAN95
}

#: A *comunidad autónoma* (or an autonomous city, Ceuta and Melilla): the first
#: four digits of ``NATCODE``, administrative level 1.
KIND_COMUNIDAD_AUTONOMA = "comunidad_autonoma"

#: A *provincia*: the first six digits of ``NATCODE``, level 2.
KIND_PROVINCIA = "provincia"

#: A *municipio*: the whole ``NATCODE``, level 3. Includes the 81 *condominios*,
#: *comuneros*, *facerías* and *parzonerías* the IGN maps at this level — shared
#: land between municipalities, which the INE does not count as municipalities and
#: gives a pseudo-province code of ``53``. They are kept: they are real ground
#: that can burn, and dropping them would leave holes in the coverage.
KIND_MUNICIPIO = "municipio"

#: One of the seven areas the IGN maps but does not call a *municipio* — see the
#: module docstring. Only reachable with ``--include-territories``.
KIND_TERRITORIO = "territorio"

#: Every value :attr:`~src.providers.ign.admin_boundary.IgnAdminBoundary.kind`
#: may take.
KINDS = (KIND_COMUNIDAD_AUTONOMA, KIND_PROVINCIA, KIND_MUNICIPIO, KIND_TERRITORIO)

#: The three levels that make up the tree, from the largest division down. A
#: *territorio* is not one of them: it is published in the *municipios* layer and
#: stored at the same level, but it is a kind rather than a rung.
TREE_KINDS = (KIND_COMUNIDAD_AUTONOMA, KIND_PROVINCIA, KIND_MUNICIPIO)

#: The administrative level each kind is stored at. Level 0 is the country, which
#: the BDDAE does not publish — see :data:`COUNTRY_ISO_3`.
LEVELS = {
    KIND_COMUNIDAD_AUTONOMA: 1,
    KIND_PROVINCIA: 2,
    KIND_MUNICIPIO: 3,
    KIND_TERRITORIO: 3,
}

#: How many digits of ``NATCODE`` identify each kind. The rest is zero padding,
#: which has to be put back when looking a parent up.
CODE_LENGTHS = {KIND_COMUNIDAD_AUTONOMA: 4, KIND_PROVINCIA: 6, KIND_MUNICIPIO: 11}

#: Full width of a ``NATCODE``, at every level.
CODE_WIDTH = 11

#: The branch holding everything that is not a Spanish administrative division:
#: the pseudo *comunidad autónoma* ``34200000000``, the pseudo *provincia*
#: ``34205400000`` and the seven ``Territorio`` areas beneath them. Excluding this
#: prefix removes all nine and nothing else — verified against the published data,
#: where ``NATLEVNAME = 'Territorio'`` and this prefix select exactly the same
#: rows.
EXCLUDED_CODE_PREFIX = "3420"

#: The IGN's own level name for the excluded areas, kept so the importer can say
#: what it filtered in the source's terms.
EXCLUDED_NATLEVNAME = "Territorio"

#: ISO 3166-1 alpha-3 code of the country the *comunidades autónomas* are parented
#: to, used to find the OCHA boundary that becomes their parent.
COUNTRY_ISO_3 = "ESP"

#: Prefix every ``INSPIREID`` is built from. It is exactly this plus the
#: ``NATCODE`` in all 8 293 published rows, so the identifier carries nothing the
#: code does not and is not stored; this is here so it can be rebuilt when an
#: INSPIRE-shaped identifier is needed.
INSPIRE_ID_PREFIX = "ES.IGN.BDDAE."


def provider_product(edition: str) -> str:
    """Return the ``DataProvider.product`` naming one BDDAE edition.

    Parameters
    ----------
    edition : str
        The edition's label, e.g. ``"2026"``.

    Returns
    -------
    str
        The product string, e.g.
        ``"Base de Datos de Divisiones Administrativas de España 2026"``.
    """
    return PROVIDER_PRODUCT_TEMPLATE.format(edition=edition)
