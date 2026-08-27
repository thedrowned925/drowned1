import asyncio
import hmac
import json
import os
import time
from collections import defaultdict

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

app = FastAPI(title="Drowned Remote Relay")
TOKEN = os.getenv("DROWNED_REMOTE_TOKEN", "").strip()
agents = {}
mobiles = defaultdict(set)
mobile_queues = {}
lock = asyncio.Lock()


def token_ok(value):
    if not TOKEN or not value.lower().startswith("bearer "):
        return False
    return hmac.compare_digest(value[7:].strip(), TOKEN)


def authorized_ws(ws):
    return token_ok(ws.headers.get("authorization", ""))


def authorized_request(request):
    return token_ok(request.headers.get("authorization", ""))


async def send(ws, payload):
    try:
        await ws.send_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
        return True
    except Exception:
        return False


def purge_screen_frames(device_id):
    queue = mobile_queues.get(device_id)
    if queue is None:
        return
    keep = []
    while True:
        try:
            item = queue.get_nowait()
        except asyncio.QueueEmpty:
            break
        if item.get("type") != "screen_frame":
            keep.append(item)
    for item in keep[-7:]:
        try:
            queue.put_nowait(item)
        except asyncio.QueueFull:
            break


def queue_message(device_id, payload):
    if payload.get("type") in {"test_approved", "test_failed", "test_stopped"}:
        purge_screen_frames(device_id)
    queue = mobile_queues.setdefault(device_id, asyncio.Queue(maxsize=8))
    if queue.full():
        try:
            queue.get_nowait()
        except asyncio.QueueEmpty:
            pass
    try:
        queue.put_nowait(payload)
    except asyncio.QueueFull:
        pass


async def broadcast(device_id, payload):
    queue_message(device_id, payload)
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


@app.get("/api/mobile/{device_id}/presence")
async def mobile_presence(device_id: str, request: Request):
    if not authorized_request(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    device_id = device_id.lower().strip()
    async with lock:
        online = device_id in agents
    return {"type": "relay_state", "device_id": device_id, "agent_online": online, "timestamp": time.time()}


@app.get("/api/mobile/{device_id}/next")
async def mobile_next(device_id: str, request: Request):
    if not authorized_request(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    device_id = device_id.lower().strip()
    queue = mobile_queues.setdefault(device_id, asyncio.Queue(maxsize=8))
    try:
        payload = await asyncio.wait_for(queue.get(), timeout=25)
        return payload
    except asyncio.TimeoutError:
        async with lock:
            online = device_id in agents
        return {"type": "relay_state", "device_id": device_id, "agent_online": online, "timestamp": time.time()}


@app.post("/api/mobile/{device_id}/command")
async def mobile_command(device_id: str, request: Request):
    if not authorized_request(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    device_id = device_id.lower().strip()
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid_json"}, status_code=400)
    async with lock:
        agent = agents.get(device_id)
    if agent is None:
        return JSONResponse({"error": "agent_offline"}, status_code=503)
    if not await send(agent, payload):
        async with lock:
            if agents.get(device_id) is agent:
                agents.pop(device_id, None)
        return JSONResponse({"error": "agent_disconnected"}, status_code=503)
    return {"ok": True}


@app.websocket("/ws/{role}/{device_id}")
async def relay(ws: WebSocket, role: str, device_id: str):
    role = role.lower()
    device_id = device_id.lower().strip()
    if role not in {"agent", "mobile"} or not device_id or not authorized_ws(ws):
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
        purge_screen_frames(device_id)
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
