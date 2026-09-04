"""In-memory delivery-ID cache (FR-006/FR-008, data-model.md DeliveryCache).

reserve() checks and marks a delivery ID in one synchronous step, with no
`await` in between — closing the TOCTOU race two concurrent deliveries with
the same X-GitHub-Delivery ID would otherwise hit (research.md/H3). A
WorkflowAlreadyStartedError is the authoritative fallback for RunCommand;
GateCommand has no such backstop, so this cache is its only defense.
"""
import collections

_DEFAULT_MAX_SIZE = 1000


class DeliveryCache:
    def __init__(self, max_size: int = _DEFAULT_MAX_SIZE) -> None:
        self._max_size = max_size
        self._seen: collections.OrderedDict[str, None] = collections.OrderedDict()

    def reserve(self, delivery_id: str) -> bool:
        """Mark delivery_id as seen and return True, or return False if it
        was already seen. Marking happens unconditionally in this same call.
        """
        if delivery_id in self._seen:
            self._seen.move_to_end(delivery_id)
            return False
        self._seen[delivery_id] = None
        if len(self._seen) > self._max_size:
            self._seen.popitem(last=False)
        return True
