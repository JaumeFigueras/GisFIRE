Thunderstorm
============

Code
----

.. autoclass:: src.data_model.thunderstorm.ThunderstormLightningAssociation
   :members:
   :exclude-members: thunderstorm_id, lightning_id, lightning, thunderstorm, _sa_class_manager
   :undoc-members:
   :show-inheritance:
   :private-members:

.. autoclass:: src.data_model.thunderstorm.Thunderstorm
   :members:
   :exclude-members: __tablename__, id, lightnings_per_minute, travelled_distance, cardinal_direction, speed,
                     _convex_hull_4326, thunderstorm_experiment_id, thunderstorm_experiment, lightnings,
                     lightnings_associations,x_4326, y_4326, geometry_4326, date_time_start, tzinfo_date_time_start,
                     date_time_end, tzinfo_date_time_end, geometry_generator_4326, ts
   :undoc-members:
   :show-inheritance:
   :special-members: __init__,

