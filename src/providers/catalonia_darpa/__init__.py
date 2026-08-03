#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DARPA — Departament d'Agricultura, Ramaderia, Pesca i Alimentació (Catalonia).

Data model for the Catalan burnt area cartography: the perimeters of the forest
fires of Catalonia, published by the department as one shapefile per year from
1986 on. Every layer is a set of burnt-area polygons in EPSG:25831.

This is the first **regional** perimeter source in GisFIRE, and it exists because
:mod:`src.providers.spain_egif` has no perimeter and never will — EGIF is an
administrative statistic and publishes a burnt *area* in hectares, not a polygon.
What the autonomous regions publish is the shape. The two are related and the
relation is modelled, on
:attr:`~src.providers.catalonia_darpa.wildfire.DarpaWildfire.egif_wildfire_id`;
what fills it in is not this import. See *The EGIF relation* below.

The acronym
-----------

``DARPA`` here is the Catalan department and nothing else. The department has been
renamed and re-lettered repeatedly — DARP, DAAM, DARP again, and DACC — and the
files in this dataset span every one of those names, so no acronym of it is both
current and true of the whole archive. The one used here is the current
department's, and it is a label for a
:class:`~src.data_model.data_provider.DataProvider` row, not a claim about which
consellería signed a given shapefile.

One layer per year, and the names are not regular
--------------------------------------------------

The published set is ``incendis1986`` … ``incendis2024``, one shapefile per year,
**with two exceptions worth knowing before pointing an import at the directory**:

``incendis10``
    2010, named with two digits where every other year uses four. It is the
    layer name inside the published ``incendis10.zip`` as well, so it is not a
    local renaming that could be tidied up. :func:`layer_year` resolves both
    spellings.

``incendis.shp``
    **A byte-identical copy of** ``incendis2022.shp`` — same MD5 on the ``.shp``
    and on the ``.dbf`` — because it is what falls out of ``incendis22.zip``:
    alone among the thirty-nine archives, that one holds a shapefile named
    ``incendis`` rather than ``incendis2022``.

    Importing a directory that holds both would import 2022 twice, and nothing
    downstream would notice: the fires have the same codes and the same geometry,
    so they would simply double the 2022 totals. The import skips it by name; see
    :data:`DUPLICATE_LAYERS`.

2010 is also the only year with no four-digit file, so a set that looks like it
runs 1986-2024 with one gap is complete.

The year comes from the archive, not from the layer inside it
--------------------------------------------------------------

Which matters precisely because of ``incendis22.zip``. Read from the zip, the GDAL
layer is called ``incendis`` and carries no year at all; read from the loose file
beside it, the same fires are in a layer called ``incendis2022``.

So a fire's year and its
:attr:`~src.providers.catalonia_darpa.wildfire.DarpaWildfire.source_layer` are
both derived from the **name of the file being imported** — the thing the
department actually versions — and ``source_layer`` is the canonical
:func:`source_layer_name`, ``incendis`` plus four digits, whatever the file or the
layer inside it happened to be called.

That is what makes the two distribution forms interchangeable: ``incendis22.zip``,
``incendis2022.shp`` and an unpacked directory all import as ``incendis2022``, so
importing one after another **replaces** the year rather than doubling it.

Four attributes, and only one of them is an identifier
-------------------------------------------------------

Every layer publishes ``CODI_FINAL``, ``DATA_INCEN``, ``MUNICIPI`` and
``GRID_CODE``, in an order that varies from layer to layer and in field types that
vary with it (``Integer (1.0)``, ``Integer (4.0)``, ``Integer64``). Two layers add
an ``OBJECTID`` the import ignores. There is **no burnt area** in any of them:
this source publishes the shape and nothing else, which is exactly the
complement of what EGIF publishes.

``GRID_CODE`` is the class of the raster these polygons were vectorised from
-----------------------------------------------------------------------------

