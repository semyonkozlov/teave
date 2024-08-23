from common.errors import TeaveError
from common.models import Teavent


class UnknownTeavent(TeaveError):
    def __init__(self, teavent_id: str):
        self.teavent_id = teavent_id
        super().__init__(f"Unknown teavent id: {teavent_id}")


class TeaventIsInFinalState(TeaveError):
    def __init__(self, teavent: Teavent):
        self.teavent = teavent
        super().__init__(f"Teavet {teavent.id} is in final state '{teavent.state}")
