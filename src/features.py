"""Transformações compartilhadas por treino e inferência (dentro do modelo MLflow)."""
from __future__ import annotations

import re

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin

# Campos do CSV Kaggle/da disciplina; identificadores e Credit_Score nunca entram no modelo.
NUMERIC = [
    "Age", "Annual_Income", "Monthly_Inhand_Salary", "Num_Bank_Accounts",
    "Num_Credit_Card", "Interest_Rate", "Num_of_Loan", "Delay_from_due_date",
    "Num_of_Delayed_Payment", "Changed_Credit_Limit", "Num_Credit_Inquiries",
    "Outstanding_Debt", "Credit_Utilization_Ratio", "Total_EMI_per_month",
    "Amount_invested_monthly", "Monthly_Balance",
]
CATEGORICAL = [
    "Occupation", "Type_of_Loan", "Credit_Mix", "Payment_of_Min_Amount",
    "Payment_Behaviour",
]
REQUIRED = NUMERIC + CATEGORICAL + ["Credit_History_Age"]
DERIVED = [
    "Credit_History_Months", "Income_to_EMI", "Income_to_Debt", "Debt_to_Income",
    "EMI_to_Income", "Delay_Rate", "Inquiry_Rate", "Credit_Utilization_per_account",
    "Log_Income", "Log_Debt", "Log_EMI",
]
FEATURE_NUMERIC = NUMERIC + DERIVED
CLIP_MAX = {"Age": 100, "Num_Bank_Accounts": 10, "Num_Credit_Card": 10,
            "Num_of_Delayed_Payment": 30, "Num_of_Loan": 20}
CLIP_MIN_ZERO = ["Delay_from_due_date", "Total_EMI_per_month", "Interest_Rate",
                 "Num_Credit_Inquiries", "Outstanding_Debt", "Monthly_Inhand_Salary"]


def _credit_months(value):
    if pd.isna(value):
        return np.nan
    text = str(value)
    years = re.search(r"(\d+)\s*Years?", text)
    months = re.search(r"(\d+)\s*Months?", text)
    return ((int(years.group(1)) if years else 0) * 12
            + (int(months.group(1)) if months else 0)) if years or months else np.nan


class CreditFeatures(BaseEstimator, TransformerMixin):
    """Transformação sem estado; imputação e vocabulário são ajustados no Pipeline.

    Assim a validação e os folds de CV não vazam estatísticas do treino, e o
    modelo registrado aceita os mesmos campos crus da API (sem SSN/nome/ID).
    """

    def fit(self, X, y=None):
        self._check(X)
        return self

    @staticmethod
    def _check(X):
        missing = set(REQUIRED) - set(X.columns)
        if missing:
            raise ValueError(f"Campos obrigatórios ausentes: {', '.join(sorted(missing))}")

    def transform(self, X):
        self._check(X)
        df = X[REQUIRED].copy()
        for col in NUMERIC:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df["Credit_History_Months"] = df["Credit_History_Age"].map(_credit_months)
        df = df.drop(columns="Credit_History_Age")
        for col, high in CLIP_MAX.items():
            df[col] = df[col].clip(lower=0, upper=high)
        for col in CLIP_MIN_ZERO:
            df[col] = df[col].clip(lower=0)
        # Cotas fixas evitam calcular quantis com dados de inferência; imputação
        # de nulos e categorias desconhecidas é aprendida SOMENTE no fit.
        salary = df["Monthly_Inhand_Salary"].fillna(0).clip(lower=0)
        debt = df["Outstanding_Debt"].fillna(0).clip(lower=0)
        emi = df["Total_EMI_per_month"].fillna(0).clip(lower=0)
        history = df["Credit_History_Months"].fillna(0).clip(lower=0)
        df["Income_to_EMI"] = salary / (emi + 1)
        df["Income_to_Debt"] = salary / (debt + 1)
        df["Debt_to_Income"] = debt / (salary + 1)
        df["EMI_to_Income"] = emi / (salary + 1)
        df["Delay_Rate"] = df["Num_of_Delayed_Payment"].fillna(0) / (history + 1)
        df["Inquiry_Rate"] = df["Num_Credit_Inquiries"].fillna(0) / (history + 1)
        df["Credit_Utilization_per_account"] = df["Credit_Utilization_Ratio"] / (df["Num_Credit_Card"].fillna(0) + 1)
        df["Log_Income"] = np.log1p(salary)
        df["Log_Debt"] = np.log1p(debt)
        df["Log_EMI"] = np.log1p(emi)
        for col in CATEGORICAL:
            df[col] = df[col].fillna("Unknown").replace("_", "Unknown").astype(str)
        return df[FEATURE_NUMERIC + CATEGORICAL]
