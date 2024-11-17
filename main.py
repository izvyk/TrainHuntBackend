from __future__ import annotations
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from uuid import uuid4, UUID
import json
from enum import Enum
from dataclasses import dataclass, field, asdict
from typing import Dict


html = '''
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
                ws.send(input.name)
                input.name = ''
                event.preventDefault()
            }
        </script>
    </body>
</html>
'''


class MessageType(Enum):
    # User related
    GET_USER_INFO = 'get_user_info'
    SET_USER_INFO = 'set_user_info'
    
    # Group related
    # CREATE_GROUP = 'create_group' # = set_group_info
    # DELETE_GROUP = 'delete_group' # = admin leaves the group
    JOIN_GROUP = 'join_group'
    LEAVE_GROUP = 'leave_group'
    GET_GROUP_INFO = 'get_group_info'
    SET_GROUP_INFO = 'set_group_info'
    # GET_GROUP_MEMBERS = 'get_group_members' # ?
    
    # System messages
    ERROR = 'error'
    SUCCESS = 'success'

    # Connection
    CONNECT = 'connect'
    DISCONNECT = 'disconnect'


@dataclass
class User:
    id: UUID
    username: str = field(compare=False)
    group_id: UUID = field(compare=False)
    image: str = field(compare=False)

    def to_json(self) -> str:
        return json.dumps(asdict(self))
    
    @classmethod
    def from_json(cls, json_str: str) -> User:
        data = json.loads(json_str)
        return cls(**data)


@dataclass
class Group:
    id: UUID = field(init=False, default_factory=uuid4)
    admin_id: UUID = field(compare=False)
    name: str = field(compare=False)
    image: str = field(compare=False)
    members: set[UUID] = field(compare=False, init=False, default_factory=set)

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    def update_from_json(self, json_str: str):
        new_group = self.__class__.from_json(json_str)
        self.name = new_group.name
        self.image = new_group.image

    @classmethod
    def from_json(cls, json_str: str) -> Group:
        data = json.loads(json_str)
        return cls(**data)


@dataclass
class Message:
    type: MessageType
    data: str
    request_id: UUID = field(default_factory=uuid4)

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, json_str: str) -> Message:
        data = json.loads(json_str)
        return cls(**data)


# TODO exceptions
class db:
    def __init__(self):
        self.__users = dict()
        self.__groups = dict()

    def add_or_update_user(self, user: User):
        self.__users[user.id] = user

    def get_user(self, user_id: UUID) -> User:
        return self.__users.get(user_id)
    
    def add_or_update_group(self, group: Group):
        self.__groups[group.id] = group

    def get_group(self, group_id: UUID) -> Group:
        return self.__groups.get(group_id)

    def join_group(self, group_id: UUID, user_id: UUID):
        user = self.__users.get(user_id)
        group = self.__groups.get(group_id)

        if not user or not group:
            raise ValueError('wrong id')

        # check if user is an admin
        if current_group_id := user.group_id:
            if current_group := self.__groups.get(current_group_id):
                if current_group.admin_id == user_id:
                    raise ValueError('admin cannot join a group')
                # else: # change group
            # else: # member of non-existent group
        # else: # not a group member
        group.members.add(user_id)

    def leave_group(self, user_id: UUID):
        if user := self.__users.get(user_id):
            if group := self.__groups.get(user.group_id):
                group.members.remove(user_id)

            user.group_id = None
    
    def delete_group(self, group_id):
        if group := self.__groups.get(group_id):
            if len(group.members) != 0:
                # TODO specify the exception type
                raise Exception('group is not empty')
            del self.__groups[group_id]
            


class WebSocketManager:
    def __init__(self):
        self.__connections: Dict[UUID, WebSocket] = dict()

    async def connect(self, ws: WebSocket) -> UUID:
        await ws.accept()
        user_id = uuid4()
        self.__connections[user_id] = ws
        return user_id

    async def disconnect(self, user_id: UUID):
        if user_id in self.__connections:
            del self.__connections[user_id]
            user = db.get_user(user_id)
            # TODO user deletion?
            if user and user.group_id:
                await self.broadcast_to_group(
                    user.group_id,
                    Message(
                        type=MessageType.DISCONNECT.value,
                        data={
                            'user_id': user_id,
                        },
                        request_id=uuid4()
                    )
                )

    # TODO reconnect

    async def send_personal_message(self, user_id: UUID, message: Message):
        if user_id in self.__connections:
            await self.__connections[user_id].send_text(message.to_json())

    # TODO overload for group:Group
    async def broadcast_to_group(self, group_id: UUID, message: Message):
        if group := db.get_group(group_id):
            for member_id in group.members:
                await self.send_personal_message(member_id, message)


