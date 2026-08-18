"""Le compare des logs ignore le bruit et montre les ecarts de comportement."""

from runner.domain.log_compare import compare_logs, is_error_line, normalize_line


def test_timestamps_durations_and_reader_names_are_not_differences():
    left = """2026-08-18 14:02:10.123 INFO - Cosmo11Secured Reader
INFO - Duration : 2.53 ms
INFO - Expected Status : 9EEE
"""
    right = """2026-08-18 14:09:44.981 INFO - Cosmo11SecuredCVertif Reader
INFO - Duration : 0.26 ms
INFO - Expected Status : 9EEE
"""

    result = compare_logs(
        (left, right),
        ("Cosmo11Secured Reader", "Cosmo11SecuredCVertif Reader"),
    )

    assert not result.any


def test_an_inserted_logger_error_is_the_difference_that_stands_out():
    left = """INFO - APDU Status : 9E EE
INFO - Expected Status : 9EEE
INFO - ## Step 2.7 : Garbage Collector deleteInstance()
"""
    right = """INFO - APDU Status : 6F EE
INFO - Expected Status : 9EEE
ERRO - Wrong Status Word, received: 6FEE ; authorized : {'9EEE'}
INFO - Start of Teardown
"""

    result = compare_logs((left, right))

    assert 2 in result.changed[1]
    assert 1 not in result.changed[0]
    assert 1 not in result.changed[1]
    assert result.errors[1] == frozenset({2})
    assert is_error_line(right.splitlines()[2])


def test_apdu_values_are_never_normalized_away():
    assert normalize_line("INFO - APDU Status : 9E EE") != normalize_line(
        "INFO - APDU Status : 6F EE")
