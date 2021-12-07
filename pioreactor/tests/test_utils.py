# -*- coding: utf-8 -*-
# test_utils
from pioreactor.utils import local_intermittent_storage


def test_that_out_scope_caches_cant_access_keys_created_by_inner_scope_cache():
    """
    You can modify caches, and the last assignment is valid.
    """
    with local_intermittent_storage("test") as cache:
        for k in cache.keys():
            del cache[k]

    with local_intermittent_storage("test") as cache1:
        cache1["A"] = b"0"
        with local_intermittent_storage("test") as cache2:
            assert cache2["A"] == b"0"
            cache2["B"] = b"1"

        assert "B" not in cache1  # note this.
        cache1["B"] = b"2"  # create, and overwritten.

    with local_intermittent_storage("test") as cache:
        assert cache["A"] == b"0"
        assert cache["B"] == b"2"


def test_caches_will_always_save_the_lastest_value_provided():
    with local_intermittent_storage("test") as cache:
        for k in cache.keys():
            del cache[k]

    with local_intermittent_storage("test") as cache1:
        with local_intermittent_storage("test") as cache2:
            cache1["A"] = b"1"
            cache2["A"] = b"0"
            cache2["B"] = b"2"

    with local_intermittent_storage("test") as cache:
        assert cache["A"] == b"0"
        assert cache["B"] == b"2"
