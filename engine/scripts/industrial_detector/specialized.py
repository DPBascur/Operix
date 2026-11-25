# SPDX-License-Identifier: AGPL-3.0-or-later
"""Prototype classification towers with shared neck and box regression."""
from copy import deepcopy

import torch
from torch import nn
from ultralytics.models.yolo.detect import DetectionTrainer


def output_slice(convolution, start, end):
    if (convolution.out_channels, convolution.kernel_size, convolution.groups) != (3, (1, 1), 1):
        raise ValueError("Unsupported classifier output geometry")
    sliced = nn.Conv2d(convolution.in_channels, end - start, 1, bias=convolution.bias is not None)
    sliced.to(device=convolution.weight.device, dtype=convolution.weight.dtype)
    with torch.no_grad():
        sliced.weight.copy_(convolution.weight[start:end])
        if sliced.bias is not None:
            sliced.bias.copy_(convolution.bias[start:end])
    return sliced


class SpecializedClassifier(nn.Module):
    """Reuse the first block. Clone the last feature block per class group."""

    def __init__(self, tower):
        super().__init__()
        if len(tower) != 3:
            raise ValueError("Expected a YOLO11 classifier with two feature blocks")
        shared, private, projection = tower
        self.shared = shared
        self.person = nn.Sequential(private, output_slice(projection, 0, 1))
        self.equipment = nn.Sequential(deepcopy(private), output_slice(projection, 1, 3))
        self.person.requires_grad_(False)
        self.person.eval()

    def train(self, mode=True):
        super().train(mode)
        self.person.eval()
        return self

    def forward(self, inputs):
        features = self.shared(inputs)
        return torch.cat((self.person(features), self.equipment(features)), dim=1)


class SpecializedTrainer(DetectionTrainer):
    def get_model(self, cfg=None, weights=None, verbose=True):
        model = super().get_model(cfg, weights, verbose)
        head = model.model[-1]
        if head.nc != 3 or head.end2end:
            raise ValueError("Prototype expects a three-class YOLO11 detection head")
        head.cv3 = nn.ModuleList(SpecializedClassifier(tower) for tower in head.cv3)
        if weights is not None and isinstance(weights.model[-1].cv3[0], SpecializedClassifier):
            model.load(weights)
        return model
