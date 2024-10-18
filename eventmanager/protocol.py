import logging

import aio_pika
from attr import define
from statemachine import State

from common.executors import Executor
from common.models import Teavent
from common.pika_pydantic import ModelMessage

log = logging.getLogger(__name__)


@define(eq=False)  # eq=False is required to be listener
class RmqProtocol:
    _outgoing_updates_queue: aio_pika.abc.AbstractQueue
    _channel: aio_pika.abc.AbstractChannel

    _executor: Executor

    async def _publish_update(self, teavent: Teavent):
        await self._channel.default_exchange.publish(
            ModelMessage(teavent),
            routing_key=self._outgoing_updates_queue.name,
        )

    # SM actions

    def after_transition(self, state: State, model: Teavent):
        self._executor.schedule(
            self._publish_update(model.model_copy()),
            group_id=f"{model.id}_pub",
            name=state.value,
        )
