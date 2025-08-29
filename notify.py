# notify.py
import os, json
from typing import Any, Dict
from fastapi import APIRouter
from pydantic import BaseModel
import requests

import firebase_admin
from firebase_admin import credentials, firestore, messaging

router = APIRouter(prefix="/notify", tags=["notify"])

def _ensure_firebase():
    if not firebase_admin._apps:
        sa_json = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS_JSON")
        if not sa_json:
            raise RuntimeError("Missing GOOGLE_APPLICATION_CREDENTIALS_JSON")
        cred = credentials.Certificate(json.loads(sa_json))
        firebase_admin.initialize_app(cred)
    return firestore.client()

def _binance_price(symbol: str) -> float:
    base = os.environ.get("BINANCE_BASE_URL", "https://api.binance.com")
    r = requests.get(f"{base}/api/v3/ticker/price", params={"symbol": symbol}, timeout=8)
    r.raise_for_status()
    return float(r.json()["price"])

class Watch(BaseModel):
    account_id: str
    scenario_id: str
    symbol: str
    tf: str
    type: str  # 'pullback' | 'breakout'
    params: Dict[str, Any]
    token: str

@router.post("/subscribe")
def subscribe(w: Watch):
    db = _ensure_firebase()
    doc_id = f"{w.account_id}:{w.scenario_id}"
    db.collection("watches").document(doc_id).set(
        {**w.dict(), "active": True, "createdAt": firestore.SERVER_TIMESTAMP},
        merge=True
    )
    return {"ok": True, "id": doc_id}

@router.post("/unsubscribe")
def unsubscribe(account_id: str, scenario_id: str):
    db = _ensure_firebase()
    doc_id = f"{account_id}:{scenario_id}"
    db.collection("watches").document(doc_id).set(
        {"active": False, "disabledAt": firestore.SERVER_TIMESTAMP},
        merge=True
    )
    return {"ok": True}

def _condition_ok(w: dict, price: float) -> bool:
    t = w.get("type")
    p = w.get("params", {})
    if t == "pullback":
        lo, hi = float(p["buy_zone"][0]), float(p["buy_zone"][1])
        return lo <= price <= hi
    if t == "breakout":
        level = float(p["level"])
        return price > level
    return False

def _send_push(token: str, title: str, body: str, data: Dict[str, str] | None = None):
    data = {k: str(v) for k, v in (data or {}).items()}
    msg = messaging.Message(
        token=token,
        notification=messaging.Notification(title=title, body=body),
        webpush=messaging.WebpushConfig(
            headers={"TTL": "60"},
            fcm_options=messaging.WebpushFCMOptions(link=data.get("url", "/"))
        ),
        data=data
    )
    messaging.send(msg)

def run_scan_once() -> int:
    db = _ensure_firebase()
    q = db.collection("watches").where("active", "==", True).stream()
    sent = 0
    for doc in q:
        w = doc.to_dict()
        try:
            price = _binance_price(w["symbol"])
        except Exception:
            continue
        if _condition_ok(w, price):
            try:
                _send_push(
                    w["token"],
                    f"{w['symbol']} • cenário {w['type'].upper()}",
                    f"Preço atual {price:.2f} atingiu a condição",
                    {"symbol": w["symbol"], "scenario_id": w["scenario_id"], "url": "/trade/trade_ia.html"}
                )
                db.collection("watches").document(doc.id).set(
                    {"active": False, "notifiedAt": firestore.SERVER_TIMESTAMP, "lastPrice": price},
                    merge=True
                )
                sent += 1
            except Exception:
                pass
    return sent

@router.post("/scan")
def scan():
    count = run_scan_once()
    return {"ok": True, "notified": count}
