# -*- coding: utf-8 -*-
from pathlib import Path

import pytest
from pioreactor.utils import cache as exported_cache
from pioreactor.utils import local_intermittent_storage
from pioreactor.utils import local_persistent_storage
from pioreactor.utils.sqlite_cache import cache as sqlite_cache


def test_that_out_scope_caches_cant_access_keys_created_by_inner_scope_cache() -> None:
    """
    You can modify caches, and the last assignment is valid.
    """
    with local_intermittent_storage("test") as cache:
        for k in cache.iterkeys():
            del cache[k]

    with local_intermittent_storage("test") as cache1:
        cache1["A"] = "0"

        with local_intermittent_storage("test") as cache2:
            assert cache2["A"] == "0"
            cache2["B"] = "1"

        assert "B" in cache1
        cache1["B"] = "2"

    with local_intermittent_storage("test") as cache:
        assert cache["A"] == "0"
        assert cache["B"] == "2"


def test_caches_will_always_save_the_lastest_value_provided() -> None:
    with local_intermittent_storage("test") as cache:
        cache.empty()

    with local_intermittent_storage("test") as cache:
        cache["A"] = "1"
        cache["A"] = "0"
        cache["B"] = "2"

    with local_intermittent_storage("test") as cache:
        assert cache["A"] == "0"
        assert cache["B"] == "2"


def test_caches_will_delete_when_asked() -> None:
    with local_intermittent_storage("test") as cache:
        for k in cache.iterkeys():
            del cache[k]

    with local_intermittent_storage("test") as cache:
        cache["test"] = "1"

    with local_intermittent_storage("test") as cache:
        assert "test" in cache
        del cache["test"]
        assert "test" not in cache


def test_caches_pop() -> None:
    with local_intermittent_storage("test") as cache:
        cache.empty()

    with local_intermittent_storage("test") as cache:
        cache["A"] = "1"

    with local_intermittent_storage("test") as cache:
        assert cache.pop("A") == "1"
        assert cache.pop("B") is None
        assert cache.pop("C", default=3) == 3


def test_cache_set_if_absent() -> None:
    with local_intermittent_storage("test") as cache:
        cache.empty()

    with local_intermittent_storage("test") as cache:
        assert cache.set_if_absent("A", "1")
        assert not cache.set_if_absent("A", "2")

    with local_intermittent_storage("test") as cache:
        assert cache["A"] == "1"


def test_caches_can_have_tuple_or_singleton_keys() -> None:
    with local_persistent_storage("test_caches_can_have_tuple_keys") as c:
        c[(1, 2)] = 1
        c[("a", "b")] = 2
        c[("a", None)] = 3
        c[4] = 4
        c["5"] = 5

    with local_persistent_storage("test_caches_can_have_tuple_keys") as c:
        assert list(c.iterkeys()) == [4, "5", ("a", "b"), ("a", None), (1, 2)]


def test_caches_integer_keys() -> None:
    with local_persistent_storage("test_caches_integer_keys") as c:
        c[1] = "a"
        c[2] = "b"

    with local_persistent_storage("test_caches_integer_keys") as c:
        assert list(c.iterkeys()) == [1, 2]


def test_caches_str_keys_as_ints_stay_as_str() -> None:
    with local_persistent_storage("test_caches_str_keys_as_ints_stay_as_str") as c:
        c["1"] = "a"
        c["2"] = "b"

    with local_persistent_storage("test_caches_str_keys_as_ints_stay_as_str") as c:
        assert list(c.iterkeys()) == ["1", "2"]


def test_cache_round_trip_and_tuple_keys(tmp_path: Path) -> None:
    db_path = tmp_path / "cache.sqlite"

    with sqlite_cache("example", db_path=str(db_path)) as c:
        c["A"] = "1"
        c[(1, 2)] = "tuple"
        c[("nested", (3, 4))] = "nested"

    with sqlite_cache("example", db_path=str(db_path)) as c:
        assert c["A"] == "1"
        assert c[(1, 2)] == "tuple"
        assert c[("nested", (3, 4))] == "nested"
        assert set(c.iterkeys()) == {"A", (1, 2), ("nested", (3, 4))}


def test_cache_set_if_absent_only_sets_once(tmp_path: Path) -> None:
    db_path = tmp_path / "cache.sqlite"

    with sqlite_cache("example", db_path=str(db_path)) as c:
        assert c.set_if_absent("A", "1") is True
        assert c.set_if_absent("A", "2") is False
        assert c["A"] == "1"

    with sqlite_cache("example", db_path=str(db_path)) as c:
        assert c["A"] == "1"


def test_cache_helpers_are_still_importable_from_pioreactor_utils() -> None:
    assert exported_cache is sqlite_cache
    assert local_intermittent_storage.__name__ == "local_intermittent_storage"
    assert local_persistent_storage.__name__ == "local_persistent_storage"


def test_typed_cache_helpers_require_explicit_fallback(tmp_path: Path) -> None:
    db_path = tmp_path / "cache.sqlite"

    with sqlite_cache("example", db_path=str(db_path)) as c:
        c["float"] = "1.5"
        c["int"] = "2"
        c["true"] = "true"
        c["false"] = "false"

        assert c.getfloat("float") == 1.5
        assert c.getint("int") == 2
        assert c.getboolean("true") is True
        assert c.getboolean("false") is False

        assert c.getfloat("missing_float", fallback=3.5) == 3.5
        assert c.getint("missing_int", fallback=4) == 4
        assert c.getboolean("missing_bool", fallback=False) is False

        with pytest.raises(KeyError):
            c.getfloat("missing_float")

        with pytest.raises(KeyError):
            c.getint("missing_int")

        with pytest.raises(KeyError):
            c.getboolean("missing_bool")
