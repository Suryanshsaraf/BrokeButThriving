from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import torch
from torch.utils.data import Dataset


ARCHETYPE_TO_INDEX = {"stress": 0, "social_pressure": 1, "boredom": 2}

FEATURE_COLUMNS = [
    "spend_total",
    "inflow_total",
    "tx_count",
    "social_tx_count",
    "essential_tx_count",
    "stress_level",
    "exam_pressure",
    "social_pressure",
    "mood_energy",
    "sleep_hours",
    "day_of_week",
    "day_of_month",
    "days_remaining_in_month",
    "is_weekend",
    "estimated_balance",
    "rolling_spend_7d",
    "rolling_spend_14d",
    "rolling_social_7d",
    "budget_utilization_ratio",
]


@dataclass
class SequenceSample:
    participant_id: str
    features: np.ndarray
    static_features: np.ndarray | None
    risk_target: float
    archetype_target: int
    spend_target: float


def build_sequence_samples(frame: pd.DataFrame, seq_len: int = 30) -> list[SequenceSample]:
    samples: list[SequenceSample] = []
    if frame.empty:
        return samples

    for participant_id, group in frame.groupby("participant_id"):
        group = group.sort_values("date").reset_index(drop=True)
        archetype = group["primary_archetype"].dropna().iloc[0] if group["primary_archetype"].notna().any() else None
        if archetype not in ARCHETYPE_TO_INDEX:
            continue

        feature_spread = ["stress_level", "exam_pressure", "social_pressure", "mood_energy", "sleep_hours"]
        group[feature_spread] = group[feature_spread].ffill()
        valid_group = group.fillna(0)

        for end_idx in range(len(valid_group)):
            target_row = valid_group.iloc[end_idx]
            start_idx = max(0, end_idx - seq_len + 1)
            window = valid_group.iloc[start_idx : end_idx + 1]
            features = window[FEATURE_COLUMNS].to_numpy(dtype=np.float32)

            if len(features) < seq_len:
                pad_width = seq_len - len(features)
                features = np.pad(features, ((pad_width, 0), (0, 0)), mode="constant", constant_values=0.0)

            # Extract base generic static representation (e.g. onboarding baseline)
            static_array = np.zeros(1, dtype=np.float32)
            if "estimated_balance" in target_row:
                static_array = np.array([target_row["estimated_balance"]], dtype=np.float32)

            samples.append(
                SequenceSample(
                    participant_id=participant_id,
                    features=features,
                    static_features=static_array,
                    risk_target=float(target_row["risk_label_14d"]),
                    archetype_target=ARCHETYPE_TO_INDEX[archetype],
                    spend_target=float(np.log1p(target_row["spend_next_7d"])),
                )
            )

    return samples


def split_participants(participant_ids: list[str]) -> tuple[set[str], set[str], set[str]]:
    ordered = sorted(set(participant_ids))
    total = len(ordered)
    train_end = max(1, int(total * 0.7))
    val_end = max(train_end + 1, int(total * 0.85)) if total > 2 else total

    train_ids = set(ordered[:train_end])
    val_ids = set(ordered[train_end:val_end])
    test_ids = set(ordered[val_end:])

    if not val_ids and train_ids:
        val_ids = {next(iter(train_ids))}
    if not test_ids and val_ids:
        test_ids = {next(iter(val_ids))}

    return train_ids, val_ids, test_ids


class MultiTaskSequenceDataset(Dataset):
    def __init__(self, samples: list[SequenceSample]) -> None:
        self.samples = samples

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, index: int) -> dict[str, torch.Tensor]:
        sample = self.samples[index]
        output = {
            "features": torch.tensor(sample.features, dtype=torch.float32),
            "risk_target": torch.tensor(sample.risk_target, dtype=torch.float32),
            "archetype_target": torch.tensor(sample.archetype_target, dtype=torch.long),
            "spend_target": torch.tensor(sample.spend_target, dtype=torch.float32),
        }
        if sample.static_features is not None:
             output["static_features"] = torch.tensor(sample.static_features, dtype=torch.float32)
        return output

