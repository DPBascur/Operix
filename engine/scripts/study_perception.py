# Copyright (C) 2026 Daniel Felipe Peña Bascur
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Compara COCO n/s/m/l en un manifiesto DEVELOPMENT_ONLY, sin escribir producción."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import datetime, timezone
import gc
import hashlib
import json
from pathlib import Path
import platform
import time

import cv2
import torch
import ultralytics
from operix_engine.byte_tracker import ByteTracker
from operix_engine.candidate_transport import candidate_payloads
from operix_engine.dual_perception import ClassPerceptionChannel, DualPerception
from operix_engine.operational_config import OperationalConfig, RuleConfig, load_operational_config
from operix_engine.person_metrics import Prediction
from operix_engine.perception_study import checked_input, class_id, metrics, timing_summary, track_summary, validate_manifest, development_path
from operix_engine.proximity_geometry import PROXIMITY_GEOMETRY_VERSION
from operix_engine.rules import RuleEngine
from operix_engine.spatiotemporal import SpatiotemporalAnalyzer
from operix_engine.visualization import OpenCvRenderer, TrajectoryAccumulator
from operix_engine.video_event_pipeline import _visible_tracks
from operix_engine.yolo_detector import YoloDetector, YoloDetectorConfig


def write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.manifest = development_path(args.manifest)
    args.output = development_path(args.output)
    if args.output.resolve().is_relative_to(Path(__file__).resolve().parents[2]):
        raise ValueError("Los resultados deben quedar fuera del repositorio")
    args.output.mkdir(exist_ok=False)
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    cfg = validate_manifest(manifest)
    if not torch.cuda.is_available():
        raise RuntimeError("Se requiere CUDA para este estudio")
    for row in manifest["samples"]:
        if row["source"] not in ("KEREMBERKE","TEST3"):
            raise ValueError("Fuente no incluida en la selección de desarrollo")
        checked_input(row["image"],row["sha256"])
    for row in manifest["videos"]:
        checked_input(row["path"],row["sha256"])
        checked_input(row["config"],row["config_sha256"])
    for model in manifest["models"]:
        checked_input(model["weights"],model["sha256"])
    checked_input(manifest["forklift_weights"],manifest["forklift_sha256"])
    identity = hashlib.sha256(args.manifest.read_bytes()).hexdigest()
    write(args.output/"campaign.json", {"study_id":manifest["study_id"],"manifest_sha256":identity,
          "started_utc":datetime.now(timezone.utc).isoformat(),"torch":torch.__version__,
          "ultralytics":ultralytics.__version__,"opencv":cv2.__version__,"python":platform.python_version(),
          "gpu":torch.cuda.get_device_name(0),"vram_bytes":torch.cuda.get_device_properties(0).total_memory,
          "geometry":PROXIMITY_GEOMETRY_VERSION,"timing":"perf_counter_ns, CUDA synchronize, FP32 batch1",
          "gpu_utilization":None,"gpu_utilization_reason":"No se añade muestreador de utilización; VRAM medida con allocator PyTorch"})
    results=[]
    for model_entry in manifest["models"]:
        model_dir=args.output/model_entry["id"]; model_dir.mkdir()
        start=time.perf_counter_ns()
        detector=YoloDetector(YoloDetectorConfig(Path(model_entry["weights"]),.10,"cuda",640,.70))
        parameters=sum(p.numel() for p in detector._model.model.parameters())
        names=detector.class_names
        mapped={name:class_id(names,name) for name in ("person","truck")}
        image=cv2.imread(manifest["samples"][0]["image"])
        def infer(frame):
            torch.cuda.synchronize();begin=time.perf_counter_ns()
            predictions=detector.detect(frame)
            torch.cuda.synchronize()
            return predictions,(time.perf_counter_ns()-begin)/1e9
        for _ in range(cfg["warmup"]): infer(image)
        cold_s=(time.perf_counter_ns()-start)/1e9
        torch.cuda.reset_peak_memory_stats()
        predictions={}; raw=[]; latencies=[]
        for repetition in range(cfg["repetitions"]):
            rep=[]
            for sample in manifest["samples"]:
                frame=cv2.imread(sample["image"])
                if frame is None or frame.shape[:2] != (sample["height"],sample["width"]):
                    raise ValueError("Imagen inválida o con dimensiones distintas")
                detected,elapsed=infer(frame);rep.append(elapsed)
                if repetition==0:
                    selected=tuple(d for d in detected if d.class_name=="person")
                    predictions[sample["id"]]=tuple(Prediction((d.bounding_box.x_min,d.bounding_box.y_min,d.bounding_box.x_max,d.bounding_box.y_max),d.confidence) for d in selected)
                    raw.append({"id":sample["id"],"person":[asdict(d) for d in selected],"inference_s":elapsed})
            latencies.extend(rep)
        quality=metrics(manifest["samples"],predictions)
        strata={source:metrics([s for s in manifest["samples"] if s["source"]==source],
                              {s["id"]:predictions[s["id"]] for s in manifest["samples"] if s["source"]==source}) for source in ("KEREMBERKE","TEST3")}
        inference=timing_summary(latencies)
        allocated=torch.cuda.max_memory_allocated();reserved=torch.cuda.max_memory_reserved()
        if detector.model_device != "cuda:0": raise RuntimeError("El modelo no quedó en CUDA:0")
        write(model_dir/"predictions.json",raw)
        forklift=YoloDetector(YoloDetectorConfig(Path(manifest["forklift_weights"]),.45,"cuda",640,.55))
        infer_fork = forklift.detect(image);torch.cuda.synchronize()
        torch.cuda.reset_peak_memory_stats()
        pipelines=[]
        for video in manifest["videos"]:
            config=load_operational_config(video["config"])
            # Mismos parámetros del fixture existente, solo diagnóstico offline.
            pair=manifest["diagnostic_pair_fixture"]
            offline_config=OperationalConfig(config.schema_version,config.view_id,config.zones,config.rules+(
                RuleConfig("TEST_DATA_PAIR",1,True,{"kind":"person_forklift_proximity","zone_id":config.zones[0].zone_id,
                           "max_distance":pair["max_distance"],"minimum_duration_seconds":pair["minimum_duration_seconds"]}),))
            all_times=[]; repetitions=[]
            for repetition in range(cfg["pipeline_repetitions"]):
                cap=cv2.VideoCapture(video["path"])
                if not cap.isOpened(): raise RuntimeError("No se pudo abrir demo")
                width,height=int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                fps=cap.get(cv2.CAP_PROP_FPS)
                perception=DualPerception(person=ClassPerceptionChannel("person",detector,ByteTracker()),forklift=ClassPerceptionChannel("forklift",forklift,ByteTracker()))
                analyzer=SpatiotemporalAnalyzer(width=width,height=height,fps=fps,zones=config.zones,proximity_roles=config.proximity_roles)
                rules=RuleEngine(offline_config);renderer=OpenCvRenderer()
                histories={name:TrajectoryAccumulator() for name in ("person","forklift")}
                seen={name:defaultdict(list) for name in histories};counts=Counter();events=Counter();event_frames=[]
                paired=[]; rows=[];index=0;stages=defaultdict(list);rep_times=[]
                try:
                    while True:
                        begin=time.perf_counter_ns();ok,frame=cap.read();decoded=time.perf_counter_ns()
                        if not ok:break
                        observed,timing=perception.process(frame,synchronize=torch.cuda.synchronize)
                        tracked=time.perf_counter_ns()
                        visible,_,_ = _visible_tracks(observed.person_tracks+observed.forklift_tracks,width,height)
                        spatial=analyzer.update(index,visible)
                        rule_result=rules.evaluate(spatial);ruled=time.perf_counter_ns()
                        annotated=frame
                        for zone in config.zones: annotated=renderer.render_zone(annotated,zone)
                        for name in histories:
                            tracks=getattr(observed,f'{name}_tracks')
                            annotated=renderer.render_tracks(annotated,tracks,histories[name].update(index,tracks))
                        annotated=renderer.render_proximity(annotated,spatial,rule_result)
                        finished=time.perf_counter_ns()
                        if index>=cfg["pipeline_warmup_frames"]:
                            total=(finished-begin)/1e9;all_times.append(total);rep_times.append(total)
                            for stage,value in {"decode":(decoded-begin)/1e9,"person_inference":timing.person_inference_s,"forklift_inference":timing.forklift_inference_s,"tracking":timing.person_tracking_s+timing.forklift_tracking_s,"spatial_rules":(ruled-tracked)/1e9,"renderer":(finished-ruled)/1e9}.items():stages[stage].append(value)
                        for name in histories:
                            counts[name]+=len(getattr(observed,f'{name}_detections'))
                            for track in getattr(observed,f'{name}_tracks'):seen[name][track.track_id].append(index)
                        frame_candidates=candidate_payloads(rule_result.candidates)
                        for candidate in frame_candidates:
                            events[candidate['candidate_kind']]+=1
                            event_frames.append(candidate)
                        pair_evaluations=[e for e in rule_result.evaluations if hasattr(e,'interaction')]
                        paired.append(len(pair_evaluations))
                        if repetition==0:
                            rows.append({'frame':index,'tracks':{name:[asdict(t) for t in getattr(observed,f'{name}_tracks')] for name in histories},'pair_evaluations':len(pair_evaluations),'total_s':(finished-begin)/1e9})
                            if index in cfg["visual_frames"]:cv2.imwrite(str(model_dir/f'{video["id"]}-frame-{index:04d}.png'),annotated)
                        index+=1
                finally:cap.release()
                repetitions.append({'frames':index,'measured_frames':len(rep_times),'timing':timing_summary(rep_times),'stages_mean_ms':{k:sum(v)/len(v)*1000 for k,v in stages.items()},'detections':dict(counts),'tracking':{name:track_summary(seen[name]) for name in histories},'pair_evaluations':sum(paired),'events':dict(events),'event_frames':event_frames})
                if repetition==0:write(model_dir/f'{video["id"]}-observations.json',rows)
            pipelines.append({'video':video['id'],'timing':timing_summary(all_times),'repetitions':repetitions})
        result={'model':model_entry,'parameters':parameters,'verified_class_mapping':mapped,'load_and_initial_warmup_s':cold_s,'person_metrics':quality,'by_source':strata,'person_predictions':sum(len(v) for v in predictions.values()),'inference':inference,'person_peak_allocated_bytes':allocated,'person_peak_reserved_bytes':reserved,'dual_peak_allocated_bytes':torch.cuda.max_memory_allocated(),'dual_peak_reserved_bytes':torch.cuda.max_memory_reserved(),'pipeline':pipelines}
        write(model_dir/"summary.json",result);results.append(result)
        write(args.output/"results.json",results)
        print(json.dumps({'model':model_entry['id'],'quality':quality,'inference_fps':inference['fps'],'pipeline_fps':{p['video']:p['timing']['fps'] for p in pipelines}},ensure_ascii=False),flush=True)
        del perception,detector,forklift,infer_fork
        gc.collect();torch.cuda.empty_cache()
    write(args.output/"completed.json",{'finished_utc':datetime.now(timezone.utc).isoformat(),'models':len(results)})


if __name__ == "__main__":
    main()
