from __future__ import annotations

import argparse
import json
import random
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from joblib import dump
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import (
    accuracy_score,
    brier_score_loss,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
    precision_score,
    r2_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import GroupShuffleSplit
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

from brokebutthriving.ml.bls_cex import BLS_SEQUENCE_BASE_FEATURES
from brokebutthriving.ml.models import SpendSequenceModel
from brokebutthriving.ml.train_public_benchmarks import BenchmarkPreprocessor, infer_feature_types


TASK_NOTE = (
    "Sequence benchmark trained on BLS Consumer Expenditure Interview public microdata with a derived "
    "next-quarter high-burn proxy label."
)
DEFAULT_SEED = 7
DEFAULT_BATCH_SIZE = 256
DEFAULT_MAX_EPOCHS = 25
DEFAULT_PATIENCE = 5


@dataclass
class SplitResult:
    train_indices: np.ndarray
    val_indices: np.ndarray
    test_indices: np.ndarray
    effective_seed: int


def _json_default(value: object) -> object:
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    raise TypeError(f"Object of type {type(value)!r} is not JSON serializable")


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, default=_json_default)


def _set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def _lag_prefixes(frame: pd.DataFrame) -> list[str]:
    prefixes = {column.split("_", 1)[0] for column in frame.columns if re.match(r"lag\d+_", column)}
    return sorted(prefixes, key=lambda value: int(value[3:]), reverse=True)


def _flattened_feature_columns(frame: pd.DataFrame, lag_prefixes: list[str]) -> list[str]:
    columns: list[str] = []
    for prefix in lag_prefixes:
        for feature in BLS_SEQUENCE_BASE_FEATURES:
            column = f"{prefix}_{feature}"
            if column in frame.columns:
                columns.append(column)
    return columns


def _prepare_frame(input_csv: str | Path) -> pd.DataFrame:
    frame = pd.read_csv(input_csv, low_memory=False)
    if frame.empty:
        raise ValueError("Sequence benchmark CSV is empty.")

    required_columns = {
        "panel_id",
        "target_next_total_expenditure_q",
        "target_high_burn_next_q",
        "young_or_student_proxy",
    }
    missing = sorted(required_columns - set(frame.columns))
    if missing:
        raise ValueError(f"Missing required sequence benchmark columns: {', '.join(missing)}")

    frame["panel_id"] = frame["panel_id"].astype(str)
    frame["target_next_total_expenditure_q"] = pd.to_numeric(
        frame["target_next_total_expenditure_q"], errors="coerce"
    )
    frame["target_high_burn_next_q"] = pd.to_numeric(
        frame["target_high_burn_next_q"], errors="coerce"
    )
    frame["young_or_student_proxy"] = pd.to_numeric(
        frame["young_or_student_proxy"], errors="coerce"
    ).fillna(0)
    frame = frame[
        frame["target_next_total_expenditure_q"].notna()
        & (frame["target_next_total_expenditure_q"] >= 0)
        & frame["target_high_burn_next_q"].notna()
    ].reset_index(drop=True)

    if len(frame) < 200:
        raise ValueError("Need at least 200 valid sequence rows to train the BLS benchmark.")
    if frame["target_high_burn_next_q"].nunique() < 2:
        raise ValueError("High-burn classification target has only one class.")

    return frame


def _group_splits(frame: pd.DataFrame, seed: int, require_subset: bool) -> SplitResult:
    groups = frame["panel_id"].to_numpy()
    indices = np.arange(len(frame))
    targets = frame["target_high_burn_next_q"].to_numpy()
    subset_mask = frame["young_or_student_proxy"].to_numpy().astype(bool)

    for attempt in range(50):
        effective_seed = seed + attempt
        outer = GroupShuffleSplit(n_splits=1, test_size=0.30, random_state=effective_seed)
        train_indices, temp_indices = next(outer.split(indices, groups=groups))
        inner = GroupShuffleSplit(n_splits=1, test_size=0.50, random_state=effective_seed)
        val_relative, test_relative = next(inner.split(temp_indices, groups=groups[temp_indices]))
        val_indices = temp_indices[val_relative]
        test_indices = temp_indices[test_relative]

        if min(len(train_indices), len(val_indices), len(test_indices)) == 0:
            continue
        if len(np.unique(targets[train_indices])) < 2 or len(np.unique(targets[test_indices])) < 2:
            continue
        if require_subset and not subset_mask[test_indices].any():
            continue

        return SplitResult(train_indices, val_indices, test_indices, effective_seed)

    raise ValueError("Could not create a valid grouped split for the BLS sequence benchmark.")


