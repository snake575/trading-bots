import time

from trading_bots.bots import Bot


class Example(Bot):
    label = "Example"

    def _setup(self, config):
        self.work_time = config["work_time"]

    def _algorithm(self):
        self.log.info("This is an example bot")
        self.log.info(f"Doing work for {self.work_time} seconds...")
        time.sleep(self.work_time)
        self.log.info("Finished!")

    def _abort(self):
        self.log.warning("Exit!")
