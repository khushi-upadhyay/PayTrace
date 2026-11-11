"""Synthetic rrweb recording for the seeded demo session, so the replay player has something to show."""
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

_CSS = (
    "body{margin:0;font-family:Helvetica,Arial,sans-serif;background:#f4f6fb;color:#0f172a}"
    ".card{max-width:520px;margin:60px auto;background:#fff;border:1px solid #dbe2ef;border-radius:16px;padding:32px}"
    "h1{font-size:22px;margin:0 0 6px}p{margin:0 0 18px;color:#475569}"
    ".item{border:1px solid #cbd5e1;border-radius:10px;padding:14px;margin-bottom:18px}"
    "button{background:#0070ba;color:#fff;border:0;border-radius:999px;padding:12px 22px;font-size:15px;font-weight:700}"
    ".status{margin-top:18px;font-size:14px;color:#0f766e}"
)

# Node ids in the snapshot below; incremental events refer to these.
ITEM_ID, BUTTON_ID, STATUS_TEXT_ID = 11, 14, 17


def _el(node_id: int, tag: str, children: List[Dict[str, Any]], **attributes: str) -> Dict[str, Any]:
    return {"type": 2, "tagName": tag, "attributes": attributes, "childNodes": children, "id": node_id}


def _text(node_id: int, text: str, **extra: Any) -> Dict[str, Any]:
    return {"type": 3, "textContent": text, "id": node_id, **extra}


def _snapshot_document() -> Dict[str, Any]:
    body = _el(7, "body", [
        _el(8, "div", [
            _el(9, "h1", [_text(10, "Checkout")]),
            _el(11, "div", [_text(12, "Enterprise Server Plan - $189.99")], **{"class": "item"}),
            _el(13, "p", [_text(15, "Pay securely with PayPal Sandbox.")]),
            _el(14, "button", [_text(16, "Pay with PayPal Sandbox")]),
            _el(18, "div", [_text(STATUS_TEXT_ID, "Ready to pay")], **{"class": "status"}),
        ], **{"class": "card"}),
    ])
    head = _el(4, "head", [_el(5, "style", [_text(6, _CSS, isStyle=True)])])
    html = _el(3, "html", [head, body], lang="en")
    return {"type": 0, "childNodes": [{"type": 1, "name": "html", "publicId": "", "systemId": "", "id": 2}, html], "id": 1}


def _ms(moment: datetime) -> int:
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return int(moment.timestamp() * 1000)


def build_demo_replay(anchor: datetime, route: str = "/checkout") -> List[Dict[str, Any]]:
    """rrweb events around `anchor` (the moment the capture timed out): -40s to +25s."""
    t0 = _ms(anchor - timedelta(seconds=40))

    def at(seconds: float) -> int:
        return t0 + int(seconds * 1000)

    def move(seconds: float, x: int, y: int, target: int) -> Dict[str, Any]:
        return {"type": 3, "timestamp": at(seconds), "data": {"source": 1, "positions": [{"x": x, "y": y, "id": target, "timeOffset": 0}]}}

    def click(seconds: float, x: int, y: int, target: int) -> Dict[str, Any]:
        return {"type": 3, "timestamp": at(seconds), "data": {"source": 2, "type": 2, "id": target, "x": x, "y": y}}

    def status(seconds: float, value: str) -> Dict[str, Any]:
        return {"type": 3, "timestamp": at(seconds), "data": {"source": 0, "texts": [{"id": STATUS_TEXT_ID, "value": value}], "attributes": [], "removes": [], "adds": []}}

    return [
        {"type": 4, "timestamp": at(0), "data": {"href": f"http://localhost:3000{route}", "width": 1280, "height": 720}},
        {"type": 2, "timestamp": at(0.05), "data": {"node": _snapshot_document(), "initialOffset": {"top": 0, "left": 0}}},
        move(2, 300, 200, 9), move(3, 420, 280, ITEM_ID), move(4, 440, 300, ITEM_ID),
        click(10, 440, 300, ITEM_ID), status(10.1, "Selected: Enterprise Server Plan - $189.99"),
        move(20, 520, 420, 13), move(24, 560, 450, BUTTON_ID),
        click(25, 560, 450, BUTTON_ID), status(25.1, "Processing payment with PayPal..."),
        status(40, "Waiting for PayPal response..."),
        move(52, 600, 500, 18),
        status(55, "Still waiting - this is taking longer than expected"),
        move(64, 610, 510, 18),
    ]
