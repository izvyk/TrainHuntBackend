from __future__ import annotations

import copy
import logging
import os
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from uuid import UUID as UUID_NON_SERIALIZABLE
import json
from enum import Enum, StrEnum
from dataclasses import dataclass, field
from typing import Dict, Any
import random
import json_fix as _ # for json.dumps() to work on custom classes with __json__ method
import uvicorn # for debugging


class UUID(UUID_NON_SERIALIZABLE):
    """Serializable UUID"""
    def __json__(self):
        return str(self)


def uuid4():
    """Generate a random UUID. Overridden to return the customized UUID type"""
    return UUID(bytes=os.urandom(16), version=4)


class MessageType(Enum):
    """
    This enum is an agreement between the server and a client on possible message types.
    """
    # User related
    GET_USER_INFO = 'get_user_info'
    SET_USER_INFO = 'set_user_info'
    SET_USER_READY = 'set_user_ready'

    # Group related
    # CREATE_GROUP = 'create_group' # = set_group_info
    DELETE_GROUP = 'delete_group' # != admin leaves the group
    JOIN_GROUP = 'join_group'
    LEAVE_GROUP = 'leave_group'
    GET_GROUP_INFO = 'get_group_info'
    SET_GROUP_INFO = 'set_group_info'
    SET_GROUP_READY = 'set_group_ready'
    # GET_GROUP_MEMBERS = 'get_group_members' # ?

    SET_TEAMS = 'set_teams'
    GET_TEAMS = 'get_teams'

    COLLECTING_STAMPS_START = 'collecting_stamps_start'
    COLLECTING_STAMPS_QUESTIONS = 'collect_stamps_questions'
    COLLECTING_STAMPS_PROGRESS_UPDATE = 'collect_stamps_progress'

    # System messages
    ERROR = 'error'
    SUCCESS = 'success'

    # Connection
    CONNECT = 'connect'
    DISCONNECT = 'disconnect'
    RECONNECT = 'reconnect'


class FieldNames(StrEnum):
    """
    This enum is an agreement between the server and a client on possible json-message keys.
    """
    MESSAGE_REQUEST_ID = 'requestId'
    MESSAGE_TYPE = 'type'
    MESSAGE_DATA = 'data'

    USER_ID = 'userId'
    USER_NAME = 'userName'
    USER_IMAGE = 'picture'
    USER_GROUP_ID = 'groupId'
    USER_IS_READY = 'isReady'

    GROUP_ID = 'groupId'
    GROUP_NAME = 'groupName'
    GROUP_MEMBERS = 'groupMembers'
    GROUP_ADMIN_ID = 'groupAdminId'
    GROUP_IS_READY = 'isReady'

    TEAM_ID = 'teamId'
    TEAM_GROUP_ID = 'teamGroupId'
    TEAM_MEMBERS = 'teamMembers'
    TEAM_IS_READY = 'teamIsReady'

    QUESTION_TEXT = 'questionText'
    QUESTION_CORRECT_ANSWER = 'correctAnswer'
    QUESTION_WRONG_ANSWERS = 'wrongAnswers'

    GAMESTATE_GAME_TYPE = 'gameType'
    GAMESTATE_GAME_PROGRESS = 'gameProgress'

    COLLECTING_STAMPS_QUESTIONS = 'collectingStampsQuestions'
    COLLECTING_STAMPS_PROGRESS = 'collectingStampsProgress'
    COLLECTING_STAMPS_QUESTION_TEXT = 'collectingStampsQuestionText'


@dataclass
class User:
    """
    A dataclass representing a user
    """
    id: UUID
    name: str | None = field(compare=False)
    image: str | None = field(compare=False)
    group_id: UUID | None = field(compare=False, default=None)
    is_ready: bool = field(init=False, default=False)

# TODO UUID control
    def to_dict(self) -> dict:
        return {
            FieldNames.USER_ID.value: self.id,
            FieldNames.USER_NAME: self.name,
            FieldNames.USER_IMAGE: self.image,
            FieldNames.USER_GROUP_ID: self.group_id,
            FieldNames.USER_IS_READY: self.is_ready,
        }

    @classmethod
    def from_dict(cls, data: dict) -> User:
        # return cls(**data)
        if group_id := data.get(FieldNames.USER_GROUP_ID):
            group_id = UUID(group_id)
        return cls(
            id=UUID(data[FieldNames.USER_ID]),
            name=data[FieldNames.USER_NAME],
            image=data[FieldNames.USER_IMAGE],
            group_id=group_id
        )

    # def update_from_dict(self, data: dict):
    #     self.name = data[FieldNames.USER_NAME]
    #     self.image = data[FieldNames.USER_IMAGE]


@dataclass
class Group:
    """
    A dataclass representing a group
    """
    id: UUID
    admin_id: UUID = field(compare=False)
    name: str = field(compare=False)
    members: set[UUID] = field(compare=False, init=False, default_factory=set)
    is_ready: bool = field(init=False, default=False)

    def update_from_dict(self, data: dict):
        self.name = data[FieldNames.GROUP_NAME]

    @classmethod
    def from_dict(cls, data: dict) -> Group:
        """
        Exceptions:
            - KeyError: some filed is missing
            - TypeError: UUID is None
            - ValueError: invalid UUID
        """
        return cls(
            id=UUID(data[FieldNames.GROUP_ID]),
            admin_id=UUID(data[FieldNames.GROUP_ADMIN_ID]),
            name=data[FieldNames.GROUP_NAME]
        )

    def to_dict(self) -> dict:
        return {
            FieldNames.GROUP_ID: self.id,
            FieldNames.GROUP_NAME: self.name,
            FieldNames.GROUP_MEMBERS: self.members,
            FieldNames.GROUP_IS_READY: self.is_ready,
        }


@dataclass
class Team:
    """
    A dataclass representing a team
    """
    id: int
    group_id: UUID
    members: frozenset[UUID] = field(compare=False)

    # TODO check exceptions
    @classmethod
    def from_dict(cls, data: dict) -> Team:
        """
        Exceptions:
            - KeyError: some filed is missing
            - TypeError: UUID is None of id is an invalid int
            - ValueError: invalid UUID
        """
        return cls(
            id=int(data[FieldNames.TEAM_ID]),
            group_id=UUID(data[FieldNames.TEAM_GROUP_ID]),
            members=frozenset(data[FieldNames.TEAM_MEMBERS])
        )

    def __json__(self):
        return {
            FieldNames.TEAM_ID: self.id,
            FieldNames.TEAM_MEMBERS: list(self.members),
        }


@dataclass(frozen=True)
class Question:
    """
    A dataclass representing a question
    """
    text: str
    correct_answer: str = field(compare=False, hash=False, default=None)
    wrong_answers: list[str] = field(compare=False, hash=False, default=None)

    def __json__(self):
        return {
            FieldNames.QUESTION_TEXT: self.text,
            FieldNames.QUESTION_CORRECT_ANSWER: self.correct_answer,
            FieldNames.QUESTION_WRONG_ANSWERS: self.wrong_answers
        }


