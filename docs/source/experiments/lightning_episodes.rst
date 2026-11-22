Lightning episodes
==================

The lightning **episodes** of one network over the zone of its nominal region, as rule 1
of :doc:`../algorithms/thunderstorm_rules` defines them: the zone's flashes cut wherever
the zone stays silent for longer than *G*. For each episode the study writes its span and
counts its zone flashes and their strokes in the zone; it also writes the minimum,
quartiles and maximum of the episodes' flashes, and how many episodes each quarter holds.

It is the tool to set *G*, which the rules leave to a study of its own: run it over the
same period once per value of *G* and compare how many episodes each gives and how large
they are. A *G* that is too long merges a summer's activity into episodes of several days
(see `An example: FMI 2018`_ below); one that is too short splits one storm's passage in
two. *G* must stay longer than the algorithms' waiting time (Cellsearch's *T*).

It writes nothing to the database. A year of a network takes seconds: FMI's 2018
(1 046 016 ground strokes) 28 s, USWFS's 2019 6 s, MeteoCat's 2020 13 s.

.. contents::
   :local:
   :depth: 1

.. automodule:: gisfire_experiments.network_lightning_study.episodes
   :members:
