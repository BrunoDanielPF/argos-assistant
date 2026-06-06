from assistant.observability.metrics import Timer


def test_timer_returns_non_negative_duration():
    timer = Timer.start()

    assert timer.elapsed_ms() >= 0
