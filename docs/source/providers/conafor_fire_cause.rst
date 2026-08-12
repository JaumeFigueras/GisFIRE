CONAFOR fire cause
==================

The catalogue of why CONAFOR says a Mexican fire started: the 179 ``(CAUSA, CAUSAESP)``
pairs the fourteen published layers contain between them, which fold to **141 stored
classifications** once the null tokens in either half become ``NULL``. See
:doc:`conafor_wildfire` for the fire that links to it, and :doc:`icnf_fire_cause` for the
same idea applied to a provider that does publish a code.

Because this one does not. The ICNF publishes ``Causa_Cod`` beside its two names; CONAFOR
publishes **no code at all**, and the cause is free text typed sixty-four different ways
over fourteen years for perhaps twenty real causes — ``'Fogatas'`` beside ``'fogatas'``
beside ``'Fogata'`` beside ``'Fogatas\n'``, ``'Tormenta Elcetrica'`` beside ``'Descargas
electricas'`` beside ``'Naturales'``.

Case- and accent-folding gets sixty-four down to forty-three and stops there. What is left
is synonymy, and it is what this table resolves — once, in a place where it can be argued
with, rather than in every query that groups by cause.

:attr:`~src.providers.mexico_conafor.fire_cause.ConaforFireCause.cause_normalised` is the
column to group by; :attr:`~src.providers.mexico_conafor.fire_cause.ConaforFireCause.cause`
is what the file said, kept byte for byte so a row can always be checked against it.

.. note::

   The natural key is the ``(cause, specific_cause)`` pair, and ``CAUSAESP`` is published
   by neither 2011 nor any year from 2020 — so ``specific_cause`` is ``NULL`` on the
   classifications covering 27,624 of the 45,914 fires, three in five.

   Uniqueness is therefore enforced by **two partial unique indexes** rather than one
   ``UNIQUE`` constraint. Two ``NULL``\ s are not equal in SQL, so a plain
   ``UNIQUE (cause, specific_cause)`` would admit ``('Fogatas', NULL)`` twice and the
   catalogue would grow a duplicate every time a layer without the column was imported.

.. automodule:: src.providers.mexico_conafor.fire_cause
   :members:
   :show-inheritance:
