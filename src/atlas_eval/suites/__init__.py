"""Suite registry, in report order."""

from .agent import AgentLLMSuite, AgentSuite
from .live import AnswersSuite, QuakeQuestionsSuite, RetrievalSuite
from .offline import QuakesSuite, RoutingSuite
from .scientific import DvvSuite, GapsSuite, PressureSuite, TimingSuite

SUITES = {s.name: s for s in (RoutingSuite(), QuakeQuestionsSuite(), RetrievalSuite(), AnswersSuite(), QuakesSuite(),
                              GapsSuite(), TimingSuite(), DvvSuite(), PressureSuite(), AgentSuite(), AgentLLMSuite())}
OFFLINE = [n for n, s in SUITES.items() if s.requires == "offline"]
