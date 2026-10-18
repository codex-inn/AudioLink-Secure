import asyncio
import json
import secrets
import string
import time
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

app = FastAPI(title="AudioLink Secure", version="0.1.0")
BASE_DIR = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

# In-memory MVP only. Sessions disappear when the service restarts.
SESSIONS: dict[str, dict[str, Any]] = {}
SESSION_TTL_SECONDS = 60 * 60


def new_code() -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(8))


def cleanup_sessions() -> None:
    now = time.time()
    for code in list(SESSIONS):
        session = SESSIONS[code]
        if now - session["created_at"] > SESSION_TTL_SECONDS:
            SESSIONS.pop(code, None)


@app.get("/", response_class=HTMLResponse)
async def home():
    return (BASE_DIR / "static" / "index.html").read_text(encoding="utf-8")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "AudioLink Secure"}


@app.post("/api/session")
async def create_session():
    cleanup_sessions()
    if len(SESSIONS) >= 500:
        raise HTTPException(status_code=503, detail="Too many active sessions. Try again later.")
    code = new_code()
    while code in SESSIONS:
        code = new_code()
    SESSIONS[code] = {
        "sender": None,
        "receivers": {},
        "created_at": time.time(),
    }
    return {"code": code, "expires_in_seconds": SESSION_TTL_SECONDS}


@app.websocket("/ws/{code}/{role}")
async def websocket_endpoint(websocket: WebSocket, code: str, role: str):
    await websocket.accept()
    session = SESSIONS.get(code)
    if not session or time.time() - session["created_at"] > SESSION_TTL_SECONDS:
        await websocket.send_json({"type": "error", "message": "Session not found or expired."})
        await websocket.close(code=1008)
        return

    peer_id = secrets.token_urlsafe(9)
    if role == "sender":
        if session["sender"] is not None:
            await websocket.send_json({"type": "error", "message": "A sender is already connected."})
            await websocket.close(code=1008)
            return
        session["sender"] = websocket
        await websocket.send_json({"type": "sender_ready", "code": code})
    elif role == "receiver":
        session["receivers"][peer_id] = {"ws": websocket, "approved": False}
        await websocket.send_json({"type": "receiver_ready", "peer_id": peer_id})
    else:
        await websocket.send_json({"type": "error", "message": "Invalid role."})
        await websocket.close(code=1008)
        return

    try:
        while True:
            message = await websocket.receive_json()
            kind = message.get("type")
            if role == "receiver":
                if kind == "join":
                    sender = session.get("sender")
                    if sender is None:
                        await websocket.send_json({"type": "error", "message": "Sender is not online yet."})
                        continue
                    await sender.send_json({
                        "type": "join_request",
                        "peer_id": peer_id,
                        "label": str(message.get("label", "Receiver"))[:60],
                    })
                elif kind in {"offer", "candidate", "hangup"}:
                    receiver = session["receivers"].get(peer_id)
                    if not receiver or not receiver["approved"]:
                        await websocket.send_json({"type": "error", "message": "This receiver has not been approved."})
                        continue
                    sender = session.get("sender")
                    if sender:
                        await sender.send_json({**message, "peer_id": peer_id})
            else:
                target_id = str(message.get("peer_id", ""))
                receiver = session["receivers"].get(target_id)
                if kind == "approve":
                    if receiver:
                        receiver["approved"] = True
                        await receiver["ws"].send_json({"type": "approved"})
                elif kind == "reject":
                    if receiver:
                        await receiver["ws"].send_json({"type": "rejected"})
                        session["receivers"].pop(target_id, None)
                elif kind in {"answer", "candidate", "hangup"}:
                    if receiver and receiver["approved"]:
                        await receiver["ws"].send_json(message)
    except WebSocketDisconnect:
        pass
    except Exception:
        # A disconnected peer should not take down the shared signaling service.
        pass
    finally:
        if role == "sender":
            if session.get("sender") is websocket:
                session["sender"] = None
            for rid, receiver in list(session["receivers"].items()):
                try:
                    await receiver["ws"].send_json({"type": "sender_disconnected"})
                except Exception:
                    pass
        else:
            session["receivers"].pop(peer_id, None)
            sender = session.get("sender")
            if sender:
                try:
                    await sender.send_json({"type": "receiver_disconnected", "peer_id": peer_id})
                except Exception:
                    pass
