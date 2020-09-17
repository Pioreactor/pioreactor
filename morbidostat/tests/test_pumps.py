# -*- coding: utf-8 -*-
import pytest
from morbidostat.actions import add_media, add_alt_media, remove_waste, clean_tubes


def test_pump_io():
    add_media.add_media(ml=0.1)
    add_alt_media.add_alt_media(ml=0.1)
    remove_waste.remove_waste(ml=0.1)


def test_pump_io_doesnt_allow_negative():
    with pytest.raises(AssertionError):
        add_media.add_media(ml=-1)
    with pytest.raises(AssertionError):
        add_alt_media.add_alt_media(ml=-1)
    with pytest.raises(AssertionError):
        remove_waste.remove_waste(ml=-1)


def test_cleaning():
    clean_tubes.clean_tubes(0.1)
