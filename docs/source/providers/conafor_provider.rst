CONAFOR provider package
========================

Constants and readers shared by the CONAFOR models and any import of them: the provider
identity, the CRS all fourteen archives publish in, the fallback time zone, the two date
precisions, the published years, and the vocabulary of the one attribute
that says how a perimeter was drawn.

Five functions live here because the model, the importer and anything else reading the
shapefiles all need them, and because between them they *are* the year-to-year mapping:

:func:`~src.providers.mexico_conafor.field_value`
    Reads one model attribute out of a published feature whatever the year, through
    :data:`~src.providers.mexico_conafor.FIELD_ALIASES`. Forty-six published names across
    fourteen files, no two consecutive years alike, and nothing downstream branches on the
    year.

:func:`~src.providers.mexico_conafor.parse_date`
    Reads ``FECHAINIC`` and ``FECHALIQ`` in whichever of the four published formats they
    are in — including the 2022 layer, which uses all four at once — day-first, and
    falling back to month-first only where no day-first reading exists.

:func:`~src.providers.mexico_conafor.parse_fire_code`
    Splits the published ``CLAVEINC`` into its year, INEGI state code and sequence. All
    45,914 rows match, and in all but one of them the state code agrees with the published
    name — which the name itself does not, being spelled 34 ways for 32 states, and which
    in the 2015 layer is not even in the column called ``ESTADO``.

:func:`~src.providers.mexico_conafor.normalise` and :func:`~src.providers.mexico_conafor.is_missing`
    Case- and accent-folding for the free-text vocabularies, and the test for the several
    strings the archives write where they mean *nothing here* — ``'0'``, ``'N/A'``,
    ``'Sin dato'``, ``'Ninguna / No aplica'``.

:func:`~src.providers.mexico_conafor.split_vegetation_type`
    Separates a ``TIPVEG`` value from the INEGI code some years append to it, without
    mistaking the *Pino* of ``'Bosque de Encino - Pino'`` for one.

The module docstring is also where the dataset itself is written down — the fourteen
archives, the schema that changes every year, the key that carries the
state code, why 2010's areas do not describe 2010's polygons, and what is wrong with the
text.

.. automodule:: src.providers.mexico_conafor
   :members:
   :show-inheritance:
