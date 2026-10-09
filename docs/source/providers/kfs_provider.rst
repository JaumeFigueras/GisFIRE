Korea Forest Service provider package
=====================================

Constants and functions shared by the Korea Forest Service model and the import
application: the provider identity, the time zone, the published header, the province
and office names in English, the two published cause vocabularies, the eighteen cause
classes and the four shared fire causes they reduce to, and the reasons an end is not
stored.

Four functions live here because both the model and the importer need them:
:func:`~src.providers.south_korea_kfs.romanize`, the Revised Romanization of a place
name; :func:`~src.providers.south_korea_kfs.cause`, which translates and classifies a
published cause text and refuses one it does not know;
:func:`~src.providers.south_korea_kfs.is_suspected`; and
:func:`~src.providers.south_korea_kfs.end_date_problem`.

The module docstring is also where the dataset itself is written down — the release, the
five place names and what a blank one means, the fourteen impossible ends, the three cause
columns and which of them carries the cause.

.. automodule:: src.providers.south_korea_kfs
   :members:
   :show-inheritance:

The cause table
---------------

The 453 published cause texts, each with its English translation and class.

.. automodule:: src.providers.south_korea_kfs.causes
