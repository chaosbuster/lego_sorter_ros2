# PartZone.msg
# Published by part_tracker / breakbeam_tracker as a part moves between zones.
# Topic: /tracking/part_zone

uint64                    part_id   # Unique part identifier
string                    zone      # Zone name: "singulation" | "inspection" | "diverter_N"
builtin_interfaces/Time   stamp     # When the transition was detected
