#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CAOP — Carta Administrativa Oficial de Portugal.

The official administrative map of Portugal, published yearly by the DGT
(Direção-Geral do Território). It is the authoritative source for the country's
administrative divisions, and GisFIRE imports three of its levels as
:class:`~src.providers.caop.admin_boundary.CaopAdminBoundary` rows:

======================  ==========  ======  =============================
Level                   Code field  Length  Count in CAOP 2025
======================  ==========  ======  =============================
*Distrito* / *Ilha*     ``dt``      2       29
*Município*             ``dtmn``    4       308
*Freguesia*             ``dtmnfr``  6       3 259
======================  ==========  ======  =============================

Why it is imported
------------------

The ICNF burnt-area layers say where a fire started as a set of administrative
codes and names — :attr:`~src.providers.icnf.wildfire.IcnfWildfire.dicofre_code`
above all — and never as a coordinate. These boundaries are what turns that code
into a location: the *freguesia* it names has a polygon, and a point on that
polygon is the fire's approximate origin. The median *freguesia* is 15.8 km²,
about 2.2 km across, which is the accuracy such a point carries; the median
*município* is 212 km², about 8.2 km, which is what the fallback carries when the
parish code is missing.

The codes nest, and that is the hierarchy
-----------------------------------------

``dt`` is a prefix of ``dtmn`` is a prefix of ``dtmnfr``, without exception across
all 3 259 parishes, and the codes are unique across the four published files. The
tree is therefore built from the codes by prefix rather than from a spatial
containment test, which is both exact and far cheaper.

.. important::

   Portugal has a **second**, incompatible hierarchy: NUTS 1 / 2 / 3. It is not a
   refinement of the first — 12 of the 26 NUTS 3 regions span more than one
   *distrito* (*Tâmega e Sousa* spans four) — so the two cannot be one tree, and
   :class:`~src.data_model.geography.admin_boundary.AdminBoundary` has one
   ``parent_id``. GisFIRE makes the *distrito* hierarchy the tree, because that is
   what the DICOFRE code encodes and what the ICNF publishes, and carries the NUTS
   region a boundary belongs to as plain columns on every row. Grouping by NUTS is
   then a ``GROUP BY`` on a column rather than a walk of the tree.

The country level is not in the data
------------------------------------

The ``nuts1`` layers give *Continente*, *R.A. Açores* and *R.A. Madeira* — never
Portugal. The *distritos* are therefore parented to the country boundary the OCHA
import loads at level 0 (see :mod:`src.providers.ocha`), which is the only level 0
polygon GisFIRE has. That makes the levels come out as the project defines them:
country 0, *distrito* 1, *município* 2, *freguesia* 3.

One provider row per edition
----------------------------

The DGT republishes the CAOP every year, and the boundaries genuinely change: the
2013 reform merged Portugal's parishes from about 4 260 down to some 3 092 and
reassigned their codes, so a DICOFRE from a 2010 fire may name nothing in CAOP
2025, or name a differently shaped parish. Editions are therefore kept side by
side, each as its own :class:`~src.data_model.data_provider.DataProvider` row —
``DGT`` / ``Carta Administrativa Oficial de Portugal 2025`` — so that
``uq_admin_boundary_provider_source`` never sees two editions of one code, and a
fire can be attributed to the boundaries that were in force when it burnt.
"""

#: Identity of the :class:`~src.data_model.data_provider.DataProvider` row every
#: CAOP boundary hangs off, kept beside the model for the same reason as OCHA's
#: (see :mod:`src.providers.ocha`). The product carries the **edition**, which is
#: what keeps successive publications of the same codes apart — see the module
#: docstring.
PROVIDER_NAME = "DGT"
PROVIDER_FULL_NAME = "Direção-Geral do Território"
PROVIDER_PRODUCT_TEMPLATE = "Carta Administrativa Oficial de Portugal {edition}"
PROVIDER_URL = "https://www.dgterritorio.gov.pt/dados-abertos"

#: Edition imported when none is given. Bump it when a newer CAOP is the one
#: normally wanted; older editions stay importable by passing ``--edition``.
DEFAULT_EDITION = "2025"

#: The four published files, each covering one territory and each in **its own**
#: projected CRS. All are ETRS89/PTRA08-based, so reprojecting to EPSG:4326 is a
#: sub-metre operation, but it cannot be done with one CRS for the whole country.
#: Listed for documentation; the import reads the CRS from each file rather than
#: from this table.
SOURCE_SRIDS = {
    "Continente": 3763,          # ETRS89 / Portugal TM06
    "Açores, Grupo Ocidental": 5014,   # PTRA08 / UTM zone 25N
    "Açores, Grupo Central e Oriental": 5015,   # PTRA08 / UTM zone 26N
    "Madeira": 5016,             # PTRA08 / UTM zone 28N
}

#: A *distrito* on the mainland, an *ilha* in the archipelagos: the 2-digit ``dt``
#: code, administrative level 1.
KIND_DISTRITO = "distrito"

#: A *município* (also *concelho*): the 4-digit ``dtmn`` code, level 2.
KIND_MUNICIPIO = "municipio"

#: A *freguesia*, the smallest division and the one the ICNF names: the 6-digit
#: ``dtmnfr`` code — the DICOFRE — level 3.
KIND_FREGUESIA = "freguesia"

#: Every value :attr:`~src.providers.caop.admin_boundary.CaopAdminBoundary.kind`
#: may take, from the largest division to the smallest.
KINDS = (KIND_DISTRITO, KIND_MUNICIPIO, KIND_FREGUESIA)

#: The administrative level each kind is stored at. Level 0 is the country, which
#: the CAOP does not publish — see the module docstring.
LEVELS = {KIND_DISTRITO: 1, KIND_MUNICIPIO: 2, KIND_FREGUESIA: 3}

#: Length of the code identifying each kind. A child's code starts with its
#: parent's, which is what the import builds the tree from.
CODE_LENGTHS = {KIND_DISTRITO: 2, KIND_MUNICIPIO: 4, KIND_FREGUESIA: 6}

#: ISO 3166-1 alpha-3 code of the country the *distritos* are parented to, used to
#: find the OCHA boundary that becomes their parent.
COUNTRY_ISO_3 = "PRT"


def provider_product(edition: str) -> str:
    """Return the ``DataProvider.product`` naming one CAOP edition.

    Parameters
    ----------
    edition : str
        The edition's year, e.g. ``"2025"``.

    Returns
    -------
    str
        The product string, e.g.
        ``"Carta Administrativa Oficial de Portugal 2025"``.
    """
    return PROVIDER_PRODUCT_TEMPLATE.format(edition=edition)
