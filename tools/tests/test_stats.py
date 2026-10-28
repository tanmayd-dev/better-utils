import tools.stats


def test_summarize():
    out = tools.stats.summarize([1, 2, 3])
    assert out["count"] == 3 and out["sum"] == 6 and out["average"] == 2


def test_fib_bounds():
    assert tools.stats.fib(1) == [0]
    assert tools.stats.fib(6)[:3] == [0, 1, 1]
