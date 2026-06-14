# PartReady.msg
# Published by breakbeam_tracker (and singulation_controller during testing)
# when a single part enters the inspection zone.
# Topic: /singulation/part_ready

uint64              part_id         # Unique ID assigned by part_tracker
builtin_interfaces/Time stamp       # When the event occurred
string              zone            # e.g. "inspection", "diverter_1"
float32             conveyor_speed  # Motor speed at event time (RPM)
