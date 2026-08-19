from marks import MarkList


def test_mark_subtracts_offset_and_returns_value():
    ml = MarkList(offset=0.30)
    assert ml.mark(73.241) == 72.941


def test_mark_appends_to_list():
    ml = MarkList(offset=0.30)
    ml.mark(73.241)
    ml.mark(20.000)
    assert ml.marks == [72.941, 19.700]


def test_mark_clamps_at_zero():
    ml = MarkList(offset=0.30)
    assert ml.mark(0.1) == 0.0
    assert ml.marks == [0.0]


def test_mark_rounds_to_three_decimals():
    ml = MarkList(offset=0.0)
    assert ml.mark(1.23456) == 1.235


def test_offset_is_mutable_live():
    ml = MarkList(offset=0.30)
    ml.offset = 0.50
    assert ml.mark(10.000) == 9.500


def test_delete_last_removes_newest():
    ml = MarkList(offset=0.0)
    ml.mark(1.0)
    ml.mark(2.0)
    ml.delete_last()
    assert ml.marks == [1.0]


def test_delete_last_on_empty_is_noop():
    ml = MarkList()
    ml.delete_last()
    assert ml.marks == []


def test_clear_empties_list():
    ml = MarkList(offset=0.0)
    ml.mark(1.0)
    ml.mark(2.0)
    ml.clear()
    assert ml.marks == []
