"""Parallel CNN/local and patch-Transformer/global branches; no severity head."""
import torch
from torch import nn
from .config import Config


class HybridCNNTransformer(nn.Module):
    def __init__(self, config: Config):
        super().__init__()
        self.image_size = config.image_size
        blocks = []
        channels = 3
        for out_channels in (32, 64, 128):
            blocks.extend([nn.Conv2d(channels, out_channels, 3, padding=1),
                           nn.GroupNorm(8, out_channels), nn.GELU(), nn.MaxPool2d(2)])
            channels = out_channels
        self.cnn = nn.Sequential(*blocks, nn.AdaptiveAvgPool2d(1), nn.Flatten())
        dim = config.embedding_dim
        self.patch_embedding = nn.Conv2d(3, dim, config.patch_size, stride=config.patch_size)
        token_count = (config.image_size // config.patch_size) ** 2
        self.position = nn.Parameter(torch.empty(1, token_count, dim))
        nn.init.normal_(self.position, std=0.02)
        # Build independent layers to avoid cloned identical initial weights.
        self.transformer = nn.Sequential(*[
            nn.TransformerEncoderLayer(dim, config.transformer_heads, dim * 4,
                                       dropout=config.dropout, activation='gelu',
                                       batch_first=True, norm_first=True)
            for _ in range(config.transformer_layers)
        ])
        self.global_norm = nn.LayerNorm(dim)
        self.classifier = nn.Sequential(
            nn.Linear(128 + dim, 128), nn.GELU(), nn.Dropout(config.dropout),
            nn.Linear(128, len(config.class_names)),
        )

    def forward(self, images):
        if images.ndim != 4 or images.shape[1:] != (3, self.image_size, self.image_size):
            raise ValueError('Expected batch × 3 × configured image size × configured image size.')
        local = self.cnn(images)
        tokens = self.patch_embedding(images).flatten(2).transpose(1, 2) + self.position
        global_features = self.global_norm(self.transformer(tokens)).mean(dim=1)
        return self.classifier(torch.cat([local, global_features], dim=1))
