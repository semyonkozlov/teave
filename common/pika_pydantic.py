from typing import TypeVar

import aio_pika
from aio_pika.abc import AbstractIncomingMessage, AbstractChannel, AbstractMessage
import pydantic


class ModelMessage(AbstractMessage):
    def __init__(self, model: pydantic.BaseModel):
        super().__init__(
            model.model_dump_json().encode(),
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        )


Model = TypeVar("Model", bound="TeaveModel")


class TeaveModel(pydantic.BaseModel):
    _delivery_tag: int = pydantic.PrivateAttr(default=None)

    @classmethod
    def from_message(cls: type[Model], message: AbstractIncomingMessage) -> Model:
        model = cls.model_validate_json(message.body.decode())
        model._delivery_tag = message.delivery_tag
        return model

    async def ack_delivery(self, channel: AbstractChannel):
        underlay = await channel.get_underlay_channel()
        return await underlay.basic_ack(self._delivery_tag)
