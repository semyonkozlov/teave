from common.errors import TeaveError


class InconsistencyError(TeaveError):
    "Inconsistent data found"


class UnknownTeavent(TeaveError):
    def __init__(self, teavent_id: str):
        self.teavent_id = teavent_id
        super().__init__(f"Unknown teavent id: {teavent_id}")
