"""
MediGuard AI – 1D Residual Convolutional Neural Network (ResNet-1D)
Architecture designed for 12-lead digital ECG classification.
Input: (batch_size, 12, sequence_length)
Output: 5 raw logits (NORM, MI, STTC, CD, HYP)
Sigmoid applied during clinical inference to produce experimental model scores.
"""

from typing import Dict, Tuple, List, Optional
import torch
import torch.nn as nn
import torch.nn.functional as F

SUPERCLASSES: List[str] = ["NORM", "MI", "STTC", "CD", "HYP"]


class ResidualBlock1D(nn.Module):
    """
    1D Residual Block with two Conv1d layers, BatchNorm1d, GELU activations,
    dropout, and an optional 1x1 projection for dimension matching.
    """

    def __init__(self, in_channels: int, out_channels: int, stride: int = 1, kernel_size: int = 7, dropout: float = 0.2):
        super().__init__()
        padding = kernel_size // 2

        self.conv1 = nn.Conv1d(in_channels, out_channels, kernel_size=kernel_size, stride=stride, padding=padding, bias=False)
        self.bn1 = nn.BatchNorm1d(out_channels)
        self.act1 = nn.GELU()
        self.dropout = nn.Dropout(dropout)

        self.conv2 = nn.Conv1d(out_channels, out_channels, kernel_size=kernel_size, stride=1, padding=padding, bias=False)
        self.bn2 = nn.BatchNorm1d(out_channels)
        self.act2 = nn.GELU()

        # Shortcut connection: identity or 1x1 convolution if channels or stride mismatch
        if stride != 1 or in_channels != out_channels:
            self.shortcut = nn.Sequential(
                nn.Conv1d(in_channels, out_channels, kernel_size=1, stride=stride, bias=False),
                nn.BatchNorm1d(out_channels)
            )
        else:
            self.shortcut = nn.Identity()

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        residual = self.shortcut(x)

        out = self.conv1(x)
        out = self.bn1(out)
        out = self.act1(out)
        out = self.dropout(out)

        out = self.conv2(out)
        out = self.bn2(out)

        out = out + residual
        out = self.act2(out)
        return out


