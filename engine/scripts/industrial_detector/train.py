# SPDX-License-Identifier: AGPL-3.0-or-later
"""Fit an isolated YOLO11 candidate with source-specific class supervision."""
import argparse
import hashlib
import json
import os
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("YOLO_OFFLINE", "true")
os.environ.setdefault("YOLO_AUTOINSTALL", "false")
os.environ.setdefault("OMP_NUM_THREADS", "3")

import torch
from ultralytics import YOLO, __version__
from ultralytics.utils.loss import v8DetectionLoss

from prepare import CLASSES, SEED, digest


def mask_class_loss(values, mask):
    if values.ndim != 3 or mask.shape != (values.shape[0], 1, values.shape[2]):
        raise ValueError("classification loss or supervision shape does not match")
    return values * mask


def check_local_amp(model):
    """Compare the actual model in FP32 and AMP without downloading a probe model."""
    device = next(model.parameters()).device
    previous = model.training
    model.eval()
    try:
        data = torch.linspace(0, 1, 3*256*256, device=device).view(1,3,256,256)
        with torch.inference_mode():
            baseline = model(data)[0]
            with torch.autocast(device.type):
                mixed = model(data)[0].float()
        diff = (baseline - mixed).abs()
        box = float(diff[:, :4].max())
        score = float(diff[:, 4:].max())
        valid = bool(torch.isfinite(diff).all()) and box < 4 and score < .04
        print(f"Local AMP check: max box delta={box:.3f} px, score delta={score:.5f}, enabled={valid}", flush=True)
        return valid
    finally:
        model.train(previous)


def freeze_person_outputs(model):
    """Fit only new classifier rows while retaining COCO features and box regression."""
    if model.names != dict(enumerate(CLASSES)):
        raise ValueError("The classifier row contract changed")
    model.requires_grad_(False)
    for classifier in model.model[-1].cv3:
        last = classifier[-1]
        if not isinstance(last, torch.nn.Conv2d) or last.out_channels != len(CLASSES):
            raise ValueError("Unsupported YOLO classification head")
        for parameter in last.parameters():
            parameter.requires_grad_(True)
            mask = torch.ones_like(parameter)
            mask[0] = 0
            parameter.register_hook(lambda gradient, mask=mask: gradient * mask)
    return tuple(module for module in model.modules() if isinstance(module, torch.nn.modules.batchnorm._BatchNorm))


class PartialClassLoss(v8DetectionLoss):
    """Zero only the classification gradients of unannotated classes."""

    def __init__(self, model, coverage):
        super().__init__(model)
        self.coverage = coverage

    def get_assigned_targets_and_loss(self, preds, batch):
        rows = [self.coverage[Path(file).name] for file in batch["im_file"]]
        mask = torch.tensor(rows, device=self.device, dtype=torch.bool).unsqueeze(1)
        criterion = self.bce
        self.bce = lambda logits, labels: mask_class_loss(criterion(logits, labels), mask)
        try:
            return super().get_assigned_targets_and_loss(preds, batch)
        finally:
            self.bce = criterion


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ("dataset", "weights", "output"):
        parser.add_argument(f"--{option}", type=lambda s: Path(s).resolve(), required=True)
    parser.add_argument("--epochs", type=int, required=True)
    parser.add_argument("--batch", type=int, default=8)
    parser.add_argument("--size", type=int, default=448)
    parser.add_argument("--lr", type=float, default=.00065)
    parser.add_argument("--device", choices=("0", "cpu"), default="0")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--freeze-person", action="store_true")
    parser.add_argument("--seconds", type=float, default=0, help="Optional seconds budget; checked by Ultralytics per epoch")
    parser.add_argument("--fp32", action="store_true")
    args = parser.parse_args()
    if __version__ != "8.4.146":
        raise SystemExit(f"Unexpected Ultralytics API version: {__version__}")
    torch.set_num_threads(3)
    manifest_path = args.dataset / "manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    coverage = {}
    for row in manifest:
        if row["split"] not in ("train", "val"):
            continue
        declared = set(row["supervised"])
        if not declared or any(cls not in declared for cls, _ in row["boxes"]):
            raise ValueError(f"Label outside source supervision: {row['image']}")
        image = args.dataset / row["image"]
        labels = args.dataset / "labels" / image.relative_to(args.dataset / "images").with_suffix(".txt")
        if digest(image) != row["sha256"] or digest(labels) != row["label_sha256"]:
            raise ValueError(f"Dataset content changed: {row['image']}")
        coverage[image.name] = [cls in declared for cls in range(len(CLASSES))]

    norms = ()

    def install_loss(trainer):
        nonlocal norms
        trainer.model.criterion = PartialClassLoss(trainer.model, coverage)
        if args.freeze_person:
            if any(group["weight_decay"] != 0 for group in trainer.optimizer.param_groups):
                raise ValueError("Frozen classifier rows require zero weight decay")
            norms = freeze_person_outputs(trainer.model)

    def preserve_statistics(_trainer):
        for norm in norms:
            norm.eval()

    model = YOLO(str(args.weights))
    model.add_callback("on_pretrain_routine_end", install_loss)
    if args.freeze_person:
        model.add_callback("on_train_batch_start", preserve_statistics)
    if args.resume:
        with patch("ultralytics.engine.trainer.check_amp", check_local_amp):
            model.train(resume=True, device=args.device)
        return
    if args.output.exists():
        raise FileExistsError(args.output)
    args.output.mkdir(parents=True)
    (args.output / "inputs.json").write_text(json.dumps({
        "dataset_manifest_sha256": digest(manifest_path),
        "input_checkpoint_sha256": digest(args.weights), "seed": SEED,
        "ultralytics": __version__, "torch": torch.__version__,
        "epochs_max": args.epochs, "batch": args.batch, "size": args.size, "device": args.device, "lr": args.lr,
        "amp_requested": args.device == "0" and not args.fp32,
        "person_frozen": args.freeze_person,
    }, indent=2), encoding="utf-8")
    opts = dict(data=str(args.dataset / "dataset.yaml"), project=str(args.output), name="fit",
                imgsz=args.size, epochs=args.epochs, batch=args.batch, nbs=args.batch,
                device=args.device, deterministic=True, seed=SEED, workers=0, amp=args.device == "0" and not args.fp32,
                save_period=3, patience=10, optimizer="AdamW", lr0=args.lr, warmup_epochs=2, cls_pw=.25,
                mosaic=0, mixup=0, copy_paste=0, cutmix=0, degrees=0, shear=0,
                fliplr=.5, flipud=0, translate=.04, scale=.17, hsv_h=0, hsv_s=.20, hsv_v=.15,
                plots=True, cache=False)
    if args.freeze_person:
        opts.update(weight_decay=0, warmup_bias_lr=.003)
    if args.seconds:
        opts["time"] = args.seconds / 3600
    with patch("ultralytics.engine.trainer.check_amp", check_local_amp):
        model.train(**opts)
    best = args.output / "fit" / "weights" / "best.pt"
    print(f"CHECKPOINT_SHA256 {digest(best)}", flush=True)


if __name__ == "__main__":
    main()
