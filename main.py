from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

from uuid import uuid4, UUID

app = FastAPI()

html = """
<!DOCTYPE html>
<html>
    <head>
        <title>Chat</title>
    </head>
    <body>
        <h1>WebSocket Chat</h1>
        <form action="" onsubmit="sendMessage(event)">
            <input type="text" id="messageText" autocomplete="off"/>
            <button>Send</button>
        </form>
        <ul id='messages'>
        </ul>
        <script>
            var ws = new WebSocket("ws://localhost:8000/ws");
            ws.onmessage = function(event) {
                var messages = document.getElementById('messages')
                var message = document.createElement('li')
                var content = document.createTextNode(event.data)
                message.appendChild(content)
                messages.appendChild(message)
            };
            function sendMessage(event) {
                var input = document.getElementById("messageText")
                ws.send(input.value)
                input.value = ''
                event.preventDefault()
            }
        </script>
    </body>
</html>
"""


class User:
    def __init__(self, ws: WebSocket = None, nickname: str = None, admin: UUID = None):
        self.nickname =  nickname
        self.ws = ws
        self.admin = admin


class UserManager:
    def __init__(self):
        self.__users = dict()

    async def connect(self, ws: WebSocket) -> UUID:
        id = uuid4()
        self.__users[id] = User(ws)
        await self.broadcast(f'connect|{id}')
        return id

    async def restore(self, id: UUID, old_id: UUID, ws: WebSocket):
        self.__users[old_id].ws = ws
        del self.__users[id]
        await self.broadcast(f'{id} is replaced with {old_id}')
        await self.broadcast(f'{old_id} is back online')
        # await notify_group(f'{old_id} is back online')

    @staticmethod
    async def send(ws: WebSocket, message: str):
        if not ws:
            return
        await ws.send_text(message)

    async def change_nickname(self, id: UUID, new_nickname: str):
        self.__users[id].nickname = new_nickname
        await self.notify_group(f'nickname_changed|{id}|{new_nickname}')

    def set_admin(self, id: UUID, admin: UUID):
        self.__users[id].admin = admin

    def set_ws(self, id: UUID, ws: WebSocket):
        self.__users[id].ws = ws

    async def notify_admin(self, id: UUID, message: str):
        await self.send(self.__users[self.__users[id].admin].ws, message)

    # async def notify_team(self, id: UUID, message: str):
    #     user = self.__users.get(id)
    #     if not user:
    #         return 1
    #
    #     for player in self.__users.values():
    #         if player.admin == user.admin:
    #             await self.send(user.ws, message)

    async def notify_group(self, id: UUID, message: str):
        user = self.__users.get(id)
        if not user:
            return 1

        for player in self.__users.values():
            if player.admin == user.admin:
                await self.send(user.ws, message)

    async def broadcast(self, message: str):
        for user in self.__users.values():
            await self.send(user.ws, message)

    async def disconnect(self, id: UUID):
        self.__users[id].ws = None
        # self.notify_group(uuid, f'disconnect|{uuid}')
        await self.broadcast(f'disconnect|{id}')

    def get_ids(self) -> list:
        return self.__users.keys()


manager = UserManager()


@app.get("/")
async def get():
    return HTMLResponse(html)


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    id = await manager.connect(ws)
    try:
        while True:
            action, *payload = (await ws.receive_text()).split('|')
            await ws.send_text(f"Message text was: {action}")

            match action:
                case 'change_nickname':
                    await manager.change_nickname(id, payload[0])
                case 'broadcast':
                    await manager.broadcast('|'.join(payload))
                case 'restore_id':
                    await manager.restore(id, UUID(payload[0]), ws)
                case 'clients':
                    await ws.send_text(f'clients are {manager.get_ids()}')
                case _:
                    await ws.send_text('Unknown request')
    except WebSocketDisconnect:
        await manager.disconnect(id)

