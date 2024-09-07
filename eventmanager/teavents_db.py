import motor.motor_asyncio as aio_mongo
from attr import define

from common.executors import Executor
from common.models import Teavent


@define(eq=False)  # eq=False for hashing by id
class TeaventsDB:
    _storage: aio_mongo.AsyncIOMotorCollection
    _executor: Executor

    async def fetch_teavents(self):
        async for document in self._storage.find():
            yield Teavent(**document)

    def after_transition(self, model: Teavent):
        self._executor.schedule(
            self._storage.replace_one({}, model.model_dump(mode="json", by_alias=True)),
            name=f"{model.id}:dbupdate",
        )
