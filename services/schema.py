from typing import Protocol

from domain.messages_schema import Message


class SenderServiceProtocol(Protocol):
    def _send(self, message: Message, user_id: str): ...

    def send_all(self, messages: list[Message], user_id: str): ...
