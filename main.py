from __future__ import annotations

import os

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from uuid import UUID as UUID_non_serializable
import json
from enum import Enum, StrEnum
from dataclasses import dataclass, field, asdict
from typing import Dict, Any
import json_fix as _ # for json.dumps() to work on custom classes with __json__ method
import uvicorn # for debugging


class UUID(UUID_non_serializable):
    def __json__(self):
        return self.hex


def uuid4():
    """Generate a random UUID. Overridden to return the customized UUID type"""
    return UUID(bytes=os.urandom(16), version=4)


class MessageType(Enum):
    # User related
    GET_USER_INFO = 'get_user_info'
    SET_USER_INFO = 'set_user_info'
    
    # Group related
    # CREATE_GROUP = 'create_group' # = set_group_info
    DELETE_GROUP = 'delete_group' # != admin leaves the group
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


class FieldNames(StrEnum):
    MESSAGE_REQUEST_ID = 'requestId'
    MESSAGE_TYPE = 'тип'
    MESSAGE_DATA = 'data'

    USER_ID = 'userId'
    USER_NAME = 'userName'
    USER_IMAGE = 'picture'
    USER_GROUP_ID = 'groupId'

    GROUP_ID = 'groupId'
    GROUP_NAME = 'groupName'
    GROUP_MEMBERS = 'groupMembers'
    GROUP_ADMIN_ID = 'groupAdminId'


@dataclass
class User:
    id: UUID
    name: str = field(compare=False)
    image: str = field(compare=False)
    group_id: UUID | None = field(compare=False, default=None)

# TODO UUID control
    def to_dict(self) -> dict:
        return {
            FieldNames.USER_ID.value: self.id,
            FieldNames.USER_NAME: self.name,
            FieldNames.USER_IMAGE: self.image,
            FieldNames.USER_GROUP_ID: self.group_id,
        }

# TODO group_id
    @classmethod
    def from_dict(cls, data: dict) -> User:
        # return cls(**data)
        if group_id := data.get(FieldNames.USER_GROUP_ID):
            group_id = UUID(group_id)
        return cls(
            id=data[FieldNames.USER_ID],
            name=data[FieldNames.USER_NAME],
            image=data[FieldNames.USER_IMAGE],
            group_id=group_id
        )


@dataclass
class Group:
    id: UUID = field(init=False, default_factory=uuid4)
    admin_id: UUID = field(compare=False)
    name: str = field(compare=False)
    members: set[UUID] = field(compare=False, init=False, default_factory=set)

    def update_from_dict(self, data: dict):
        new_group = self.__class__.from_dict(data)
        self.name = new_group.name

    @classmethod
    def from_dict(cls, data: dict) -> Group:
        return cls(**data)

    def to_dict(self) -> dict:
        return {
            FieldNames.GROUP_ID: self.id,
            FieldNames.GROUP_NAME: self.name,
            FieldNames.GROUP_MEMBERS: self.members,
        }


@dataclass
class Message:
    type: MessageType
    data: Any
    request_id: UUID = field(default_factory=uuid4)

    @classmethod
    def from_dict(cls, data: dict) -> Message:
        # return cls(**data)
        return cls(
            type=data[FieldNames.MESSAGE_TYPE],
            data=data[FieldNames.MESSAGE_DATA],
            request_id=data[FieldNames.MESSAGE_REQUEST_ID]
        )

    def __json__(self):
        return {
            FieldNames.MESSAGE_TYPE: self.type,
            FieldNames.MESSAGE_DATA: self.data,
            FieldNames.MESSAGE_REQUEST_ID: self.request_id,
        }

    def to_dict(self) -> dict:
        return {
            FieldNames.MESSAGE_TYPE: self.type.value,
            FieldNames.MESSAGE_DATA: self.data,
            FieldNames.MESSAGE_REQUEST_ID: self.request_id,
        }


# TODO exceptions
class DB:
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
            for user in group.members:
                user.group_id = None
            del self.__groups[group_id]
            

