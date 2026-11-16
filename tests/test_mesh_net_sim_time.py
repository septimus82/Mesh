"""The simulated clock the simulated networking tests run on (tests/net_sim_time.py): timers fire at their exact
times and in real time's order, on every platform; a timeout is simulated time too; real loops keep real time; and a
run that can never finish fails, quickly, instead of hanging."""

import asyncio
import time

import pytest

from tests.net_sim_time import SimulationStuck, run

pytestmark = pytest.mark.integration


async def scenario(log, unit):
    """Sleeps, a poll, a timeout and a cancellation whose times never coincide (in units of ``unit`` seconds)."""
    loop = asyncio.get_running_loop()
    start = loop.time()

    def note(what):
        log.append((what, round((loop.time() - start) / unit)))

    async def sleeper(name, units):
        await asyncio.sleep(units * unit)
        note(name)

    async def poller():
        try:
            while True:
                await asyncio.sleep(4 * unit)
                note("poll")
        except asyncio.CancelledError:
            note("poll cancelled")
            raise

    async def timed_out():
        try:
            async with asyncio.timeout(7 * unit):
                await asyncio.sleep(100 * unit)
        except TimeoutError:
            note("timeout")

    tasks = [asyncio.create_task(c) for c in (sleeper("a", 5), sleeper("b", 2), poller(), timed_out(), sleeper("c", 10))]
    await asyncio.sleep(13 * unit)
    tasks[2].cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    note("end")


EXPECTED = [("b", 2), ("poll", 4), ("a", 5), ("timeout", 7), ("poll", 8), ("c", 10), ("poll", 12), ("poll cancelled", 13), ("end", 13)]


def test_events_come_in_the_order_and_at_the_times_real_time_gives_them():
    """The same tasks on a real loop (40 ms a unit: wider than any platform's timer) and on the simulated one."""
    real, simulated = [], []
    asyncio.run(scenario(real, 0.04))
    started = time.perf_counter()
    run(scenario(simulated, 0.04))
    assert simulated == EXPECTED  # the exact times
    assert [what for what, _ in real] == [what for what, _ in EXPECTED]  # (real timers run a little late)
    assert time.perf_counter() - started < 0.3  # (0.52 s of it simulated)


def test_a_timer_fires_at_its_own_time_not_at_an_earlier_timers():
    """1 ms and 5 ms sleeps, as the walking tests' server and helper use. (A real Windows loop calls a timer due
    15.6 ms early: on that rule the 5 ms sleep would end with the first 1 ms one.)"""
    log = []

    async def every(name, delay, times):
        loop = asyncio.get_running_loop()
        for _ in range(times):
            await asyncio.sleep(delay)
            log.append((name, loop.time()))

    async def main():
        await asyncio.gather(every("server", 0.001, 12), every("helper", 0.005, 2))

    run(main())
    assert [at for name, at in log if name == "helper"] == pytest.approx([0.005, 0.010], abs=1e-9)
    assert [at for name, at in log if name == "server"] == pytest.approx([0.001 * n for n in range(1, 13)], abs=1e-9)


def test_a_timeout_is_simulated_time_and_still_fails_the_wait():
    async def main():
        loop = asyncio.get_running_loop()
        polls = 0
        try:
            async with asyncio.timeout(15):
                while True:
                    await asyncio.sleep(0.005)
                    polls += 1
        except TimeoutError:
            return loop.time(), polls

    started = time.perf_counter()
    at, polls = run(main())
    assert at == pytest.approx(15) and 2990 <= polls <= 3000
    assert time.perf_counter() - started < 5


def test_the_result_and_an_exception_come_back_as_from_asyncio_run():
    async def answer():
        await asyncio.sleep(1)
        return 42

    async def fails():
        await asyncio.sleep(1)
        raise AssertionError("not reached in 1 s")

    assert run(answer()) == 42
    with pytest.raises(AssertionError, match="not reached in 1 s"):
        run(fails())


def test_a_run_leaves_no_task_or_loop_behind_and_real_loops_keep_real_time():
    seen = {}

    async def background():
        try:
            await asyncio.sleep(1000)
        finally:
            seen["background ended"] = True

    async def main():
        seen["loop"] = asyncio.get_running_loop()
        seen["task"] = asyncio.create_task(background())
        await asyncio.sleep(1)

    run(main())
    assert seen["background ended"] and seen["task"].cancelled() and seen["loop"].is_closed()

    async def real():
        loop = asyncio.get_running_loop()
        started = time.perf_counter()
        before = loop.time()
        await asyncio.sleep(0.05)
        return time.perf_counter() - started, loop.time() - before

    waited, loop_time = asyncio.run(real())
    assert waited >= 0.04 and loop_time >= 0.04  # a real 50 ms, on a loop this module never touched


def test_a_wait_nothing_can_end_fails_at_once():
    async def main():
        await asyncio.Event().wait()

    started = time.perf_counter()
    with pytest.raises(SimulationStuck, match="nothing can continue"):
        run(main())
    assert time.perf_counter() - started < 2


def test_a_poll_with_no_timeout_of_its_own_fails_on_simulated_time():
    async def main():
        while True:
            await asyncio.sleep(0.005)

    started = time.perf_counter()
    with pytest.raises(SimulationStuck, match="simulated time"):
        run(main(), simulated_limit=20)
    assert time.perf_counter() - started < 5


def test_a_loop_that_never_waits_fails_on_real_time():
    """The simulated clock never moves here, so only the real one can end it."""
    async def main():
        while True:
            await asyncio.sleep(0)

    started = time.perf_counter()
    with pytest.raises(SimulationStuck, match="real time"):
        run(main(), real_limit=0.2)
    assert 0.2 <= time.perf_counter() - started < 5
