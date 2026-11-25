# SPDX-License-Identifier: AGPL-3.0-or-later
"""Assemble small external evaluation sets, preserving publisher annotations."""
import argparse
import ast
import csv
import hashlib
import io
import json
import random
import zlib
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.request import urlopen
from zipfile import ZipFile

from PIL import Image
from prepare import digest, normalize_box
from ranged_zip import RangedZip

TOMIE = "https://zenodo.org/api/records/7849183/files/scenario_3_without_dist_LVL_0.zip/content"
TOMIE_SIZE = 4992152092
TALTECH = "https://data.taltech.ee/api/records/3ytc7-2z453/files/camera2.zip/container"
TALTECH_CLASSES = {1:1,2:2,3:0,5:1,6:1,7:2,8:2}


def get(url, maximum):
    with urlopen(url, timeout=25) as stream:
        data = stream.read(maximum+1)
    if not data or len(data) > maximum:
        raise ValueError("resource length outside budget")
    return data


def evenly_spaced(sequence, count):
    if len(sequence) <= count:
        return sequence
    return [sequence[(2*i+1)*len(sequence)//(2*count)] for i in range(count)]


def tomie(count):
    with ZipFile(RangedZip(TOMIE,TOMIE_SIZE)) as archive:
        rows = []
        for camera in (1, 6):
            group = f"scenario_3_without_dist_LVL_0/camera_{camera}"
            data = archive.read(f"{group}/data.csv")
            annotations = defaultdict(list)
            for item in csv.DictReader(io.StringIO(data.decode("utf-8-sig"))):
                name = Path(item["fileName"]).name
                boxes = annotations[name]
                if item["ObjectName"].startswith("FORKLIFT") and float(item["Visible"])>0:
                    boxes.append((ast.literal_eval(item["BoundingBox"]), float(item["Occlusion"])))
            available = archive.namelist()
            partition = []
            for positive in (True,False):
                members = [name for name in annotations if bool(annotations[name]) == positive
                           and f"{group}/images/{name}" in available]
                partition.extend(evenly_spaced(sorted(members,key=lambda x:int(Path(x).stem)),
                                               max(1,count//2) if positive else max(1,count//4)))
            for name in partition:
                member = f"{group}/images/{name}"
                image = archive.read(member)
                with Image.open(io.BytesIO(image)) as decoded:
                    w,h=decoded.size
                boxes = []
                for (x,y,bw,bh), occ in annotations[name]:
                    clipped=(max(0,x),max(0,y),min(w,x+bw),min(h,y+bh))
                    if clipped[0] < clipped[2] and clipped[1] < clipped[3]:
                        boxes.append((normalize_box(2,clipped,w,h),occ))
                # The paper identifies the objects as manual pallet trucks. This
                # subset's projected boxes did not pass visual registration review.
                rows.append((member,group,(),(),image,
                             {"annotation_sha256": hashlib.sha256(data).hexdigest(),
                              "unverified_projected_pallet_jack_boxes": [box for box,_ in boxes],
                              "publisher_occlusion": [occ for _,occ in boxes],
                              "publisher_crc32": archive.getinfo(member).CRC}))
        return rows


def taltech(count):
    data=get(f"{TALTECH}/camera2/annotations/instances_test.json",8_000_000)
    listing=json.loads(get(TALTECH,400_000))
    annotations=json.loads(data)
    items=defaultdict(list)
    for a in annotations["annotations"]:
        items[a["image_id"]].append(a)
    rng=random.Random(20261126)
    images=sorted(annotations["images"],key=lambda x:x["id"])
    rng.shuffle(images)
    chosen=images[:count]
    listed={i["key"]:i for i in listing["entries"]}
    def decode(row):
        member=f'camera2/test/{row["file_name"]}'
        image=get(f"{TALTECH}/{member}",5_000_000)
        if member in listed and zlib.crc32(image) != listed[member]["crc"]:
            raise ValueError("TalTech member checksum differs")
        w,h=row["width"],row["height"]
        with Image.open(io.BytesIO(image)) as decoded:
            if decoded.size != (w,h):
                raise ValueError("TalTech annotated dimensions differ")
        boxes=[]
        for a in items[row["id"]]:
            cls=TALTECH_CLASSES.get(a["category_id"])
            if cls is not None and not a["iscrowd"]:
                x,y,bw,bh=a["bbox"]
                boxes.append(normalize_box(cls,(x,y,x+bw,y+bh),w,h))
        return (member,"taltech-camera2-publisher-test",(0,1,2),boxes,image,
                {"annotation_sha256": hashlib.sha256(data).hexdigest()})
    with ThreadPoolExecutor(max_workers=3) as pool:
        return list(pool.map(decode,chosen))


def export(source, count, output):
    output.mkdir(parents=True)
    (output/"images").mkdir()
    material = tomie(count) if source=="tomie" else taltech(count)
    manifest=[]
    for member,group,supervised,boxes,raw,details in material:
        slug=hashlib.sha256(member.encode()).hexdigest()[:20]
        image=output/"images"/(slug+".jpg")
        with Image.open(io.BytesIO(raw)) as decoded:
            rgb=decoded.convert("RGB")
            rgb.thumbnail((1280,1280),Image.Resampling.LANCZOS)
            rgb.save(image,quality=94)
        manifest.append(dict(split="holdout" if source=="taltech" else "annotation_audit",
                             source=source,capture_group=group,supervised=supervised,
                             boxes=boxes,image=image.relative_to(output).as_posix(),sha256=digest(image),
                             source_sha256=hashlib.sha256(raw).hexdigest(),member=member,**details))
    (output/"manifest.json").write_text(json.dumps(manifest,indent=2))
    stats=Counter(box[0] for row in manifest for box in row["boxes"])
    metadata={"images":len(manifest),"boxes":dict(stats),"source":source,
              "reference":"10.5281/zenodo.7849183" if source=="tomie" else "10.48726/3ytc7-2z453",
              "archive_md5":"0ce7271977d88f31ab7e14f21271513c" if source=="tomie" else "03db157dcfb11d11e1bf9d6a704b45ce",
              "license":"CC BY 4.0" if source=="tomie" else "MIT","synthetic":source=="taltech",
              "evaluation_status":"usable" if source=="taltech" else "annotation_audit_only"}
    (output/"provenance.json").write_text(json.dumps(metadata,indent=2))
    print(json.dumps(metadata),flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source",choices=("tomie","taltech"))
    parser.add_argument("output",type=Path)
    parser.add_argument("--count",type=int,choices=range(8,65),default=32)
    args=parser.parse_args()
    export(args.source,args.count,args.output)
