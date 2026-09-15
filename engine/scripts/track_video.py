"""Valida YOLO11 + ByteTrack sobre un video y genera evidencia diagnóstica."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections import Counter, defaultdict
from dataclasses import asdict
from pathlib import Path

import cv2

from operix_engine.byte_tracker import ByteTrackConfig, ByteTracker
from operix_engine.tracking import Track
from operix_engine.video_processor import RecordedVideoSource, VideoSourceError
from operix_engine.yolo_detector import YoloDetector, YoloDetectorConfig


def sha256_file(path: Path) -> str:
    """Calcula SHA-256 sin cargar el archivo completo en memoria."""
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_metadata(
    *,
    width: int,
    height: int,
    fps: float | None,
    frame_count: int | None,
    expected_width: int,
    expected_height: int,
    expected_fps: float,
    expected_frames: int,
) -> None:
    """Impide validar accidentalmente una muestra distinta de la declarada."""
    if (width, height) != (expected_width, expected_height):
        raise VideoSourceError(
            f"Resolución inesperada: {width}x{height}; "
            f"se esperaba {expected_width}x{expected_height}"
        )
    if fps is None or not math.isclose(fps, expected_fps, rel_tol=0, abs_tol=0.01):
        raise VideoSourceError(f"FPS inesperados: {fps}; se esperaba {expected_fps}")
    if frame_count != expected_frames:
        raise VideoSourceError(
            f"Cantidad declarada inesperada: {frame_count}; se esperaba {expected_frames}"
        )


def _track_color(track_id: int) -> tuple[int, int, int]:
    return (
        64 + (track_id * 67) % 192,
        64 + (track_id * 97) % 192,
        64 + (track_id * 131) % 192,
    )


def draw_tracks(
    frame,
    tracks: tuple[Track, ...],
    trajectories: dict[int, list[tuple[int, int]]],
):
    """Dibuja una salida local de diagnóstico; no forma parte de la API del Motor."""
    annotated = frame.copy()
    for track in tracks:
        box = track.bounding_box
        start = (round(box.x_min), round(box.y_min))
        end = (round(box.x_max), round(box.y_max))
        center = (round((box.x_min + box.x_max) / 2), round((box.y_min + box.y_max) / 2))
        trajectories[track.track_id].append(center)
        color = _track_color(track.track_id)
        cv2.rectangle(annotated, start, end, color, 2)
        cv2.putText(
            annotated,
            f"ID {track.track_id} {track.class_name} {track.confidence:.2f}",
            (start[0], max(20, start[1] - 6)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            color,
            2,
            cv2.LINE_AA,
        )
        points = trajectories[track.track_id]
        for first, second in zip(points, points[1:]):
            cv2.line(annotated, first, second, color, 2, cv2.LINE_AA)
    return annotated


def _missing_ranges(frames: list[int]) -> list[dict[str, int]]:
    ranges = []
    for previous, current in zip(frames, frames[1:]):
        if current - previous > 1:
            ranges.append(
                {
                    "start_frame": previous + 1,
                    "end_frame": current - 1,
                    "length": current - previous - 1,
                }
            )
    return ranges


def summarize_tracks(observations: dict[int, list[int]]) -> list[dict[str, object]]:
    """Resume continuidad observable sin inventar identidad física ground-truth."""
    summaries = []
    for track_id, frames in sorted(observations.items()):
        gaps = _missing_ranges(frames)
        summaries.append(
            {
                "track_id": track_id,
                "first_frame": frames[0],
                "last_frame": frames[-1],
                "observed_frames": len(frames),
                "span_frames": frames[-1] - frames[0] + 1,
                "gaps": gaps,
                "recoveries": len(gaps),
            }
        )
    return summaries


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path)
    parser.add_argument("--weights", type=Path, required=True)
    parser.add_argument("--output-jsonl", type=Path, required=True)
    parser.add_argument("--output-video", type=Path, required=True)
    parser.add_argument("--expected-video-sha256", required=True)
    parser.add_argument("--expected-frames", type=int, required=True)
    parser.add_argument("--expected-fps", type=float, required=True)
    parser.add_argument("--expected-width", type=int, required=True)
    parser.add_argument("--expected-height", type=int, required=True)
    parser.add_argument("--conf", type=float, default=0.10)
    parser.add_argument("--device", choices=("cuda", "cpu"), default="cuda")
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--iou", type=float, default=0.70)
    parser.add_argument("--track-high-thresh", type=float, default=0.25)
    parser.add_argument("--track-low-thresh", type=float, default=0.10)
    parser.add_argument("--new-track-thresh", type=float, default=0.25)
    parser.add_argument("--track-buffer", type=int, default=30)
    parser.add_argument("--match-thresh", type=float, default=0.80)
    parser.add_argument("--no-fuse-score", action="store_true")
    args = parser.parse_args()

    try:
        video_hash = sha256_file(args.video)
    except OSError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2
    if video_hash.lower() != args.expected_video_sha256.lower():
        print("Error: SHA-256 del video no coincide con el esperado", file=sys.stderr)
        return 2

    detector_config = YoloDetectorConfig(
        weights_path=args.weights,
        confidence_threshold=args.conf,
        device=args.device,
        image_size=args.imgsz,
        iou_threshold=args.iou,
    )
    tracker_config = ByteTrackConfig(
        track_high_thresh=args.track_high_thresh,
        track_low_thresh=args.track_low_thresh,
        new_track_thresh=args.new_track_thresh,
        track_buffer=args.track_buffer,
        match_thresh=args.match_thresh,
        fuse_score=not args.no_fuse_score,
    )
    detector = YoloDetector(detector_config)
    tracker = ByteTracker(tracker_config)

    args.output_jsonl.parent.mkdir(parents=True, exist_ok=True)
    args.output_video.parent.mkdir(parents=True, exist_ok=True)
    processed_frames = 0
    frames_with_person_detections = 0
    person_detection_count = 0
    track_observations: dict[int, list[int]] = defaultdict(list)
    trajectories: dict[int, list[tuple[int, int]]] = defaultdict(list)
    class_changes: Counter[tuple[int, str, str]] = Counter()
    last_class_by_track: dict[int, str] = {}

    try:
        with RecordedVideoSource(args.video) as source:
            metadata = source.metadata()
            validate_metadata(
                width=metadata.width,
                height=metadata.height,
                fps=metadata.declared_fps,
                frame_count=metadata.declared_frame_count,
                expected_width=args.expected_width,
                expected_height=args.expected_height,
                expected_fps=args.expected_fps,
                expected_frames=args.expected_frames,
            )
            writer = cv2.VideoWriter(
                str(args.output_video),
                cv2.VideoWriter_fourcc(*"mp4v"),
                metadata.declared_fps,
                (metadata.width, metadata.height),
            )
            if not writer.isOpened():
                raise VideoSourceError("OpenCV no pudo crear el video diagnóstico")

            try:
                with args.output_jsonl.open("w", encoding="utf-8") as output:
                    for frame_index, frame in source.frames():
                        person_detections = tuple(
                            detection
                            for detection in detector.detect(frame)
                            if detection.class_name == "person"
                        )
                        if person_detections:
                            frames_with_person_detections += 1
                        person_detection_count += len(person_detections)

                        tracks = tracker.update(person_detections)
                        for track in tracks:
                            track_observations[track.track_id].append(frame_index)
                            previous_class = last_class_by_track.get(track.track_id)
                            if previous_class is not None and previous_class != track.class_name:
                                class_changes[(track.track_id, previous_class, track.class_name)] += 1
                            last_class_by_track[track.track_id] = track.class_name

                        output.write(
                            json.dumps(
                                {
                                    "frame_index": frame_index,
                                    "tracks": [asdict(track) for track in tracks],
                                },
                                ensure_ascii=False,
                            )
                            + "\n"
                        )
                        writer.write(draw_tracks(frame, tracks, trajectories))
                        processed_frames += 1
            finally:
                writer.release()
    except (VideoSourceError, ValueError, OSError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2

    if processed_frames != args.expected_frames:
        print(
            f"Error: se procesaron {processed_frames} frames; se esperaban {args.expected_frames}",
            file=sys.stderr,
        )
        return 2

    track_summaries = summarize_tracks(track_observations)
    summary = {
        "video_sha256": video_hash,
        "weights_name": args.weights.name,
        "weights_sha256": sha256_file(args.weights),
        "video_metadata": {
            "frames": processed_frames,
            "fps": args.expected_fps,
            "width": args.expected_width,
            "height": args.expected_height,
        },
        "detector_configuration": asdict(detector_config) | {"weights_path": args.weights.name},
        "tracker_configuration": asdict(tracker_config),
        "person_filter": True,
        "processed_frames": processed_frames,
        "frames_with_person_detections": frames_with_person_detections,
        "person_detections": person_detection_count,
        "track_observations": sum(len(frames) for frames in track_observations.values()),
        "unique_track_ids": len(track_observations),
        "short_tracks_at_most_two_observations": sum(
            item["observed_frames"] <= 2 for item in track_summaries
        ),
        "track_summaries": track_summaries,
        "class_changes": [
            {
                "track_id": track_id,
                "from": previous,
                "to": current,
                "count": count,
            }
            for (track_id, previous, current), count in sorted(class_changes.items())
        ],
        "output_jsonl_name": args.output_jsonl.name,
        "output_jsonl_sha256": sha256_file(args.output_jsonl),
        "output_video_name": args.output_video.name,
        "output_video_sha256": sha256_file(args.output_video),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
