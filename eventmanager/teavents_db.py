import motor.motor_asyncio as aio_mongo
from attr import define

from common.executors import Executor
from common.models import Teavent
from common.flow import TeaventFlow


@define(eq=False)  # eq=False is required to be listener
class TeaventsDB:
    _storage: aio_mongo.AsyncIOMotorCollection
    _executor: Executor

    _update_id: int = 0

    async def fetch_teavents(self):
        async for document in self._storage.find():
            yield Teavent(**document)

    # SM actions

    def after_transition(self, model: Teavent):
        self._update_id += 1

        self._executor.schedule(
            self._storage.replace_one(
                {}, model.model_dump(mode="json", by_alias=True), upsert=True
            ),
            group_id=f"{model.id}_db",
            name=f"update_{self._update_id}",
        )

    @TeaventFlow.finalized.enter
    def _drop_from_storage(self, model: Teavent):
        self._executor.schedule(
            self._storage.delete_one({"_id": model.id}),
            group_id=f"{model.id}_db",
            name="drop",
        )
