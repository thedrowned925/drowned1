import os

os.environ["DROWNED_REMOTE_TOKEN"] = "relay-test-secret"

from fastapi.testclient import TestClient

import server

server.TOKEN = "relay-test-secret"
client = TestClient(server.app)
HEADERS = {"Authorization": "Bearer relay-test-secret"}


def main():
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["storage"] == "none"

    unauthorized = client.get("/api/mobile/test-pc/presence")
    assert unauthorized.status_code == 401

    with client.websocket_connect("/ws/agent/test-pc", headers=HEADERS) as agent:
        presence = client.get("/api/mobile/test-pc/presence", headers=HEADERS)
        assert presence.status_code == 200
        assert presence.json()["agent_online"] is True

        first = client.get("/api/mobile/test-pc/next", headers=HEADERS)
        assert first.status_code == 200
        assert first.json()["type"] == "relay_state"
        assert first.json()["agent_online"] is True

        agent.send_json({"type": "agent_status", "hostname": "TEST-PC", "cpu": 12.5})
        relayed = client.get("/api/mobile/test-pc/next", headers=HEADERS)
        assert relayed.status_code == 200
        assert relayed.json()["type"] == "agent_status"
        assert relayed.json()["hostname"] == "TEST-PC"

        command = {"type": "command", "command": "request_status", "request_id": "smoke-1"}
        posted = client.post("/api/mobile/test-pc/command", headers=HEADERS, json=command)
        assert posted.status_code == 200
        received = agent.receive_json()
        assert received == command


if __name__ == "__main__":
    main()
