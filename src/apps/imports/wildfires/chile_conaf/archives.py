#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Reading CONAF's published archives.

CONAF distributes its shapefiles in **RAR** archives, one per season, and GDAL has
no ``/vsirar/`` to match the ``/vsizip/`` that
:func:`src.apps.imports.common.shapefile_datasource` uses everywhere else. So a RAR
has to be unpacked before it can be read, which is what :func:`archive_datasource`
does — into a temporary directory that goes away with the ``with`` block.

The other thing that cannot be shared is choosing the CRS to stage in. Every other
provider in GisFIRE publishes on one grid and its importer names it as a constant;
CONAF publishes the mainland on EPSG:32719 and Easter Island on EPSG:32712, so the
grid is a property of the archive rather than of the provider, and
:func:`archive_grid` reads it off the layer's own ``.prj``.

Both importers use this module — the seasonal reports and the *incendios de
magnitud* perimeters come in the same shape of archive.

Why not put this in :mod:`src.apps.imports.common`
----------------------------------------------------

The RAR handling would sit there quite naturally, and it is deliberately not there
yet: it is one provider's problem, ``unrar`` is a dependency nothing else in the
project needs, and the moment a second provider publishes RAR is the moment to move
it. Until then this is where a reader looking at the Chilean import will find it.
"""

from __future__ import annotations

import contextlib
import logging
import re
import shutil
import subprocess
import tempfile
import typing

from pathlib import Path

from src.apps.imports import common
from src.providers import chile_conaf

#: Programs that can unpack a RAR, in the order they are tried.
#:
#: ``unrar`` is the reference implementation and reads every RAR version CONAF has
#: published; ``7z`` is the fallback because it is far more commonly installed and
#: handles RAR5, which is what the more recent archives are. Both are asked to work
#: quietly and to overwrite, so a re-run of a failed import does not stop on a
#: prompt no one is there to answer.
UNPACKERS = (
    ("unrar", ("x", "-inul", "-o+")),
    ("7z", ("x", "-y", "-bso0", "-bsp0")),
)

#: What a ``.prj`` says when the layer is on the Easter Island grid.
#:
#: Matched on the zone rather than on an EPSG code because **none of the 36
#: published ``.prj`` files names an EPSG code at all**: they are ESRI WKT 1 naming
#: ``WGS_1984_UTM_Zone_12S`` or ``WGS_1984_UTM_Zone_19S``, and two of them spell the
#: parameters differently again. The zone number and the hemisphere letter are the
#: only thing every one of them agrees on.
_EASTER_ZONE = re.compile(r"UTM[_ ]zone[_ ]?12S", re.IGNORECASE)

#: What a ``.prj`` says when the layer is on the mainland grid.
_MAINLAND_ZONE = re.compile(r"UTM[_ ]zone[_ ]?19S", re.IGNORECASE)


@contextlib.contextmanager
def archive_datasource(path: Path,
                       logger: logging.Logger) -> typing.Iterator[tuple[str, str, Path]]:
    """Yield the GDAL datasource, layer and ``.shp`` path for a published archive.

    Parameters
    ----------
    path : pathlib.Path
        A ``.rar``, a ``.zip``, a directory holding one shapefile, or a ``.shp``.
    logger : logging.Logger
        Where the unpacking is reported.

    Yields
    ------
    tuple
        ``(datasource, layer, shapefile)`` — the first two to hand to
        :func:`src.apps.imports.common.load_staging_table`, the third for
        :func:`archive_grid` to read the ``.prj`` beside.

    Raises
    ------
    RuntimeError
        If no unpacker is installed, if the unpacker fails, or if the archive holds
        no shapefile or more than one.

    Notes
    -----
    Everything that is not a RAR is handed straight to
    :func:`src.apps.imports.common.shapefile_datasource`, which already covers zips
    without unpacking them and directories and bare ``.shp`` files. So a user who
    has unpacked the archives by hand — or converted them to zip — needs nothing
    from this function, and passing ``-d`` a directory of unpacked directories works
    unchanged.

    A RAR is unpacked into a :func:`tempfile.TemporaryDirectory` that is removed when
    the block ends, whether or not the import succeeded. The largest published
    archive is 9 MB and unpacks to about 25 MB, so this costs nothing worth managing;
    it is a context manager rather than a plain function only so that the cleanup is
    not something a caller can forget.

    Two of the published archives — ``if_isla_pascua_2013_2014.rar`` among them —
    hold their shapefile inside a directory rather than at the archive root, so the
    search is recursive.
    """
    if path.suffix.lower() != ".rar":
        datasource, layer = common.shapefile_datasource(path)
        shapefile = Path(datasource.replace("/vsizip/", "", 1))
        yield datasource, layer, shapefile
        return

    unpacker = next(((name, flags) for name, flags in UNPACKERS
                     if shutil.which(name) is not None), None)
    if unpacker is None:
        raise RuntimeError(
            f"{path} is a RAR archive and neither "
            f"{' nor '.join(name for name, _ in UNPACKERS)} is installed. Install one, "
            f"or unpack the archives by hand and pass the directory"
        )
    program, flags = unpacker

    with tempfile.TemporaryDirectory(prefix="conaf-") as directory:
        target = Path(directory)
        logger.debug("Unpacking %s with %s into %s", path.name, program, target)
        command = [program, *flags, str(path)]
        # unrar wants the destination as a trailing argument, 7z as -o<dir> with no
        # space. Neither accepts the other's form.
        command.append(f"{target}/" if program == "unrar" else f"-o{target}")
        result = subprocess.run(command, text=True, capture_output=True)
        if result.returncode != 0:
            raise RuntimeError(
                f"{program} failed to unpack {path} with exit code "
                f"{result.returncode}:\n{(result.stderr or result.stdout).strip()}"
            )

        members = sorted(target.rglob("*.shp"))
        if not members:
            raise RuntimeError(f"{path} contains no shapefile (.shp)")
        if len(members) > 1:
            raise RuntimeError(
                f"{path} contains {len(members)} shapefiles "
                f"({', '.join(member.name for member in members)}); "
                f"unpack it and pass the one you want"
            )
        yield str(members[0]), members[0].stem, members[0]


def archive_grid(shapefile: Path, logger: logging.Logger) -> int:
    """The SRID this archive should be staged on.

    Parameters
    ----------
    shapefile : pathlib.Path
        The ``.shp``; its ``.prj`` is read from beside it.
    logger : logging.Logger
        Where an unrecognised or missing ``.prj`` is reported.

    Returns
    -------
    int
        :data:`~src.providers.chile_conaf.SOURCE_SRID_EASTER` for an Easter Island
        layer, :data:`~src.providers.chile_conaf.SOURCE_SRID_MAINLAND` otherwise.

    Notes
    -----
    This chooses the grid to **stage on**, not the grid the file is on. ``ogr2ogr``
    reads the ``.prj`` itself and reprojects from whatever it finds, so a layer whose
    ``.prj`` this function misreads still lands in the right place on the ground —
    it just lands in the wrong column. That is what
    :data:`~src.providers.chile_conaf.PLAUSIBLE_EXTENT_MAINLAND` and its Easter
    Island counterpart catch, after staging, before anything is written.

    Mainland is the default for anything unrecognised, and there is one layer that
    needs it: ``if_temporada_2024_2025`` publishes a bare geographic WGS 84 ``.prj``
    with no projection at all, and its 6,262 fires are ordinary mainland fires.
    Defaulting the other way would put a whole season on the Rapa Nui grid, where the
    extent check would then reject it — which is a good failure, but a worse one than
    getting it right.
    """
    projection = shapefile.with_suffix(".prj")
    if not projection.exists():
        logger.warning("%s has no .prj; staging it on the mainland grid EPSG:%d",
                       shapefile.name, chile_conaf.SOURCE_SRID_MAINLAND)
        return chile_conaf.SOURCE_SRID_MAINLAND

    text = projection.read_text(encoding="utf-8", errors="replace")
    if _EASTER_ZONE.search(text):
        logger.debug("%s is on the Easter Island grid EPSG:%d",
                     shapefile.name, chile_conaf.SOURCE_SRID_EASTER)
        return chile_conaf.SOURCE_SRID_EASTER
    if not _MAINLAND_ZONE.search(text):
        logger.info("%s names neither UTM zone 19S nor 12S in its .prj; staging it on "
                    "the mainland grid EPSG:%d and checking its extent",
                    shapefile.name, chile_conaf.SOURCE_SRID_MAINLAND)
    return chile_conaf.SOURCE_SRID_MAINLAND


#: Bounds a staged geometry has to fall in, per grid. See
#: :func:`src.apps.imports.common.load_staging_table` — the check runs after staging,
#: on the geometries as they will be stored.
PLAUSIBLE_EXTENTS = {
    chile_conaf.SOURCE_SRID_MAINLAND: chile_conaf.PLAUSIBLE_EXTENT_MAINLAND,
    chile_conaf.SOURCE_SRID_EASTER: chile_conaf.PLAUSIBLE_EXTENT_EASTER,
}

#: The staged extent, for :func:`check_extent`.
EXTENT_SQL = """
SELECT ST_XMin(extent) AS min_x, ST_YMin(extent) AS min_y,
       ST_XMax(extent) AS max_x, ST_YMax(extent) AS max_y