It takes two values, and it is not an attribute of the fire:
:data:`GRID_CODE_BURNT` (``2``) is the burnt class and ``0`` is the background.
The ``0`` features are not fires — 179 of the 4,712 published features, 173 of
them in 1991 — and **152 of them carry no code and no date at all**. Every corrupt
value in the dataset is among them too: the twenty features whose ``DATA_INCEN``
is ``2,152543589*``, a float written into a twelve-character text column.

Dropping ``GRID_CODE <> 2`` therefore removes every null and every unparseable
date in one filter, which is why
:attr:`~src.data_model.wildfire.Wildfire.start_date_time` can stay ``NOT NULL``
here without a placeholder of the kind the ICNF import has to invent.

A fire is many polygons, and the import dissolves them
-------------------------------------------------------

These layers were vectorised from a raster and **never dissolved**. Most years
publish one feature per fire, but three do not:

======  ========  =====  =========================================
Layer   Features  Fires  Largest fire
======  ========  =====  =========================================
1991         306     36  67 polygons
1993          67     21  15 polygons
1994       3,642    109  **1,309 polygons**
======  ========  =====  =========================================

4,533 burnt features are 860 fires. The import groups them and stores one
``MULTIPOLYGON`` per fire, keeping the count in
:attr:`~src.providers.catalonia_darpa.wildfire.DarpaWildfire.part_count` so that
the shattering is visible rather than silently smoothed over.

The natural key is the code **and the date**
---------------------------------------------

``CODI_FINAL`` alone is not a key. ``303/22N`` names two different fires —
Lleida on 19 June 2022 and Figueres on 7 July — so grouping on the code alone
would merge them into one polygon spanning half of Catalonia. The key is
``(CODI_FINAL, DATA_INCEN)``, which is unique across the whole archive: 860 pairs
for 859 codes. No code is used in two different years.

Five formats of code, and only the last one is EGIF's
------------------------------------------------------

``CODI_FINAL`` changed shape four times in forty years:

``1986``, ``1992``, ``1993``
    Nine digits, province plus year plus sequence: ``178600064`` is Girona, 1986,
    fire 64.
``1987``, ``1988``
    A province letter and seven digits: ``G0870016``, ``T0880051``.
``1989``-``1991``
    A province letter and eight digits: ``L89004001``.
``1994``-``1996``
    Six or seven bare digits with no visible structure: ``894496``.
``1997``-
    **Ten digits: year, INE province code, four-digit sequence** —
    ``2013080287`` is 2013, Barcelona (``08``), fire 0287.

That last form is exactly
:attr:`~src.providers.spain_egif.wildfire.EgifWildfire.report_number`, and it is
not a coincidence: all 529 of the ten-digit codes in the archive parse as one, with
a Catalan INE province (:data:`PROVINCE_INE_CODES`) and a year that always matches
the layer they are in.

Thirteen recent fires use a sixth form instead — ``303/22N``, ``210_24N`` — which
is an internal reference and not an EGIF code at all.

The code is stored **exactly as published**, in every one of the six forms. It is
not parsed, split or normalised: doing that would bake a matching rule into the
import, and the matching rule is the thing that has not been agreed yet.

The EGIF relation
-----------------

:attr:`~src.providers.catalonia_darpa.wildfire.DarpaWildfire.egif_wildfire_id`
exists and the import **never fills it in**. It is left ``NULL`` on every row.

The column is here so that a later binding application is an ``UPDATE`` rather
than a migration, and because a perimeter dataset for Spanish fires whose relation
to the national statistic was not modelled at all would be a strange thing to
build. What is deliberately *not* here is a matching rule: the ten-digit codes
look like a join key and probably are, but a third of the archive predates that
form entirely, thirteen fires use a code EGIF never issued, and none of that has
been checked against real EGIF rows yet.

See the module docstring of :mod:`src.providers.spain_egif.wildfire` for why the
link is a relation between two wildfires rather than a Catalan polygon written
onto a MITECO row.