class SequenceFeatureScaler:
    def __init__(self, lag_prefixes: list[str], base_features: list[str]) -> None:
        self.lag_prefixes = lag_prefixes
        self.base_features = base_features
        self.medians: dict[str, float] = {}
        self.scales: dict[str, float] = {}

    def fit(self, frame: pd.DataFrame) -> "SequenceFeatureScaler":
        for feature in self.base_features:
            columns = [f"{prefix}_{feature}" for prefix in self.lag_prefixes if f"{prefix}_{feature}" in frame]
            values = (
                frame[columns]
                .apply(pd.to_numeric, errors="coerce")
                .to_numpy(dtype=np.float32)
                .reshape(-1)
            )
            valid = values[np.isfinite(values)]
            median = float(np.median(valid)) if valid.size else 0.0
            scale = float(np.std(valid)) if valid.size else 1.0
            if scale < 1e-6:
                scale = 1.0
            self.medians[feature] = median
            self.scales[feature] = scale
        return self

    def transform(self, frame: pd.DataFrame) -> np.ndarray:
        sequence_rows: list[np.ndarray] = []
        for prefix in self.lag_prefixes:
            lag_columns = [f"{prefix}_{feature}" for feature in self.base_features]
            lag_frame = frame.reindex(columns=lag_columns).copy()
            lag_frame.columns = self.base_features
            lag_frame = lag_frame.apply(pd.to_numeric, errors="coerce")
            for feature in self.base_features:
                lag_frame[feature] = lag_frame[feature].fillna(self.medians[feature])
                lag_frame[feature] = (lag_frame[feature] - self.medians[feature]) / self.scales[feature]
            sequence_rows.append(lag_frame[self.base_features].to_numpy(dtype=np.float32))
        return np.stack(sequence_rows, axis=1)

    def fit_transform(self, frame: pd.DataFrame) -> np.ndarray:
        self.fit(frame)
        return self.transform(frame)


def _classification_metrics(targets: np.ndarray, probabilities: np.ndarray) -> dict[str, float]:
    predictions = (probabilities >= 0.5).astype(int)
    auroc = None
    if len(np.unique(targets)) >= 2:
        auroc = float(roc_auc_score(targets, probabilities))
    return {
        "auroc": auroc,
        "f1": float(f1_score(targets, predictions, zero_division=0)),
        "precision": float(precision_score(targets, predictions, zero_division=0)),
        "recall": float(recall_score(targets, predictions, zero_division=0)),
        "accuracy": float(accuracy_score(targets, predictions)),
        "brier_score": float(brier_score_loss(targets, probabilities)),
    }


def _regression_metrics(targets: np.ndarray, predictions: np.ndarray) -> dict[str, float]:
    return {
        "mae": float(mean_absolute_error(targets, predictions)),
        "rmse": float(mean_squared_error(targets, predictions) ** 0.5),
        "r2": float(r2_score(targets, predictions)),
    }


def _dataset_tensor(
    sequence_features: np.ndarray,
    static_features: np.ndarray,
    regression_targets: np.ndarray,
    classification_targets: np.ndarray,
) -> TensorDataset:
    return TensorDataset(
        torch.tensor(sequence_features, dtype=torch.float32),
        torch.tensor(static_features, dtype=torch.float32),
        torch.tensor(regression_targets, dtype=torch.float32),
        torch.tensor(classification_targets, dtype=torch.float32),
    )