FROM (SELECT ST_Extent(geom) AS extent FROM {staging_table}) AS bounds
"""


def check_extent(session, staging_table: str, srid: int,
                 logger: logging.Logger) -> bool:
    """Warn if the staged geometries do not look like they are on ``srid``.

    Parameters
    ----------
    session : sqlalchemy.orm.Session
        The session the archive was staged through.
    staging_table : str
        The staging table, schema-qualified.
    srid : int
        The grid :func:`archive_grid` chose.
    logger : logging.Logger
        Where a failure is reported.

    Returns
    -------
    bool
        Whether the extent is plausible. An empty staging table is plausible — there
        is nothing to disagree with — and returns ``True``.

    Notes
    -----
    A warning and not a refusal, on the judgement the sibling imports make: the
    ``.prj`` files are the least reliable part of this archive and a bounds test
    widened enough to admit Magallanes is not tight enough to be certain with. What
    it is certain about is the case that matters — a mainland layer staged on the
    Rapa Nui grid, or the reverse, which is out by thousands of kilometres and
    cannot be mistaken for a fire in Aysén.
    """
    from sqlalchemy import text as sql_text

    bounds = session.execute(sql_text(EXTENT_SQL.format(staging_table=staging_table))).one()
    if bounds.min_x is None:
        return True

    min_x, min_y, max_x, max_y = PLAUSIBLE_EXTENTS[srid]
    if (min_x <= bounds.min_x and bounds.max_x <= max_x
            and min_y <= bounds.min_y and bounds.max_y <= max_y):
        return True

    logger.warning(
        "Staged extent (%.0f, %.0f)-(%.0f, %.0f) is outside the expected "
        "(%.0f, %.0f)-(%.0f, %.0f) for EPSG:%d. The archive's .prj may name the wrong "
        "grid, or this may not be a Chilean layer",
        bounds.min_x, bounds.min_y, bounds.max_x, bounds.max_y,
        min_x, min_y, max_x, max_y, srid,
    )
    return False