Two character sets, and the files do say which
-----------------------------------------------

The published ``.dbf`` files are **not all in the same encoding**, and not one of
them carries a ``.cpg``:

* **ISO-8859-1** — 1986-1988 and 1991-2012.
* **UTF-8** — 1989, 1990 and 2013-2024. The first two are the odd ones out of
  their era: they were re-saved in 2016, long after the years around them.

What decides it is the DBF **language-driver byte**, at offset 29 of the header,
and the correlation over all forty files is exact with no exceptions:

========  ==========  =====================================
LDID      Encoding    Files
========  ==========  =====================================
``0x57``  ISO-8859-1  23, plus 2 that are pure ASCII anyway
``0x00``  UTF-8       15
========  ==========  =====================================

So this is not a guess GDAL happens to get right. The files describe themselves,
GDAL reads the byte, and every layer comes back correct with **no ``ENCODING``
open option at all**.

Forcing one, as the ICNF import has to
(:data:`src.providers.portugal_icnf.SOURCE_ENCODING`), is actively harmful here —
it overrides the byte. ``ENCODING=ISO-8859-1`` turns ``Alfarràs`` into
``AlfarrÃ s`` in the newer half of the archive, and ``ENCODING=UTF-8`` turns
``Vallès`` into a name with a replacement character in it in the older half.

The import passes none, and checks the staged names for both signatures of a
mangling afterwards. The check is cheap and the rule is one byte deep in a file
format from 1986, which is a thing worth asserting rather than trusting.

Dates: two formats, both of them dates
---------------------------------------

``DATA_INCEN`` is text, and it is ``dd/mm/yy`` to 2018 and ``dd/mm/yyyy`` from
2019, with a single-digit day here and there (``1/07/13``). Every one of the 4,533
burnt features parses, and the year always agrees with the layer it is in — so the
century of a two-digit year is resolved from the layer rather than from a pivot
rule, and the agreement is checked rather than assumed.

There is no time of day anywhere in the dataset. A fire's
:attr:`~src.data_model.wildfire.Wildfire.start_date_time` is local midnight on
the published date, and
:attr:`~src.providers.catalonia_darpa.wildfire.DarpaWildfire.fire_date` keeps the
date itself, which is what the source actually said.

Five values end in a line ending
---------------------------------

Small, and worth writing down because it is invisible until it costs five fires.
Six published values carry a literal ``\\r\\n`` **inside the DBF field**: the dates
of ``2021170071``, ``2021430077``, ``202117006``, ``2021170060`` and ``4394032``,
and the municipality of two of those and of a 2021 fire in Torà.

