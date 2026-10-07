import json
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
from fastapi.testclient import TestClient

from src import api
from src.features import CreditFeatures, REQUIRED
from src.predict import CreditScorePredictor, ModelNotAvailableError
from src.train import choose, make_pipeline
from sklearn.ensemble import RandomForestClassifier

SAMPLE = json.loads((Path(__file__).resolve().parents[1] / "examples" / "cliente.json").read_text())


def test_features_stable_with_new_category():
    data = pd.DataFrame([SAMPLE, {**SAMPLE, "Occupation": "Unknown", "Credit_History_Age": "NA"}])
    model = make_pipeline(RandomForestClassifier(n_estimators=5, random_state=42))
    model.fit(data, [0, 1])
    assert len(model.predict(pd.DataFrame([{**SAMPLE, "Occupation": "New Occupation"}]))) == 1
    assert CreditFeatures().transform(data)["Credit_History_Months"].iloc[0] == 265
    assert set(REQUIRED) <= set(SAMPLE)


def test_choose_baseline_incumbent_and_tie():
    results = [{"f1_val": 0.71, "f1_train": 0.85, "name": "a"},
               {"f1_val": 0.707, "f1_train": 0.72, "name": "b"}]
    assert choose(results)["name"] == "b"  # empate técnico, menor gap
    assert choose(results, incumbent_f1=0.706) is None  # exige melhoria >= 0.005
    assert choose(results, minimum=0.75) is None


def test_predict_reloads_on_new_production(monkeypatch):
    p = CreditScorePredictor()
    p.client = MagicMock()
    versions = iter(["1", "1", "2"])
    monkeypatch.setattr("src.predict.production_version", lambda client: next(versions))
    model = MagicMock()
    model.predict.return_value = [2]
    loader = MagicMock(return_value=model)
    monkeypatch.setattr("src.predict.mlflow.pyfunc.load_model", loader)
    assert p.predict(SAMPLE)["model_version"] == "1"
    assert p.predict(SAMPLE)["credit_score_predicted"] == "Standard"
    assert p.predict(SAMPLE)["model_version"] == "2"
    assert loader.call_count == 2


def test_api_security_errors_and_success(monkeypatch):
    monkeypatch.setenv("QF_API_KEYS", "test-key")
    monkeypatch.setenv("QF_RATE_PER_SECOND", "2")
    monkeypatch.setenv("QF_RATE_PER_MINUTE", "2")
    api._buckets.clear()
    monkeypatch.setattr(api.predictor, "predict", lambda payload: {"credit_score_predicted": "Good", "model_version": "2"})
    with TestClient(api.app) as client:
        url = "/credit-score/v1/predict"
        assert client.get("/credit-score/v1/health").json() == {"status": "ok"}
        assert client.post(url, json=SAMPLE).status_code == 401
        assert client.post(url, json={}, headers={"X-API-Key": "test-key"}).status_code == 400
        headers = {"X-API-Key": "test-key", "X-Request-Id": "abc"}
        ok = client.post(url, json=SAMPLE, headers=headers)
        assert ok.status_code == 200
        assert ok.json() == {"credit_score_predicted": "Good", "model_version": "2", "request_id": "abc"}
        assert client.post(url, json=SAMPLE, headers=headers).status_code == 200
        limited = client.post(url, json=SAMPLE, headers=headers)
        assert limited.status_code == 429 and "Retry-After" in limited.headers


def test_api_missing_production(monkeypatch):
    monkeypatch.setenv("QF_API_KEYS", "another-key")
    api._buckets.clear()
    def unavailable(payload):
        raise ModelNotAvailableError("nothing")
    monkeypatch.setattr(api.predictor, "predict", unavailable)
    with TestClient(api.app) as client:
        response = client.post("/credit-score/v1/predict", json=SAMPLE, headers={"X-API-Key": "another-key"})
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "model_not_available"
