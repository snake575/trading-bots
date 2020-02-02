import simple_settings


class LazySettings(simple_settings.LazySettings):
    DEFAULT_SETTINGS = "trading_bots.conf.global_settings"
    ENVIRON_KEYS = ("settings", "SETTINGS")
    COMMAND_LINE_ARGS = ("--settings",)

    def __init__(self):
        settings_value = self._get_settings_value()
        settings_list = settings_value.split(",") if settings_value else {}
        super().__init__(self.DEFAULT_SETTINGS, *settings_list)


settings = LazySettings()