def train_sequence_model(
    train_sequence_features: np.ndarray,
    train_static_features: np.ndarray,
    train_regression_targets: np.ndarray,
    train_classification_targets: np.ndarray,
    val_sequence_features: np.ndarray,
    val_static_features: np.ndarray,
    val_regression_targets: np.ndarray,
    val_classification_targets: np.ndarray,
    seed: int,
) -> tuple[SpendSequenceModel, list[dict[str, float]]]:
    _set_seed(seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = SpendSequenceModel(
        input_dim=train_sequence_features.shape[2],
        static_dim=train_static_features.shape[1],
    ).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)

    positive_count = max(float(train_classification_targets.sum()), 1.0)
    negative_count = max(float(len(train_classification_targets) - train_classification_targets.sum()), 1.0)
    classification_loss_fn = nn.BCEWithLogitsLoss(
        pos_weight=torch.tensor([negative_count / positive_count], dtype=torch.float32, device=device)
    )
    regression_loss_fn = nn.SmoothL1Loss()

    train_loader = DataLoader(
        _dataset_tensor(
            train_sequence_features,
            train_static_features,
            train_regression_targets,
            train_classification_targets,
        ),
        batch_size=DEFAULT_BATCH_SIZE,
        shuffle=True,
    )
    val_loader = DataLoader(
        _dataset_tensor(
            val_sequence_features,
            val_static_features,
            val_regression_targets,
            val_classification_targets,
        ),
        batch_size=DEFAULT_BATCH_SIZE,
        shuffle=False,
    )

    best_state = None
    best_val_loss = float("inf")
    no_improvement = 0
    history: list[dict[str, float]] = []

    for epoch in range(DEFAULT_MAX_EPOCHS):
        model.train()
        train_loss_total = 0.0
        train_batches = 0
        for sequence_batch, static_batch, regression_batch, classification_batch in train_loader:
            sequence_batch = sequence_batch.to(device)
            static_batch = static_batch.to(device)
            regression_batch = regression_batch.to(device)
            classification_batch = classification_batch.to(device)

            optimizer.zero_grad()
            outputs = model(sequence_batch, static_features=static_batch)
            loss = regression_loss_fn(outputs["next_total_spend"], regression_batch) + classification_loss_fn(
                outputs["high_burn_logit"], classification_batch
            )
            loss.backward()
            optimizer.step()
            train_loss_total += float(loss.item())
            train_batches += 1

        model.eval()
        val_loss_total = 0.0
        val_batches = 0
        with torch.no_grad():
            for sequence_batch, static_batch, regression_batch, classification_batch in val_loader:
                sequence_batch = sequence_batch.to(device)
                static_batch = static_batch.to(device)
                regression_batch = regression_batch.to(device)
                classification_batch = classification_batch.to(device)
                outputs = model(sequence_batch, static_features=static_batch)
                loss = regression_loss_fn(outputs["next_total_spend"], regression_batch) + classification_loss_fn(
                    outputs["high_burn_logit"], classification_batch
                )
                val_loss_total += float(loss.item())
                val_batches += 1

        train_loss = train_loss_total / max(train_batches, 1)
        val_loss = val_loss_total / max(val_batches, 1)
        history.append({"epoch": epoch + 1, "train_loss": train_loss, "val_loss": val_loss})

        if val_loss < best_val_loss - 1e-6:
            best_val_loss = val_loss
            best_state = {key: value.detach().cpu().clone() for key, value in model.state_dict().items()}
            no_improvement = 0
        else:
            no_improvement += 1
            if no_improvement >= DEFAULT_PATIENCE:
                break

    if best_state is not None:
        model.load_state_dict(best_state)

    return model, history