class GameType(StrEnum):
    """
    Enum for different game types
    """
    COLLECTING_STAMPS = 'collectingStamps'


@dataclass
class BaseGameState:
    """
    Base class for all game states
    """
    game_type: GameType

    def __json__(self):
        return {
            FieldNames.GAMESTATE_GAME_TYPE: self.game_type.name,
        }


@dataclass
class CollectingStampsState(BaseGameState):
    """
    State for Collecting Stamps game
    """
    questions: Dict[Question: bool]
    game_type: GameType = field(init=False, default=GameType.COLLECTING_STAMPS)
    current_progress: int = field(init=False, default=0)

    # def __post_init__(self):
    #     self.game_type = GameType.COLLECTING_STAMPS

    def update_progress(self, question_text: str, answered_correctly: bool) -> int:
        """
        Update progress and return the number of completed questions
        """

        if not self.questions.get(tmp_question := Question(question_text)):
            self.questions[tmp_question] = answered_correctly
            self.current_progress += 1

        return self.current_progress

    def __json__(self):
        base_json = super().__json__()
        return {
            **base_json,
            FieldNames.COLLECTING_STAMPS_QUESTIONS: self.questions,
            FieldNames.COLLECTING_STAMPS_PROGRESS: self.current_progress,
        }



@dataclass
class Message:
    """
    A dataclass representing a message
    """
    type: MessageType
    data: Any
    request_id: UUID = field(default_factory=uuid4)

    @classmethod
    def from_dict(cls, data: dict) -> Message:
        # return cls(**data)
        return cls(
            type=data[FieldNames.MESSAGE_TYPE],
            data=data[FieldNames.MESSAGE_DATA],
            request_id=UUID(data[FieldNames.MESSAGE_REQUEST_ID])
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
    """
    This class encapsulates database operations
    """
    def __init__(self):
        self.__users: Dict[UUID: User] = dict()
        self.__groups: Dict[UUID: Group] = dict()
        self.__teams: Dict[(UUID, int): Team] = dict() # TODO proper id
        self.__questions: list[Question] = self.__init_questions()
        self.__game_states: Dict[UUID, Dict[GameType: BaseGameState]] = dict()  # user_id -> game state

    @staticmethod
    def __init_questions() -> list[Question]:
        # Add your predefined questions here
        return [
            Question(
                text='What is 2+2?',
                correct_answer='4',
                wrong_answers=['3', '4', '5', '6']
            ),
            Question(
                text='What is the capital of France?',
                correct_answer='Paris',
                wrong_answers=['London', 'Berlin', 'Madrid']
            ),
            Question(
                text='Which programming language was created by Guido van Rossum?',
                correct_answer='Python',
                wrong_answers=['Java', 'C++', 'Ruby']
            ),
            Question(
                text='What is the chemical symbol for gold?',
                correct_answer='Au',
                wrong_answers=['Ag', 'Fe', 'Cu']
            ),
            Question(
                text='In which year did World War II end?',
                correct_answer='1945',
                wrong_answers=['1944', '1946', '1943']
            ),
            Question(
                text='What is the largest planet in our solar system?',
                correct_answer='Jupiter',
                wrong_answers=['Saturn', 'Mars', 'Neptune']
            ),
            Question(
                text='Who painted the Mona Lisa?',
                correct_answer='Leonardo da Vinci',
                wrong_answers=['Michelangelo', 'Raphael', 'Vincent van Gogh']
            ),
            Question(
                text='What is the square root of 144?',
                correct_answer='12',
                wrong_answers=['10', '14', '16']
            ),
            Question(
                text='Which element has the atomic number 1?',
                correct_answer='Hydrogen',
                wrong_answers=['Helium', 'Oxygen', 'Carbon']
            ),
            Question(
                text='What is the main component of the Sun?',
                correct_answer='Hydrogen',
                wrong_answers=['Helium', 'Nitrogen', 'Oxygen']
            ),
            Question(
                text='Which continent is the largest by land area?',
                correct_answer='Asia',
                wrong_answers=['Africa', 'North America', 'Europe']
            )
            # Add more questions...
        ]

    def add_or_update_user(self, user: User):
        logger.debug(f'DB: add_or_update_user with id {user.id}')
        self.__users[user.id] = user

    def get_user(self, user_id: UUID) -> User | None:
        logger.debug(f'DB: get_user with id {user_id}')
        if not (user := self.__users.get(user_id)):
            logger.debug(f'DB: get_user: user with id {user_id} is not found')
        return copy.deepcopy(user)

    def add_or_update_group(self, group: Group):
        logger.debug(f'DB: add_or_update_group with id {group.id}')
        self.__groups[group.id] = group

    def get_group(self, group_id: UUID) -> Group | None:
        logger.debug(f'DB: get_group with id {group_id}')
        if not (group := self.__groups.get(group_id)):
            logger.debug(f'DB: get_group: group with id {group_id} is not found')
        return copy.deepcopy(group)

    # TODO also delete teams of this group
    def delete_group(self, group_id: UUID):
        logger.debug(f'DB: delete_group {group_id}')
        if group_id not in self.__groups:
            logger.error(f'DB: delete_group: group with id {group_id} is not found')
        del self.__groups[group_id]

    def add_or_update_team(self, team: Team):
        logger.debug(f'DB: add_or_update_team with id ({team.group_id}, {team.id})')
        self.__teams[(team.group_id, team.id)] = team

    def get_team(self, group_id: UUID, team_id: int) -> Team | None:
        logger.debug(f'DB: get_team with id ({group_id}, {team_id})')
        if not (team := self.__teams.get( (group_id, team_id) )):
            logger.debug(f'DB: get_team: team with id {team_id} in group {group_id} is not found')
        return copy.deepcopy(team)

    def get_group_teams(self, group_id: UUID) -> list[Team]:
        """
        Exceptions:
            ValueError: group with id <group_id> is not found
        """
        logger.debug(f'DB: get_group_teams with id {group_id}')
        if group_id not in self.__groups:
            logger.error(f'DB: get_team: group {group_id} is not found')
            raise ValueError(f'Group {group_id} is not found')
        teams = list()
        for team in self.__teams.values():
            if team.group_id == group_id:
                teams.append(team)
        return copy.deepcopy(teams)

    def delete_team(self, group_id: UUID, team_id: int):
        logger.debug(f'DB: delete_team ({group_id}, {team_id})')
        if (group_id, team_id) not in self.__teams:
            logger.error(f'DB: delete_team: team with id ({group_id}, {team_id}) is not found')
            return
        del self.__teams[(group_id, team_id)]

    def get_team_members(self, group_id: UUID, team_id: int) -> list[User] | None:
        logger.debug(f'DB: get_team_members with id ({group_id}, {team_id})')
        if not (team := self.__teams.get((group_id, team_id))):
            logger.error(f'DB: get_team_members: team with id ({group_id}, {team_id}) is not found')
            return None
        members = list(filter(lambda user: user.id in team.members, self.__users.values()))

        if len(members) != len(team.members):
            logger.error(f'DB: get_team_members: team with id ({group_id}, {team_id}) has non-existent members')
            return None

        return copy.deepcopy(members)

    def get_random_questions(self, count: int) -> list[Question]:
        logger.debug(f'DB: get_random_questions with count {count}')
        return copy.deepcopy(random.sample(self.__questions, count))

    def add_or_update_game_states(self, user_id, game_states: Dict[GameType: BaseGameState]):
        logger.debug(f'DB: add_or_update_game_states with {user_id}')
        self.__game_states[user_id] = game_states

    def get_game_states(self, user_id) -> Dict[GameType: BaseGameState] | None:
        logger.debug(f'DB: get_game_states with {user_id}')
        return copy.deepcopy(self.__game_states.get(user_id))


class WebSocketManager:
    """
    This class encapsulates websocket operations
    """
    def __init__(self, db: DB):
        self.__connections: Dict[UUID, WebSocket] = dict()
        self.db = db

    async def connect(self, ws: WebSocket) -> UUID:
        """
        Accept a connection and return its user's id
        Args:
            ws: websocket object

        Returns:
            user_id: UUID
        """
        await ws.accept()
        user_id = uuid4()
        self.__connections[user_id] = ws
        return user_id

    async def disconnect(self, user_id: UUID):
        """
        Handle disconnection and notify all the other clients interested
        Args:
            user_id: UUID of the user to disconnect
        """
        if user_id in self.__connections:
            del self.__connections[user_id]
            user = self.db.get_user(user_id)
            if user and user.group_id:
                if group := self.db.get_group(user.group_id):
                    await self.broadcast(
                        group.members,
                        Message(
                            type=MessageType.DISCONNECT,
                            data={
                                FieldNames.USER_ID: user_id,
                            },
                            request_id=uuid4()
                        )
                    )
                else:
                    logger.error(f'WebSocketManager: disconnect: group {user.group_id} is not found')

    async def reconnect(self, user_id: UUID, message: Message):
        logger.debug(f'WebSocketManager reconnect: user {user_id}')
        if not (target_user_id := message.data.get(FieldNames.USER_ID)):
            logger.warning(f'WebSocketManager reconnect: {FieldNames.USER_ID} is not found')
            await self.send_personal_message(user_id, Message(
                type=MessageType.ERROR,
                data=f'{FieldNames.USER_ID} is missing',
                request_id=message.request_id
            ))
            return user_id

        try:
            target_user_id = UUID(target_user_id)
        except ValueError | TypeError:
            logger.debug(f'WebSocketManager reconnect: {FieldNames.USER_ID} {target_user_id} is invalid')
            await self.send_personal_message(user_id, Message(
                type=MessageType.ERROR,
                data=f'{FieldNames.USER_ID} is invalid',
                request_id=message.request_id
            ))
            return user_id

        if target_user_id not in self.__connections:
            logger.debug(f'WebSocketManager reconnect: {FieldNames.USER_ID} {user_id} is invalid')
            await self.send_personal_message(user_id, Message(
                type=MessageType.ERROR,
                data=f'{FieldNames.USER_ID} is invalid',
                request_id=message.request_id
            ))
            return user_id

        logger.debug(f'WebSocketManager reconnect: setting user_id to {target_user_id}')
        self.__connections[target_user_id] = self.__connections[user_id]
        del self.__connections[user_id]
        logger.debug(f'WebSocketManager reconnect: successfully set user_id to {target_user_id}')
        return target_user_id

    async def send_personal_message(self, user_id: UUID, message: Message):
        """
        Send a personal message to the user identified by user_id
        Args:
            user_id: addressee's id
            message: message to send
        """
        if not message:
            logger.error(f'send_personal_message: message is None')
            return
        if user_ws := self.__connections.get(user_id):
            await user_ws.send_json(message.to_dict())
            logger.debug(f'WebSocketManager: {user_id} will get: {message.to_dict()}')

    async def broadcast(self, addressees: set[UUID], message: Message):
        logger.debug('broadcast started')
        for addressee_id in addressees:
            await self.send_personal_message(addressee_id, message)
        logger.debug('broadcast ended')


class MessageHandler:
    """
    This class holds all the logic to handle received messages
    """
    def __init__(self, ws_manager: WebSocketManager, db: DB):
        self.ws_manager = ws_manager
        self.db = db

    async def handle_message(self, user_id: UUID, message: Message) -> Message:
        """
        This method decides which handler to use
        Args:
            user_id: message sender's id
            message: message to handle

        Returns:
            A response message
        """
        try:
            message_type = MessageType(message.type)

            handlers = {
                MessageType.GET_USER_INFO: self.handle_get_user_info,
                MessageType.SET_USER_INFO: self.handle_set_user_info,
                MessageType.SET_USER_READY: self.handle_set_user_ready,
                MessageType.GET_GROUP_INFO: self.handle_get_group_info,
                MessageType.SET_GROUP_INFO: self.handle_set_group_info,
                MessageType.JOIN_GROUP: self.handle_join_group,
                MessageType.LEAVE_GROUP: self.handle_leave_group,
                MessageType.DELETE_GROUP: self.handle_delete_group,
                MessageType.SET_GROUP_READY: self.handle_set_group_ready,
                MessageType.GET_TEAMS: self.handle_get_teams,
                MessageType.SET_TEAMS: self.handle_set_teams,
                MessageType.COLLECTING_STAMPS_START: self.handle_collecting_stamps_start,
                MessageType.COLLECTING_STAMPS_PROGRESS_UPDATE: self.handle_collecting_stamps_progress_update,
            }

            if handler := handlers.get(message_type):
                logger.info(f'handle_message: {handler.__name__} will be used')

                return await handler(user_id, message)

            logger.error(f'handle_message: no suitable handler for {message_type} is found')

            return Message(
                type=MessageType.ERROR,
                data='unknown message type',
                request_id=message.request_id
            )

        # TODO specify Exception
        except Exception as e:
            logger.warning(f'handle_message: unknown error: {e}')
            return Message(
                type=MessageType.ERROR,
                data='internal error',
                request_id=message.request_id
            )

    async def handle_get_user_info(self, user_id: UUID, message: Message) -> Message:
        """
        This method handles user info request
        Args:
            user_id: message sender's id
            message: message to handle

        Returns:
            A response message with user info or an error message
        """
        try:
            if not message.data:
                logger.warning(f'handle_get_user_info: message has no {FieldNames.USER_ID}')
                return Message(
                    type=MessageType.ERROR,
                    data=f'{FieldNames.USER_ID} is missing',
                    request_id=message.request_id
                )
            requested_user_id = UUID(message.data)
            if user := self.db.get_user(requested_user_id):
                return Message(
                    type=MessageType.SUCCESS,
                    data=user.to_dict(),
                    request_id=message.request_id
                )
            logger.warning(f'handle_get_user_info: user with id {user_id} is not found')
            return Message(
                type=MessageType.ERROR,
                data='user not found',
                request_id=message.request_id
            )
        # TODO specify Exception
        except ValueError:
            logger.warning(f'handle_get_user_info: {message.data.get(FieldNames.USER_ID)} is an invalid UUID')
            return Message(
                type=MessageType.ERROR,
                data=f'{FieldNames.USER_ID} is an invalid UUID',
                request_id=message.request_id
            )
        except Exception as e:
            logger.warning(f'handle_get_user_info: unknown error: {e}')
            return Message(
                type=MessageType.ERROR,
                data=str(e),
                request_id=message.request_id
            )

    async def handle_set_user_info(self, user_id: UUID, message: Message) -> Message:
        """
        This method handles user info request
        Args:
            user_id: message sender's id
            message: message to handle

        Returns:
            A response message with user info or an error message
        """
        try:
            message.data = message.data | {
                FieldNames.USER_ID: user_id.hex,
                FieldNames.GROUP_ID: None,
            }

            if not (old_user := self.db.get_user(user_id)): # Creating a user
                logger.debug(f'handle_set_user_info: creating user with id {user_id}')
            else: # Updating the user
                logger.debug(f'handle_set_user_info: updating user with id {user_id}')
                if group_id := old_user.group_id:
                    message.data = message.data | {FieldNames.USER_GROUP_ID: group_id.hex}

            new_user = User.from_dict(message.data)
            self.db.add_or_update_user(user=new_user)

            logger.debug(f'handle_set_user_info: success')
            if old_user and (group := self.db.get_group(old_user.group_id)):
                await self.ws_manager.broadcast(
                    group.members - {user_id},
                    Message(
                        type=MessageType.SET_USER_INFO,
                        data=new_user.to_dict(),
                        request_id=uuid4()
                    )
                )
                logger.debug(f'handle_set_user_info: all the members of the group {group.id} are notified')

            return Message(
                type=MessageType.SUCCESS,
                data={
                    FieldNames.USER_ID: user_id,
                },
                request_id=message.request_id
            )
        # TODO specify Exception
        except Exception as e:
            logger.warning(f'handle_set_user_info: unknown error: {e}')
            return Message(
                type=MessageType.ERROR,
                data='failed to create or update user',
                request_id=message.request_id
            )

    async def handle_get_group_info(self, user_id: UUID, message: Message) -> Message:
        """
        This method handles group info request.
        Args:
            user_id: message sender's id. NOT USED.
            message: message to handle

        Returns:
            A response message with group info or an error message
        """
        try:
            if not message.data:
                logger.warning(f'handle_get_group_info: message has no {FieldNames.GROUP_ID}')
                return Message(
                    type=MessageType.ERROR,
                    data=f'{FieldNames.GROUP_ID} is missing',
                    request_id=message.request_id
                )
            group_id = UUID(message.data)
            if not (group := self.db.get_group(group_id)):
                logger.warning(f'handle_get_group_info: group with id {group_id} is not found')
                return Message(
                    type=MessageType.ERROR,
                    data=f'group with {FieldNames.GROUP_ID} = {group_id} is not found',
                    request_id=message.request_id
                )
            return Message(
                type=MessageType.SUCCESS,
                data=group.to_dict(),
                request_id=message.request_id
            )
        except ValueError:
            logger.warning(f'handle_get_group_info: {message.data.get(FieldNames.GROUP_ID)} is an invalid UUID')
            return Message(
                type=MessageType.ERROR,
                data=f'{FieldNames.USER_ID} is an invalid UUID',
                request_id=message.request_id
            )
        # TODO specify Exception
        except Exception as e:
            logger.warning(f'handle_get_group_info: unknown error: {e}')
            return Message(
                type=MessageType.ERROR,
                data=f'handle_get_group_info: unknown error: {e}',
                request_id=message.request_id
            )

    async def handle_set_group_info(self, user_id: UUID, message: Message) -> Message:
        """
        This method handles group update/creation request.
        Args:
            user_id: message sender's id
            message: message to handle. Must have group info

        Returns:
            One of:
            - A response message with no data and 'success' status in case the group is updated
            - A response message with group info and 'success' status in case the group is created
            - An error message
        """
        try:
            if not (user := self.db.get_user(user_id)):
                logger.error(f'handle_set_group_info: user with id {user_id} is not found')
                return Message(
                    type=MessageType.ERROR,
                    data='handle_set_group_info: unknown error',
                    request_id=message.request_id
                )
            if user.group_id: # user is a group member
                if not (group := self.db.get_group(user.group_id)): # a member of non-existent group
                    logger.error(f'handle_set_group_info: group with id {user.group_id} is not found')
                    return Message(
                        type=MessageType.ERROR,
                        data='handle_set_group_info: unknown error',
                        request_id=message.request_id
                    )

                if group.admin_id != user_id: # not an admin
                    logger.error(f'handle_set_group_info: change is not allowed as user is not an admin')
                    return Message(
                        type=MessageType.ERROR,
                        data='user is already a group member, leave a group to create one',
                        request_id=message.request_id
                    )

                group.update_from_dict(message.data)
                self.db.add_or_update_group(group)
                logger.debug(f'handle_set_group_info: group info updated by the admin')

                await self.ws_manager.broadcast(
                    group.members - {user_id},
                    Message(
                        type=MessageType.SET_GROUP_INFO,
                        data=group.to_dict(),
                        request_id=uuid4()
                    )
                )
                logger.debug(f'handle_set_group_info: all the members of the group {group.id} are notified')

                return Message(
                    type=MessageType.SUCCESS,
                    data=None,
                    request_id=message.request_id
                )

            # Creating group

            group = Group.from_dict(message.data | {FieldNames.GROUP_ADMIN_ID: user_id.hex})

            group.members.add(user_id)
            self.db.add_or_update_group(group)
            user.group_id = group.id
            self.db.add_or_update_user(user)

            logger.debug(f'handle_set_group_info: created a group with id {group.id}')
            return Message(
                type=MessageType.SUCCESS,
                data=None,
                request_id=message.request_id
            )

        except KeyError:
            logger.debug(f'handle_set_group_info: some field is missing')
            return Message(
                type=MessageType.ERROR,
                data='some field is missing',
                request_id=message.request_id
            )
        except TypeError:
            logger.debug(f'handle_set_group_info: id is None')
            return Message(
                type=MessageType.ERROR,
                data='id is null',
                request_id=message.request_id
            )
        except ValueError:
            logger.debug(f'handle_set_group_info: id is invalid')
            return Message(
                type=MessageType.ERROR,
                data='invalid id',
                request_id=message.request_id
            )
        except Exception as e:
            logger.error(f'handle_set_group_info: unknown error: {str(e)}')
            return Message(
                type=MessageType.ERROR,
                data='unknown error',
                request_id=message.request_id
            )

    async def handle_join_group(self, user_id: UUID, message: Message) -> Message:
        """
        This method handles a join group request.
        Args:
            user_id: message sender's id. This user joins the group
            message: message to handle. Must have group id

        Returns:
            A response message with 'success' status and no data or an error message
        """
        if not message.data:
            logger.debug(f'handle_join_group: {FieldNames.GROUP_ID} is missing')
            return Message(
                type=MessageType.ERROR,
                data=f'{FieldNames.GROUP_ID} is missing',
                request_id=message.request_id
            )
        try:
            target_group_id = UUID(message.data)
            if not (target_group := self.db.get_group(target_group_id)):
                logger.error(f'handle_join_group: no group with id {target_group_id} is found')
                return Message(
                    type=MessageType.ERROR,
                    data=f'no group with {FieldNames.GROUP_ID} {target_group_id} is found',
                    request_id=message.request_id
                )

            if not (user := self.db.get_user(user_id)):
                logger.error(f'handle_join_group: no user with id {user_id} is found')
                return Message(
                    type=MessageType.ERROR,
                    data=f'internal error',
                    request_id=message.request_id
                )

            if user.group_id:
                logger.debug(f'handle_join_group: user with id {user_id} is already a group member')
                return Message(
                    type=MessageType.ERROR,
                    data=f'already a group member',
                    request_id=message.request_id
                )

            if target_group.is_ready:
                logger.debug(f'handle_join_group: target group {target_group.id} is ready')
                return Message(
                    type=MessageType.ERROR,
                    data='target group is ready',
                    request_id=message.request_id
                )

            target_group.members.add(user_id)
            self.db.add_or_update_group(target_group)

            user.group_id = target_group_id
            self.db.add_or_update_user(user)

            logger.debug(f'handle_join_group: user with id {user_id} joined the group {target_group_id}')

            await self.ws_manager.broadcast(
                target_group.members - {user_id},
                Message(
                    type=MessageType.JOIN_GROUP,
                    data=user.to_dict(),
                    request_id=uuid4()
                )
            )
            logger.debug(f'handle_join_group: all the members of the group {target_group_id} are notified')

            return Message(
                type=MessageType.SUCCESS,
                data=None,
                request_id=message.request_id
            )
        except ValueError:
            logger.error(f'handle_join_group: invalid UUID: {message.data}')
            return Message(
                type=MessageType.ERROR,
                data=f'invalid UUID: {message.data}',
                request_id=message.request_id
            )
        except Exception as e:
            logger.error(f'handle_join_group: unknown error: {str(e)}')
            return Message(
                type=MessageType.ERROR,
                data='internal error',
                request_id=message.request_id
            )

    async def handle_leave_group(self, user_id: UUID, message: Message) -> Message:
        """
        This method handles a leave group request.
        Args:
            user_id: message sender's id. This user leaves the group
            message: message to handle. Must have group id

        Returns:
            A response message with 'success' status and no data or an error message
        """
        try:
            if not (user := self.db.get_user(user_id)):
                logger.error(f'handle_leave_group: user with id {user_id} is not found')
                return Message(
                    type=MessageType.ERROR,
                    data='internal error',
                    request_id=message.request_id
                )

            if not (group_id := user.group_id):
                logger.debug(f'handle_leave_group: user with id {user.id} is not a group member')
                return Message(
                    type=MessageType.ERROR,
                    data='user is not a group member',
                    request_id=message.request_id
                )

            if message.data:
                try:
                    id_to_remove = UUID(message.data)
                except ValueError:
                    logger.debug(f'handle_leave_group: {message.data} is not a valid UUID')
                    return Message(
                        type=MessageType.ERROR,
                        data=f'{message.data} is not a valid UUID',
                        request_id=message.request_id
                    )
                logger.debug(f'handle_leave_group: {FieldNames.USER_ID} to remove is set to {user_id}')
                if not (user_to_remove := self.db.get_user(id_to_remove)):
                    logger.debug(f'handle_leave_group: user with id {id_to_remove} is not found')
                    return Message(
                        type=MessageType.ERROR,
                        data='user is not found',
                        request_id=message.request_id
                    )
            else:
                logger.debug(f'handle_leave_group: {FieldNames.USER_ID} to remove is not provided and set to {user_id}')
                id_to_remove = user_id
                user_to_remove = user

            if user_to_remove.group_id != group_id:
                logger.debug(f'handle_leave_group: user with id {user_to_remove.id} is not a member of the group {group_id}')
                return Message(
                    type=MessageType.ERROR,
                    data='user is not a member of your group',
                    request_id=message.request_id
                )
            if not (group := self.db.get_group(group_id)):
                logger.error(f'handle_leave_group: no group with id {group_id} is found')
                return Message(
                    type=MessageType.ERROR,
                    data=f'no group with {FieldNames.GROUP_ID} {group_id} is found',
                    request_id=message.request_id
                )
            if id_to_remove != user_id and group.admin_id != user_id:
                logger.debug(f'handle_leave_group: user {user_id} tried to kick out {id_to_remove}. Operation denied due to lack of permissions')
                return Message(
                    type=MessageType.ERROR,
                    data='operation not permitted',
                    request_id=message.request_id
                )
            if id_to_remove == group.admin_id:
                logger.debug(f'handle_leave_group: user {id_to_remove} is an admin of the group {group_id} and therefore cannot leave')
                return Message(
                    type=MessageType.ERROR,
                    data=f'admin cannot leave the group',
                    request_id=message.request_id
                )
            try:
                group.members.remove(id_to_remove)
                self.db.add_or_update_group(group)
            except KeyError:
                logger.debug(f'handle_leave_group: user {id_to_remove} is not a member of group {group_id}')
                return Message(
                    type=MessageType.ERROR,
                    data=f'{id_to_remove} is not a member of group {group_id}',
                    request_id=message.request_id
                )

            user_to_remove.group_id = None
            self.db.add_or_update_user(user_to_remove)

            logger.debug(f'handle_leave_group: user {id_to_remove} left the group {group_id}')
            await self.ws_manager.broadcast(
                group.members - {id_to_remove if id_to_remove == user_id else user_id},
                Message(
                    type=MessageType.LEAVE_GROUP,
                    data=id_to_remove,
                    request_id=uuid4()
                )
            )
            logger.debug(f'handle_leave_group: all the members of the group {group_id} are notified')
            return Message(
                type=MessageType.SUCCESS,
                data=None,
                request_id=message.request_id
            )
        except Exception as e:
            logger.error(f'handle_leave_group: unknown error: {str(e)}')
            return Message(
                type=MessageType.ERROR,
                data='internal error',
                request_id=message.request_id
            )

    async def handle_delete_group(self, user_id: UUID, message: Message) -> Message:
        """
        This method handles a delete group request.
        Args:
            user_id: message sender's id
            message: message to handle. Must have group id

        Returns:
            A response message with 'success' status and no data or an error message
        """
        if not (user := self.db.get_user(user_id)):
            logger.error(f'handle_delete_group: user {user_id} is not found')
            return Message(
                type=MessageType.ERROR,
                data='internal error',
                request_id=message.request_id
            )

        if not (group := self.db.get_group(user.group_id)):
            logger.debug(f'handle_delete_group: group {user.group_id} is not found')
            return Message(
                type=MessageType.ERROR,
                data='group is not found',
                request_id=message.request_id
            )

        if group.admin_id != user_id:
            logger.debug(f'handle_delete_group: only admin can delete a group')
            return Message(
                type=MessageType.ERROR,
                data='only admin can delete a group',
                request_id=message.request_id
            )

        group.members.remove(user_id) # remove admin first
        for member_id in group.members: # notify & update members
            await self.ws_manager.send_personal_message(
                member_id,
                Message(
                    type=MessageType.DELETE_GROUP,
                    data=None,
                    request_id=uuid4()
                )
            )
            if member := self.db.get_user(member_id):
                member.group_id = None
                self.db.add_or_update_user(member)
                logger.debug(f'handle_delete_group: delete a member with id {member_id}')
            else:
                logger.error(f'handle_delete_group: member {member_id} of a group {group.id} is not found')

        user.group_id = None
        self.db.add_or_update_user(user)
        self.db.delete_group(group.id)

        logger.debug(f'handle_delete_group: the group with id {group.id} has been deleted successfully. All the members are notified')

        return Message(
            type=MessageType.SUCCESS,
            data=None,
            request_id=message.request_id
        )

    async def handle_get_teams(self, user_id: UUID, message: Message) -> Message:
        if not (user := self.db.get_user(user_id)):
            logger.error(f'handle_get_teams: user {user_id} is not found')
            return Message(
                type=MessageType.ERROR,
                data='internal error',
                request_id=message.request_id
            )

        if not user.group_id:
            logger.debug(f'handle_get_teams: user {user_id} is not a group member')
            return Message(
                type=MessageType.ERROR,
                data=f'user {user_id} is not a group member',
                request_id=message.request_id
            )

        try:
            teams = self.db.get_group_teams(user.group_id)
        except ValueError:
            logger.error(f'handle_get_teams: group {user.group_id} is not found')
            return Message(
                type=MessageType.ERROR,
                data='internal error',
                request_id=message.request_id
            )

        return Message(
            type=MessageType.SUCCESS,
            data=teams,
            request_id=message.request_id
        )

    async def handle_set_teams(self, user_id: UUID, message: Message) -> Message:
        if not (user := self.db.get_user(user_id)):
            logger.error(f'handle_set_teams: user {user_id} is not found')
            return Message(
                type=MessageType.ERROR,
                data='internal error',
                request_id=message.request_id
            )

        if not user.group_id:
            logger.debug(f'handle_set_teams: user {user_id} is not a group member')
            return Message(
                type=MessageType.ERROR,
                data=f'user {user_id} is not a group member',
                request_id=message.request_id
            )

        if not (group := self.db.get_group(user.group_id)):
            logger.error(f'handle_set_teams: group with id {user.group_id} is not found')
            return Message(
                type=MessageType.ERROR,
                data=f'group with {FieldNames.GROUP_ID} = {user.group_id} is not found',
                request_id=message.request_id
            )

        if group.is_ready:
            logger.debug(f'handle_set_teams: group {group.id} is ready')
            return Message(
                type=MessageType.ERROR,
                data='group is ready',
                request_id=message.request_id
            )

        if group.admin_id != user_id:
            logger.debug(f'handle_set_teams: only admin can set teams')
            return Message(
                type=MessageType.ERROR,
                data='only admin can set teams',
                request_id=message.request_id
            )

        unassigned_members: set[UUID] = group.members
        assigned_members: set[UUID] = set()

        teams: list[Team] = list()
        for raw_team in message.data:
            try:
                # TODO check the case when message.data is not a list
                if not (team_id := raw_team.get(FieldNames.TEAM_ID)):
                    logger.warning(f'handle_set_teams: team has no {FieldNames.TEAM_ID}')
                    return Message(
                        type=MessageType.ERROR,
                        data=f'{FieldNames.TEAM_ID} is missing',
                        request_id=message.request_id
                    )
                team_id = int(team_id)
                # TODO check the case when members is not a list
                if not (members := raw_team.get(FieldNames.TEAM_MEMBERS)):
                    logger.warning(f'handle_set_teams: {FieldNames.TEAM_MEMBERS} list is missing')
                    return Message(
                        type=MessageType.ERROR,
                        data=f'{FieldNames.TEAM_MEMBERS} list is missing or empty',
                        request_id=message.request_id
                    )
            except ValueError:
                logger.warning(f'handle_set_teams: team id {FieldNames.TEAM_ID} is not an integer')
                return Message(
                    type=MessageType.ERROR,
                    data=f'{FieldNames.TEAM_ID} is invalid',
                    request_id=message.request_id
                )

            try:
                members = list(map(UUID, members))
            except ValueError:
                logger.warning("handle_set_teams: member's id is invalid")
                return Message(
                    type=MessageType.ERROR,
                    data="member's id is invalid",
                    request_id=message.request_id
                )

            # TODO exceptions
            teams.append(Team(team_id, user.group_id, frozenset(members)))

            for member_id in members:
                try:
                    unassigned_members.remove(member_id)
                    assigned_members.add(member_id)
                except KeyError:
                    logger.warning(f'handle_set_teams: member {member_id} is already in another team or does not exist')
                    return Message(
                        type=MessageType.ERROR,
                        data=f'member {member_id} is already in another team or does not exist',
                        request_id=message.request_id
                    )

        if len(unassigned_members) > 0:
            logger.warning(f'handle_set_teams: some group members do not have a team')
            return Message(
                type=MessageType.ERROR,
                data=f'some group members do not have a team',
                request_id=message.request_id
            )

        for team in teams:
            self.db.add_or_update_team(team)

        logger.debug(f'handle_set_teams: teams updated by the admin')

        await self.ws_manager.broadcast(
            assigned_members - {user_id},
            Message(
                type=MessageType.SET_TEAMS,
                data=teams,
                request_id=uuid4()
            )
        )
        logger.debug(f'handle_set_teams: all the members of the group {group.id} are notified')

        return Message(
            type=MessageType.SUCCESS,
            data=None,
            request_id=message.request_id
        )

    async def handle_set_user_ready(self, user_id: UUID, message: Message) -> Message:
        if not isinstance(is_ready := message.data, bool):
            logger.warning(f'handle_set_user_ready: data is invalid')
            return Message(
                type=MessageType.ERROR,
                data='data is invalid',
                request_id=message.request_id
            )

        if not (user := self.db.get_user(user_id)):
            logger.error(f'handle_set_user_ready: user {user_id} is not found')
            return Message(
                type=MessageType.ERROR,
                data='internal error',
                request_id=message.request_id
            )

        # if user.is_ready == is_ready:
        #     logger.debug(f'handle_set_user_ready: old and new value of {FieldNames.USER_IS_READY} for the user {user_id} are the same')
        #     return Message(
        #         type=MessageType.SUCCESS,
        #         data=f'old and new value of {FieldNames.USER_IS_READY} are the same',
        #         request_id=message.request_id
        #     )

        if not user.group_id:
            logger.debug(f'handle_set_user_ready: user {user_id} is not a group member')
            return Message(
                type=MessageType.ERROR,
                data=f'user {user_id} is not a group member',
                request_id=message.request_id
            )

        if not (teams := self.db.get_group_teams(user.group_id)):
            logger.debug(f'handle_set_user_ready: group {user.group_id} has no teams')
            return Message(
                type=MessageType.ERROR,
                data='group has no teams',
                request_id=message.request_id
            )

        teams = filter(lambda team: user_id in team.members, teams)
        if not (team := next(teams, None)):
            logger.debug(f'handle_set_user_ready: user {user_id} in group {user.group_id} is not a team member')
            return Message(
                type=MessageType.ERROR,
                data='internal error',
                request_id=message.request_id
            )

        if next(teams, False):
            logger.error(f'handle_set_user_ready: user {user_id} in group {user.group_id} is a member of multiple teams')
            return Message(
                type=MessageType.ERROR,
                data='internal error',
                request_id=message.request_id
            )

        if user.is_ready == is_ready:
            logger.debug(f'handle_set_user_ready: old and new value of {FieldNames.USER_IS_READY} for the user {user_id} are the same')
        else:
            user.is_ready = is_ready
            self.db.add_or_update_user(user)

        logger.debug(f'handle_set_user_ready: user {user_id} is {'' if is_ready else 'not '}ready')
        members: list[User] = self.db.get_team_members(user.group_id, team.id)

        if team_is_ready := all(member.is_ready for member in members):
            logger.debug(f'handle_set_user_ready: all the members are ready')
        await self.ws_manager.broadcast(
            team.members - {user_id},
            Message(
                type=MessageType.SET_USER_READY,
                data={
                    FieldNames.USER_ID: user_id,
                    FieldNames.USER_IS_READY: is_ready,
                    FieldNames.TEAM_IS_READY: team_is_ready,
                },
                request_id=uuid4()
            )
        )
        logger.debug(f'handle_set_user_ready: all the members of the team ({team.group_id}, {team.id}) are notified')

        return Message(
            type=MessageType.SUCCESS,
            data={
                FieldNames.USER_ID: user_id,
                FieldNames.TEAM_IS_READY: team_is_ready,
            },
            request_id=message.request_id
        )

    async def handle_set_group_ready(self, user_id: UUID, message: Message) -> Message:
        if not isinstance(is_ready := message.data, bool):
            logger.warning(f'handle_set_group_ready: data is invalid')
            return Message(
                type=MessageType.ERROR,
                data='data is invalid',
                request_id=message.request_id
            )
        if not (user := self.db.get_user(user_id)):
            logger.error(f'handle_set_group_ready: user with id {user_id} is not found')
            return Message(
                type=MessageType.ERROR,
                data=f'internal error',
                request_id=message.request_id
            )
        if not (group_id := user.group_id):
            logger.debug(f'handle_set_group_ready: user is not a group member')
            return Message(
                type=MessageType.ERROR,
                data='not a group member',
                request_id=message.request_id
            )
        if not (group := self.db.get_group(group_id)):
            logger.error(f'handle_set_group_ready: group with id {group_id} is not found')
            return Message(
                type=MessageType.ERROR,
                data='internal error',
                request_id=message.request_id
            )
        if user_id != group.admin_id:
            logger.debug(f'handle_set_group_ready: user {user_id} is an admin')
            return Message(
                type=MessageType.ERROR,
                data='operation is not permitted',
                request_id=message.request_id
            )

        if len(self.db.get_group_teams(group.id)) == 0:
            logger.debug(f'handle_set_group_ready: group {group.id} has no teams')
            return Message(
                type=MessageType.ERROR,
                data='group has no teams',
                request_id=message.request_id
            )

        group.is_ready = is_ready
        self.db.add_or_update_group(group)

        return Message(
            type=MessageType.SUCCESS,
            data=group.to_dict(),
            request_id=message.request_id
        )

    async def handle_collecting_stamps_start(self, user_id, message: Message) -> Message:
        if not (user := self.db.get_user(user_id)):
            logger.error(f'handle_collecting_stamps_start: user {user_id} is not found')
            return Message(
                type=MessageType.ERROR,
                data='internal error',
                request_id=message.request_id
            )

        if not (group := self.db.get_group(user.group_id)):
            logger.debug(f'handle_collecting_stamps_start: group {user.group_id} is not found')
            return Message(
                type=MessageType.ERROR,
                data='not a group member',
                request_id=message.request_id
            )

        if not group.is_ready:
            logger.debug(f'handle_collecting_stamps_start: group {group.id} is not ready')
            return Message(
                type=MessageType.ERROR,
                data='group is not ready',
                request_id=message.request_id
            )

        if not (teams := self.db.get_group_teams(user.group_id)):
            logger.debug(f'handle_collecting_stamps_start: group {user.group_id} has no teams')
            return Message(
                type=MessageType.ERROR,
                data='group has no teams',
                request_id=message.request_id
            )

        teams = filter(lambda team: user_id in team.members, teams)
        if not (team := next(teams, None)):
            logger.debug(f'handle_collecting_stamps_start: user {user_id} in group {user.group_id} is not a team member')
            return Message(
                type=MessageType.ERROR,
                data='internal error',
                request_id=message.request_id
            )

        if next(teams, False):
            logger.error(f'handle_collecting_stamps_start: user {user_id} in group {user.group_id} is a member of multiple teams')
            return Message(
                type=MessageType.ERROR,
                data='internal error',
                request_id=message.request_id
            )

        members: list[User] = self.db.get_team_members(user.group_id, team.id)
        if not all(member.is_ready for member in members):
            logger.error(f'handle_collecting_stamps_start: not all the members are ready')
            return Message(
                type=MessageType.ERROR,
                data='not all the members are ready',
                request_id=message.request_id
            )

        for team_member in team.members - {user_id}:
            logger.debug(f'handle_collecting_stamps_start: member {team_member}')
            game_states: Dict[GameType: BaseGameState] = self.db.get_game_states(team_member) or dict()

            if GameType.COLLECTING_STAMPS in game_states.keys():
                logger.debug(f'handle_collecting_stamps_start: user {user_id} already has a {GameType.COLLECTING_STAMPS} game state')
                return Message(
                    type=MessageType.ERROR,
                    data='already played',
                    request_id=message.request_id
                )

            new_state = CollectingStampsState(self.db.get_random_questions(COLLECTING_STAMPS_QUESTIONS_PER_PLAYER))
            game_states[GameType.COLLECTING_STAMPS] = new_state
            self.db.add_or_update_game_states(team_member, game_states)
            logger.debug(f'handle_collecting_stamps_start: {GameType.COLLECTING_STAMPS} game started for the user {team_member}')

            await self.ws_manager.send_personal_message(
                team_member,
                Message(
                    type=MessageType.COLLECTING_STAMPS_START,
                    data=new_state.questions,
                    request_id=uuid4()
                )
            )
        logger.debug(f'handle_collecting_stamps_start: all the members of the team ({team.group_id}, {team.id}) are notified')

        game_states: Dict[GameType: BaseGameState] = self.db.get_game_states(user_id) or dict()

        if GameType.COLLECTING_STAMPS in game_states.keys():
            logger.debug(f'handle_collecting_stamps_start: user {user_id} already has a {GameType.COLLECTING_STAMPS} game state')
            return Message(
                type=MessageType.ERROR,
                data='already played',
                request_id=message.request_id
            )

        new_state = CollectingStampsState(self.db.get_random_questions(COLLECTING_STAMPS_QUESTIONS_PER_PLAYER))
        game_states[GameType.COLLECTING_STAMPS] = new_state
        self.db.add_or_update_game_states(user_id, game_states)
        logger.debug(f'handle_collecting_stamps_start: {GameType.COLLECTING_STAMPS} game started for the user {user_id}')

        return Message(
            type=MessageType.SUCCESS,
            data=new_state.questions,
            request_id=message.request_id
        )

    async def handle_collecting_stamps_progress_update(self, user_id, message: Message) -> Message:
        if not isinstance(answered_correctly := message.data.get('answered_correctly'), bool):
            logger.warning(f'handle_collecting_stamps_progress: data is invalid')
            return Message(
                type=MessageType.ERROR,
                data='data is invalid',
                request_id=message.request_id
            )

        if not (question_text := message.data.get(FieldNames.COLLECTING_STAMPS_QUESTION_TEXT)):
            logger.debug(f'handle_collecting_stamps_progress: {FieldNames.COLLECTING_STAMPS_QUESTION_TEXT} is missing')
            return Message(
                type=MessageType.ERROR,
                data=f'{FieldNames.COLLECTING_STAMPS_QUESTION_TEXT} is missing',
                request_id=message.request_id
            )

        if not (user := self.db.get_user(user_id)):
            logger.error(f'handle_collecting_stamps_progress: user {user_id} is not found')
            return Message(
                type=MessageType.ERROR,
                data='internal error',
                request_id=message.request_id
            )

        if not (game_states := self.db.get_game_states(user_id)):
            logger.debug(f'handle_collecting_stamps_progress: user {user_id} has not started any games yet')
            return Message(
                type=MessageType.ERROR,
                data='no started games',
                request_id=message.request_id
            )

        if not (stamps_state := game_states.get(GameType.COLLECTING_STAMPS)):
            logger.debug(f'handle_collecting_stamps_progress: user {user_id} has not started {GameType.COLLECTING_STAMPS} game')
            return Message(
                type=MessageType.ERROR,
                data=f'{GameType.COLLECTING_STAMPS} is not started',
                request_id=message.request_id
            )

        progress: int = stamps_state.update_progress(question_text, answered_correctly)

        if not (teams := self.db.get_group_teams(user.group_id)):
            logger.debug(f'handle_collecting_stamps_progress: group {user.group_id} has no teams')
            return Message(
                type=MessageType.ERROR,
                data='group has no teams',
                request_id=message.request_id
            )

        teams = filter(lambda team: user_id in team.members, teams)
        if not (team := next(teams, None)):
            logger.debug(f'handle_collecting_stamps_progress: user {user_id} in group {user.group_id} is not a team member')
            return Message(
                type=MessageType.ERROR,
                data='internal error',
                request_id=message.request_id
            )

        if next(teams, False):
            logger.error(f'handle_collecting_stamps_progress: user {user_id} in group {user.group_id} is a member of multiple teams')
            return Message(
                type=MessageType.ERROR,
                data='internal error',
                request_id=message.request_id
            )

        await self.ws_manager.broadcast(
            team.members - {user_id},
            Message(
                type=MessageType.COLLECTING_STAMPS_PROGRESS_UPDATE,
                data=progress,
                request_id=message.request_id
            )
        )

        return Message(
            type=MessageType.SUCCESS,
            data=progress,
            request_id=message.request_id
        )


app = FastAPI()
db = DB()
ws_manager = WebSocketManager(db)
message_handler = MessageHandler(ws_manager, db)
logger = logging.getLogger('uvicorn.error')
COLLECTING_STAMPS_QUESTIONS_PER_PLAYER = 5


@app.get('/')
async def get():
    return FileResponse('index.html')


def log_message(func, text):
    LOG_MAX_MESSAGE_LINES = 15
    textlines = text.splitlines()
    for line in textlines[:LOG_MAX_MESSAGE_LINES]:
        func(f'\t{line}')
    if len(textlines) > LOG_MAX_MESSAGE_LINES:
        func('\t...')
        func(f'\t{len(textlines) - LOG_MAX_MESSAGE_LINES} more lines are suppressed')


@app.websocket('/ws')
async def websocket_endpoint(ws: WebSocket):
    user_id = await ws_manager.connect(ws)
    db.add_or_update_user(User(
        user_id,
        None,
        None
    ))
    try:
        while True:
            text = await ws.receive_text()
            logger.debug(f'Received a message from the user with id {user_id}:')
            log_message(logger.debug, text)

            try:
                message = Message.from_dict(json.loads(text))

                if message.type != MessageType.RECONNECT:
                    response = await message_handler.handle_message(user_id, message)
                    await ws_manager.send_personal_message(user_id, response)
                else:
                    user_id = ws_manager.reconnect(user_id, message)

            except json.JSONDecodeError: # Invalid json
                logger.warning(f'Invalid json message received from the user {user_id}: failed to decode')
                log_message(logger.warning, text)

                await ws_manager.send_personal_message(
                    user_id,
                    Message(
                        type=MessageType.ERROR,
                        data='invalid json',
                        request_id=uuid4()
                    )
                )
            except TypeError as e: # cannot serialize object
                logger.warning(f'internal error. User {user_id}: {e}')
                log_message(logger.warning, text)

                await ws_manager.send_personal_message(
                    user_id,
                    Message(
                        type=MessageType.ERROR,
                        data='internal error',
                        request_id=uuid4()
                    )
                )
            except KeyError as e: # Failed to decode a message as there is a key missing
                logger.warning(f'Invalid message received from the user {user_id}: key {e} is missing')
                log_message(logger.warning, text)

                await ws_manager.send_personal_message(
                    user_id,
                    Message(
                        type=MessageType.ERROR,
                        data=f'a key is missing',
                        request_id=uuid4()
                    )
                )
            except ValueError: # requestId is an invalid UUID
                logger.warning(f'Invalid message received from the user {user_id}: invalid UUID')
                log_message(logger.warning, text)

                await ws_manager.send_personal_message(
                    user_id,
                    Message(
                        type=MessageType.ERROR,
                        data='invalid UUID',
                        request_id=uuid4()
                    )
                )
    except WebSocketDisconnect as e:
        logger.debug(f'ws: {e}')
        await ws_manager.disconnect(user_id)


if __name__ == '__main__':
    uvicorn.run(app, host='::', port=8000, log_level='debug') # for debugging
