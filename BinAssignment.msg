# BinAssignment.msg
# Published by bin_router with the target bin for a recognised part.
# Topic: /routing/assignment

uint64              part_id         # Matches the part_id chain
string              bin_id          # Target bin identifier
string              reason          # "normal" | "unknown" | "overflow" | "reject"
