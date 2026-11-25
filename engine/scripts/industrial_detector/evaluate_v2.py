# SPDX-License-Identifier: AGPL-3.0-or-later
"""Select V2 on validation, evaluating localization and NMS before any external inference."""
import argparse
import json
import statistics
from pathlib import Path

from evaluate import LEGACY, error_counts, error_sheet, operating_point, predict, score
from operix_engine.person_metrics import box_iou, match_frame
from prepare import CLASSES, digest

SHAPE = (384,640)
WIDE = (480,800)
GATE = {"max_person_loss_vs_legacy_and_v1":.03, "min_forklift_precision":.60,
        "min_forklift_recall":.55, "max_forklift_recall_loss":.02,
        "min_forklift_f1_gain":0., "max_forklift_fp_per_image_gain":0.,
        "max_forklift_duplicate_increase":0, "min_external_real_positive_forklifts":20,
        "min_external_real_persons":20, "min_real_small_forklifts":12,
        "min_real_small_recall":.10}


def truth_for(rows, index):
    return {r["image"]: tuple(box for c,box in r["boxes"] if c==index)
            for r in rows if index in r["supervised"]}


def forklift_diagnostics(rows, predicted, threshold):
    truth = truth_for(rows, 1)
    close = {key: tuple(box for i,box in enumerate(boxes)
                        if any(j!=i and box_iou(box,other)>=.25 for j,other in enumerate(boxes)))
             for key,boxes in truth.items()}
    close = {key:boxes for key,boxes in close.items() if boxes}
    duplicate_iou, duplicate_scores, geometry = [], [], []
    for key,boxes in truth.items():
        available=set(range(len(boxes)))
        matched={}
        for p in sorted(predicted["forklift"][key], key=lambda p:-p.confidence):
            if p.confidence < threshold or not boxes:
                continue
            index=max(available,key=lambda i:box_iou(p.box,boxes[i]),default=None)
            if index is not None and box_iou(p.box,boxes[index])>=.50:
                matched[index]=p
                available.remove(index)
                continue
            closest=max(range(len(boxes)),key=lambda i:box_iou(p.box,boxes[i]))
            gt = boxes[closest]
            overlap = box_iou(p.box,gt)
            if overlap >= .50 and closest in matched:
                duplicate_iou.append(box_iou(p.box,matched[closest].box))
                duplicate_scores.append(p.confidence)
            elif .10 <= overlap < .50:
                a,b,c,d=gt
                x,y,w,h=p.box
                geometry.append((overlap,(w-x)/(c-a),(h-y)/(d-b),
                                 ((x+w)-(a+c))/(2*(c-a)),((y+h)-(b+d))/(2*(d-b))))
    def distribution(xs):
        return {"count":len(xs),"min":min(xs,default=None),"median":statistics.median(xs) if xs else None,
                "max":max(xs,default=None)}
    labels=("iou","width_ratio","height_ratio","center_dx_relative","center_dy_relative")
    return {"duplicate_iou_to_matched_prediction":distribution(duplicate_iou),
            "duplicate_confidence":distribution(duplicate_scores),
            "localization":{label:distribution([row[i] for row in geometry]) for i,label in enumerate(labels)},
            "overlapping_reference_images":len(close),
            "overlapping_reference_boxes":sum(map(len,close.values())),
            "overlapping_reference_tp":sum(match_frame(boxes,predicted["forklift"][key],
                                                        confidence=threshold).tp for key,boxes in close.items())}


def quality(old, legacy, candidate, *, real=False):
    def op(model, role, key):
        row=model["classes"].get(role)
        return (row["operating_point"][key] or 0.) if row else None
    gates={}
    person_tolerance=GATE["max_person_loss_vs_legacy_and_v1"]
    if "person" in candidate["classes"]:
        for k in ("precision","recall"):
            gates["person_"+k]=op(candidate,"person",k) >= max(op(legacy,"person",k), op(old,"person",k))-person_tolerance
        gates["person_ap50"]=(candidate["classes"]["person"]["ap50"] or 0.) >= max(
            x["classes"]["person"]["ap50"] or 0. for x in (legacy,old))-person_tolerance
    if "forklift" in candidate["classes"]:
        gates.update(forklift_precision=op(candidate,"forklift","precision") >= GATE["min_forklift_precision"],
             forklift_recall=op(candidate,"forklift","recall") >= max(GATE["min_forklift_recall"],
                 op(legacy,"forklift","recall")-GATE["max_forklift_recall_loss"]),
             forklift_f1=op(candidate,"forklift","f1") >= op(legacy,"forklift","f1")+GATE["min_forklift_f1_gain"],
             forklift_false_positives=op(candidate,"forklift","fp_per_image") <=
                 op(legacy,"forklift","fp_per_image")+GATE["max_forklift_fp_per_image_gain"],
             forklift_duplicates=candidate["false_positives"].get("forklift",{}).get("duplicate",0) <=
                 legacy["false_positives"].get("forklift",{}).get("duplicate",0)+GATE["max_forklift_duplicate_increase"])
    if real:
        people=candidate["classes"].get("person",{})
        trucks=candidate["classes"].get("forklift",{})
        small=trucks.get("small_recall",{})
        gates["real_person_coverage"]=people.get("instances",0)>=GATE["min_external_real_persons"]
        gates["real_forklift_coverage"]=trucks.get("instances",0)>=GATE["min_external_real_positive_forklifts"]
        gates["real_small_trucks_coverage"]=small.get("instances",0)>=GATE["min_real_small_forklifts"]
        gates["real_small_trucks_recall"]=(small.get("recall") or 0)>=GATE["min_real_small_recall"]
    return {"passed":bool(gates) and all(gates.values()),"checks":gates}


