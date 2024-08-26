from common.errors import TeaveError
from common.models import Teavent


class BadTeavent(TeaveError):
    def __init__(self, msg: str, teavent: Teavent):
        self.teavent = teavent
        super().__init__(msg)


class UnknownTeavent(TeaveError):
    def __init__(self, teavent_id: str):
        self.teavent_id = teavent_id
        super().__init__(f"Unknown teavent id: {teavent_id}")


class TeaventIsInFinalState(BadTeavent):
    def __init__(self, teavent: Teavent):
        super().__init__(
            f"Teavet {teavent.id} is in final state '{teavent.state}'", teavent=teavent
        )


class TeaventFromThePast(BadTeavent):
    def __init__(self, teavent: Teavent):
        super().__init__(f"Teavent is from the past: {teavent.start}", teavent=teavent)
