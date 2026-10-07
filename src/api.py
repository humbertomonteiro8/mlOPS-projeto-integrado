"""API local FastAPI: chave por parceiro e throttling em memória por chave.

Produção multi-réplica exige Redis/API gateway para limites globais e HTTPS/TLS.
"""
from __future__ import annotations

import os
import secrets
import threading
import time
import uuid
from collections import defaultdict, deque

from fastapi import FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from src.predict import CreditScorePredictor, ModelNotAvailableError

app = FastAPI(title="QuantumFinance Credit Score", version="1.0")
predictor = CreditScorePredictor()
_buckets = defaultdict(deque)
_lock = threading.Lock()


class CreditRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    Age: int
    Annual_Income: float = Field(allow_inf_nan=False)
    Monthly_Inhand_Salary: float = Field(allow_inf_nan=False)
    Num_Bank_Accounts: int
    Num_Credit_Card: int
    Interest_Rate: int
    Num_of_Loan: int
    Delay_from_due_date: int
    Num_of_Delayed_Payment: int
    Changed_Credit_Limit: float = Field(allow_inf_nan=False)
    Num_Credit_Inquiries: float = Field(allow_inf_nan=False)
    Outstanding_Debt: float = Field(allow_inf_nan=False)
    Credit_Utilization_Ratio: float = Field(allow_inf_nan=False)
    Total_EMI_per_month: float = Field(allow_inf_nan=False)
    Amount_invested_monthly: float = Field(allow_inf_nan=False)
    Monthly_Balance: float = Field(allow_inf_nan=False)
    Occupation: str
    Type_of_Loan: str
    Credit_Mix: str
    Payment_of_Min_Amount: str
    Payment_Behaviour: str
    Credit_History_Age: str


def error(code, message, request_id, status, headers=None):
    return JSONResponse(status_code=status,
                        content={"error": {"code": code, "message": message, "request_id": request_id}},
                        headers=headers)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request.state.request_id = request.headers.get("X-Request-Id") or str(uuid.uuid4())
    response = await call_next(request)
    response.headers["X-Request-Id"] = request.state.request_id
    return response


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    return error("invalid_payload", "JSON inválido ou campos faltando/com tipo inválido.",
                 request.state.request_id, 400)


def allow_request(key):
    now = time.monotonic()
    minute_limit = int(os.getenv("QF_RATE_PER_MINUTE", "60"))
    second_limit = int(os.getenv("QF_RATE_PER_SECOND", "10"))
    with _lock:
        bucket = _buckets[key]
        while bucket and bucket[0] <= now - 60:
            bucket.popleft()
        recent = [t for t in bucket if t > now - 1]
        wait = (bucket[0] + 60 - now) if len(bucket) >= minute_limit else (
            recent[0] + 1 - now if len(recent) >= second_limit else 0)
        if wait > 0:
            return False, max(1, int(wait) + 1), max(0, minute_limit - len(bucket))
        bucket.append(now)
        return True, 0, max(0, minute_limit - len(bucket))


@app.get("/credit-score/v1/health")
def health():
    # Apenas liveness; Production é conferido sob demanda no /predict.
    return {"status": "ok"}


@app.post("/credit-score/v1/predict")
def predict(request: Request, payload: CreditRequest, x_api_key: str | None = Header(default=None)):
    request_id = request.state.request_id
    keys = [x.strip() for x in os.getenv("QF_API_KEYS", "").split(",") if x.strip()]
    if not keys:
        return error("service_not_configured", "Chaves da API não configuradas.", request_id, 503)
    if not x_api_key or not any(secrets.compare_digest(x_api_key, k) for k in keys):
        return error("invalid_api_key", "X-API-Key ausente ou inválida.", request_id, 401)
    allowed, retry, remaining = allow_request(x_api_key)
    if not allowed:
        return error("rate_limit_exceeded", "Limite de chamadas excedido.", request_id, 429,
                     headers={"Retry-After": str(retry)})
    try:
        result = predictor.predict(payload.model_dump())
    except ModelNotAvailableError:
        return error("model_not_available", "Modelo Production indisponível; execute o treinamento.", request_id, 503)
    except Exception:
        # Não expor paths internos, dados do cliente nem tracebacks na resposta.
        return error("internal_error", "Falha interna ao gerar score.", request_id, 500)
    return JSONResponse({**result, "request_id": request_id}, headers={"X-RateLimit-Limit": os.getenv("QF_RATE_PER_MINUTE", "60"),
                                                                   "X-RateLimit-Remaining": str(remaining)})
