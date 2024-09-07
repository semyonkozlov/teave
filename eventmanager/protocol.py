import asyncio
from collections.abc import Coroutine
import logging

import aio_pika
from attr import define
from statemachine import State

from common.executors import Executor
from common.models import FlowUpdate, Teavent
from common.pika_pydantic import ModelMessage

log = logging.getLogger(__name__)


@define(eq=False)  # eq=False for hashing by id
class RmqProtocol:
    _teavents_queue: aio_pika.abc.AbstractQueue
    _outgoing_updates_queue: aio_pika.abc.AbstractQueue

    _channel: aio_pika.abc.AbstractChannel

    _executor: Executor

    async def publish_update(self, outgoing_update: FlowUpdate):
        await self._channel.default_exchange.publish(
            ModelMessage(outgoing_update),
            routing_key=self._outgoing_updates_queue.name,
        )

    # SM actions

    def on_enter_state(self, state: State, model: Teavent):
        self._executor.schedule(
            self.publish_update(FlowUpdate.for_teavent(model, type=state.name)),
            name=f"{model.id}:pub_{state.value}",
        )
