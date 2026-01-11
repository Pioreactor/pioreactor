# -*- coding: utf-8 -*-
# tests the mocking in our test suite
from pioreactor.cluster_management import get_active_workers_in_inventory


# Define the test function
def test_get_active_workers_in_inventory() -> None:
    # Call the function under test
    active_workers = get_active_workers_in_inventory()

    # Assert the expected result
    assert active_workers == ("unit1", "unit2")
