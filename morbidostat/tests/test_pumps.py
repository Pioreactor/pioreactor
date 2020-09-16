import pytest
from morbidostat.actions import add_media, add_alt_media, remove_waste


def test_pump_io():
    add_media.add_media(ml=0.1, unit=1)
    add_alt_media.add_alt_media(ml=0.1, unit=1)
    remove_waste.remove_waste(ml=0.1, unit=1)


def test_pump_io_doesnt_allow_negative():
    with pytest.raises(AssertionError):
        add_media.add_media(ml=-1, unit=1)
    with pytest.raises(AssertionError):
        add_alt_media.add_alt_media(ml=-1, unit=1)
    with pytest.raises(AssertionError):
        remove_waste.remove_waste(ml=-1, unit=1)


