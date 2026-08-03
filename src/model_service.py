from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Any

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import StratifiedKFold, cross_val_score, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from .config import CATEGORICAL_FEATURES, MODEL_FEATURES, NUMERIC_FEATURES, MODEL_VERSION
from .expert_system import cm_to_inches, kg_to_pounds


@dataclass
class ModelCandidate:
    name: str
    pipeline: Pipeline
    metrics: dict[str, float]
    cm: np.ndarray
    y_true: np.ndarray
    y_pred: np.ndarray
    y_probability: np.ndarray
    feature_importance: pd.DataFrame


@dataclass
class ModelBundle:
    selected: ModelCandidate
    candidates: list[ModelCandidate]
    training_data: pd.DataFrame
    source_name: str
    version: str = MODEL_VERSION


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()
    result.columns = [str(c).strip() for c in result.columns]
    return result


def read_csv_bytes(csv_bytes: bytes) -> pd.DataFrame:
    return normalize_columns(pd.read_csv(BytesIO(csv_bytes)))


def validate_training_data(df: pd.DataFrame) -> list[str]:
    required = set(MODEL_FEATURES + ["glyhb"])
    return sorted(required - set(df.columns))


def _preprocessor() -> ColumnTransformer:
    numeric_pipe = Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("scaler", StandardScaler()),
    ])
    categorical_pipe = Pipeline([
        ("imputer", SimpleImputer(strategy="most_frequent")),
        ("onehot", OneHotEncoder(handle_unknown="ignore")),
    ])
    return ColumnTransformer([
        ("num", numeric_pipe, NUMERIC_FEATURES),
        ("cat", categorical_pipe, CATEGORICAL_FEATURES),
    ])


def _feature_importance(pipe: Pipeline, model_name: str) -> pd.DataFrame:
    pre = pipe.named_steps["preprocess"]
    model = pipe.named_steps["model"]
    try:
        names = pre.get_feature_names_out()
    except Exception:
        names = np.array(MODEL_FEATURES)

    if hasattr(model, "feature_importances_"):
        values = np.asarray(model.feature_importances_)
    elif hasattr(model, "coef_"):
        values = np.abs(np.asarray(model.coef_)).ravel()
    else:
        return pd.DataFrame(columns=["feature", "importance", "model"])

    size = min(len(names), len(values))
    frame = pd.DataFrame({
        "feature": [str(name).replace("num__", "").replace("cat__", "") for name in names[:size]],
        "importance": values[:size],
        "model": model_name,
    })
    return frame.sort_values("importance", ascending=False).reset_index(drop=True)


