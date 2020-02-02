import os
import unittest

from trading_bots.core.storage import *


class JSONStorageTest(unittest.TestCase):
    def setUp(self):
        self.filename = "test.json"
        self.types_dict = {
            "str": "a",
            "int": 1,
            "float": 1.0,
            "bool": True,
            "list": ["a", 1, 1.0, True],
            "test": "test",
        }
        self.sample_json = {
            **self.types_dict,
            "dict": {**self.types_dict},
        }
        with open(self.filename, "w") as outfile:
            j.dump(self.sample_json, outfile)

        self.store = JSONStore(self.filename)

    def tearDown(self):
        try:
            os.remove(self.filename)
        except OSError:
            pass

    def test_instantiate_bot(self):
        self.assertIsInstance(self.store, Store)

    # GET --------------------------------------------------------------------
    def test_get(self):
        for name, value in self.sample_json.items():
            stored_value = self.store.get(name)
            self.assertEqual(stored_value, value)

    def test_get_none(self):
        none_value = self.store.get("foo")
        self.assertIsNone(none_value)

    def test_hget(self):
        for key, value in self.sample_json["dict"].items():
            stored_value = self.store.hget("dict", key)
            self.assertEqual(stored_value, value)

    def test_hget_none(self):
        none_value = self.store.hget("dict", "foo")
        self.assertIsNone(none_value)

    # GET --------------------------------------------------------------------
    def test_set_add(self):
        self.store.set("foo", self.types_dict)
        stored_value = self.store.get("foo")
        self.assertDictEqual(stored_value, self.types_dict)

    def test_set_replace(self):
        self.store.set("test", self.types_dict)
        stored_value = self.store.get("test")
        self.assertDictEqual(stored_value, self.types_dict)

    def test_hset_add(self):
        self.store.hset("foo", "bar", self.types_dict)
        stored_value = self.store.hget("foo", "bar")
        self.assertDictEqual(stored_value, self.types_dict)

    def test_hset_replace(self):
        self.store.hset("test", "foo", self.types_dict)
        stored_value = self.store.hget("test", "foo")
        self.assertDictEqual(stored_value, self.types_dict)

    def test_hset_update(self):
        self.store.hset("dict", "test", "foo")
        stored_value = self.store.get("dict")
        self.assertDictEqual(stored_value, {**self.types_dict, "test": "foo"})

    # DEL --------------------------------------------------------------------
    def test_delete(self):
        self.store.delete("test")
        value = self.store.get("test")
        self.assertIsNone(value)

    def test_delete_none(self):
        self.store.delete("foo")
        value = self.store.get("foo")
        self.assertIsNone(value)

    def test_hdel(self):
        self.store.hdel("dict", "test")
        value = self.store.hget("dict", "test")
        self.assertIsNone(value)

    def test_hdel_none(self):
        self.store.hdel("foo", "bar")
        value = self.store.hget("foo", "bar")
        self.assertIsNone(value)
