from __future__ import annotations

import torch
from torch import nn


class MultiTaskSequenceModel(nn.Module):
    def __init__(
        self,
        input_dim: int,
        static_dim: int = 0,
        hidden_dim: int = 96,
        num_layers: int = 2,
        dropout: float = 0.25,
    ) -> None:
        super().__init__()
        self.encoder = nn.LSTM(
            input_size=input_dim,
            hidden_size=hidden_dim,
            num_layers=num_layers,
            batch_first=True,
            dropout=dropout if num_layers > 1 else 0.0,
        )
        self.norm = nn.LayerNorm(hidden_dim)
        self.shared = nn.Sequential(
            nn.Linear(hidden_dim + static_dim, hidden_dim),
            nn.ReLU(),
            nn.Dropout(dropout),
        )
        self.risk_head = nn.Linear(hidden_dim, 1)
        self.archetype_head = nn.Linear(hidden_dim, 3)
        self.spend_head = nn.Linear(hidden_dim, 1)

    def forward(
        self, features: torch.Tensor, static_features: torch.Tensor | None = None
    ) -> dict[str, torch.Tensor]:
        encoded, _ = self.encoder(features)
        pooled = self.norm(encoded[:, -1, :])
        if static_features is not None:
            pooled = torch.cat([pooled, static_features], dim=-1)
        shared = self.shared(pooled)
        return {
            "risk_logits": self.risk_head(shared).squeeze(-1),
            "archetype_logits": self.archetype_head(shared),
            "spend_prediction": self.spend_head(shared).squeeze(-1),
        }


class TabularMLP(nn.Module):
    def __init__(
        self,
        input_dim: int,
        hidden_dims: tuple[int, ...] = (256, 128),
        dropout: float = 0.3,
    ) -> None:
        super().__init__()
        layers: list[nn.Module] = []
        current_dim = input_dim

        for hidden_dim in hidden_dims:
            layers.extend(
                [
                    nn.Linear(current_dim, hidden_dim),
                    nn.BatchNorm1d(hidden_dim),
                    nn.ReLU(),
                    nn.Dropout(dropout),
                ]
            )
            current_dim = hidden_dim

        self.backbone = nn.Sequential(*layers)
        self.output = nn.Linear(current_dim, 1)

    def forward(self, features: torch.Tensor) -> torch.Tensor:
        hidden = self.backbone(features)
        return self.output(hidden)


class SpendSequenceModel(nn.Module):
    def __init__(
        self,
        input_dim: int,
        static_dim: int = 0,
        hidden_dim: int = 96,
        num_layers: int = 2,
        dropout: float = 0.25,
    ) -> None:
        super().__init__()
        self.encoder = nn.LSTM(
            input_size=input_dim,
            hidden_size=hidden_dim,
            num_layers=num_layers,
            batch_first=True,
            dropout=dropout if num_layers > 1 else 0.0,
        )
        self.norm = nn.LayerNorm(hidden_dim)
        self.shared = nn.Sequential(
            nn.Linear(hidden_dim + static_dim, hidden_dim),
            nn.ReLU(),
            nn.Dropout(dropout),
        )
        self.regression_head = nn.Linear(hidden_dim, 1)
        self.classification_head = nn.Linear(hidden_dim, 1)

    def forward(
        self, features: torch.Tensor, static_features: torch.Tensor | None = None
    ) -> dict[str, torch.Tensor]:
        encoded, _ = self.encoder(features)
        pooled = self.norm(encoded[:, -1, :])
        if static_features is not None:
            pooled = torch.cat([pooled, static_features], dim=-1)
        shared = self.shared(pooled)
        return {
            "next_total_spend": self.regression_head(shared).squeeze(-1),
            "high_burn_logit": self.classification_head(shared).squeeze(-1),
        }
