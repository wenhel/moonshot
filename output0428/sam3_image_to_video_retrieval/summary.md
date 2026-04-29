# SAM 3.1 image-as-prompt video retrieval (no concat hack)

Approach: overlay.png is frame 0 of a SAM 3.1 multiplex video session.
Boxes from parts_db.json (in overlay coords) are added as prompts at
frame 0; SAM 3.1 propagates the corresponding objects through every
frame of the actual video.

- Reference parts: [(1, 'split_plate_front', 1), (2, 'split_plate_rear', 2), (3, 'five_inch_arm', 3)]
- Render stride: every 30th video frame

## Per clip

| clip | video_frames | rendered | frames_with_dets | propagate_s |
|---|---|---|---|---|
| clip_000.mp4 | 3 | 3 | 0 | 15.97 |

## How to inspect

Each `clip_NNN/renders/vidframe_*.jpg` shows a video frame with the
tracked objects overlaid (color-coded by obj_id). If the masks land
on the actual drone parts, image-prompt video retrieval works.

`clip_NNN/session_frames/0.jpg` is the resized manual overlay — the
frame on which the box prompts were seeded (purple in renders).
