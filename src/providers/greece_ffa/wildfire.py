#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Greek Fire Service wildfire model.

One row per published fire record: an intervention by the Hellenic Fire Service.
The generic :class:`~src.data_model.wildfire.Wildfire` already holds the start and
end instants; this model adds the two identifiers the recent years publish, where
the fire is filed administratively, the eight burnt areas, what was sent to it,
and the link to the published point.

See :mod:`src.providers.greece_ffa` for the dataset itself — the twenty-six
sheets, the six column arrangements, the years with no coordinate and the 2025
outlier.

There is no perimeter, ever
---------------------------

:attr:`~src.data_model.wildfire.Wildfire.perimeter` is ``NULL`` on every Greek
fire and always will be, for the reason it is ``NULL`` on every EGIF one
(:mod:`src.providers.spain_egif.wildfire`): this is an administrative statistic
and it publishes no polygon in any year, in any file. What it publishes is a
burnt *area*, split by land cover.

What it does publish, from 2020, is a point — on
:class:`~src.providers.greece_ffa.ignition.GreeceFfaIgnition`, linked by
:attr:`ignition_id` rather than embedded as two columns, for the reason set out in
:mod:`src.data_model.ignition`. Four fires in five have none.

Should Greek perimeters appear later from another agency, they will be that
agency's provider with its own :class:`~src.data_model.wildfire.Wildfire`
subclass, and **they will not be written into this row**: a row belongs to the
provider named by its ``data_provider_id``, and a polygon from elsewhere on a Fire
Service row would quietly make the provenance a lie.

The areas are hectares, and the source publishes στρέμματα
------------------------------------------------------------

The eight ``area_ha_*`` columns are the published land-cover figures multiplied by
:data:`~src.providers.greece_ffa.STREMMA_HA`. Every other provider in GisFIRE
stores hectares, and a burnt-area report over two countries cannot carry a unit
per country; the conversion is exact — a στρέμμα is 1,000 m² by definition, a
tenth of a hectare — so nothing is rounded away and the published number is
recoverable by multiplying by ten.

There is no published total and none is stored. The eight columns are the parts;
a stored sum is a value that can disagree with them after an edit, and adding
eight columns is not expensive.

The 2000-2011 sheets publish ``Σκουπιδότοποι`` (landfill) and the 2012-2024 ones
publish it as ``Σκουπι-δότοποι``; it is one column and
:func:`~src.providers.greece_ffa.normalise_column` is what makes it one.

The deployment block is a fact about the response, not about the fire
----------------------------------------------------------------------

Thirteen counts, published from 2011 on and ``NULL`` for 2000-2010: how many
firefighters, ground units, volunteers, soldiers and others attended, how many
vehicles of each kind, and how many aircraft of each type flew.

They are kept because they are the only thing in GisFIRE that measures a
*response* rather than an event, and because nothing else publishes them — but
they measure what was sent, which is a function of what was available and what
was feared as much as of what burnt. A large fire in a year with no aircraft
serviceable records no aircraft.

Two of them are the same slot renamed and are stored as one column:

* ``ΟΧΗΜ. ΟΤΑ`` (2011-2021, municipal vehicles) becomes ``ΟΧΗΜ. ΥΠΗΡΕΣΙΑΚΑ``
  (2022 on, service vehicles) — :attr:`vehicles_public_service`.

And two are genuinely new rather than renamed: :attr:`aircraft_leased_helicopters`
and :attr:`aircraft_leased_planes` arrive in 2021, :attr:`aircraft_other_agencies`
in 2025 — while :attr:`aircraft_gru` stops being published after 2024. A ``NULL``
in any of them means *this year did not publish this column*, never *zero*.

``incident_category`` has no ``CHECK``
---------------------------------------

:attr:`incident_category` holds ``Κατηγορία Συμβάντος``, which the 2025 file
publishes and no earlier year does — three size classes and
:data:`~src.providers.greece_ffa.CATEGORY_FALSE_ALARM`, a call-out that found no
fire at all.

No constraint lists them. The vocabulary is one year of one file observed once,
and a ``CHECK`` built from it would reject the first class the service adds — the
same decision, for the same reason, as
:mod:`src.providers.andalusia_rediam.wildfire`'s ``match_method`` at the point it
was created. :data:`~src.providers.greece_ffa.INCIDENT_CATEGORIES` is the observed
vocabulary, in Python, where being wrong costs a test rather than a migration.

