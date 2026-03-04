from datetime import datetime, timezone
from typing import List, Tuple
from .db import get_conn

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def lane_type(seller_postcode: str, buyer_postcode: str) -> str:
    try:
        return "METRO" if str(seller_postcode)[0] == str(buyer_postcode)[0] else "REGIONAL"
    except Exception:
        return "REGIONAL"

def provider_enabled(provider: str) -> bool:
    conn = get_conn()
    try:
        row = conn.execute("SELECT is_enabled FROM provider_status WHERE provider=?", (provider,)).fetchone()
        return bool(row["is_enabled"]) if row else False
    finally:
        conn.close()

def recent_failures(provider: str) -> int:
    conn = get_conn()
    try:
        row = conn.execute(
            """SELECT COUNT(*) AS c
                FROM label_attempts
                WHERE provider=? AND success=0
                  AND created_at >= datetime('now','-5 minutes')""",
            (provider,),
        ).fetchone()
        return int(row["c"])
    finally:
        conn.close()

def get_carriers() -> List[dict]:
    conn = get_conn()
    try:
        rows = conn.execute("SELECT * FROM carriers").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()

def quote_for_order(order: dict, carrier: dict) -> dict:
    prov = carrier["provider"]
    lt = lane_type(order["seller_postcode"], order["buyer_postcode"])
    weight = float(order["weight_kg"])
    method = order["collection_method"]

    eligible = True
    reason = None

    if not provider_enabled(prov):
        eligible = False
        reason = "PROVIDER_DISABLED"
    if int(carrier["enabled"]) != 1:
        eligible = False
        reason = reason or "CARRIER_DISABLED"
    if weight > float(carrier["max_weight_kg"]):
        eligible = False
        reason = reason or "OVER_MAX_WEIGHT"
    if method == "PICKUP" and int(carrier["supports_pickup"]) != 1:
        eligible = False
        reason = reason or "NO_PICKUP"
    if method == "DROPOFF" and int(carrier["supports_dropoff"]) != 1:
        eligible = False
        reason = reason or "NO_DROPOFF"
    if method == "PRINTER_FREE" and int(carrier["supports_printer_free"]) != 1:
        eligible = False
        reason = reason or "NO_PRINTER_FREE"
    if eligible and recent_failures(prov) >= 2:
        eligible = False
        reason = "UNHEALTHY_RECENT_FAILURES"

    cost = float(carrier["base_price"]) + float(carrier["price_per_kg"]) * weight
    if method in ("PICKUP", "PRINTER_FREE"):
        cost += float(carrier["pickup_fee"])

    est_days = int(carrier["metro_sla_days"] if lt == "METRO" else carrier["regional_sla_days"])

    return {
        "order_id": order["order_id"],
        "provider": prov,
        "lane_type": lt,
        "quoted_cost": round(cost, 2) if eligible else None,
        "estimated_days": est_days if eligible else None,
        "eligible": 1 if eligible else 0,
        "ineligible_reason": reason,
        "created_at": now_iso(),
    }

def persist_quotes(quotes: List[dict]) -> None:
    conn = get_conn()
    try:
        for q in quotes:
            conn.execute(
                """INSERT INTO rate_quotes(order_id, provider, lane_type, quoted_cost, estimated_days, eligible, ineligible_reason, created_at)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (q["order_id"], q["provider"], q["lane_type"], q["quoted_cost"], q["estimated_days"], q["eligible"], q["ineligible_reason"], q["created_at"]),
            )
        conn.commit()
    finally:
        conn.close()

def generate_quotes(order: dict) -> List[dict]:
    quotes = [quote_for_order(order, c) for c in get_carriers()]
    persist_quotes(quotes)
    return quotes

def choose_best_provider(order: dict, quotes: List[dict]) -> Tuple[str, dict]:
    eligible = [q for q in quotes if q["eligible"] == 1]
    if not eligible:
        return "NONE", {"selection_reason": "NO_ELIGIBLE_CARRIER"}

    promised = int(order["promised_days"])
    meets = [q for q in eligible if int(q["estimated_days"]) <= promised]
    if meets:
        best = sorted(meets, key=lambda x: (float(x["quoted_cost"]), int(x["estimated_days"])))[0]
        return best["provider"], {"selection_reason": "CHEAPEST_MEETING_PROMISE", "chosen_quote": best}

    best = sorted(eligible, key=lambda x: (int(x["estimated_days"]), float(x["quoted_cost"])))[0]
    return best["provider"], {"selection_reason": "BEST_AVAILABLE_PROMISE_RISK", "chosen_quote": best}
