"""SAM 3.1 noun phrases segmented on every clip (d4-samall, chosen Oct 28).

Chosen from a 7-phrase test on two clips: barrier-level "raised sidewalk slab"
localizes heaved slabs (and nothing on a clean clip); "uneven sidewalk" and
"cracked pavement" were dropped because SAM returns one whole-frame box for
them, the same box as "sidewalk"; "grass" was a noisy duplicate of "overgrown
vegetation". Changing this list changes spend: ~$0.33 per phrase for the 11
Oct-27 clips.
"""

# check_id -> phrases whose tracks are evidence for it
CHECK_PHRASES: dict[str, list[str]] = {
    "sidewalk_obstruction": ["trash bin", "car", "pole"],
    "surface_damage": ["raised sidewalk slab"],
    "missing_curb_ramp": ["curb ramp", "curb"],
    "sidewalk_ends": ["sidewalk"],
    "steps_without_ramp": ["stairs", "ramp"],
    "missing_handrail": ["handrail", "stairs", "ramp"],
    "round_doorknob": ["doorknob"],
    "narrow_passage": ["overgrown vegetation", "pole", "trash bin", "sidewalk"],
}

# privacy only: plate tracks blur report frames and are never shown to the agent
PLATE_PHRASE = "license plate"

SAM_PHRASES: list[str] = list(
    dict.fromkeys([p for ps in CHECK_PHRASES.values() for p in ps] + [PLATE_PHRASE])
)
