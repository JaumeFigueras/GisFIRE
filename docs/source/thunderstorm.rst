Thunderstorms
=============

The thunderstorms experiment application, QGis Plugin and its data model.

To determine the characteristics of a thunderstorm and the lightnings that belong to it different clustering
algorithms and parameters have to be tested to find the best fit.

Experiments
-----------

Data Model
----------

The data model contains two parts:

    - The base data model
    - The data providers data model

The base data model is the parent (in OO programing paradigm) for the experiments, thunderstorms and lightnings and
the data providers contain the specific information that each provider retrieves, so they are children of the
base data model (in OO programing paradigm)

Base
^^^^

.. toctree::
   :maxdepth: 1
   :caption: Contents:

   src/data_model/thunderstorm_experiment
   src/data_model/thunderstorm
   src/data_model/lightning

MeteCat Data Provider
^^^^^^^^^^^^^^^^^^^^^

.. toctree::
   :maxdepth: 1
   :caption: Contents:

   src/meteocat/data_model/thunderstorm
   src/meteocat/data_model/lightning

QGis Plugin
-----------

