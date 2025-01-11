import contextlib
import json

import pytest
from fastapi.testclient import TestClient
from starlette.testclient import WebSocketTestSession

from main import app, Message, MessageType, uuid4, UUID, FieldNames


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


@pytest.fixture(scope="module")
def websockets(client):
    num_clients = 3
    with contextlib.ExitStack() as stack:
        connections = [
            stack.enter_context(client.websocket_connect('/ws'))
            for _ in range(num_clients)
        ]
        yield connections


@pytest.fixture(scope="module")
def user_id():
    return None


@pytest.fixture(scope="module")
def created_user_id(websockets):
    ws1 = websockets[0]

    request = Message(
        type=MessageType.SET_USER_INFO,
        data={
            FieldNames.USER_NAME: 'Alex',
            FieldNames.USER_IMAGE: 'test'
        },
        request_id=uuid4()
    )

    ws1.send_json(request)
    actual_response = Message.from_dict(ws1.receive_json())
    return UUID(actual_response.data[FieldNames.USER_ID])


@pytest.fixture(scope="module")
def test_set_user_info1(websockets):
    ws1 = websockets[0]

    request = Message(
        type=MessageType.SET_USER_INFO,
        data={
            FieldNames.USER_NAME: 'Alex',
            FieldNames.USER_IMAGE: 'test'
        },
        request_id=uuid4()
    )

    ws1.send_json(request)

    actual_response = Message.from_dict(ws1.receive_json())
    print(actual_response)

    assert actual_response.type == MessageType.SUCCESS
    assert actual_response.request_id == request.request_id
    assert isinstance(actual_response.data, dict)
    assert FieldNames.USER_ID.value in actual_response.data
    assert len(actual_response.data.keys()) == 1
    pytest.user_id = UUID(actual_response.data[FieldNames.USER_ID])


def get_user(ws: WebSocketTestSession, user_id: UUID):
    request = Message(
        type=MessageType.GET_USER_INFO,
        data=user_id,
        request_id=uuid4()
    )
    expected_response = Message(
        type=MessageType.SUCCESS,
        data=json.loads(json.dumps(app.state.db.get_user(user_id).to_dict())),
        request_id=request.request_id
    )

    ws.send_json(request)

    actual_response = Message.from_dict(ws.receive_json())
    assert actual_response == expected_response


def test_get_user1(websockets, created_user_id):
    get_user(ws=websockets[0], user_id=created_user_id)

def test_get_user2(websockets, created_user_id):
    get_user(ws=websockets[1], user_id=created_user_id)


