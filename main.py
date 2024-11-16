from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

from uuid import uuid4, UUID

import json

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
    def __init__(self, ws: WebSocket = None, username: str = None):
        self.ws = ws
        self.username = username
        # self.admin = admin
        self.group_id = None
        self.image = None
        self.id = uuid4()

    def to_json(self) -> str:
        return json.dumps({
            'username': self.username,
            'group_id': self.group_id,
            'image': self.image,
        })
    
    # TODO exceptions
    def from_json(self, json_data: str, ws: WebSocket) -> None:
        self.ws = ws
        # try:
        json_data = json.loads(json_data)
        self.username = json_data['username']
        self.group_id = json_data['group_id']
        self.image = json_data['image']
        # except json.decoder.JSONDecodeError:
        #     pass
        # except KeyError:
        #     pass


class Group:
    def __init__(self, admin_id: UUID, name: str = None):
        self.name = name
        self.admin_id = admin_id  # admin user id
        self.image = None
        self.members = list()
        self.id = uuid4()

    def to_json(self) -> str:
        return json.dumps({
            'username': self.name,
            'admin_id': self.admin_id,
            'image': self.image,
            'members': self.members,
        })
    
    # TODO exceptions
    def from_json(self, json_data: str) -> None:
        json_data = json.loads(json_data)
        self.name = json_data['name']
        self.admin_id = json_data['admin_id']
        self.image = json_data['image']
        self.members = json_data['members']


class Message:
    # TODO exceptions
    def __init__(self, message: str):
        self.from_json(message)

    def __init__(self, type: str, data: str, request_id: UUID = uuid4()):
        self.type = type
        self.data = data
        self.request_id = request_id

    def get_type(self) -> str:
        return self.type

    def to_json(self) -> str:
        return json.dumps({
            'type': self.type,
            'data': self.data,
            'request_id': str(self.request_id),
        })
    
    # TODO exceptions
    def from_json(self, json_data: str) -> None:
        json_data = json.loads(json_data)
        self.type = json_data['type']
        self.data = json_data['data']
        self.request_id = UUID(json_data['request_id'])


# TODO exceptions
class db:
    def __init__(self):
        self.__users = dict()
        self.__groups = dict()

    def add_or_update_user(self, user: User) -> None:
        user_id = user.id
        self.__users[user_id] = user

    def get_user(self, user_id: UUID) -> User:
        return self.__users.get(user_id)
    
    def add_or_update_group(self, group: Group) -> None:
        group_id = group.id
        self.__groups[group_id] = group

    def get_group(self, group_id: UUID) -> Group:
        return self.__groups.get(group_id)



class UserManager:
    def __init__(self):
        self.__users = dict()
        self.__groups = dict()

    async def connect(self, ws: WebSocket) -> UUID:
        id = uuid4()
        self.__users[id] = User(ws)
        # await self.broadcast(f'connect|{id}')
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


    async def set_user_name(self, id: UUID, new_username: str):
        self.__users[id].username = new_username
        await self.send('set_user_name|ok')

    async def get_user_name(self, id: UUID):
        await self.send(f'get_user_name|{self.__users[id].username}')


    async def set_user_image(self, id: UUID, image: str):
        self.__users[id].image = image
        await self.send('set_user_image|ok')

    async def get_user_image(self, id: UUID):
        await self.send(f'get_user_image|{self.__users[id].image}')

    
    async def create_group(self, user_id: UUID):
        user = self.__users[id]
        if user.group_id is not None:
            old_group = self.__groups[user.group_id]
            if old_group.admin_id == user_id:
                await self.send(f'create_group|error|this user already is an admin in another group')
                return
            await self.send(f'create_group|error|this user is already a member of another group')
            return
        new_group_id = uuid4()
        self.__groups[new_group_id] = Group(admin_id=user_id)
        self.__users[user_id].group_id = new_group_id
        await self.send(f'create_group|{new_group_id}')

    # async def get_group(self, user_id)



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

if __name__ == '__main__':
    app = FastAPI()
    # manager = UserManager()


@app.get("/")
async def get():
    return HTMLResponse(html)

 
@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    # размер картинок
    
    await ws.accept()
    # id = await manager.connect(ws)
    user_id = uuid4()
    try:
        while True:
            try:
                message = Message(await ws.receive_text())
            except (json.decoder.JSONDecodeError, KeyError) as e:
                await ws.send_text(
                    Message(
                        type='error',
                        data=['invalid json'],
                        request_id=uuid4()
                    ).to_json()
                )

            # action, *payload = (await ws.receive_text()).split('|', 1)
            # await ws.send_text(f"Message text was: {action}")

            match action:
                # case 'get_user_image':
                #     await manager.get_image(id)
                # case 'set_user_image':
                #     await manager.set_image(id, payload[0])

                # case 'get_user_name':
                #     await manager.get_user_name(id)
                # case 'set_user_name':
                #     await manager.set_user_name(id, payload[0])

                # case 'get_group_name': # id в запросе
                #     # await manager.set_user_name(id, payload[0])
                # case 'set_group_name': # id в запросе
                #     # await manager.set_user_name(id, payload[0])

                # case 'get_group_image': # id в запросе
                #     # await manager.set_image(id, payload[0])
                # case 'set_group_image': # id в запросе
                #     await manager.set_image(id, payload[0])

                # case 'get_groups':
                #     # await manager.set_user_name(id, payload[0])
                #     # <- get_groups|group_id,group_id,group_id

                # case 'get_group_members': # group id в запросе
                #     # await manager.set_user_name(id, payload[0])
                #     # <- get_group_members|user_id,user_id,user_id

                # case 'add_group_member': # group id в запросе
                #     # await manager.set_image(id, payload[0])

                # case 'set_user_ready': # true / false в запросе
                #     # await manager.set_image(id, payload[0])

                




                case 'restore_user_id':
                    await manager.restore(id, UUID(payload[0]), ws)


                case 'broadcast':
                    await manager.broadcast('|'.join(payload))
                case 'clients':
                    await ws.send_text(f'clients are {manager.get_ids()}')

                case _:
                    await ws.send_text('Unknown request')
    except WebSocketDisconnect:
        await manager.disconnect(id)

