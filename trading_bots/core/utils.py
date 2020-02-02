import codecs
import importlib

import yaml


def load_class_by_name(name: str):
    """Given a dotted path, returns the class"""
    mod_path, _, cls_name = name.rpartition(".")
    mod = importlib.import_module(mod_path)
    cls = getattr(mod, cls_name)
    return cls


def load_yaml_file(file_path: str):
    """Load a YAML file from path"""
    with codecs.open(file_path, "r") as f:
        return yaml.safe_load(f)
