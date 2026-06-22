from alerting.console_alert import AlertManager


def test_should_alert_returns_false_for_none_priority():
    assert AlertManager().should_alert({"alert_priority": "none"}) is False


def test_should_alert_returns_false_for_low_priority():
    assert AlertManager().should_alert({"alert_priority": "low"}) is False


def test_should_alert_returns_true_for_medium_priority():
    assert AlertManager().should_alert({"alert_priority": "medium"}) is True


def test_should_alert_returns_true_for_high_priority():
    assert AlertManager().should_alert({"alert_priority": "high"}) is True
