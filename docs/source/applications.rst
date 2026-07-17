Applications
============

.. contents::
   :local:
   :depth: 1

Overview
--------

GisFIRE provides several command-line applications that support its data and analysis
tasks — for example importing provider data, running clustering and generating analysis
outputs. They are argparse-based scripts run as modules::

   python3 -m src.apps.<...>

Applications are grouped by purpose. Domain applications (data import and analysis) are
documented here; database/DDL helper tools have their own section
(:doc:`auxiliary_applications`).

.. note::

   Individual application pages are added as the applications are ported into
   ``src/apps/``.