class MessageHandler:
    def __init__(self, ws_manager: WebSocketManager, db_instance: db):
        self.ws_manager = ws_manager
        self.db = db_instance

    async def handle_message(self, user_id: UUID, message: Message) -> Message:
        try:
            message_type = MessageType(message.type)
            
            handlers = {
                MessageType.GET_USER_INFO: self.handle_get_user_info,
                MessageType.SET_USER_INFO: self.handle_set_user_info,
                MessageType.GET_GROUP_INFO: self.handle_get_group_info,
                MessageType.SET_GROUP_INFO: self.handle_set_group_info,
                MessageType.JOIN_GROUP: self.handle_join_group,
                MessageType.LEAVE_GROUP: self.handle_leave_group,
            }
            
            if handler := handlers.get(message_type):
                return await handler(user_id, message)
            
            return Message(
                type=MessageType.ERROR.value,
                data='unknown message type',
                request_id=message.request_id
            )
        
        # TODO specify Exception
        except Exception as e:
            return Message(
                type=MessageType.ERROR.value,
                data=str(e),
                request_id=message.request_id
            )

    async def handle_get_user_info(self, user_id: UUID, message: Message) -> Message:
        try:
            requested_user_id = json.loads(message.data)['user_id']
            if user := self.db.get_user(requested_user_id):
                return Message(
                    # TODO SUCCESS or USER
                    type=MessageType.SUCCESS.value,
                    data=user.to_json(),
                    request_id=message.request_id
                )
            return Message(
                type=MessageType.ERROR.value,
                data='user not found',
                request_id=message.request_id
            )
        # TODO specify Exception
        except Exception as e:
            return Message(
                type=MessageType.ERROR.value,
                data=str(e),
                request_id=message.request_id
            )

    async def handle_set_user_info(self, user_id: UUID, message: Message) -> Message:
        # TODO notify group members?
        try:
            user = User.from_json(message.data)
            user.id = user_id
            self.db.add_or_update_user(user)
            return Message(
                type=MessageType.SUCCESS.value,
                data='user info saved',
                request_id=message.request_id
            )
        # TODO specify Exception
        except Exception as e:
            return Message(
                type=MessageType.ERROR.value,
                data=f'failed to update user info: {str(e)}',
                request_id=message.request_id
            )

    async def handle_get_group_info(self, user_id: UUID, message: Message) -> Message:
        try:
            if not (group_id := message.data.get('group_id')):
                return Message(
                    type=MessageType.ERROR.value,
                    data=f'no group_id is given',
                    request_id=message.request_id
                )
            if not (group := self.db.get_group(group_id)):
                return Message(
                    type=MessageType.ERROR.value,
                    data=f'group_id is wrong',
                    request_id=message.request_id
                )
            return Message(
                type=MessageType.SUCCESS.value,
                data=group.to_json(),
                request_id=message.request_id
            )
        # TODO specify Exception
        except Exception as e:
            return Message(
                type=MessageType.ERROR.value,
                data=f'failed to get the group: {str(e)}',
                request_id=message.request_id
            )

    async def handle_set_group_info(self, user_id: UUID, message: Message) -> Message:
        try:
            user = self.db.get_user(user_id)
            if user.group_id:
                group = self.db.get_group(user.group_id)

                if group.admin_id != user_id:
                    return Message(
                        type=MessageType.ERROR.value,
                        data='user is already a group member',
                        request_id=message.request_id
                    )
                # update group info
                group.update_from_json(message.data)
                return Message(
                    type=MessageType.SUCCESS.value,
                    data='group updated',
                    request_id=message.request_id
                )
            
            group = Group.from_json(message.data)
            group.admin_id = user_id
            
            self.db.add_or_update_group(group)
            user.group_id = group.id
            self.db.add_or_update_user(user)
            
            return Message(
                type=MessageType.SUCCESS.value,
                data='group created',
                request_id=message.request_id
            )
        # TODO specify Exception
        except Exception as e:
            return Message(
                type=MessageType.ERROR.value,
                data=f'failed to create group: {str(e)}',
                request_id=message.request_id
            )

    async def handle_join_group(self, user_id: UUID, message: Message) -> Message:
        try:
            if not (group_id := message.data.get('group_id')):
                return Message(
                    type=MessageType.ERROR.value,
                    data=f'no group_id is given',
                    request_id=message.request_id
                )
            self.db.join_group(group_id, user_id)

            self.ws_manager.broadcast_to_group(
                group_id,
                Message(
                    type=message.type,
                    data={'user_id': user_id},
                    request_id=uuid4()
                )
            )

            return Message(
                type=MessageType.SUCCESS.value,
                data='joined the group',
                request_id=message.request_id
            )
        # TODO specify Exception
        except Exception as e:
            return Message(
                type=MessageType.ERROR.value,
                data=f'failed to join a group: {str(e)}',
                request_id=message.request_id
            )

    async def handle_leave_group(self, user_id: UUID, message: Message) -> Message:
        user = self.db.get_user(user_id)
        group_id = user.group_id
        group = self.db.get_group(group_id)

        if group.admin_id == user_id:
            for member_id in group.members:
                self.db.leave_group(member_id)
                self.ws_manager.send_personal_message(
                    member_id,
                    Message(
                        type=MessageType.LEAVE_GROUP.value,
                        data=f'group is deleted',
                        request_id=uuid4()
                    )
                )
            self.db.delete_group(group_id)
            self.db.leave_group(user_id)
            return Message(
                type=MessageType.SUCCESS.value,
                data=f'group is deleted',
                request_id=message.request_id
            )

        self.db.leave_group(user_id)
        self.ws_manager.broadcast_to_group(
            group_id,
            Message(
                type=MessageType.LEAVE_GROUP.value,
                data={'user_id': user_id},
                request_id=uuid4()
            )
        )
        return Message(
            type=MessageType.SUCCESS.value,
            data=f'leaved the group',
            request_id=message.request_id
        )

# if __name__ == '__main__':
app = FastAPI()
ws_manager = WebSocketManager()
message_handler = MessageHandler()


@app.get('/')
async def get():
    return HTMLResponse(html)


@app.websocket('/ws')
async def websocket_endpoint(ws: WebSocket):
    user_id = await ws_manager.connect(ws)
    try:
        while True:
            try:
                message = Message(await ws.receive_text())
                
                response = await message_handler.handle_message(user_id, message)
                
                # Respond
                await ws_manager.send_personal_message(user_id, response)
                
            except json.JSONDecodeError:
                await ws_manager.send_personal_message(
                    user_id,
                    Message(
                        type=MessageType.ERROR.value,
                        data='invalid json format',
                        request_id=uuid4()
                    )
                )
    except WebSocketDisconnect:
        await ws_manager.disconnect(user_id)