They are ordinary values with a line ending typed into them. GDAL strips a
character field's space padding but not those, so ``31/07/2021\\r\\n`` fails any
date parse and ``LA POBLA DE MASSALUCA\\r\\n`` is stored with the line ending still
in it. The import trims them; the failure mode if it did not is four 2021 fires
and one 1994 fire silently absent, which no count in the log would have flagged.
"""

#: Identity of the :class:`~src.data_model.data_provider.DataProvider` row every
#: Catalan wildfire hangs off. The product names the cartography rather than the
#: department, which publishes a great deal else — see the module docstring on why
#: the acronym is a label rather than a claim.
PROVIDER_NAME = "DARPA"
PROVIDER_FULL_NAME = "Departament d'Agricultura, Ramaderia, Pesca i Alimentació"
PROVIDER_PRODUCT = "Perímetres d'incendis forestals de Catalunya"
PROVIDER_URL = "https://agricultura.gencat.cat"

#: The projected CRS the department publishes in — ETRS89 / UTM zone 31N, the
#: Catalan and eastern-Spanish grid. Every layer of every year, checked on all
#: thirty-nine: not one of them differs, and none is unprojected.
#:
#: The published geometry is kept in it unchanged
#: (:attr:`~src.providers.catalonia_darpa.wildfire.DarpaWildfire.perimeter_etrs89_utm31n`)
#: alongside the EPSG:4326 reprojection on the generic model, for the reason set
#: out in :mod:`src.providers.portugal_icnf.wildfire`: a national grid in metres
#: is what an area or a distance means something in, and reprojecting is neither
#: free nor lossless.
SOURCE_SRID = 25831

#: ``GRID_CODE`` of a burnt polygon. See the module docstring: this is the class of
#: the raster the layers were vectorised from, not an attribute of the fire, and
#: everything that is not this value is background — including every feature in the
#: archive with a missing or corrupt attribute.
GRID_CODE_BURNT = 2

#: Zone the published dates are resolved against. Catalonia is one zone and always
#: has been. Like every other importer's, it is a fallback rather than a rule: the
#: zone is resolved from the geometry, and this is what is used if no time zone
#: areas have been imported.
DEFAULT_TIME_ZONE = "Europe/Madrid"

#: File names that are a second copy of another year and must not be imported.
#:
#: ``incendis.shp`` is byte-identical to ``incendis2022.shp`` — same MD5 on the
#: ``.shp`` and the ``.dbf`` — because it is what unpacking ``incendis22.zip``
#: produces. Importing both would double 2022, with the same codes and the same
#: polygons, which nothing downstream would flag.
#:
#: Matched against the name of the **file**, not of the layer inside it: the zip is
#: a perfectly good source of 2022 and is imported normally, and it is only the
#: loose copy sitting beside ``incendis2022.shp`` that is redundant. Skipped by
#: name rather than by comparing files, because the name is what the import can
#: know before spending a minute loading a staging table.
DUPLICATE_LAYERS = frozenset({"incendis"})

#: INE province codes of the four Catalan provinces, in the order the codes use
#: them: Barcelona, Girona, Lleida, Tarragona.
#:
#: Not used by the import — the code is stored exactly as published — but it is
#: what makes the ten-digit form recognisable as an EGIF ``report_number``, and it
#: is what restricts the EGIF side of a binding to the fires that could possibly
#: be Catalan.
PROVINCE_INE_CODES = ("08", "17", "25", "43")

#: The province letter the 1987-1991 codes begin with, as an INE code.
#:
#: ``B0880104`` is Barcelona, ``G89031003`` Girona, ``L90023010`` Lleida and
#: ``T91030011`` Tarragona. Read off the codes of those five layers and checked
#: against the municipality each fire is filed in.
PROVINCE_LETTERS = {"B": "08", "G": "17", "L": "25", "T": "43"}

#: Prefix every published layer name carries.
LAYER_PREFIX = "incendis"

#: Two-digit years at or above this are 19xx, below it 20xx.
#:
#: Only ever consulted for ``incendis10``, the single layer named with two digits,
#: and the archive starts in 1986 and runs to 2024 — so any split between 24 and 86
#: gives the same answer. It is written down rather than left to a library's own
#: pivot so that the one layer it decides is decided here.
CENTURY_PIVOT = 70


def layer_year(layer: str) -> int:
    """The year a published layer covers, from its name.

    Parameters
    ----------
    layer : str
        A published layer name: ``incendis1994``, or ``incendis10`` for 2010.

    Returns
    -------
    int
        The four-digit year.

    Raises
    ------
    ValueError
        If the name is not a published layer name. Raised rather than guessed:
        a layer whose year cannot be read is a file that does not belong in the
        directory, and importing it under a wrong year would be worse than
        stopping.

    Examples
    --------
    >>> layer_year("incendis1994")
    1994
    >>> layer_year("incendis10")
    2010

    Notes
    -----
    Both spellings exist in the published set and neither is a local renaming:
    ``incendis10`` is the layer name inside the department's own
    ``incendis10.zip``, and every zip is named with two digits. See the module
    docstring.

    Applied to the **file** being imported rather than to the GDAL layer inside it,
    because ``incendis22.zip`` holds a layer called ``incendis``, which carries no
    year at all and would raise here.

    The year is used to resolve the century of a two-digit ``DATA_INCEN``, to fill
    :attr:`~src.providers.catalonia_darpa.wildfire.DarpaWildfire.year`, and to build
    :func:`source_layer_name`. The import checks it against the dates it parses
    rather than trusting it, so a file named for the wrong year is caught rather
    than propagated.
    """
    if not layer.startswith(LAYER_PREFIX):
        raise ValueError(
            f"{layer!r} is not a DARPA layer name; expected {LAYER_PREFIX}<year>"
        )
    digits = layer[len(LAYER_PREFIX):]
    if len(digits) == 4 and digits.isdigit():
        return int(digits)
    if len(digits) == 2 and digits.isdigit():
        value = int(digits)
        return 1900 + value if value >= CENTURY_PIVOT else 2000 + value
    raise ValueError(
        f"{layer!r} carries no year; expected {LAYER_PREFIX} followed by two or four "
        f"digits, as in {LAYER_PREFIX}1994 or {LAYER_PREFIX}10"
    )


def source_layer_name(year: int) -> str:
    """The canonical layer name for a year, as stored on every fire of it.

    Parameters
    ----------
    year : int
        The four-digit year the archive covers.

    Returns
    -------
    str
        ``incendis`` followed by the four-digit year.

    Examples
    --------
    >>> source_layer_name(2010)
    'incendis2010'

    Notes
    -----
    Canonical rather than "whatever the file was called", because the department
    ships the same year under three names: ``incendis2022.shp``, ``incendis22.zip``
    and — inside that zip — a GDAL layer called plainly ``incendis``. 2010 adds a
    fourth, ``incendis10``, in both forms.

    Storing the name as found would put the same fires under two different
    :attr:`~src.providers.catalonia_darpa.wildfire.DarpaWildfire.source_layer`
    values depending on which copy was to hand, and the import's replace-the-layer
    rule keys on exactly that column — so importing the zip after the shapefile
    would double the year instead of replacing it.
    """
    return f"{LAYER_PREFIX}{year:04d}"


def egif_report_number(code: str, year: int) -> str | None:
    """The EGIF ``report_number`` a published ``CODI_FINAL`` is, if it is one.

    Parameters
    ----------
    code : str
        A published code, in any of its six forms.
    year : int
        The year of the layer the code was published in. Used to decide which of
        two readings of an ambiguous format is the right one, and to reject a
        decode that lands in the wrong year.

    Returns
    -------
    str or None
        The ten-character report number, or ``None`` where the format is not one.

    Examples
    --------
    >>> egif_report_number("2013080287", 2013)
    '2013080287'
    >>> egif_report_number("178600064", 1986)
    '1986170064'
    >>> egif_report_number("920800034", 1992)
    '1992080034'
    >>> egif_report_number("894496", 1994)
    '1994080496'
    >>> egif_report_number("L89004001", 1989) is None
    True

    Notes
    -----
    **Four of the six published formats are the EGIF report number rearranged.**
    That is not obvious from looking at them, and it is worth setting out, because
    it is what turns a third of this dataset from a fuzzy match into an identity.

    A report number is ``YYYY`` + INE province + a four-digit sequence. The Catalan
    codes carry the same three fields in different orders and widths:

    ==================  ===============  ====================  =========
    Years               Form             Example               Decodes to
    ==================  ===============  ====================  =========
    1997-                ``YYYYPPNNNN``  ``2013080287``        itself
    1986                 ``PPYYNNNNN``   ``178600064``         ``1986170064``
    1992, 1993           ``YYPPNNNNN``   ``920800034``         ``1992080034``
    1994-1996            ``PYYNNN``      ``894496``            ``1994080496``
    1994-1996            ``PPYYNNN``     ``4394032``           ``1994430032``
    ==================  ===============  ====================  =========

    The nine-digit form is genuinely ambiguous — ``PPYY`` in 1986 and ``YYPP`` in
    1992-1993 — so the reading is chosen by which one puts the fire in the year of
    the layer it was published in. ``920800034`` reads as province 92 of 1908 one
    way and as province 08 of 1992 the other, and only the second is a year this
    dataset has.

    Every decode is required to yield a **Catalan province**
    (:data:`PROVINCE_INE_CODES`) and the layer's own year, so a code of some other
    kind that happens to have the right number of digits is refused rather than
    turned into a plausible-looking report number.

    .. note::

       The 1987-1991 letter forms — ``G0870016``, ``L89004001`` — are **not**
       decoded, and return ``None``. The letter is a province and the next two
       digits are the year, but what follows is six digits where a report number
       has four, and no reading of them matches EGIF at a rate distinguishable from
       chance. Those fires are left to the date and the municipality name.

    The decodes were checked the only way they can be: against the dates. All 122
    fires that match EGIF through a decode have **identical published dates on both
    sides** — a cleaner record than the undecoded ten-digit form, which disagrees on
    nine of its 480. The application that uses this requires that agreement before
    trusting a decode; see
    :mod:`src.apps.bindings.wildfires.catalonia_darpa.bind_egif_wildfires`.
    """
    if not code or not code.isdigit():
        return None
    century, decade = divmod(year, 100)

    def assemble(province: str, sequence: str, code_year: int) -> str | None:
        """One reading, accepted only if it is Catalan and in the layer's year."""
        if province not in PROVINCE_INE_CODES or code_year != year:
            return None
        return f"{year:04d}{province}{int(sequence):04d}"

    if len(code) == 10:
        return code if assemble(code[4:6], code[6:], int(code[:4])) else None
    if len(code) == 9:
        # PPYYNNNNN, then YYPPNNNNN. Only one can put the fire in the layer's year.
        for province, published_year, sequence in (
            (code[0:2], code[2:4], code[4:]),
            (code[2:4], code[0:2], code[4:]),
        ):
            report = assemble(province, sequence, century * 100 + int(published_year))
            if report is not None:
                return report
        return None
    if len(code) in (6, 7):
        # One or two digits of province, then the two-digit year, then the sequence.
        for width in (1, 2):
            province, rest = code[:width].zfill(2), code[width:]
            if len(rest) < 3:
                continue
            report = assemble(province, rest[2:], century * 100 + int(rest[:2]))
            if report is not None:
                return report
    return None


