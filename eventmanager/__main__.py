import asyncio
import logging

import aio_pika
from aio_pika.patterns import RPC
from attr import define
from statemachine import State, StateMachine

from common.pika_pydantic import ModelMessage
from common.models import Teavent, FlowUpdate


class InconsistencyError(RuntimeError):
    "Inconsistent data found"


class TeaventFlow(StateMachine):
    # states
    created = State(initial=True)
    not_enough_participants = State()
    enough_participants = State()
    started = State()
    finished = State(final=True)

    # transitions
    # fmt: off
    confirm = (
        created.to(enough_participants, cond="ready") | 
        enough_participants.to(enough_participants, cond="has_slots") |
        not_enough_participants.to(enough_participants, cond="ready") | 
        created.to(not_enough_participants)
    )
    start_ = enough_participants.to(started)
    reject = enough_participants.to(not_enough_participants, unless="ready")
    finish = started.to(finished)
    # fmt: on

    @property
    def teavent(self) -> Teavent:
        return self.model

    def on_confirm(self, user_id: str, model: Teavent):
        model.participant_ids.append(user_id)

    def on_reject(self, user_id: str, model: Teavent):
        model.participant_ids.remove(user_id)

    @confirm.validators
    def not_confirmed_before(self, user_id: str, model: Teavent):
        if model.confirmed_by(user_id):
            raise Exception()

    @reject.validators
    def confirmed_before(self, user_id: str, model: Teavent):
        if model.confirmed_by(user_id):
            raise Exception()


@define(hash=True)
class Protocol:
    _teavents_queue: aio_pika.abc.AbstractQueue
    _outgoing_updates_queue: aio_pika.abc.AbstractQueue

    _channel: aio_pika.abc.AbstractChannel

    async def on_enter_state(self, state: State, model: Teavent):
        await self.publish_teavent(model)
        await self.publish_update(FlowUpdate.for_teavent(model, type=state.name))

    async def publish_update(self, outgoing_update: FlowUpdate):
        await self._channel.default_exchange.publish(
            ModelMessage(outgoing_update),
            routing_key=self._outgoing_updates_queue.name,
        )

    async def publish_teavent(self, teavent: Teavent):
        await self._channel.default_exchange.publish(
            ModelMessage(teavent),
            routing_key=self._teavents_queue.name,
        )

    async def ack_teavent(self, teavent: Teavent, new_delivery_tag: str):
        "Drop old message from queue and update delivery tag"

        await teavent.ack_delivery(self._channel)
        teavent._delivery_tag = new_delivery_tag


@define
class TeaventManager:
    _protocol: Protocol
    _teavents_sm: dict[str, TeaventFlow] = {}

    def list_teavents(self) -> list[Teavent]:
        return list(sm.teavent for sm in self._teavents_sm.values())

    async def _setup_timers(self, teavent: Teavent): ...

    async def handle_teavent(self, teavent: Teavent):
        if teavent.id not in self._teavents_sm:
            logging.info(f"Got new event {teavent}")
            self._teavents_sm[teavent.id] = TeaventFlow(
                model=teavent, listeners=[self._protocol]
            )
            await self._setup_timers(teavent)
        else:
            logging.info(f"Got known event {teavent}")
            sm = self._teavents_sm[teavent.id]

            self._check_consistency(teavent, sm.teavent)
            await self._protocol.ack_teavent(
                sm.teavent, new_delivery_tag=teavent._delivery_tag
            )

    def _check_consistency(self, new_teavent: Teavent, managed_teavent: Teavent):
        assert new_teavent.id == managed_teavent.id

        if new_teavent.state != managed_teavent.state:
            raise InconsistencyError(
                f"Event {managed_teavent.id} has state '{managed_teavent.state}', but '{new_teavent.state}' received"
            )

    async def handle_user_action(self, type: str, user_id: str, teavent_id: str):
        return await self._teavents_sm[teavent_id].send(type, user_id=user_id)


async def main():
    logging.basicConfig(level=logging.INFO)

    connection = await aio_pika.connect("amqp://guest:guest@rabbitmq/")
    async with connection:
        channel = await connection.channel()

        teavents = await channel.declare_queue("teavents", durable=True)
        outgoing_updates = await channel.declare_queue("outgoing_updates", durable=True)
        await channel.set_qos(prefetch_size=0)

        protocol = Protocol(teavents, outgoing_updates, channel)
        teavent_manager = TeaventManager(protocol=protocol)

        logging.info("Register RPC")

        rpc = await RPC.create(channel)

        async def list_teavents() -> list[Teavent]:
            return teavent_manager.list_teavents()

        async def user_action(type: str, user_id: str, teavent_id: str):
            return await teavent_manager.handle_user_action(
                type=type, user_id=user_id, teavent_id=teavent_id
            )

        await rpc.register("list_teavents", list_teavents, auto_delete=True)
        await rpc.register("user_action", user_action, auto_delete=True)

        logging.info("Register consumers")

        async def on_teavent(message: aio_pika.abc.AbstractIncomingMessage):
            await teavent_manager.handle_teavent(Teavent.from_message(message))

        await teavents.consume(on_teavent)

        await asyncio.Future()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
