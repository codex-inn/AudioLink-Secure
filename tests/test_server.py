from fastapi.testclient import TestClient

from server import app, SESSIONS

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_create_session_and_sender_socket():
    response = client.post("/api/session")
    assert response.status_code == 200
    code = response.json()["code"]
    assert len(code) == 8
    assert code in SESSIONS

    with client.websocket_connect(f"/ws/{code}/sender") as websocket:
        message = websocket.receive_json()
        assert message["type"] == "sender_ready"
        assert message["code"] == code


def test_invalid_session_is_rejected():
    with client.websocket_connect("/ws/INVALID1/receiver") as websocket:
        message = websocket.receive_json()
        assert message["type"] == "error"
