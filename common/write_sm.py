from statemachine.contrib.diagram import DotGraphMachine

from common.flow import TeaventFlow


class FakeModel:
    def ready(self) -> bool:
        return True


# sudo apt install graphviz
# pip install pydot

graph = DotGraphMachine(TeaventFlow(model=FakeModel()))
graph().write_png("sm.png")
