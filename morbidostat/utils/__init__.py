def pump_ml_to_duration(ml, rate, bias):
    """
    ml = rate * duration + bias
    """
    duration = (ml - bias) / rate
    assert duration > 0, "pump duration is negative"
    return duration
