# SPDX-License-Identifier: AGPL-3.0-or-later
"""Prepare a bounded, auditable 3-class research dataset outside the product tree."""
import argparse
import hashlib
import io
import json
import math
import random
from collections import Counter, defaultdict
from pathlib import Path
from zipfile import ZipFile

from PIL import Image, ImageDraw

CLASSES = ("person", "forklift", "pallet_jack")
PPE_IDS = {5: 0, 10: 1}
PPE_URL = "https://github.com/ultralytics/assets/releases/download/v0.0.0/construction-ppe.zip"
RF_ROOT = "https://huggingface.co/datasets/keremberke/forklift-object-detection/resolve/2c0f4e8e9085f3079b80137e780aab0e54936cfc/data/"
PINNED = {
    "construction-ppe.zip": (PPE_URL, "e5817aa9c73f33e525d76ca6bc6af4e4eac9dcea9bcfef1cfd1a71c09fbc1232"),
    "roboflow-train.zip": (RF_ROOT + "train.zip", "bf5c3364b39160d4d212a454b9a7689f8b89e81eab3ea3da50031c4e7bf92fe0"),
    "roboflow-valid.zip": (RF_ROOT + "valid.zip", "0f8013a437dc85e8f218b252ce8cffa32b2724c8021cf6b983febd3a9145d53f"),
    "roboflow-test.zip": (RF_ROOT + "test.zip", "9baace711b989e84c731fa3b3e2b45f8a636880d475c2c2d6b91b8cdff803cbe"),
}
LOCO_MANIFEST = "97d5cb77b28571ff2e172e2c740902cce4251ef7841623c806bea4c15d03e936"
SEED = 20261125


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def fingerprint(image):
    gray = image.convert("L")
    patterns = []
    for rotated in (gray, gray.transpose(Image.Transpose.ROTATE_90)):
        pixels = list(rotated.resize((9, 8), Image.Resampling.LANCZOS).tobytes())
        bits = sum((pixels[y * 9 + x] > pixels[y * 9 + x + 1]) << (y * 8 + x)
                   for y in range(8) for x in range(8))
        patterns.append(bits)
    return tuple(patterns)


def normalize_box(cls, xyxy, width, height):
    x1, y1, x2, y2 = xyxy
    if (not all(math.isfinite(v) for v in xyxy)
            or not (-1 <= x1 < x2 <= width + 1 and -1 <= y1 < y2 <= height + 1)):
        raise ValueError(f"invalid box {xyxy} at {width}×{height}")
    return cls, (max(x1, 0) / width, max(y1, 0) / height,
                 min(x2, width) / width, min(y2, height) / height)


def yolo_boxes(raw, width, height):
    for line in raw.decode("utf-8-sig").splitlines():
        if not line.strip():
            continue
        cls, x, y, w, h = line.split()
        index = int(cls)
        if index not in range(12):
            raise ValueError(f"unknown PPE class {index}")
        if index in PPE_IDS:
            x, y, w, h = map(float, (x, y, w, h))
            yield normalize_box(PPE_IDS[index],
                                ((x - w/2)*width, (y - h/2)*height,
                                 (x + w/2)*width, (y + h/2)*height), width, height)


def coco_boxes(items, width, height, indices):
    for item in items:
        if item.get("iscrowd"):
            raise ValueError("crowd annotations require a separate evaluation policy")
        x, y, w, h = item["bbox"]
        yield normalize_box(indices[item["category_id"]], (x, y, x+w, y+h), width, height)


def source_rows(archives, loco):
    # A publisher-level holdout remains isolated even when capture groups are unavailable.
    for name in ("roboflow-train.zip", "roboflow-valid.zip", "roboflow-test.zip"):
        with ZipFile(archives / name) as z:
            coco = json.loads(z.read("_annotations.coco.json"))
            indices = {c["id"]: CLASSES.index(c["name"]) for c in coco["categories"]}
            assert set(indices.values()) == {0, 1}
            allowed = {v["id"] for v in coco["licenses"] if v["name"] == "CC BY 4.0"}
            categories = defaultdict(list)
            for item in coco["annotations"]:
                categories[item["image_id"]].append(item)
            for row in coco["images"]:
                assert row["license"] in allowed
                f = row["file_name"]
                w, h = row["width"], row["height"]
                yield ("roboflow", "holdout", name + "/" + f, name, (0, 1), z.read(f),
                       tuple(coco_boxes(categories[row["id"]], w, h, indices)), (w, h))
    with ZipFile(archives / "construction-ppe.zip") as z:
        assert "CC BY 4.0" in z.read("construction-ppe/README.md").decode("utf-8")
        for split in ("val", "train"):
            prefix = f"construction-ppe/images/{split}/"
            for path in sorted(p for p in z.namelist() if p.startswith(prefix) and p.endswith(".jpg")):
                member = path.replace("/images/", "/labels/").removesuffix(".jpg") + ".txt"
                data = z.read(path)
                with Image.open(io.BytesIO(data)) as image:
                    w, h = image.size
                yield ("ppe", split, path, f"publisher-{split}", (0, 1), data,
                       tuple(yolo_boxes(z.read(member), w, h)), (w, h))
    assert digest(loco / "manifest.json") == LOCO_MANIFEST
    rows = json.loads((loco / "manifest.json").read_bytes())
    rng = random.Random(SEED)
    for split, targets in (("val", (160, 180, 60)), ("train", (400, 420, 120))):
        strata = ([], [], [])
        for row in rows:
            if row.get("split") != split:
                continue
            cls = {box[0] for box in row["boxes"]}
            if 0 in cls:
                strata[0].append(row)
            elif 1 in cls:
                strata[1].append(row)
            elif row.get("context", {}).keys() & {"pallet", "stillage"}:
                strata[2].append(row)
        for pool, limit in zip(strata, targets, strict=True):
            rng.shuffle(pool)
            for row in pool[:limit]:
                w, h = row["width"], row["height"]
                boxes = tuple(normalize_box(cls+1, (x,y,x+bw,y+bh), w,h)
                              for cls,x,y,bw,bh in row["boxes"])
                data = (loco / row["export_path"]).read_bytes()
                if hashlib.sha256(data).hexdigest() != row["sha256"]:
                    raise ValueError(f"LOCO source digest mismatch: {row['id']}")
                yield ("loco", "loco_val" if split == "val" else "train", str(row["id"]),
                       row["capture_group"], (1, 2), data, boxes, (w,h))


