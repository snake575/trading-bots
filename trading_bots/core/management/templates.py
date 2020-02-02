import os
import shutil
import stat
from importlib import import_module
from os import path

import click
import stringcase
from jinja2 import Template

import trading_bots
from trading_bots.conf import defaults, settings

# Rewrite the following suffixes when determining the target filename.
rewrite_template_suffixes = (
    # Allow shipping invalid .py files without byte-compilation.
    (".py.jinja2", ".py"),
)
# The file extension(s) to render
extensions = ("py", "yml")


def handle_template(bot_or_project, name, target=None, **options):
    """
    Copy either a bot layout template or a Trading-Bots project
    layout template into the specified directory.
    :param bot_or_project: The string 'bot' or 'project'.
    :param name: The name of the bot or project.
    :param target: The directory to which the template should be copied.
    :param options: The additional variables passed to project or bot templates
    """
    bot_or_project = bot_or_project
    paths_to_remove = []
    verbosity = int(options["verbosity"])

    validate_name(name, bot_or_project)

    # if some directory is given, make sure it's nicely expanded
    if target is None:
        top_dir = path.join(os.getcwd(), name)
        try:
            os.makedirs(top_dir)
        except FileExistsError:
            raise click.ClickException("'%s' already exists" % top_dir)
        except OSError as e:
            raise click.ClickException(e)
    else:
        top_dir = os.path.abspath(path.expanduser(target))
        if not os.path.exists(top_dir):
            raise click.ClickException(
                "Destination directory '%s' does not "
                "exist, please create it first." % top_dir
            )

    base_name = "%s_name" % bot_or_project
    base_subdir = "%s_template" % bot_or_project
    base_directory = "%s_directory" % bot_or_project
    target_name = "%s_target" % bot_or_project
    pascal_case_name = "pascal_case_%s_name" % bot_or_project
    pascal_case_value = stringcase.pascalcase(name)
    snake_case_name = "snake_case_%s_name" % bot_or_project
    snake_case_value = stringcase.snakecase(name)

    context = {
        **options,
        base_name: name,
        base_directory: top_dir,
        target_name: target,
        pascal_case_name: pascal_case_value,
        snake_case_name: snake_case_value,
        "settings_files": defaults.SETTINGS,
        "version": trading_bots.__version__.__version__,
    }

    # Setup a stub settings environment for template rendering
    settings.configure()
    trading_bots.setup()

    template_dir = path.join(trading_bots.__path__[0], "conf", base_subdir)
    prefix_length = len(template_dir) + 1

    for root, dirs, files in os.walk(template_dir):

        path_rest = root[prefix_length:]
        relative_dir = path_rest.replace(snake_case_name, snake_case_value)
        if relative_dir:
            target_dir = path.join(top_dir, relative_dir)
            if not path.exists(target_dir):
                os.mkdir(target_dir)

        for dirname in dirs[:]:
            if dirname.startswith(".") or dirname == "__pycache__":
                dirs.remove(dirname)

        for filename in files:
            if filename.endswith((".pyo", ".pyc", ".py.class")):
                # Ignore some files as they cause various breakages.
                continue
            old_path = path.join(root, filename)
            new_path = path.join(
                top_dir,
                relative_dir,
                filename.replace(snake_case_name, snake_case_value),
            )
            for old_suffix, new_suffix in rewrite_template_suffixes:
                if new_path.endswith(old_suffix):
                    new_path = new_path[: -len(old_suffix)] + new_suffix
                    break  # Only rewrite once

            if path.exists(new_path):
                raise click.ClickException(
                    "%s already exists, overlaying a "
                    "project or bot into an existing "
                    "directory won't replace conflicting "
                    "files" % new_path
                )

            # Only render the Python files, as we don't want to
            # accidentally render Trading-Bots templates files
            if new_path.endswith(extensions):
                with open(old_path, "r", encoding="utf-8") as template_file:
                    content = template_file.read()
                template = Template(content, keep_trailing_newline=True)
                content = template.render(**context)
                with open(new_path, "w", encoding="utf-8") as new_file:
                    new_file.write(content)
            else:
                shutil.copyfile(old_path, new_path)

            if verbosity >= 2:
                click.echo("Creating %s\n" % new_path)
            try:
                shutil.copymode(old_path, new_path)
                make_writeable(new_path)
            except OSError:
                click.echo(
                    "Notice: Couldn't set permission bits on %s. You're "
                    "probably using an uncommon filesystem setup. No "
                    "problem." % new_path
                )

    if paths_to_remove:
        if verbosity >= 2:
            click.echo("Cleaning up temporary files.\n")
        for path_to_remove in paths_to_remove:
            if path.isfile(path_to_remove):
                os.remove(path_to_remove)
            else:
                shutil.rmtree(path_to_remove)


def validate_name(name, bot_or_project):
    a_or_an = "an" if bot_or_project == "bot" else "a"
    if name is None:
        raise click.ClickException(
            "you must provide {an} {bot} name".format(an=a_or_an, bot=bot_or_project)
        )
    # Check it's a valid directory name.
    if not name.isidentifier():
        raise click.ClickException(
            "'{name}' is not a valid {bot} name. Please make sure the "
            "name is a valid identifier.".format(name=name, bot=bot_or_project)
        )
    # Check it cannot be imported.
    try:
        import_module(name)
    except ImportError:
        pass
    else:
        raise click.ClickException(
            "'{name}' conflicts with the name of an existing Python "
            "module and cannot be used as {an} {bot} name. Please try "
            "another name.".format(name=name, an=a_or_an, bot=bot_or_project)
        )


def make_writeable(filename):
    """
    Make sure that the file is writeable.
    Useful if our source is read-only.
    """
    if not os.access(filename, os.W_OK):
        st = os.stat(filename)
        new_permissions = stat.S_IMODE(st.st_mode) | stat.S_IWUSR
        os.chmod(filename, new_permissions)
