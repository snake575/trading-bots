import os

import click

from trading_bots.bots import BotTask
from trading_bots.conf import defaults

from .templates import handle_template

# Parameters
bot_argument = click.argument("bot")

config_option = click.option(
    "--config",
    "-c",
    default=defaults.BOT_CONFIG,
    help="Specify your Bot's configuration filename (YAML format). "
    "By default, configuration files must be placed inside the Bot's 'configs/' folder. "
    f"Defaults to '{defaults.BOT_CONFIG}'.",
)

interval_option = click.option(
    "--interval",
    "-i",
    default=defaults.LOOP_INTERVAL,
    help="Loop interval (in seconds). " f"Defaults to {defaults.LOOP_INTERVAL}s",
)

settings_option = click.option(
    "--settings",
    help="Specify your global settings files (YAML format), "
    f"e.g '{defaults.SETTINGS}'.",
)


verbosity_option = click.option(
    "-v",
    "--verbosity",
    default=str(defaults.VERBOSITY),
    type=click.Choice(["0", "1", "2", "3"]),
    help="Verbosity level; 0=minimal output, 1=normal output, 2=verbose output, 3=very verbose output",
)


def print_banner():
    click.echo()
    click.echo("TRADING BOTS 🤖")
    click.echo("===============")
    click.echo()


def print_options(bot, config, settings):
    click.echo(f"Global settings")
    click.echo(f"- Settings files: {os.environ.get('SETTINGS', settings)}")
    click.echo()
    click.echo(f"Bot: {bot}")
    click.echo(f"- Config file: {config or 'default'}")


# CLI
@click.group()
def cli():
    print_banner()


@cli.command(short_help="Execute a bot's logic")
@bot_argument
@config_option
@settings_option
def run(bot, config, settings):
    """Run a specified BOT by label e.g. 'MyBot'"""
    print_options(bot, config, settings)
    click.echo()
    bot_task = BotTask(bot, config)
    bot_task.run_once()


@cli.command(short_help="Schedule a bot to run on an interval")
@bot_argument
@config_option
@interval_option
@settings_option
def loop(bot, config, interval, settings):
    """Schedule a BOT (by label) to run on an interval, e.g. 'MyBot -i 60'"""
    print_options(bot, config, settings)
    click.echo(f"- Interval: {interval}s")
    click.echo()
    bot_task = BotTask(bot, config)
    bot_task.run_loop(interval)


@cli.command(short_help="Execute a bot's abort command")
@bot_argument
@config_option
@settings_option
def abort(bot, config, settings):
    """Run the abort command of a specified BOT by label e.g. 'MyBot'"""
    print_options(bot, config, settings)
    click.echo()
    bot_task = BotTask(bot, config)
    bot_task.abort()


@cli.command(short_help="Creates a Trading-Bots project directory structure")
@click.option("--name", prompt=True, default="MyAwesomeProject")
@click.option("--directory", prompt=True, default=".")
@verbosity_option
def startproject(name, directory, verbosity):
    """
    Creates a Trading-Bots project directory structure for the given project
    NAME in the current directory or optionally in the given DIRECTORY.
    """
    handle_template("project", name, target=directory, verbosity=verbosity)
    click.echo(f"Success: '{name}' project was successfully created on '{directory}'")


@cli.command(short_help="Creates a Bot's directory structure")
@click.option("--name", prompt=True, default="MyAwesomeBot")
@click.option("--directory", prompt="Directory (your project's dir)")
@verbosity_option
def createbot(name, directory, verbosity):
    """
    Creates a Bot's directory structure for the given bot NAME in
    the current directory or optionally in the given DIRECTORY.
    """
    handle_template("bot", name, target=directory, verbosity=verbosity)
    click.echo(f"Success: '{name}' bot was successfully created on '{directory}'")
