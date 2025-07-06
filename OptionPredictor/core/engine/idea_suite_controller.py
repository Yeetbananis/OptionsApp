# idea_suite_controller.py
from __future__ import annotations
import queue, threading
from typing import Iterable, List, TYPE_CHECKING # Import TYPE_CHECKING for circular dependency

if TYPE_CHECKING:
    from core.engine.idea_engine import IdeaEngine # Import with TYPE_CHECKING to avoid circular import


class IdeaSuiteController:
    """
    Threaded orchestrator: ask IdeaEngine for a universe,
    push resulting list[Idea] back to the Tk view.
    """
    def __init__(self, engine: 'IdeaEngine', sink: queue.Queue) -> None:
        self.engine = engine
        self.sink = sink
        self._thread: threading.Thread | None = None

    def refresh(self, universe: Iterable[str], progress_sink: queue.Queue) -> None: # NEW: Accept progress_sink
        if self._thread and self._thread.is_alive():
            return
        # Pass the progress_sink to the engine instance directly before starting the thread
        self.engine.progress_sink = progress_sink # NEW: Assign progress_sink to engine
        self._thread = threading.Thread(target=self._worker,
                                         args=(list(universe),), daemon=True)
        self._thread.start()

    def _worker(self, universe: List[str]) -> None:
        ideas = self.engine.generate(universe)
        self.sink.put(ideas)