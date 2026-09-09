from intervals_mcp_server.utils.ranges import range_query, validate_range


def test_range_malformed():
    assert isinstance(validate_range("bad", "2026-01-02", None, "UTC"), str)


def test_range_reversed_equal():
    assert isinstance(validate_range("2026-01-02", "2026-01-02", None, "UTC"), str)
    assert isinstance(validate_range("2026-01-03", "2026-01-02", None, "UTC"), str)


def test_range_simultaneous_end_forms():
    assert isinstance(validate_range("2026-01-01", "2026-01-03", "2026-01-02", "UTC"), str)


def test_range_legacy_inclusive():
    result = validate_range("2026-01-01", None, "2026-01-02", "UTC")
    assert result[1] == "2026-01-03" and result[3] is True


def test_range_timezone_invalid():
    assert isinstance(validate_range("2026-01-01", "2026-01-02", None, "No/Such"), str)


def test_range_reports_dst_aware_utc_boundaries():
    checked = validate_range(
        "2026-03-28", "2026-03-30", None, "Europe/Warsaw"
    )
    assert not isinstance(checked, str)
    start, end, zone, _ = checked
    query = range_query(start, end, zone, "Europe/Warsaw")
    assert query["start_utc"] == "2026-03-27T23:00:00Z"
    assert query["end_utc_exclusive"] == "2026-03-29T22:00:00Z"
