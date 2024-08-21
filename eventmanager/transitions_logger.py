import logging

from statemachine import State

from common.models import Teavent

log = logging.getLogger("transitions")


class TransitionsLogger:
    def on_transition(self, event, source: State, target: State, model: Teavent):
        log.info(f"{model.id}: {source.id} -({event})-> {target.id}")