def predict_sequence_model(
    model: SpendSequenceModel, sequence_features: np.ndarray, static_features: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    device = next(model.parameters()).device
    loader = DataLoader(
        TensorDataset(
            torch.tensor(sequence_features, dtype=torch.float32),
            torch.tensor(static_features, dtype=torch.float32),
        ),
        batch_size=DEFAULT_BATCH_SIZE,
        shuffle=False,
    )
    regression_predictions: list[np.ndarray] = []
    class_probabilities: list[np.ndarray] = []

    model.eval()
    with torch.inference_mode():
        for sequence_batch, static_batch in loader:
            outputs = model(sequence_batch.to(device), static_features=static_batch.to(device))
            regression_predictions.append(outputs["next_total_spend"].cpu().numpy())
            class_probabilities.append(torch.sigmoid(outputs["high_burn_logit"]).cpu().numpy())

    return np.concatenate(regression_predictions), np.concatenate(class_probabilities)


def run_spend_sequence_training(
    benchmark_csv: str | Path,
    output_dir: str | Path,
    seed: int,
    young_subset_eval: bool,
) -> dict[str, object]:
    frame = _prepare_frame(benchmark_csv)
    lag_prefixes = _lag_prefixes(frame)
    flat_feature_columns = _flattened_feature_columns(frame, lag_prefixes)

    split = _group_splits(frame, seed=seed, require_subset=young_subset_eval)
    train_frame = frame.iloc[split.train_indices].reset_index(drop=True)
    val_frame = frame.iloc[split.val_indices].reset_index(drop=True)
    test_frame = frame.iloc[split.test_indices].reset_index(drop=True)

    numeric_features, boolean_features, categorical_features = infer_feature_types(
        train_frame,
        flat_feature_columns,
    )
    flat_preprocessor = BenchmarkPreprocessor(
        numeric_features=numeric_features,
        boolean_features=boolean_features,
        categorical_features=categorical_features,
    )
    train_flat = flat_preprocessor.fit_transform(train_frame[flat_feature_columns])
    val_flat = flat_preprocessor.transform(val_frame[flat_feature_columns])
    test_flat = flat_preprocessor.transform(test_frame[flat_feature_columns])

    sequence_scaler = SequenceFeatureScaler(lag_prefixes=lag_prefixes, base_features=BLS_SEQUENCE_BASE_FEATURES)
    train_sequence = sequence_scaler.fit_transform(train_frame)
    val_sequence = sequence_scaler.transform(val_frame)
    test_sequence = sequence_scaler.transform(test_frame)

    train_regression = np.log1p(train_frame["target_next_total_expenditure_q"].to_numpy(dtype=np.float32))
    val_regression = np.log1p(val_frame["target_next_total_expenditure_q"].to_numpy(dtype=np.float32))
    test_regression_raw = test_frame["target_next_total_expenditure_q"].to_numpy(dtype=np.float32)

    train_classification = train_frame["target_high_burn_next_q"].to_numpy(dtype=np.float32)
    val_classification = val_frame["target_high_burn_next_q"].to_numpy(dtype=np.float32)
    test_classification = test_frame["target_high_burn_next_q"].to_numpy(dtype=np.float32)

    output_path = Path(output_dir)
    model_dir = output_path / "models"
    model_dir.mkdir(parents=True, exist_ok=True)

    regression_models = {
        "ridge": Ridge(),
        "hist_gradient_boosting": HistGradientBoostingRegressor(random_state=seed),
    }
    classification_models = {
        "logistic_regression": LogisticRegression(
            max_iter=1000,
            class_weight="balanced",
            random_state=seed,
            solver="liblinear",
        ),
        "hist_gradient_boosting": HistGradientBoostingClassifier(random_state=seed),
    }

    regression_metrics: dict[str, dict[str, float]] = {}
    classification_metrics: dict[str, dict[str, float]] = {}
    comparison_rows: list[dict[str, object]] = []
    predictions = test_frame[
        ["panel_id", "history_start_quarter_label", "target_quarter_label", "young_or_student_proxy"]
    ].copy()
    predictions["actual_next_total_expenditure_q"] = test_regression_raw
    predictions["actual_high_burn_next_q"] = test_classification.astype(int)

    for model_name, model in regression_models.items():
        model.fit(train_flat, train_regression)
        predicted_log = model.predict(test_flat)
        predicted_raw = np.expm1(predicted_log)
        metrics = _regression_metrics(test_regression_raw, predicted_raw)
        regression_metrics[model_name] = metrics
        comparison_rows.append({"task": "regression", "model_name": model_name, **metrics})
        predictions[f"{model_name}_next_total_expenditure_q"] = predicted_raw
        dump(model, model_dir / f"{model_name}_regression.joblib")

    for model_name, model in classification_models.items():
        model.fit(train_flat, train_classification)
        probabilities = model.predict_proba(test_flat)[:, 1]
        metrics = _classification_metrics(test_classification.astype(int), probabilities)
        classification_metrics[model_name] = metrics
        comparison_rows.append({"task": "classification", "model_name": model_name, **metrics})
        predictions[f"{model_name}_high_burn_probability"] = probabilities
        predictions[f"{model_name}_high_burn_prediction"] = (probabilities >= 0.5).astype(int)
        dump(model, model_dir / f"{model_name}_classification.joblib")

    sequence_model, training_history = train_sequence_model(
        train_sequence_features=train_sequence,
        train_static_features=train_flat,
        train_regression_targets=train_regression,
        train_classification_targets=train_classification,
        val_sequence_features=val_sequence,
        val_static_features=val_flat,
        val_regression_targets=val_regression,
        val_classification_targets=val_classification,
        seed=seed,
    )
    predicted_log, sequence_probabilities = predict_sequence_model(sequence_model, test_sequence, test_flat)
    predicted_raw = np.expm1(predicted_log)
    regression_metrics["lstm"] = _regression_metrics(test_regression_raw, predicted_raw)
    classification_metrics["lstm"] = _classification_metrics(
        test_classification.astype(int), sequence_probabilities
    )
    comparison_rows.append({"task": "regression", "model_name": "lstm", **regression_metrics["lstm"]})
    comparison_rows.append(
        {"task": "classification", "model_name": "lstm", **classification_metrics["lstm"]}
    )
    predictions["lstm_next_total_expenditure_q"] = predicted_raw
    predictions["lstm_high_burn_probability"] = sequence_probabilities
    predictions["lstm_high_burn_prediction"] = (sequence_probabilities >= 0.5).astype(int)

    torch.save(
        {
            "seed": seed,
            "lag_prefixes": lag_prefixes,
            "base_features": BLS_SEQUENCE_BASE_FEATURES,
            "model_state": sequence_model.state_dict(),
            "history": training_history,
            "sequence_scaler_medians": sequence_scaler.medians,
            "sequence_scaler_scales": sequence_scaler.scales,
        },
        model_dir / "spend_sequence_model.pt",
    )
    dump(flat_preprocessor, model_dir / "flat_preprocessor.joblib")
    _write_json(model_dir / "sequence_history.json", training_history)

    predictions.to_csv(output_path / "predictions_test.csv", index=False)
    pd.DataFrame(comparison_rows).to_csv(output_path / "comparison.csv", index=False)

    feature_manifest = {
        "seq_len": len(lag_prefixes),
        "lag_prefixes": lag_prefixes,
        "sequence_base_features": BLS_SEQUENCE_BASE_FEATURES,
        "flat_feature_columns": flat_feature_columns,
        "flat_numeric_features": flat_preprocessor.active_numeric_features,
        "flat_boolean_features": flat_preprocessor.active_boolean_features,
        "flat_categorical_features": categorical_features,
        "flat_transformed_feature_names": flat_preprocessor.get_feature_names_out(),
        "flat_transformed_feature_count": len(flat_preprocessor.get_feature_names_out()),
    }
    _write_json(output_path / "feature_manifest.json", feature_manifest)

    split_manifest = {
        "base_seed": seed,
        "effective_seed": split.effective_seed,
        "row_counts": {
            "train": int(len(train_frame)),
            "val": int(len(val_frame)),
            "test": int(len(test_frame)),
        },
        "group_counts": {
            "train": int(train_frame["panel_id"].nunique()),
            "val": int(val_frame["panel_id"].nunique()),
            "test": int(test_frame["panel_id"].nunique()),
        },
        "train_panel_ids": sorted(train_frame["panel_id"].unique().tolist()),
        "val_panel_ids": sorted(val_frame["panel_id"].unique().tolist()),
        "test_panel_ids": sorted(test_frame["panel_id"].unique().tolist()),
    }
    _write_json(output_path / "split_manifest.json", split_manifest)

    subset_mask = test_frame["young_or_student_proxy"].astype(bool)
    subset_rows = int(subset_mask.sum())
    if young_subset_eval and subset_rows == 0:
        raise ValueError("No young-or-student proxy rows were present in the test split.")

    subset_metrics = {
        "young_or_student_test_rows": subset_rows,
        "young_or_student_panel_count": int(test_frame.loc[subset_mask, "panel_id"].nunique()),
        "regression_metrics": {},
        "classification_metrics": {},
    }
    if subset_rows > 0:
        subset_targets_reg = test_regression_raw[subset_mask.to_numpy()]
        subset_targets_cls = test_classification[subset_mask.to_numpy()].astype(int)
        for model_name in regression_metrics:
            subset_predictions = predictions.loc[subset_mask, f"{model_name}_next_total_expenditure_q"].to_numpy()
            subset_metrics["regression_metrics"][model_name] = _regression_metrics(
                subset_targets_reg, subset_predictions
            )
        for model_name in classification_metrics:
            subset_probabilities = predictions.loc[
                subset_mask, f"{model_name}_high_burn_probability"
            ].to_numpy()
            subset_metrics["classification_metrics"][model_name] = _classification_metrics(
                subset_targets_cls, subset_probabilities
            )
    _write_json(output_path / "young_student_subset_metrics.json", subset_metrics)

    metrics = {
        "task_id": "bls_spend_sequence_multitask",
        "note": TASK_NOTE,
        "row_count": int(len(frame)),
        "panel_count": int(frame["panel_id"].nunique()),
        "seq_len": len(lag_prefixes),
        "feature_count_flat": int(len(flat_preprocessor.get_feature_names_out())),
        "feature_count_sequence": int(len(BLS_SEQUENCE_BASE_FEATURES)),
        "split_counts": split_manifest["row_counts"],
        "positive_class_rate": {
            "overall": float(frame["target_high_burn_next_q"].mean()),
            "train": float(train_frame["target_high_burn_next_q"].mean()),
            "val": float(val_frame["target_high_burn_next_q"].mean()),
            "test": float(test_frame["target_high_burn_next_q"].mean()),
        },
        "regression_metrics": regression_metrics,
        "classification_metrics": classification_metrics,
        "young_subset_eval_enabled": bool(young_subset_eval),
        "young_or_student_test_rows": subset_rows,
    }
    _write_json(output_path / "metrics.json", metrics)
    return metrics


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Train baselines and an LSTM on the BLS spend-sequence benchmark."
    )
    parser.add_argument(
        "--benchmark-csv",
        default="artifacts/benchmarks/bls_cex_spend_sequence_benchmark.csv",
        help="Path to the BLS spend-sequence benchmark CSV",
    )
    parser.add_argument("--output-dir", required=True, help="Directory for saved training artifacts")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument(
        "--young-subset-eval",
        default=True,
        action=argparse.BooleanOptionalAction,
        help="Compute young-or-student proxy subset metrics on the test split",
    )
    args = parser.parse_args(argv)

    _set_seed(args.seed)
    metrics = run_spend_sequence_training(
        benchmark_csv=args.benchmark_csv,
        output_dir=args.output_dir,
        seed=args.seed,
        young_subset_eval=args.young_subset_eval,
    )
    print(json.dumps(metrics, indent=2, default=_json_default))


if __name__ == "__main__":
    main()
