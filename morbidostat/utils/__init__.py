def pump_ml_to_duration(ml, rate, bias):
    """
    ml = rate * duration + bias
    """
    duration = (ml - bias) / rate
    assert duration > 0, "pump duration is negative"
    return duration


def execute_sql(SQL):
    pass



def current_alt_media_level(history):
    # history looks like [("add_media", 0.25), ("add_alt_media", 0.5), ...]

    VOLUME_ml = 12.0
    alt_media_ml = 0.0

    for event, vol in history:
        if event == "add_media":
            alt_media_ml -= vol / VOLUME_ml * alt_media_ml
        elif event == "add_alt_media":
            alt_media_ml -= vol / VOLUME_ml * alt_media_ml
            alt_media_ml += vol
        else:
            raise ValueError()
    return alt_media_ml

