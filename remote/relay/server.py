import asyncio
import hmac
import json
import os
import time
from collections import defaultdict

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

app = FastAPI(title="Drowned Remote Relay")
TOKEN = os.getenv("DROWNED_REMOTE_TOKEN", "").strip()
agents = {}
mobiles = defaultdict(set)
lock = asyncio.Lock()


def authorized(ws):
    auth = ws.headers.get("authorization", "")
    if not TOKEN or not auth.lower().startswith("bearer "):
        return False
    return hmac.compare_digest(auth[7:].strip(), TOKEN)


async def send(ws, payload):
    try:
        await ws.send_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
        return True
    except Exception:
        return False


async def broadcast(device_id, payload):
    async with lock:
        targets = list(mobiles.get(device_id, set()))
    dead = []
    for ws in targets:
        if not await send(ws, payload):
            dead.append(ws)
    if dead:
        async with lock:
            for ws in dead:
                mobiles[device_id].discard(ws)


@app.get("/health")
async def health():
    async with lock:
        return {
            "ok": True,
            "agents_online": len(agents),
            "mobile_sessions": sum(len(x) for x in mobiles.values()),
            "storage": "none",
            "timestamp": time.time(),
        }


@app.websocket("/ws/{role}/{device_id}")
async def relay(ws: WebSocket, role: str, device_id: str):
    role = role.lower()
    device_id = device_id.lower().strip()
    if role not in {"agent", "mobile"} or not device_id or not authorized(ws):
        await ws.close(code=1008)
        return
    await ws.accept()
    if role == "agent":
        await agent_connection(ws, device_id)
    else:
        await mobile_connection(ws, device_id)


async def agent_connection(ws, device_id):
    async with lock:
        old = agents.get(device_id)
        agents[device_id] = ws
    if old and old is not ws:
        try:
            await old.close(code=1012)
        except Exception:
            pass
    await broadcast(device_id, {
        "type": "relay_state", "device_id": device_id,
        "agent_online": True, "timestamp": time.time(),
    })
    try:
        while True:
            message = json.loads(await ws.receive_text())
            await broadcast(device_id, message)
    except (WebSocketDisconnect, json.JSONDecodeError):
        pass
    finally:
        async with lock:
            if agents.get(device_id) is ws:
                agents.pop(device_id, None)
        await broadcast(device_id, {
            "type": "relay_state", "device_id": device_id,
            "agent_online": False, "timestamp": time.time(),
        })


async def mobile_connection(ws, device_id):
    async with lock:
        mobiles[device_id].add(ws)
        online = device_id in agents
    await send(ws, {
        "type": "relay_state", "device_id": device_id,
        "agent_online": online, "timestamp": time.time(),
    })
    try:
        while True:
            message = json.loads(await ws.receive_text())
            async with lock:
                agent = agents.get(device_id)
            if agent is None:
                await send(ws, {
                    "type": "relay_state", "device_id": device_id,
                    "agent_online": False, "timestamp": time.time(),
                })
            else:
                await send(agent, message)
    except (WebSocketDisconnect, json.JSONDecodeError):
        pass
    finally:
        async with lock:
            mobiles[device_id].discard(ws)
            if not mobiles[device_id]:
                mobiles.pop(device_id, None)
