# Annotations (ground truth for eval)

One JSON file per clip: `data/annotations/<clip>.json`, where `<clip>` is the raw file name
without `.mp4`. These are the answers the eval compares the agent against, so mark what *you*
see, not what SAM or the agent found.

## Quick start

```bash
micromamba run -n accesswalk python scripts/annotate.py new PXL_20261027_213504057
# edit the file while watching the clip, then:
micromamba run -n accesswalk python scripts/annotate.py check
```

Watch the raw clip or `data/cache/<sha>/proxy.mp4`: both use the same timeline. Times are
**seconds as the player shows them** (one decimal is plenty).

## Format

```json
{
  "clip": "PXL_20261027_211833467",
  "annotator": "tahmid",
  "status": "done",
  "duration_s": 22.2,
  "barriers": [
    {"check": "surface_damage", "t": [11.5, 16.5], "sev": "high",
     "note": "heaved slab beside the tree", "verify": true}
  ],
  "clean": [[0.0, 5.0], [19.5, 22.2]],
  "not_applicable": ["round_doorknob", "steps_without_ramp"],
  "notes": ""
}
```

| Field | What to put |
|---|---|
| `barriers[]` | One row per barrier. `t` = start/end seconds while it is in view. |
| `check` | `sidewalk_obstruction`, `surface_damage`, `missing_curb_ramp`, `sidewalk_ends`, `steps_without_ramp`, `missing_handrail`, `round_doorknob`, `narrow_passage` |
| `sev` | `high` = likely stops a wheelchair · `medium` = passable with effort or help · `low` = minor, worth knowing |
| `note` | A few words: what and where ("bin on left half of sidewalk"). |
| `verify` | `true` if you could not judge it from the video either (height, slope, width). |
| `clean` | Stretches with **no barrier of any check**. These are what make precision honest: any finding inside one is a false positive. |
| `not_applicable` | Checks that cannot occur in this clip (no entrance → `round_doorknob`, `steps_without_ramp`, `missing_handrail`; no crossing → `missing_curb_ramp`). Any finding of these checks is a false positive. |
| `status` | `draft` while working; `done` when finished. **Only `done` files are scored.** |

## Tips for speed

- Leave unsure stretches unlabelled (neither barrier nor clean). They are not scored.
- One long barrier is fine when the same problem continues (a run of broken slabs).
- A curb ramp *present* at a crossing is not a barrier: mark the stretch clean.
- Do not look at the agent's report first (it biases the labels).

## How eval scores it (d7)

A finding matches a barrier when the check is the same and its frame time is inside `t`
(±1 s). Recall = barriers with at least one matching finding. Precision counts a finding as
wrong when it falls inside a `clean` range or its check is `not_applicable`. Findings
elsewhere are not scored.

## Files

- `PXL_20261027_211833467.json` is an example draft written by Claude from blurred frames.
  Check it against the video and set `status` to `done` (or fix it) before it counts.
