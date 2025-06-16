# idea_suite_controller.py
from __future__ import annotations
import queue, threading
from typing import Iterable, List

from idea_models import Idea
from idea_engine import IdeaEngine


class IdeaSuiteController:
    """
    Threaded orchestrator: ask IdeaEngine for a universe,
    push resulting list[Idea] back to the Tk view.
    """
    def __init__(self, engine: IdeaEngine, sink: queue.Queue) -> None:
        self.engine = engine
        self.sink = sink
        self._thread: threading.Thread | None = None

    def refresh(self, universe: Iterable[str]) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._worker,
                                        args=(list(universe),), daemon=True)
        self._thread.start()

    def _worker(self, universe: List[str]) -> None:
        ideas = self.engine.generate(universe)
        self.sink.put(ideas)
