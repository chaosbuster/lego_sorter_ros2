# RecognitionResult.msg
# Published by brickognize_recognizer after API call completes.
# Topic: /recognition/result

uint64              part_id         # Matches the part_id from PartReady
string              label           # Best match label (e.g. "3001" for 2x4 brick)
float32             confidence      # 0.0 – 1.0
string              raw_json        # Full Brickognize API response (optional)
string[]            top_n_labels    # Runner-up candidates for re-check logic
float32[]           top_n_scores