def province_ine_code(code: str, year: int) -> str | None:
    """The INE province a published ``CODI_FINAL`` names, if it names one.

    Parameters
    ----------
    code : str
        A published code, in any of its six forms.
    year : int
        The year of the layer, needed to read the ambiguous nine-digit form.

    Returns
    -------
    str or None
        Two digits, or ``None`` where the format encodes no province.

    Examples
    --------
    >>> province_ine_code("2013080287", 2013)
    '08'
    >>> province_ine_code("920800034", 1992)
    '08'
    >>> province_ine_code("G0870016", 1987)
    '17'
    >>> province_ine_code("303/22N", 2022) is None
    True

    Notes
    -----
    Taken from :func:`egif_report_number` wherever that can read one, so the two can
    never disagree about what a code says. The letter forms are the exception: they
    are not decodable into a report number but their **leading letter is a province**
    all the same (:data:`PROVINCE_LETTERS`), and that is worth having — it is the
    only thing narrowing the candidates for 97 fires of 1987-1991.

    This is **derived, not stored**: the code is kept exactly as published (see the
    module docstring), and a function that reads it is a rule that can be corrected,
    where a column would be a decision frozen at import time.
    """
    report = egif_report_number(code, year)
    if report is not None:
        return report[4:6]
    if len(code) > 1 and code[0] in PROVINCE_LETTERS and code[1:].isdigit():
        return PROVINCE_LETTERS[code[0]]
    return None