class WebSocketManager:
    def __init__(self, db: DB):
        self.__connections: Dict[UUID, WebSocket] = dict()
        self.db = db

    async def connect(self, ws: WebSocket) -> UUID:
        await ws.accept()
        user_id = uuid4()
        self.__connections[user_id] = ws
        return user_id

    async def disconnect(self, user_id: UUID):
        if user_id in self.__connections:
            del self.__connections[user_id]
            user = self.db.get_user(user_id)
            # TODO user deletion?
            if user and user.group_id:
                await self.broadcast_to_group(
                    user.group_id,
                    Message(
                        type=MessageType.DISCONNECT,
                        data={
                            FieldNames.USER_ID: user_id,
                        },
                        request_id=uuid4()
                    )
                )

    # TODO reconnect

    async def send_personal_message(self, user_id: UUID, message: Message):
        if user_id in self.__connections:
            await self.__connections[user_id].send_json(message.to_dict())

    # TODO overload for group:Group
    async def broadcast_to_group(self, group_id: UUID, message: Message):
        if group := self.db.get_group(group_id):
            for member_id in group.members:
                await self.send_personal_message(member_id, message)


class MessageHandler:
    def __init__(self, ws_manager: WebSocketManager, db: DB):
        self.ws_manager = ws_manager
        self.db = db

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
                MessageType.DELETE_GROUP: self.handle_delete_group,
            }
            
            if handler := handlers.get(message_type):
                return await handler(user_id, message)

            return Message(
                type=MessageType.ERROR,
                data='unknown message type',
                request_id=message.request_id
            )
        
        # TODO specify Exception
        except Exception as e:
            return Message(
                type=MessageType.ERROR,
                data=str(e),
                request_id=message.request_id
            )

    async def handle_get_user_info(self, user_id: UUID, message: Message) -> Message:
        try:
            if not (requested_user_id := UUID(message.data.get('user_id'))):
                return Message(
                    type=MessageType.ERROR,
                    data='user_id is missing',
                    request_id=message.request_id
                )
            if user := self.db.get_user(requested_user_id):
                return Message(
                    type=MessageType.SUCCESS,
                    data=user.to_dict(),
                    request_id=message.request_id
                )
            return Message(
                type=MessageType.ERROR,
                data='user not found',
                request_id=message.request_id
            )
        # TODO specify Exception
        except Exception as e:
            return Message(
                type=MessageType.ERROR,
                data=str(e),
                request_id=message.request_id
            )

    async def handle_set_user_info(self, user_id: UUID, message: Message) -> Message:
        # TODO notify group members?
        try:
            # Do not allow to update group_id directly
            if old_user := self.db.get_user(user_id):
                message.data = message.data | {FieldNames.USER_GROUP_ID: old_user.group_id}
            new_user = User.from_dict(message.data | {FieldNames.USER_ID: user_id})
            self.db.add_or_update_user(user=new_user)
            return Message(
                type=MessageType.SUCCESS,
                data={
                    FieldNames.USER_ID: user_id,
                },
                request_id=message.request_id
            )
        # TODO specify Exception
        except Exception as e:
            return Message(
                type=MessageType.ERROR,
                data=f'failed to update user info: {str(e)}',
                request_id=message.request_id
            )

    async def handle_get_group_info(self, user_id: UUID, message: Message) -> Message:
        try:
            if not (group_id := UUID(message.data.get(FieldNames.GROUP_ID))):
                return Message(
                    type=MessageType.ERROR,
                    data='group_id is missing',
                    request_id=message.request_id
                )
            if not (group := self.db.get_group(group_id)):
                return Message(
                    type=MessageType.ERROR,
                    data='group_id is wrong',
                    request_id=message.request_id
                )
            return Message(
                type=MessageType.SUCCESS,
                data=group.to_dict(),
                request_id=message.request_id
            )
        # TODO specify Exception
        except Exception as e:
            return Message(
                type=MessageType.ERROR,
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
                        type=MessageType.ERROR,
                        data='user is already a group member',
                        request_id=message.request_id
                    )
                # update group info
                group.update_from_dict(message.data)
                self.db.add_or_update_group(group)
                return Message(
                    type=MessageType.SUCCESS,
                    data='group updated',
                    request_id=message.request_id
                )
            
            group = Group.from_dict(message.data | {FieldNames.GROUP_ADMIN_ID: user_id})
            group.members.add(user_id)
            self.db.add_or_update_group(group)
            user.group_id = group.id
            self.db.add_or_update_user(user)
            
            return Message(
                type=MessageType.SUCCESS,
                data={
                    FieldNames.GROUP_ID: group.id,
                },
                request_id=message.request_id
            )
        # TODO specify Exception
        except Exception as e:
            return Message(
                type=MessageType.ERROR,
                data=f'failed to create group: {str(e)}',
                request_id=message.request_id
            )

    async def handle_join_group(self, user_id: UUID, message: Message) -> Message:
        try:
            if not message.data.get(FieldNames.GROUP_ID):
                return Message(
                    type=MessageType.ERROR,
                    data='group_id is missing',
                    request_id=message.request_id
                )
            group_id = UUID(message.data.get(FieldNames.GROUP_ID))
            self.db.join_group(group_id, user_id)

            await self.ws_manager.broadcast_to_group(
                group_id,
                Message(
                    type=MessageType.JOIN_GROUP,
                    data={FieldNames.USER_ID: user_id},
                    request_id=uuid4()
                )
            )

            return Message(
                type=MessageType.SUCCESS,
                data='joined the group',
                request_id=message.request_id
            )
        # TODO specify Exception
        except Exception as e:
            return Message(
                type=MessageType.ERROR,
                data=f'failed to join a group: {str(e)}',
                request_id=message.request_id
            )

    async def handle_leave_group(self, user_id: UUID, message: Message) -> Message:
        user = self.db.get_user(user_id)
        if not (group_id := user.group_id):
            return Message(
                type=MessageType.ERROR,
                data='user is not a group member',
                request_id=message.request_id
            )

        self.db.leave_group(user_id)
        await self.ws_manager.broadcast_to_group(
            group_id,
            Message(
                type=MessageType.LEAVE_GROUP,
                data={FieldNames.USER_ID: user_id},
                request_id=uuid4()
            )
        )
        return Message(
            type=MessageType.SUCCESS,
            data='left the group',
            request_id=message.request_id
        )

    async def handle_delete_group(self, user_id: UUID, message: Message) -> Message:
        user = self.db.get_user(user_id)
        group = self.db.get_group(user.group_id)

        if group.admin_id != user_id:
            return Message(
                type=MessageType.ERROR,
                data='only admin can delete the group',
                request_id=message.request_id
            )

        for member_id in group.members:
            await self.ws_manager.send_personal_message(
                member_id,
                Message(
                    type=MessageType.DELETE_GROUP,
                    data='group is deleted',
                    request_id=uuid4()
                )
            )
        self.db.delete_group(group.id)
        return Message(
            type=MessageType.SUCCESS,
            data='group is deleted',
            request_id=message.request_id
        )


app = FastAPI()
db = DB()
ws_manager = WebSocketManager(db)
message_handler = MessageHandler(ws_manager, db)


@app.get('/')
async def get():
    return FileResponse('index.html')


@app.websocket('/ws')
async def websocket_endpoint(ws: WebSocket):
    user_id = await ws_manager.connect(ws)
    try:
        while True:
            try:
                text = await ws.receive_text()
                text = text.replace("'", '"')
                print(text)
                message = Message.from_dict(json.loads(text))
                response = await message_handler.handle_message(user_id, message)
                
                # Respond
                await ws_manager.send_personal_message(user_id, response)
                
            except (json.JSONDecodeError, TypeError):
                await ws_manager.send_personal_message(
                    user_id,
                    Message(
                        type=MessageType.ERROR,
                        data='invalid json format',
                        request_id=uuid4()
                    )
                )
    except WebSocketDisconnect:
        await ws_manager.disconnect(user_id)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000) # for debugging