def train_models_from_dataframe(df: pd.DataFrame, source_name: str = "diabetes.csv") -> ModelBundle:
    data = normalize_columns(df)
    missing = validate_training_data(data)
    if missing:
        raise ValueError("Faltan columnas requeridas para entrenar: " + ", ".join(missing))

    for column in NUMERIC_FEATURES + ["glyhb"]:
        data[column] = pd.to_numeric(data[column], errors="coerce")

    data = data.dropna(subset=["glyhb"]).copy()
    data["target"] = (data["glyhb"] >= 6.5).astype(int)
    if data["target"].nunique() < 2:
        raise ValueError("La clase objetivo necesita registros de ambas categorías.")

    X = data[MODEL_FEATURES].copy()
    y = data["target"].astype(int)
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.20, random_state=42, stratify=y
    )

    estimators = [
        (
            "Random Forest",
            RandomForestClassifier(
                n_estimators=500,
                max_depth=8,
                min_samples_leaf=2,
                class_weight="balanced",
                random_state=42,
            ),
        ),
        (
            "Regresión logística",
            LogisticRegression(
                max_iter=3000,
                class_weight="balanced",
                random_state=42,
            ),
        ),
    ]

    min_class = int(y.value_counts().min())
    folds = min(5, max(2, min_class))
    cv = StratifiedKFold(n_splits=folds, shuffle=True, random_state=42)
    candidates: list[ModelCandidate] = []

    for model_name, estimator in estimators:
        pipe = Pipeline([("preprocess", _preprocessor()), ("model", estimator)])
        pipe.fit(X_train, y_train)
        pred = pipe.predict(X_test)
        probability = pipe.predict_proba(X_test)[:, 1]
        try:
            cv_f1 = float(cross_val_score(pipe, X, y, cv=cv, scoring="f1").mean())
        except Exception:
            cv_f1 = float("nan")
        metrics = {
            "accuracy": float(accuracy_score(y_test, pred)),
            "precision": float(precision_score(y_test, pred, zero_division=0)),
            "recall": float(recall_score(y_test, pred, zero_division=0)),
            "f1": float(f1_score(y_test, pred, zero_division=0)),
            "roc_auc": float(roc_auc_score(y_test, probability)),
            "cv_f1": cv_f1,
            "n_total": float(len(data)),
            "n_train": float(len(X_train)),
            "n_test": float(len(X_test)),
        }
        candidates.append(ModelCandidate(
            name=model_name,
            pipeline=pipe,
            metrics=metrics,
            cm=confusion_matrix(y_test, pred, labels=[0, 1]),
            y_true=y_test.to_numpy(),
            y_pred=np.asarray(pred),
            y_probability=np.asarray(probability),
            feature_importance=_feature_importance(pipe, model_name),
        ))

    # El proyecto expuesto es explícitamente híbrido con Random Forest. La regresión
    # logística se conserva como modelo de comparación, pero no reemplaza al bosque
    # seleccionado para las inferencias de la aplicación.
    selected = next(item for item in candidates if item.name == "Random Forest")
    return ModelBundle(selected=selected, candidates=candidates, training_data=data, source_name=source_name)


def train_models_from_bytes(csv_bytes: bytes, source_name: str = "diabetes.csv") -> ModelBundle:
    return train_models_from_dataframe(read_csv_bytes(csv_bytes), source_name=source_name)


def patient_model_row(values: dict[str, Any]) -> pd.DataFrame:
    ratio = float(values.get("ratio") or (float(values["chol"]) / max(float(values["hdl"]), 0.01)))
    return pd.DataFrame([{
        "chol": float(values["chol"]),
        "stab.glu": float(values.get("stab_glu", values.get("stab.glu"))),
        "hdl": float(values["hdl"]),
        "ratio": ratio,
        "age": float(values["age"]),
        "gender": str(values["gender"]),
        "height": cm_to_inches(float(values["height_cm"])),
        "weight": kg_to_pounds(float(values["weight_kg"])),
        "frame": str(values["frame"]),
        "bp.1s": float(values["bp1s"]),
        "bp.1d": float(values["bp1d"]),
        "bp.2s": float(values["bp2s"]),
        "bp.2d": float(values["bp2d"]),
        "waist": cm_to_inches(float(values["waist_cm"])),
        "hip": cm_to_inches(float(values["hip_cm"])),
        "time.ppn": float(values["time_ppn"]),
    }])


def predict_probability(bundle: ModelBundle | None, values: dict[str, Any]) -> float | None:
    if bundle is None:
        return None
    row = patient_model_row(values)
    return float(bundle.selected.pipeline.predict_proba(row)[:, 1][0])


def metrics_dataframe(bundle: ModelBundle) -> pd.DataFrame:
    rows = []
    for candidate in bundle.candidates:
        rows.append({
            "Modelo": candidate.name,
            "Accuracy": candidate.metrics["accuracy"],
            "Precision": candidate.metrics["precision"],
            "Recall": candidate.metrics["recall"],
            "F1": candidate.metrics["f1"],
            "ROC-AUC": candidate.metrics["roc_auc"],
            "F1 validación cruzada": candidate.metrics["cv_f1"],
            "Seleccionado": candidate.name == bundle.selected.name,
        })
    return pd.DataFrame(rows)