def export(args):
    if args.output.exists():
        raise FileExistsError(args.output)
    sources = {}
    for filename, (url, expected) in PINNED.items():
        actual = digest(args.archives / filename)
        if actual != expected:
            raise ValueError(f"archive digest mismatch: {filename} {actual}")
        sources[filename] = {"url": url, "sha256": actual, "license": "CC-BY-4.0"}
    sources["loco"] = {"url": "https://github.com/tum-fml/loco", "license": "CC0-1.0",
                       "manifest_sha256": LOCO_MANIFEST}
    manifest, excluded = [], []
    exact, seen, previews = {}, [], defaultdict(list)
    for source, split, member, group, observed, data, boxes, size in source_rows(args.archives, args.loco):
        with Image.open(io.BytesIO(data)) as container:
            image = container.convert("RGB")
        if image.size != size or len(set(boxes)) != len(boxes):
            raise ValueError(f"size mismatch or conflicting duplicate boxes: {source}/{member}")
        image_sha = hashlib.sha256(data).hexdigest()
        pixels = hashlib.sha256(f"{size}:".encode() + image.tobytes()).hexdigest()
        hashed = fingerprint(image)
        hit = exact.get(pixels)
        near = next((row for fp, row in seen if row["split"] != split
                     and (fp[0] ^ hashed[0]).bit_count() <= 4
                     and (fp[1] ^ hashed[1]).bit_count() <= 6), None)
        if hit or near:
            other = hit or near
            excluded.append({"source": source, "split": split, "member": member,
                             "duplicate_of": other["image"], "exact_pixels": bool(hit),
                             "label_disagreement": bool(hit and boxes != other["boxes"])})
            continue
        stem = f"{source}-{image_sha[:20]}"
        image_path = args.output / "images" / split / (stem + ".jpg")
        label_path = args.output / "labels" / split / (stem + ".txt")
        image_path.parent.mkdir(parents=True, exist_ok=True)
        label_path.parent.mkdir(parents=True, exist_ok=True)
        image.thumbnail((960, 960), Image.Resampling.LANCZOS)
        image.save(image_path, quality=92)
        rows = [f"{cls} {(a+c)/2:.8f} {(b+d)/2:.8f} {c-a:.8f} {d-b:.8f}" for cls,(a,b,c,d) in boxes]
        label_path.write_text("\n".join(rows), encoding="utf-8")
        entry = {"source": source, "split": split, "member": member, "capture_group": group,
                 "supervised": observed, "image": image_path.relative_to(args.output).as_posix(),
                 "source_sha256": image_sha, "sha256": digest(image_path),
                 "label_sha256": digest(label_path), "boxes": boxes}
        manifest.append(entry)
        exact[pixels] = entry
        seen.append((hashed, entry))
        if split == "train" and boxes and len(previews[source]) < 8:
            image.thumbnail((240, 155))
            draw = ImageDraw.Draw(image)
            for cls,(a,b,c,d) in boxes:
                draw.rectangle((a*image.width,b*image.height,c*image.width,d*image.height),
                               outline=("cyan","yellow","violet")[cls], width=2)
            previews[source].append(image)
    for split in {r["split"] for r in manifest}:
        (args.output / f"{split}.txt").write_text("\n".join(str(args.output / r["image"])
            for r in manifest if r["split"] == split) + "\n", encoding="utf-8")
    (args.output / "dataset.yaml").write_text(
        f'path: "{args.output.as_posix()}"\ntrain: train.txt\nval: val.txt\nnames:\n'
        + "".join(f"  {i}: {name}\n" for i,name in enumerate(CLASSES)), encoding="utf-8")
    stats = defaultdict(Counter)
    for row in manifest:
        key = f'{row["source"]}/{row["split"]}'
        stats[key]["images"] += 1
        stats[key]["empty_labels"] += not row["boxes"]
        stats[key].update(CLASSES[cls] for cls, _ in row["boxes"])
    sheet = Image.new("RGB", (960, len(previews)*360), (23, 29, 43))
    for row, (source, images) in enumerate(sorted(previews.items())):
        ImageDraw.Draw(sheet).text((10, row*360+8), f"{source} | cyan PERSON; yellow FORKLIFT; violet PALLET_JACK", fill="white")
        for i, image in enumerate(images):
            sheet.paste(image, ((i%4)*240,(i//4)*163+30+row*360))
    sheet.save(args.output / "train-label-samples.jpg", quality=90)
    for name, data in (("manifest", manifest), ("provenance", sources), ("excluded_duplicates", excluded), ("stats", stats)):
        (args.output / f"{name}.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(json.dumps(stats, indent=2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for argument in ("archives", "loco", "output"):
        parser.add_argument(argument, type=lambda value: Path(value).resolve())
    export(parser.parse_args())
