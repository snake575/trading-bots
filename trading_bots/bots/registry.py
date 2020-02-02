import os
import sys
import threading
from collections import Counter, OrderedDict, defaultdict
from importlib import import_module
from os import path

from ..conf import defaults
from ..core.exceptions import AppRegistryNotReady, ImproperlyConfigured
from ..core.utils import load_class_by_name, load_yaml_file
from .base import Bot

# The file extension(s) to import as configs
config_extensions = ("py", "yml")


class BotRegistry:
    """Class representing a Bot and its configuration files."""

    def __init__(self, bot_name, bot_module, label=None):
        # Full Python path to the bot class e.g. 'trading_bots.bots.Bot'.
        self.name = bot_name

        # Root module for the bot e.g. <module 'trading_bots.bots'
        # from 'trading_bots/bots/__init__.py'>.
        self.module = bot_module

        # Bot class for the bot
        self.cls = load_class_by_name(bot_name)

        # Reference to the Bots registry that holds this BotRegistry. Set by the
        # registry when it registers the BotRegistry instance.
        self.bots = None

        # Last component of the Python path to the bot class e.g. 'Bot'.
        # This value must be unique across a project.
        self.label = label or bot_name.rpartition(".")[-1]

        # Filesystem path to the bot directory e.g.
        # '/path/to/trading_bots/bots'.
        self.path = self._path_from_module(bot_module)

        # Filesystem path containing configs e.g. '/path/to/trading_bots/bots'.
        # Set by import_configs().
        # None if the bot doesn't have a configs dir.
        self.configs_path = None

        # Mapping of lower case config file names to config files. Initially set to
        # None to prevent accidental access before import_configs() runs.
        self.configs = OrderedDict()

    def __repr__(self):
        return "<%s: %s>" % (self.__class__.__name__, self.label)

    @staticmethod
    def _path_from_module(module):
        """Attempt to determine bot's filesystem path from its module."""
        # Convert paths to list because Python's _NamespacePath doesn't support
        # indexing.
        paths = list(getattr(module, "__path__", []))
        if len(paths) != 1:
            filename = getattr(module, "__file__", None)
            if filename is not None:
                paths = [os.path.dirname(filename)]
            else:
                # For unknown reasons, sometimes the list returned by __path__
                # contains duplicates that must be removed.
                paths = list(set(paths))
        if len(paths) > 1:
            raise ImproperlyConfigured(
                "The bot module %r has multiple filesystem locations (%r); "
                "you must configure this bot with an AppConfig subclass "
                "with a 'path' class attribute." % (module, paths)
            )
        elif not paths:
            raise ImproperlyConfigured(
                "The bot module %r has no filesystem location, "
                "you must configure this bot with an AppConfig subclass "
                "with a 'path' class attribute." % (module,)
            )
        return paths[0]

    @classmethod
    def create(cls, entry):
        """
        Factory that creates an bot config from an entry in INSTALLED_APPS.
        """
        # trading_bots.example.bot.ExampleBot
        try:
            # If import_module succeeds, entry is a path to a bot module,
            # which may specify a bot class with a default_bot attribute.
            # Otherwise, entry is a path to a bot class or an error.
            module = import_module(entry)

        except ImportError:
            # Track that importing as a bot module failed. If importing as a
            # bot class fails too, we'll trigger the ImportError again.
            module = None

            mod_path, _, cls_name = entry.rpartition(".")

            # Raise the original exception when entry cannot be a path to an
            # bot config class.
            if not mod_path:
                raise

        else:
            try:
                # If this works, the bot module specifies a bot class.
                entry = module.default_bot
            except AttributeError:
                # Otherwise, it simply uses the default bot registry class.
                return cls(f"{entry}.Bot", module)
            else:
                mod_path, _, cls_name = entry.rpartition(".")

        # If we're reaching this point, we must attempt to load the bot
        # class located at <mod_path>.<cls_name>
        mod = import_module(mod_path)
        try:
            bot_cls = getattr(mod, cls_name)
        except AttributeError:
            if module is None:
                # If importing as an bot module failed, that error probably
                # contains the most informative traceback. Trigger it again.
                import_module(entry)
            raise

        # Check for obvious errors. (This check prevents duck typing, but
        # it could be removed if it became a problem in practice.)
        if not issubclass(bot_cls, Bot):
            raise ImproperlyConfigured("'%s' isn't a subclass of Bot." % entry)

        # Entry is a path to an bot config class.
        return cls(entry, mod, bot_cls.label)

    def get_config(self, config_name, require_ready=True):
        """
        Return the config with the given case-insensitive config_name.
        Raise LookupError if no config exists with this name.
        """
        if require_ready:
            self.bots.check_configs_ready()
        else:
            self.bots.check_bots_ready()

        return self.configs.get(config_name.lower(), {})

    def get_configs(self):
        """
        Return an iterable of models.
        """
        self.bots.check_models_ready()
        for config in self.configs.values():
            yield config

    def import_configs(self):
        self.configs_path = os.path.join(self.path, defaults.CONFIGS_DIR_NAME)
        for root, _dirs, files in os.walk(self.configs_path):
            for filename in files:
                file_path = path.join(root, filename)
                if file_path.endswith(config_extensions):
                    config = load_yaml_file(file_path)
                    config_name = path.splitext(filename)[0]
                    self.configs[config_name] = config
                    bots.register_config(self.label, config_name, config)


