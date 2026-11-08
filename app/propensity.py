"""Win-back propensity: which dropped leads should a Saathi call first?

Uses only what is known when the lead arrives (no stage dates, drop reasons or
outcomes), so there is no leakage. Time-based split: train on April-May leads,
evaluate on June leads. SHAP gives each lead its top reasons in plain words.
"""
from __future__ import annotations

from functools import lru_cache

import lightgbm as lgb
import numpy as np
import pandas as pd
import shap
from sklearn.metrics import roc_auc_score

from .config import DATA_DIR
from .registry import mask

CAT = ["lead_source", "segment", "business_type", "preferred_language", "annual_turnover_band",
       "current_internet", "current_provider", "city"]
NUM = ["city_tier", "employee_count", "num_sites", "monthly_telecom_spend_inr", "n_interests",
       "has_gstin_y", "has_udyam_y", "created_dow"]
PRETTY = {"lead_source": "Lead source", "segment": "Segment", "business_type": "Business type",
          "preferred_language": "Language", "annual_turnover_band": "Turnover", "current_internet": "Current internet",
          "current_provider": "Current provider", "city": "City", "city_tier": "City tier",
          "employee_count": "Staff", "num_sites": "Sites", "monthly_telecom_spend_inr": "Telecom spend",
          "n_interests": "Products asked about", "has_gstin_y": "Has GSTIN", "has_udyam_y": "Has Udyam",
          "created_dow": "Day created"}


def features(df: pd.DataFrame) -> pd.DataFrame:
    X = pd.DataFrame(index=df.index)
    for c in CAT:
        X[c] = df[c].fillna("NA").astype("category")
    X["city_tier"] = df["city_tier"].astype(int)
    X["employee_count"] = df["employee_count"].astype(int)
    X["num_sites"] = df["num_sites"].astype(int)
    X["monthly_telecom_spend_inr"] = df["monthly_telecom_spend_inr"].astype(float)
    X["n_interests"] = df["products_of_interest"].fillna("").str.count(";") + df["products_of_interest"].notna()
    X["has_gstin_y"] = (df["has_gstin"] == "Y").astype(int)
    X["has_udyam_y"] = (df["has_udyam"] == "Y").astype(int)
    X["created_dow"] = pd.to_datetime(df["created_date"]).dt.dayofweek
    return X


@lru_cache(maxsize=1)
def model() -> dict:
    df = pd.read_csv(DATA_DIR / "smb_leads.csv")
    y = (df["outcome"] == "Activated").astype(int)
    X = features(df)
    created = pd.to_datetime(df["created_date"])
    train, test = created < "2026-06-01", created >= "2026-06-01"
    params = dict(n_estimators=300, learning_rate=0.03, num_leaves=15, min_child_samples=40,
                  subsample=0.8, subsample_freq=1, colsample_bytree=0.8, reg_lambda=2.0, verbose=-1, random_state=7)
    clf = lgb.LGBMClassifier(**params).fit(X[train], y[train])
    p_test = clf.predict_proba(X[test])[:, 1]
    auc = roc_auc_score(y[test], p_test)
    k = int(0.2 * test.sum())
    top = np.argsort(-p_test)[:k]
    capture = y[test].values[top].sum() / y[test].sum()
    final = lgb.LGBMClassifier(**params).fit(X, y)            # refit on all data for scoring
    return {"clf": final, "X": X, "df": df, "auc": round(float(auc), 3),
            "top20_capture": round(float(capture), 3), "lift": round(float(capture / 0.2), 2),
            "n_train": int(train.sum()), "n_test": int(test.sum())}


def reasons_for(row_shap: np.ndarray, row: pd.Series, n: int = 3) -> list[dict]:
    order = np.argsort(-np.abs(row_shap))[:n]
    out = []
    for i in order:
        col = row.index[i]
        val = row.iloc[i]
        val = "Yes" if col.endswith("_y") and val == 1 else ("No" if col.endswith("_y") else val)
        out.append({"feature": PRETTY.get(col, col), "value": str(val), "direction": "up" if row_shap[i] > 0 else "down"})
    return out


def winback_queue(limit: int = 50) -> dict:
    m = model()
    df, X = m["df"], m["X"]
    dropped = df["outcome"] != "Activated"
    Xd = X[dropped]
    scores = m["clf"].predict_proba(Xd)[:, 1]
    order = np.argsort(-scores)[:limit]
    sv = shap.TreeExplainer(m["clf"]).shap_values(Xd.iloc[order])
    sv = sv[1] if isinstance(sv, list) else sv
    rows = []
    for rank, (idx, s) in enumerate(zip(order, sv), 1):
        lead = df[dropped].iloc[idx]
        rows.append({"rank": rank, "lead_id": lead["lead_id"], "business": lead["business_name"],
                     "segment": lead["segment"], "city": lead["city"], "language": lead["preferred_language"],
                     "gstin": mask(lead["gstin"]) if isinstance(lead["gstin"], str) else "—",
                     "dropped_at": lead["stage_reached"], "drop_reason": lead["drop_reason"],
                     "score": round(float(scores[idx]) * 100), "reasons": reasons_for(s, Xd.iloc[idx])})
    return {"model": {"auc": m["auc"], "top20_capture": m["top20_capture"], "lift": m["lift"],
                      "train": m["n_train"], "test": m["n_test"], "split": "time-based: Apr-May train, Jun test"},
            "queue": rows}
