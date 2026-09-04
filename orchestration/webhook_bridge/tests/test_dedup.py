from webhook_bridge.dedup import DeliveryCache


def test_reserve_first_call_marks_and_returns_true() -> None:
    cache = DeliveryCache()
    assert cache.reserve("delivery-1") is True


def test_reserve_second_call_same_id_returns_false() -> None:
    cache = DeliveryCache()
    assert cache.reserve("delivery-1") is True
    assert cache.reserve("delivery-1") is False


def test_reserve_distinct_ids_both_succeed() -> None:
    cache = DeliveryCache()
    assert cache.reserve("delivery-1") is True
    assert cache.reserve("delivery-2") is True


def test_reserve_bounded_evicts_oldest() -> None:
    cache = DeliveryCache(max_size=2)
    assert cache.reserve("a") is True
    assert cache.reserve("b") is True
    assert cache.reserve("c") is True  # evicts "a"
    assert cache.reserve("a") is True  # "a" was evicted, so it's new again