.. warning::

   1,255 of the 9,043 rows of 2025 are false alarms — 14% of the year. They are
   records of a dispatch, not of a wildfire, and **any query that counts or
   measures fires must exclude them**::

      WHERE incident_category IS DISTINCT FROM 'ΨΕΥΔΗΣ ΑΝΑΓΓΕΛΙΑ'

   ``IS DISTINCT FROM`` and not ``<>``: the column is ``NULL`` for every year
   before 2025, and ``<>`` would drop the other twenty-five.
"""

from __future__ import annotations

from sqlalchemy import BigInteger
from sqlalchemy import Float
from sqlalchemy import ForeignKey
from sqlalchemy import Index
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship

from src.data_model.ignition import Ignition
from src.data_model.wildfire import Wildfire
from src.providers.greece_ffa.ignition import GreeceFfaIgnition


class GreeceFfaWildfire(Wildfire):
    """A fire record published by the Hellenic Fire Service.

    Uses joined table inheritance: the columns shared by every wildfire live in
    the ``wildfire`` table and only the Greek ones are stored here, in
    ``greece_ffa_wildfire``, whose primary key is also a foreign key to the parent
    row.

    Attributes
    ----------
    id : int
        Primary key, and a foreign key to
        :attr:`~src.data_model.wildfire.Wildfire.id`. The local GisFIRE
        identifier, shared with the parent row.
    year : int
        The year of the sheet the record was read from. ``NOT NULL`` and indexed.

        This is the dataset's only stable handle: it is what a report groups on,
        what an import replaces, and — because nothing identifies an individual
        fire — the unit at which the data can be reasoned about at all. It is the
        sheet's year and not the year of
        :attr:`~src.data_model.wildfire.Wildfire.start_date_time`, on the rule
        every provider in GisFIRE follows: a published yearly total is a total of
        what the service filed under that year.
    source_sheet : str
        The workbook sheet the record was read from — ``"2011"``, or ``"Sheet0"``
        for the 2025 file. Provenance, and what tells the thirteen sheets of the
        2000-2012 workbook apart from one another.
    record_number : int or None
        ``Α/Α ΕΓΓΡΑΦΗΣ``, the service's record number. Published from 2020 and
        ``None`` for every year before it.

        Indexed and **not unique**: 512 of the 57,734 values in the archive are
        used by more than one row. See :mod:`src.providers.greece_ffa` — a
        ``UNIQUE`` here would reject records the service really published.

        A ``bigint``, though its published values run only 13,970 to 2,047,844:
        see :attr:`engage_id`, which is the same kind of number written by the
        same service.
    engage_id : int or None
        ``Α/Α ENGAGE``, the incident number in the dispatch system. Published
        2020-2025, ``None`` before, and not unique either — 48 values repeat.

        A ``bigint`` because it has to be. The values run 92,687 to
        **911,023,000,013**, and two rows of the 2023 sheet are past what a
        32-bit integer holds: ``2310230025`` and ``911023000013``, against a
        median around a million. They look like a date and a sequence run
        together by whatever wrote them, and they are what the service published,
        so they are stored as published rather than rejected or truncated.
    incident_category : str or None
        ``Κατηγορία Συμβάντος`` — ``ΜΙΚΡΗ``, ``ΜΕΣΑΙΑ``, ``ΜΕΓΑΛΗ`` or
        :data:`~src.providers.greece_ffa.CATEGORY_FALSE_ALARM`. Published in 2025
        and in no earlier year, so ``None`` means *not published* and never *not a
        false alarm*. Indexed, because excluding the false alarms is a filter every
        count over 2025 has to apply. See the module docstring.
    station_name : str or None
        ``Υπηρεσία`` — the fire station or unit that attended. 350 distinct values
        over the archive. Published in every year.
    prefecture_name : str or None
        ``Νομός`` — the prefecture. Published in every year, and 95 distinct
        values, which is more than the 51 prefectures that existed: the *nomoi*
        were abolished as an administrative tier by the 2011 Kallikratis reform
        and the service kept filing under a mixture of the old names and the new
        regional units.
    forest_district_name : str or None
        ``Δασαρχείο`` — the forest district. Published in every year, frequently
        blank in the sheet itself.
    municipality_name : str or None
        ``Δήμος`` — the municipality. Published from 2009; ``None`` for 2000-2008.
    locality_name : str or None
        ``Περιοχή`` — the locality. Published in every year, as
        ``Περιοχή - Τοποθεσία`` until 2011 and as ``Περιοχή`` from 2012, when the
        address below splits off it.
    address : str or None
        ``Διεύθυνση`` — the address or place description. Published from 2012;
        ``None`` for 2000-2011, where it is part of :attr:`locality_name`.
    area_ha_forest : float or None
        ``Δάση`` — burnt forest, in hectares.
    area_ha_forest_land : float or None
        ``Δασική Έκταση`` — burnt forest land: the wooded land that is not forest
        proper, the Greek statistic's own distinction.
    area_ha_grove : float or None
        ``Άλση`` — burnt groves.
    area_ha_grassland : float or None
        ``Χορτ/κές Εκτάσεις`` — burnt grassland.
    area_ha_reeds_marsh : float or None
        ``Καλάμια - Βάλτοι`` — burnt reed beds and marsh.
    area_ha_agricultural : float or None
        ``Γεωργικές Εκτάσεις`` — burnt agricultural land.
    area_ha_crop_residue : float or None
        ``Υπολλείματα Καλλιεργειών`` — burnt crop residue.
    area_ha_landfill : float or None
        ``Σκουπιδότοποι`` — burnt landfill.
    personnel_fire_service : int or None
        ``ΠΥΡΟΣ. ΣΩΜΑ`` — firefighters of the Fire Service. Published from 2011,
        with the whole deployment block; ``None`` for 2000-2010.
    personnel_infantry_units : int or None
        ``ΠΕΖΟΠΟΡΑ ΤΜΗΜΑΤΑ`` — members of the walking (ground) units.
    personnel_volunteers : int or None
        ``ΕΘΕΛΟΝΤΕΣ`` — volunteers.
    personnel_army : int or None
        ``ΣΤΡΑΤΟΣ`` — soldiers.
    personnel_other : int or None
        ``ΑΛΛΕΣ ΔΥΝΑΜΕΙΣ`` — other forces.
    vehicles_fire_service : int or None
        ``ΠΥΡΟΣ. ΟΧΗΜ.`` — Fire Service vehicles.
    vehicles_public_service : int or None
        Other public vehicles: ``ΟΧΗΜ. ΟΤΑ`` (local-authority) in 2011-2021 and
        ``ΟΧΗΜ. ΥΠΗΡΕΣΙΑΚΑ`` (service) from 2022. One slot renamed, stored as one
        column; see the module docstring.
    vehicles_water_tankers : int or None
        ``ΒΥΤΙΟΦΟΡΑ`` — water tankers.
    vehicles_machinery : int or None
        ``ΜΗΧΑΝΗΜΑΤΑ`` — earthmoving and other machinery.
    aircraft_helicopters : int or None
        ``ΕΛΙΚΟΠΤΕΡΑ`` — helicopters.
    aircraft_cl415 : int or None
        ``Α/Φ CL415`` — Canadair CL-415 water bombers.
    aircraft_cl215 : int or None
        ``Α/Φ CL215`` — Canadair CL-215 water bombers.
    aircraft_pzl : int or None
        ``Α/Φ PZL`` — PZL M18 Dromader light water bombers.
    aircraft_gru : int or None
        ``Α/Φ GRU.`` — the Grumman fleet. Published 2011-2024 and **not** in 2025,
        where the column is gone rather than zero.
    aircraft_leased_helicopters : int or None
        ``ΜΙΣΘ. ΕΛΙΚΟΠΤ.`` — leased helicopters. Published from 2021.
    aircraft_leased_planes : int or None
        ``ΜΙΣΘ. ΑΕΡΟΣΚ.`` — leased aeroplanes. Published from 2021.
    aircraft_other_agencies : int or None
        ``ΑΛΛΩΝ ΦΟΡΕΩΝ`` — aircraft of other agencies. Published in 2025 only.
    ignition_id : int or None
        Foreign key to the
        :class:`~src.providers.greece_ffa.ignition.GreeceFfaIgnition` holding the
        point the service was engaged at.

        Nullable, and ``NULL`` far more often than not: **205,703 of the 260,194
        fires in the archive have no point** — every fire before 2020, and 3,755 of
        the later ones for which the service published a pair of zeros.
    ignition : GreeceFfaIgnition or None
        The published point, where there is one.

    Notes
    -----
    :attr:`~src.data_model.wildfire.Wildfire.start_date_time` is the instant the
    service was **engaged** and
    :attr:`~src.data_model.wildfire.Wildfire.end_date_time` the instant the fire
    was declared extinguished. Neither is the ignition: nothing in this dataset
    says when the fire actually started.

    27,183 records — 10.4% — publish no extinction date, so the end is ``NULL`` on
    one row in ten and a burning duration computed over the archive is a duration
    over nine tenths of it.
    """

    __tablename__ = "greece_ffa_wildfire"

    __table_args__ = (
        Index("ix_greece_ffa_wildfire_year", "year"),
        Index("ix_greece_ffa_wildfire_record_number", "record_number"),
        Index("ix_greece_ffa_wildfire_incident_category", "incident_category"),
        Index("ix_greece_ffa_wildfire_ignition_id", "ignition_id"),
        Index("ix_greece_ffa_wildfire_prefecture_name", "prefecture_name"),
    )

    id: Mapped[int] = mapped_column(ForeignKey(Wildfire.id), primary_key=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    source_sheet: Mapped[str] = mapped_column(String, nullable=False)
    record_number: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    engage_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    incident_category: Mapped[str | None] = mapped_column(String, nullable=True)

    station_name: Mapped[str | None] = mapped_column(String, nullable=True)
    prefecture_name: Mapped[str | None] = mapped_column(String, nullable=True)
    forest_district_name: Mapped[str | None] = mapped_column(String, nullable=True)
    municipality_name: Mapped[str | None] = mapped_column(String, nullable=True)
    locality_name: Mapped[str | None] = mapped_column(String, nullable=True)
    address: Mapped[str | None] = mapped_column(String, nullable=True)

    area_ha_forest: Mapped[float | None] = mapped_column(Float, nullable=True)
    area_ha_forest_land: Mapped[float | None] = mapped_column(Float, nullable=True)
    area_ha_grove: Mapped[float | None] = mapped_column(Float, nullable=True)
    area_ha_grassland: Mapped[float | None] = mapped_column(Float, nullable=True)
    area_ha_reeds_marsh: Mapped[float | None] = mapped_column(Float, nullable=True)
    area_ha_agricultural: Mapped[float | None] = mapped_column(Float, nullable=True)
    area_ha_crop_residue: Mapped[float | None] = mapped_column(Float, nullable=True)
    area_ha_landfill: Mapped[float | None] = mapped_column(Float, nullable=True)

    personnel_fire_service: Mapped[int | None] = mapped_column(Integer, nullable=True)
    personnel_infantry_units: Mapped[int | None] = mapped_column(Integer, nullable=True)
    personnel_volunteers: Mapped[int | None] = mapped_column(Integer, nullable=True)
    personnel_army: Mapped[int | None] = mapped_column(Integer, nullable=True)
    personnel_other: Mapped[int | None] = mapped_column(Integer, nullable=True)

    vehicles_fire_service: Mapped[int | None] = mapped_column(Integer, nullable=True)
    vehicles_public_service: Mapped[int | None] = mapped_column(Integer, nullable=True)
    vehicles_water_tankers: Mapped[int | None] = mapped_column(Integer, nullable=True)
    vehicles_machinery: Mapped[int | None] = mapped_column(Integer, nullable=True)

    aircraft_helicopters: Mapped[int | None] = mapped_column(Integer, nullable=True)
    aircraft_cl415: Mapped[int | None] = mapped_column(Integer, nullable=True)
    aircraft_cl215: Mapped[int | None] = mapped_column(Integer, nullable=True)
    aircraft_pzl: Mapped[int | None] = mapped_column(Integer, nullable=True)
    aircraft_gru: Mapped[int | None] = mapped_column(Integer, nullable=True)
    aircraft_leased_helicopters: Mapped[int | None] = mapped_column(Integer, nullable=True)
    aircraft_leased_planes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    aircraft_other_agencies: Mapped[int | None] = mapped_column(Integer, nullable=True)

    ignition_id: Mapped[int | None] = mapped_column(ForeignKey(Ignition.id), nullable=True)

    ignition: Mapped[GreeceFfaIgnition | None] = relationship(foreign_keys=[ignition_id])

    __mapper_args__ = {
        "polymorphic_identity": "greece_ffa_wildfire",
    }

    def __repr__(self) -> str:
        return (f"GreeceFfaWildfire(id={self.id!r}, year={self.year!r}, "
                f"record_number={self.record_number!r})")
