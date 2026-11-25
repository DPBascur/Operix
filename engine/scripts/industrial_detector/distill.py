# SPDX-License-Identifier: AGPL-3.0-or-later
"""Training-only response distillation anchored to verified foreground targets."""
import torch
from torch.nn import functional as F
from ultralytics import YOLO
from ultralytics.utils.metrics import box_iou
from ultralytics.utils.nms import non_max_suppression

# Require a clear same-class overlap with a verified box. The ordinary YOLO
# loss stays authoritative for every label and for the supervised background.
MIN_IOU = .70
AMBIGUITY_MARGIN = .10
CONFIDENCE = (.65, .55)
CLASS_GAIN = .10
BOX_GAIN = .25
LOCALIZATION_MARGIN = .02


def trusted_pairs(truth, proposals, confidence):
    """Return unique teacher/label pairs with a clear mutual match."""
    qualified = proposals[:, 4] >= confidence
    proposals = proposals[qualified]
    if not truth.numel() or not proposals.numel():
        return torch.empty(0, dtype=torch.long, device=truth.device), proposals[:0]
    overlaps = box_iou(truth, proposals[:, :4])
    values, target = overlaps.max(dim=0)
    remaining = overlaps.clone()
    remaining.scatter_(0, target.unsqueeze(0), -1)
    best = overlaps.argmax(dim=1)
    candidate = torch.arange(len(proposals), device=truth.device)
    keep = ((values >= MIN_IOU) & (values - remaining.max(dim=0).values >= AMBIGUITY_MARGIN)
            & (best[target] == candidate))
    return target[keep], proposals[keep]


def mean_response_loss(responses, *, balanced):
    available = [group for group in responses if group]
    if balanced:
        return torch.stack([torch.stack(group).mean() for group in available]).mean()
    return torch.stack([term for group in available for term in group]).mean()


class ResponseDistillation:
    def __init__(self, device, teacher_paths, *, balanced=False):
        self.teachers = []
        for role, path in zip(("person", "forklift"), teacher_paths, strict=True):
            model = YOLO(str(path), task="detect")
            index = next(index for index, name in model.names.items() if name.lower() == role)
            network = model.model.to(device).float().eval().requires_grad_(False)
            self.teachers.append((network, index))
        self.matches = [0, 0]
        self.localization_matches = [0, 0]
        self.batches = 0
        self.weighted_loss = torch.zeros(2, device=device)
        self.balanced = balanced

    def add(self, criterion, predictions, batch, assignments, loss, trusted):
        if not torch.is_grad_enabled():
            return loss
        foreground, target_idx, target_boxes, anchors, stride = assignments
        images = batch["img"]
        with torch.no_grad():
            inputs = images.float()
            targets = torch.cat((batch["batch_idx"].view(-1, 1), batch["cls"].view(-1, 1),
                                 batch["bboxes"]), dim=1)
            scale = images.new_tensor([images.shape[3], images.shape[2]] * 2)
            labels = criterion.preprocess(targets, images.shape[0], scale)
        scores = predictions["scores"].transpose(1, 2).float()
        boxes = criterion.bbox_decode(anchors, predictions["boxes"].transpose(1, 2).contiguous()) * stride
        loss_class, loss_box = [[], []], [[], []]
        for cls, (teacher, raw_class) in enumerate(self.teachers):
            eligible = trusted[:, 0, cls] & (labels[..., 0].eq(cls) & labels[..., 1:].sum(2).gt(0)).any(1)
            indices = eligible.nonzero().flatten().tolist()
            if not indices:
                continue
            with torch.no_grad(), torch.autocast(device_type=images.device.type, enabled=False):
                raw = teacher(inputs[indices])[0]
                results = non_max_suppression(raw, conf_thres=CONFIDENCE[cls], iou_thres=.55,
                                              classes=[raw_class], nc=len(teacher.names), max_det=80)
            for image_idx, proposals in zip(indices, results, strict=True):
                gt = labels[image_idx]
                rows = ((gt[:, 0] == cls) & gt[:, 1:].sum(1).gt(0)).nonzero().flatten()
                matched, response = trusted_pairs(gt[rows, 1:], proposals, CONFIDENCE[cls])
                self.matches[cls] += len(matched)
                for original_idx, teacher_box in zip(rows[matched], response, strict=True):
                    hits = foreground[image_idx] & (target_idx[image_idx] == original_idx)
                    if not hits.any():
                        continue
                    strength = teacher_box[4]
                    score = scores[image_idx, hits, cls]
                    loss_class[cls].append(
                        F.binary_cross_entropy_with_logits(score, strength.expand_as(score)) * strength)
                    predicted = boxes[image_idx, hits]
                    target = target_boxes[image_idx, hits][:1]
                    if self.balanced:
                        teacher_overlap = box_iou(target, teacher_box[:4].reshape(1, 4))[0, 0]
                        student_overlap = box_iou(target, predicted.detach())[0]
                        predicted = predicted[teacher_overlap >= student_overlap + LOCALIZATION_MARGIN]
                        if not predicted.numel():
                            continue
                    unit = (target[:, 2:] - target[:, :2]).clamp_min(1).repeat(1, 2)
                    residual = (predicted - teacher_box[:4]) / unit
                    loss_box[cls].append(F.smooth_l1_loss(residual, torch.zeros_like(residual)) * strength)
                    self.localization_matches[cls] += 1
        self.batches += 1
        if not any(loss_class):
            return loss
        box_term = BOX_GAIN * mean_response_loss(loss_box, balanced=self.balanced) if any(loss_box) else loss.new_zeros(())
        class_term = CLASS_GAIN * mean_response_loss(loss_class, balanced=self.balanced)
        self.weighted_loss += torch.stack((box_term.detach(), class_term.detach()))
        return loss + torch.stack((box_term, class_term, loss.new_zeros(())))