def evaluate_model(rows, predicted, thresholds, validation, reference=None):
    metrics=score(rows,predicted,thresholds,validation,reference=reference)
    report={"classes":metrics,"false_positives":error_counts(rows,predicted,metrics)}
    if "forklift" in metrics:
        report["forklift_diagnostics"]=forklift_diagnostics(rows,predicted,metrics["forklift"]["threshold"])
        report["forklift_at_common_0175"]=operating_point(truth_for(rows,1),predicted["forklift"],.175)
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("mode",choices=("validation","external"))
    for name in ("dataset","v1","person","forklift","output","preset"):
        p.add_argument(f"--{name}",type=lambda v:Path(v).resolve(),required=name!="preset")
    p.add_argument("--candidate",type=lambda v:Path(v).resolve(),action="append",required=True)
    p.add_argument("--device",choices=("0","cpu"),default="0")
    args=p.parse_args()
    validation=args.mode=="validation"
    if validation == bool(args.preset) or not validation and len(args.candidate)!=1:
        p.error("external requires one locked validation preset and one candidate")
    manifest=args.dataset/"manifest.json"
    rows=[r for r in json.loads(manifest.read_bytes()) if r["split"] in
          (("val","loco_val") if validation else ("holdout",))]
    if not rows or args.output.exists() or any(digest(args.dataset/r["image"])!=r["sha256"] for r in rows):
        raise ValueError("empty, previously scored or altered split")
    sources=sorted({r["source"] for r in rows})
    synthetic=False
    if not validation:
        provenance=json.loads((args.dataset/"provenance.json").read_bytes())
        if (sources!=[provenance["source"]] or type(provenance["synthetic"]) is not bool
                or provenance.get("evaluation_status")!="usable"):
            raise ValueError("external provenance does not match manifest")
        synthetic=provenance["synthetic"]
    categories=tuple(role for i,role in enumerate(CLASSES) if truth_for(rows,i))
    params={name:digest(getattr(args,name)) for name in ("person","forklift","v1")}
    locked=json.loads(args.preset.read_bytes()) if args.preset else None
    if locked and (locked["references"]!=params or locked["gate"]!=GATE or
                   locked["selected"]["checkpoint_sha256"]!=digest(args.candidate[0])):
        raise ValueError("checkpoint or evaluation contract changed")
    def infer(path, roles, nms, shape, selected_rows=rows):
        predictions,timing=predict(path,selected_rows,args.dataset,device=args.device,classes=roles,nms=nms,input_size=shape)
        return predictions,timing
    legacy_predictions={}
    for role, (_,nms) in LEGACY.items():
        if role in categories:
            part,_=infer(getattr(args,role),(role,),nms,SHAPE,
                         [r for r in rows if CLASSES.index(role) in r["supervised"]])
            legacy_predictions.update(part)
    legacy=evaluate_model(rows,legacy_predictions,{k:v[0] for k,v in LEGACY.items()},False)
    old_predictions,_=infer(args.v1,categories,.60,SHAPE)
    old=evaluate_model(rows,old_predictions,dict.fromkeys(categories,.175),False)
    result={"mode":args.mode,"dataset_sha256":digest(manifest),"gate":GATE,"references":params,
            "sources":sources,"external_synthetic":synthetic if not validation else None,
            "legacy":legacy,"v1":old,"images":len(rows)}
    if validation:
        result["v1_nms_sweep"] = {".60":old}
        for nms in (.45,.55):
            detections,_=infer(args.v1,categories,nms,SHAPE)
            result["v1_nms_sweep"][f"{nms:.2f}".lstrip("0")]=evaluate_model(
                rows,detections,dict.fromkeys(categories,.175),False)
    trials=[]
    configs = [(SHAPE,.45),(SHAPE,.55),(SHAPE,.60),(WIDE,.55)] if validation else [
               (locked["selected"]["shape"],locked["selected"]["nms"])]
    for checkpoint in args.candidate:
        for shape,nms in configs:
            predicted,timing=infer(checkpoint,categories,nms,shape)
            thresholds={k:None if validation else locked["selected"]["classes"][k]["threshold"] for k in categories}
            reference=max((legacy["classes"],old["classes"]),key=lambda x:x["person"]["operating_point"]["recall"]) if validation else None
            report=evaluate_model(rows,predicted,thresholds,validation,reference=reference)
            gate=quality(old,legacy,report,real=not validation and not synthetic)
            trial={**report,"checkpoint_sha256":digest(checkpoint),"checkpoint_file":str(checkpoint),
                   "shape":list(shape),"nms":nms,"timing":timing,"quality":gate}
            trials.append(trial)
            print(checkpoint.parent.parent.parent.name,shape,nms,gate,flush=True)
            if not validation:
                error_sheet(rows,predicted,report["classes"],args.dataset,args.output.with_suffix(".jpg"))
    def rank(t):
        metrics=t["classes"]
        checks=t["quality"]["checks"]
        return (t["quality"]["passed"],sum(v for k,v in checks.items() if k.startswith("person_")),
                metrics["forklift"]["operating_point"]["f1"] or 0.,
                -metrics["forklift"]["operating_point"]["fp_per_image"],-t["shape"][0])
    result.update(trials=trials,selected=max(trials,key=rank))
    if locked:
        result["validation_preset_sha256"]=digest(args.preset)
        result["promotion_eligible"]=not synthetic and result["selected"]["quality"]["passed"]
    args.output.write_text(json.dumps(result,indent=2,allow_nan=False))


if __name__=="__main__":
    main()
