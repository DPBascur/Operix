"""Compare track and rule outcomes from one backend proof at native nominal cadence."""

import argparse
import json
from pathlib import Path

from operix_engine.byte_tracker import ByteTrackConfig, ByteTracker
from operix_engine.detection import BoundingBox, Detection
from operix_engine.motion import MotionConfig
from operix_engine.operational_config import OperationalConfig, RuleConfig, Zone
from operix_engine.rules import PairRuleEvaluation, RuleEngine
from operix_engine.spatiotemporal import SpatiotemporalAnalyzer
from operix_engine.video_event_pipeline import _visible_tracks


ROLES = ("person", "forklift")
CONFIG = OperationalConfig(1, "qa_backend_parity", (
    Zone("frame", "Encuadre de prueba", ((0, 0), (1, 0), (1, 1), (0, 1))),
), (
    RuleConfig("presence", 1, True, {
        "kind": "zone_dwell", "zone_id": "frame", "class_name": "person", "min_duration_s": .5,
    }),
    RuleConfig("proximity", 1, True, {
        "kind": "person_forklift_proximity", "zone_id": "frame", "distance_unit": "normalized",
        "max_distance": .8, "minimum_duration_seconds": .25, "exclude_possible_occupant": True,
    }),
), motion=MotionConfig("normalized", .4, 4, .15, .01, .03, .015, True))


def replay(detections, width, height, fps):
    trackers = [ByteTracker(ByteTrackConfig()) for _ in ROLES]
    analyzer = SpatiotemporalAnalyzer(width=width, height=height, fps=fps, zones=CONFIG.zones,
                                      proximity_roles=CONFIG.proximity_roles, motion=CONFIG.motion,
                                      observe_occupants=CONFIG.observe_occupants)
    rules = RuleEngine(CONFIG)
    frame_states, events, pairs = {}, [], {}
    for person, forklift in zip(*(detections[role] for role in ROLES), strict=True):
        index = person["frame_index"]
        if index != forklift["frame_index"]:
            raise ValueError("PERSON and FORKLIFT came from different frames")
        tracks = []
        for tracker, row in zip(trackers, (person, forklift), strict=True):
            observations = tuple(Detection(item["class_id"], item["class_name"], item["confidence"],
                                           BoundingBox(**item["bounding_box"])) for item in row["detections"])
            tracks.extend(tracker.update(observations))
        visible, _, _ = _visible_tracks(tuple(tracks), width, height)
        spatial = analyzer.update(index, visible, timestamp_s=index / fps)
        frame_states[index] = {
            "tracks": sorted((obj.class_name, obj.track_id) for obj in spatial.objects),
            "membership": sorted((obj.class_name, obj.track_id, zone.zone_id, zone.inside)
                                 for obj in spatial.objects for zone in obj.zones),
            "motion": sorted((obj.track_id, obj.motion.state) for obj in spatial.objects if obj.motion is not None),
            "occupancy": sorted((person_id.track_id, forklift_id.track_id, state.state)
                                for (person_id, forklift_id), state in spatial.occupant_associations.items()),
        }
        result = rules.evaluate(spatial)
        for evaluation in result.evaluations:
            if isinstance(evaluation, PairRuleEvaluation):
                pair = evaluation.interaction
                key = (index, pair.person.track_id, pair.forklift.track_id)
                pairs[key] = (evaluation.observed_normalized_distance, evaluation.satisfied, evaluation.reason)
        for event in result.candidates:
            pair = getattr(event, "interaction", None)
            ids = (pair.person.track_id, pair.forklift.track_id) if pair else (event.track_id,)
            events.append((index, event.rule_id, event.rule_version, *ids))
    return frame_states, sorted(events), pairs


def compare(reference, candidate):
    ref_frames, ref_events, ref_pairs = reference
    frames, events, pairs = candidate
    if ref_frames.keys() != frames.keys():
        raise ValueError("The compared reports must cover the same frame indices")
    common_pairs = ref_pairs.keys() & pairs.keys()
    return {
        "frames": len(frames),
        "differences_by_frame": {
            metric: [index for index in frames if frames[index][metric] != ref_frames[index][metric]]
            for metric in ("tracks", "membership", "motion", "occupancy")
        },
        "reference_motion_observations": sum(len(row["motion"]) for row in ref_frames.values()),
        "reference_occupancy_observations": sum(len(row["occupancy"]) for row in ref_frames.values()),
        "identical_event_keys": ref_events == events,
        "reference_event_keys": ref_events,
        "candidate_event_keys": events,
        "matched_pair_evaluations": len(common_pairs),
        "identical_pair_keys": ref_pairs.keys() == pairs.keys(),
        "different_pair_outcomes": sum(ref_pairs[key][1:] != pairs[key][1:] for key in common_pairs),
        "max_normalized_distance_delta": max((abs(ref_pairs[key][0] - pairs[key][0]) for key in common_pairs), default=None),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path, help="Completed benchmark_backends.py report with approved media provenance")
    args = parser.parse_args()
    report = json.loads(args.report.read_bytes())
    results = []
    for clip, case in zip(report["clips"], report["comparisons"], strict=True):
        height, width, _ = case["decode"]["shape_hwc"]
        fps = clip["provenance"]["average_fps"]
        reference = replay(case["operational_detections"], width, height, fps)
        for trial, sample in enumerate(case["candidate"], 1):
            candidate = replay(sample["detections"], width, height, fps)
            results.append({"clip": Path(clip["path"]).name, "trial": trial,
                            "nominal_fps": fps, **compare(reference, candidate)})
    print(json.dumps({"replay": report["protocol"]["backend"], "results": results}, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
