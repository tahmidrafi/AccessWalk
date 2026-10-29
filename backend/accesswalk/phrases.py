"""SAM 3.1 noun phrases segmented on every clip: the union of every check's
``evidence_phrases`` in rules.yaml, plus the license-plate phrase.

Chosen from phrase tests on the Oct-27 clips: barrier-level "raised sidewalk
slab" localizes heaved slabs (and nothing on a clean clip); "uneven sidewalk"
and "cracked pavement" were dropped because SAM returns one whole-frame box for
them, the same box as "sidewalk"; "grass" was a noisy duplicate of "overgrown
vegetation". "ramp", "curb ramp", "wheelchair ramp" and "sloped walkway" never
localized a ramp, even on clips with one, so ramps are judged by the agent from
handrail / stairs / curb / tactile paving keyframes. "tactile paving" finds the
detectable-warning pad of a curb ramp (its absence does not prove a missing
ramp). Changing this list changes spend: ~$0.33 per phrase for the 11 Oct-27
clips.
"""
from .rules import load_rules

# check_id -> phrases whose tracks are evidence for it
CHECK_PHRASES: dict[str, list[str]] = {
    check: rule.evidence_phrases for check, rule in load_rules().checks.items()
}

# privacy only: plate tracks blur report frames and are never shown to the agent
PLATE_PHRASE = "license plate"

SAM_PHRASES: list[str] = list(
    dict.fromkeys([p for ps in CHECK_PHRASES.values() for p in ps] + [PLATE_PHRASE])
)
