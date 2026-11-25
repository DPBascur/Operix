# SPDX-License-Identifier: AGPL-3.0-or-later
"""Build a training-only small-FORKLIFT crop supplement without changing validation."""
import argparse
import json
import os
import random
from collections import Counter
from pathlib import Path

from PIL import Image

from prepare import CLASSES, LOCO_MANIFEST, digest

SMALL = .025
PARENT = "877449d66ce7ab28b54e3adab765d0951c2cb6cdff0ecaea156e89b76d523cf0"


def crop_labels(boxes, window):
    left, top, right, bottom = window
    w, h = right-left, bottom-top
    result = []
    for cls, (a,b,c,d) in boxes:
        x1, y1, x2, y2 = max(a,left), max(b,top), min(c,right), min(d,bottom)
        if x2 <= x1 or y2 <= y1:
            continue
        if (x2-x1)*(y2-y1) < .8*(c-a)*(d-b):
            return None
        result.append((cls, ((x1-left)/w, (y1-top)/h, (x2-left)/w, (y2-top)/h)))
    return result


def verified_negatives(source, selected, existing, target):
    if not selected:
        return []
    manifest=source/"manifest.json"
    if digest(manifest)!=LOCO_MANIFEST or len(set(selected))!=len(selected):
        raise ValueError("unexpected LOCO manifest or duplicate IDs")
    catalog={r["id"]:r for r in json.loads(manifest.read_bytes())}
    used={r["source_sha256"] for r in existing}
    result=[]
    for name in selected:
        row=catalog[name]
        expected=row["sha256"]
        source_file=source/row["export_path"]
        if (row.get("split")!="train" or row["boxes"] or expected in used
                or not row["context"].keys() & {"pallet","stillage"} or digest(source_file)!=expected):
            raise ValueError(f"not a verified unused training negative: {name}")
        relative=Path("images/train")/f"verified-negative-{name}.jpg"
        os.link(source_file,target/relative)
        label=target/"labels/train"/relative.with_suffix(".txt").name
        label.touch(exist_ok=False)
        result.append(dict(source="loco",split="train",image=relative.as_posix(),
                           boxes=[],supervised=[1,2],member=row["archive_member"],
                           capture_group=row["capture_group"],source_sha256=expected,
                           sha256=expected,label_sha256=digest(label),verified_negative_id=name))
    return result


def build(original, target, limit, *, negative_source=None, negative_ids=()):
    manifest = original/"manifest.json"
    if digest(manifest) != PARENT:
        raise ValueError("unexpected V1 manifest")
    rows = [row for row in json.loads(manifest.read_bytes()) if row["split"] != "holdout"]
    target.mkdir(parents=True)
    pool = [row for row in rows if row["split"] == "train"]
    random.Random(20261126).shuffle(pool)
    supplements = []
    for row in rows:
        image = Path(row["image"])
        label = Path("labels") / image.relative_to("images").with_suffix(".txt")
        for entry in (image, label):
            (target / entry).parent.mkdir(parents=True, exist_ok=True)
            os.link(original / entry, target / entry)
    for row in pool:
        for cls,(a,b,c,d) in row["boxes"]:
            if cls != 1 or (c-a)*(d-b) >= SMALL:
                continue
            width = max(.55, c-a+.10)
            height = max(.55, d-b+.10)
            x = max(0,min(1-width,(a+c-width)/2))
            y = max(0,min(1-height,(b+d-height)/2))
            pixels = target/row["image"]
            with Image.open(pixels) as image:
                full = image.width,image.height
                bounds = tuple(round(v * full[i%2]) for i,v in enumerate((x,y,x+width,y+height)))
                window = tuple(v/full[i%2] for i,v in enumerate(bounds))
                boxes = crop_labels(row["boxes"], window)
                if boxes is None:
                    continue
                path = Path("images/train") / ("crop-"+pixels.name)
                image.crop(bounds).save(target/path, quality=92)
            label = target/"labels/train"/path.with_suffix(".txt").name
            label.write_text("\n".join(f"{c} {(a+x)/2:.8f} {(b+y)/2:.8f} {x-a:.8f} {y-b:.8f}"
                                       for c,(a,b,x,y) in boxes), encoding="utf-8")
            supplements.append({**row, "image": path.as_posix(), "boxes": boxes,
                                "sha256": digest(target/path), "label_sha256": digest(label),
                                "crop_of": row["image"], "crop_window": window})
            break
        if len(supplements) == limit:
            break
    rows.extend(supplements)
    rows.extend(verified_negatives(negative_source,negative_ids,rows,target))
    for split in ("train", "val"):
        (target/f"{split}.txt").write_text("\n".join(str(target/r["image"]) for r in rows if r["split"]==split)+"\n")
    (target/"dataset.yaml").write_text(f'path: "{target.as_posix()}"\ntrain: train.txt\nval: val.txt\nnames:\n'
                                     + "".join(f"  {i}: {name}\n" for i,name in enumerate(CLASSES)))
    (target/"manifest.json").write_text(json.dumps(rows,indent=2))
    counts = {split:dict(Counter(CLASSES[c]+("_small" if (x-a)*(y-b)<SMALL else "_other")
                                for row in subset for c,(a,b,x,y) in row["boxes"]))
              for split,subset in {"train_original":pool,"train_crops":supplements,"validation":[r for r in rows if r["split"] in ("val","loco_val")]}.items()}
    counts.update(train_original_images=len(pool), train_crop_images=len(supplements),
                  verified_negative_ids=negative_ids)
    (target/"size-audit.json").write_text(json.dumps(counts,indent=2))
    print(json.dumps(counts,indent=2))


if __name__=="__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("original", type=lambda s: Path(s).resolve())
    parser.add_argument("output", type=lambda s: Path(s).resolve())
    parser.add_argument("--limit", type=int, default=240, choices=range(1,401))
    parser.add_argument("--negative-source", type=lambda s: Path(s).resolve())
    parser.add_argument("--negative-id",type=int,action="append",default=[])
    args = parser.parse_args()
    if bool(args.negative_id)!=bool(args.negative_source):
        parser.error("Review and request specific training negatives with their pinned source")
    build(args.original,args.output,args.limit,negative_source=args.negative_source,
          negative_ids=args.negative_id)