class Bots:
    """
    A registry that stores the installed bots.
    """

    def __init__(self, installed_bots=()):
        # installed_bots is set to None when creating the master registry
        # because it cannot be populated at that point. Other registries must
        # provide a list of installed bots and are populated immediately.
        if installed_bots is None and hasattr(sys.modules[__name__], "bots"):
            raise RuntimeError("You must supply an installed_bots argument.")

        # Mapping of bot labels => config names => config files.
        self.all_configs = defaultdict(OrderedDict)

        # Mapping of labels to Bot instances for installed bots.
        self.bots = OrderedDict()

        # Whether the registry is populated.
        self.bots_ready = self.configs_ready = self.ready = False

        # Lock for thread-safe population.
        self._lock = threading.RLock()
        self.loading = False

        # Populate bots and models, unless it's the master registry.
        if installed_bots is not None:
            self.populate(installed_bots)

    def populate(self, installed_bots=None):
        """
        Load bots.
        Import each bot module.
        It is thread-safe and idempotent, but not re-entrant.
        """
        if self.ready:
            return

        # populate() might be called by two threads in parallel on servers
        # that create threads before initializing the WSGI callable.
        with self._lock:
            if self.ready:
                return

            # An RLock prevents other threads from entering this section. The
            # compare and set operation below is atomic.
            if self.loading:
                # Prevent re-entrant calls to avoid running AppConfig.ready()
                # methods twice.
                raise RuntimeError("populate() isn't re-entrant")
            self.loading = True

            # Phase 1: Initialize bots
            for entry in installed_bots or {}:
                if isinstance(entry, Bot):
                    cls = entry
                    entry = ".".join([cls.__module__, cls.__name__])
                bot_reg = BotRegistry.create(entry)
                if bot_reg.label in self.bots:
                    raise ImproperlyConfigured(
                        "Bot labels aren't unique, " "duplicates: %s" % bot_reg.label
                    )

                self.bots[bot_reg.label] = bot_reg
                bot_reg.bots = self

            # Check for duplicate bot names.
            counts = Counter(bot_reg.name for bot_reg in self.bots.values())
            duplicates = [name for name, count in counts.most_common() if count > 1]
            if duplicates:
                raise ImproperlyConfigured(
                    "Bot names aren't unique, " "duplicates: %s" % ", ".join(duplicates)
                )

            self.bots_ready = True

            # Phase 2: import config files
            for bot in self.bots.values():
                bot.import_configs()

            self.configs_ready = True

            self.ready = True

    def check_bots_ready(self):
        """Raise an exception if all bots haven't been imported yet."""
        if not self.bots_ready:
            raise AppRegistryNotReady("Bots aren't loaded yet.")

    def check_configs_ready(self):
        """Raise an exception if all models haven't been imported yet."""
        if not self.configs_ready:
            raise AppRegistryNotReady("Configs aren't loaded yet.")

    def get_bots(self):
        """Import all bots and return an iterable of bot classes."""
        self.check_bots_ready()
        return self.bots.values()

    def get_bot(self, bot_label):
        """
        Import all bots and returns a bot class for the given label.
        Raise LookupError if no bot exists with this label.
        """
        self.check_bots_ready()
        try:
            return self.bots[bot_label]
        except KeyError:
            message = "No installed bot with label '%s'." % bot_label
            for bot_cls in self.get_bots():
                if bot_cls.name == bot_label:
                    message += " Did you mean '%s'?" % bot_cls.label
                    break
            raise LookupError(message)

    def get_configs(self):
        """
        Return a list of all installed configs.
        """
        self.check_configs_ready()

        result = []
        for bot in self.bots.values():
            result.extend(list(bot.get_models()))
        return result

    def get_config(self, bot_label, config_name=None, require_ready=True):
        """
        Return the config matching the given bot_label and config_name.
        config_name is case-insensitive.
        Raise LookupError if no bot exists with this label, or no config
        exists with this name in the bot. Raise ValueError if called with a
        single argument that doesn't contain exactly one dot.
        """
        if require_ready:
            self.check_configs_ready()
        else:
            self.check_bots_ready()

        if config_name is None:
            config_name = defaults.BOT_CONFIG

        bot = self.get_bot(bot_label)

        if not require_ready and bot.configs is None:
            bot.import_configs()

        return bot.get_config(config_name, require_ready=require_ready)

    def register_config(self, bot_label, config_name, config):
        # Since this method is called when models are imported, it cannot
        # perform imports because of the risk of import loops. It mustn't
        # call get_bot().
        bot_configs = self.all_configs[bot_label]
        bot_configs[config_name] = config

    def is_installed(self, bot_name):
        """
        Check whether a bot with this name exists in the registry.
        bot_name is the full name of the bot e.g. 'trading_bots.core.bot'.
        """
        self.check_bots_ready()
        return any(b.name == bot_name for b in self.bots.values())


bots = Bots(installed_bots=None)
