import time

import pytest

from torque.ai.filler import FILLERS, FillerGate


def slow(first_delay, items, gap=0.0):
    time.sleep(first_delay)
    for i, item in enumerate(items):
        if i:
            time.sleep(gap)
        yield item


def test_fast_replies_get_no_filler():
    assert list(FillerGate(after=0.3).wrap(slow(0.0, ["a", "b"]))) == ["a", "b"]


def test_slow_first_sentence_gets_one_filler_then_the_reply():
    out = list(FillerGate(after=0.1).wrap(slow(0.35, ["answer"])))
    assert out[0] in FILLERS and out[-1] == "answer"
    assert 1 <= out.count(out[0]) <= 4 and out[-1] == "answer"


def test_only_the_first_wait_counts():
    out = list(FillerGate(after=0.1).wrap(slow(0.0, ["a", "b"], gap=0.4)))
    assert out == ["a", "b"]


def test_disabled_with_zero():
    assert list(FillerGate(after=0).wrap(slow(0.2, ["x"]))) == ["x"]


def test_errors_reach_the_caller():
    def boom():
        yield "a"
        raise RuntimeError("llm died")

    gate = FillerGate(after=0.5).wrap(boom())
    assert next(gate) == "a"
    with pytest.raises(RuntimeError, match="llm died"):
        next(gate)


def test_cutting_off_stops_the_producer():
    produced = []

    def endless():
        for i in range(10_000):
            produced.append(i)
            time.sleep(0.001)
            yield f"s{i}"

    gate = FillerGate(after=0.5).wrap(endless())
    assert next(gate) == "s0"
    gate.close()
    time.sleep(0.1)
    count = len(produced)
    time.sleep(0.1)
    assert len(produced) == count and count < 500


def test_empty_reply_ends_cleanly():
    assert list(FillerGate(after=0.1).wrap(iter([]))) == []


def test_fillers_rotate():
    gate = FillerGate(after=0.05)
    first = list(gate.wrap(slow(0.12, ["x"])))[0]
    second = list(gate.wrap(slow(0.12, ["y"])))[0]
    assert first != second