class ResNet1D_MediGuard(nn.Module):
    """
    Clinical Decision Support 1D ResNet for 12-lead ECG Classification.
    Processes (B, 12, L) digital signals and outputs 5 diagnostic superclass logits.
    """

    def __init__(
        self,
        in_channels: int = 12,
        num_classes: int = 5,
        base_filters: int = 64,
        kernel_size: int = 7,
        dropout: float = 0.3,
        model_version: str = "v1.0.0-ptbxl"
    ):
        super().__init__()
        self.in_channels = in_channels
        self.num_classes = num_classes
        self.model_version = model_version
        self.superclasses = SUPERCLASSES

        # Stem: initial receptive field expansion
        self.stem = nn.Sequential(
            nn.Conv1d(in_channels, base_filters, kernel_size=kernel_size, stride=2, padding=kernel_size // 2, bias=False),
            nn.BatchNorm1d(base_filters),
            nn.GELU(),
            nn.MaxPool1d(kernel_size=3, stride=2, padding=1)
        )

        # Residual Stages: 64 -> 128 -> 256 -> 512
        self.stage1 = nn.Sequential(
            ResidualBlock1D(base_filters, base_filters, stride=1, kernel_size=kernel_size, dropout=dropout),
            ResidualBlock1D(base_filters, base_filters, stride=1, kernel_size=kernel_size, dropout=dropout)
        )
        self.stage2 = nn.Sequential(
            ResidualBlock1D(base_filters, base_filters * 2, stride=2, kernel_size=kernel_size, dropout=dropout),
            ResidualBlock1D(base_filters * 2, base_filters * 2, stride=1, kernel_size=kernel_size, dropout=dropout)
        )
        self.stage3 = nn.Sequential(
            ResidualBlock1D(base_filters * 2, base_filters * 4, stride=2, kernel_size=kernel_size, dropout=dropout),
            ResidualBlock1D(base_filters * 4, base_filters * 4, stride=1, kernel_size=kernel_size, dropout=dropout)
        )
        self.stage4 = nn.Sequential(
            ResidualBlock1D(base_filters * 4, base_filters * 8, stride=2, kernel_size=kernel_size, dropout=dropout),
            ResidualBlock1D(base_filters * 8, base_filters * 8, stride=1, kernel_size=kernel_size, dropout=dropout)
        )

        # Global Pooling & Clinical Classifier Head
        self.global_pool = nn.AdaptiveAvgPool1d(1)
        self.head_dropout = nn.Dropout(dropout)
        self.classifier = nn.Linear(base_filters * 8, num_classes)

        self._init_weights()

    def _init_weights(self):
        """Kaiming normal initialization for conv layers."""
        for m in self.modules():
            if isinstance(m, nn.Conv1d):
                nn.init.kaiming_normal_(m.weight, mode="fan_out", nonlinearity="relu")
            elif isinstance(m, nn.BatchNorm1d):
                nn.init.constant_(m.weight, 1.0)
                nn.init.constant_(m.bias, 0.0)
            elif isinstance(m, nn.Linear):
                nn.init.xavier_normal_(m.weight)
                if m.bias is not None:
                    nn.init.constant_(m.bias, 0.0)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Forward pass returning raw logits (for BCEWithLogitsLoss).
        Input: (B, 12, L)
        Output: (B, 5)
        """
        if x.dim() != 3 or x.size(1) != self.in_channels:
            raise ValueError(f"Expected input shape (batch, {self.in_channels}, seq_len), got {x.shape}")

        out = self.stem(x)
        out = self.stage1(out)
        out = self.stage2(out)
        out = self.stage3(out)
        out = self.stage4(out)

        out = self.global_pool(out).squeeze(-1)  # (B, channels)
        out = self.head_dropout(out)
        logits = self.classifier(out)  # (B, 5)
        return logits

    @torch.no_grad()
    def predict_scores(self, x: torch.Tensor) -> torch.Tensor:
        """
        Inference pass: applies sigmoid to logits to produce experimental model scores in [0.0, 1.0].
        Non-negotiable rule: scores are experimental model scores, NOT calibrated diagnostic probabilities.
        """
        self.eval()
        logits = self.forward(x)
        scores = torch.sigmoid(logits)
        return scores


def build_model(config: Optional[Dict] = None) -> ResNet1D_MediGuard:
    """Factory function to build ResNet1D_MediGuard from a config dictionary or defaults."""
    cfg = config or {}
    model_cfg = cfg.get("model", {})

    return ResNet1D_MediGuard(
        in_channels=model_cfg.get("in_channels", 12),
        num_classes=model_cfg.get("num_classes", 5),
        base_filters=model_cfg.get("base_filters", 64),
        kernel_size=model_cfg.get("kernel_size", 7),
        dropout=model_cfg.get("dropout", 0.3),
        model_version=model_cfg.get("version", "v1.0.0-ptbxl")
    )


def get_model_summary(model: nn.Module) -> Dict:
    """Print and return total parameter counts and model summary."""
    total_params = sum(p.numel() for p in model.parameters())
    trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)

    print("=" * 60)
    print(f"MediGuard AI Model: {model.__class__.__name__}")
    print(f"Total Parameters:     {total_params:,}")
    print(f"Trainable Parameters: {trainable_params:,}")
    print(f"Model Version:        {getattr(model, 'model_version', 'v1.0.0')}")
    print("=" * 60)

    return {
        "model_name": model.__class__.__name__,
        "total_params": total_params,
        "trainable_params": trainable_params,
        "version": getattr(model, "model_version", "v1.0.0")
    }


if __name__ == "__main__":
    test_net = build_model()
    get_model_summary(test_net)

    # Test dummy forward pass
    dummy_input = torch.randn(4, 12, 1000)
    out_logits = test_net(dummy_input)
    out_scores = test_net.predict_scores(dummy_input)
    print(f"Input shape:  {dummy_input.shape}")
    print(f"Logits shape: {out_logits.shape}")
    print(f"Scores shape: {out_scores.shape} (values between {out_scores.min().item():.3f} and {out_scores.max().item():.3f})")
