import importlib

from qfluentwidgets import FluentIcon

from ok import ConfigOption, Logger
from ok.util.file import get_relative_path, read_json_file

logger = Logger.get_logger(__name__)

# Set on a task class once its post_init has been wrapped, so re-importing this module cannot nest wrappers.
HIDDEN_MARKER = "_ok_gf2_region_hidden"

REGION_CONFIG_NAME = "Region"
REGION_CONFIG_KEY = "Game Client"
REGION_GLOBAL = "Global"
REGION_CN = "CN"
REGION_DEFAULT = REGION_GLOBAL

# Module prefix of the CN task package. Anything registered from there belongs to the CN client.
CN_TASK_PREFIX = "src.tasks."

# Tasks that drive the Global client. They live in src/global/ and match English on-screen text
# directly instead of going through the reverse ocr.po translation.
GLOBAL_TASKS = [
    ["src.global.GlobalDailyTask", "GlobalDailyTask"],
    ["src.global.GlobalWeeklyTask", "GlobalWeeklyTask"],
]

region_option = ConfigOption(
    REGION_CONFIG_NAME,
    {REGION_CONFIG_KEY: REGION_DEFAULT},
    config_type={REGION_CONFIG_KEY: {"type": "drop_down", "options": [REGION_GLOBAL, REGION_CN]}},
    config_description={REGION_CONFIG_KEY: "Which game client to automate. Restart the app to apply."},
    icon=FluentIcon.GLOBE,
)


def current_region(config_folder="configs"):
    """Read the selected region straight off disk.

    The task list has to be built while `src/config.py` is still being imported, which is before the framework instantiates its own `Config` objects. Both
    paths resolve the same `Region.json`, so reading it directly here stays in sync with whatever the settings tab writes.

    Args:
        config_folder: Folder holding the config JSON files. Comes from the app config so it cannot drift from where the settings tab writes.

    Returns:
        Either `REGION_GLOBAL` or `REGION_CN`. Falls back to `REGION_DEFAULT` when the file is missing or holds an unknown value.
    """
    saved = read_json_file(get_relative_path(config_folder, f"{REGION_CONFIG_NAME}.json")) or {}
    region = saved.get(REGION_CONFIG_KEY, REGION_DEFAULT)
    return region if region in (REGION_GLOBAL, REGION_CN) else REGION_DEFAULT


def _hiding_post_init(original):
    """Wrap a task's `post_init` so the instance ends up hidden.

    Args:
        original: The `post_init` being replaced.

    Returns:
        A replacement `post_init` that runs `original` and then hides the instance.
    """

    def post_init(self):
        original(self)
        self.visible = False

    return post_init


def _hide_tasks(task_entries):
    """Keep the given task classes out of the sidebar.

    The framework builds every registered task and then filters the sidebar on each instance's `visible` attribute, so hiding has to happen per instance,
    after construction. A class attribute would not survive `BaseTask.__init__` setting `self.visible = True`, and `post_init` is the one hook that runs at
    the right moment. Patching it from here keeps the CN task files untouched, which matters because they are upstream's and get merged in regularly.

    Args:
        task_entries: `[module_path, class_name]` pairs to hide.
    """
    for module_path, class_name in task_entries:
        try:
            task_class = getattr(importlib.import_module(module_path), class_name)
        except (ImportError, AttributeError):
            logger.warning(f'could not hide {module_path}.{class_name}, it was registered but does not exist')
            continue
        if getattr(task_class, HIDDEN_MARKER, False):
            continue
        task_class.post_init = _hiding_post_init(task_class.post_init)
        setattr(task_class, HIDDEN_MARKER, True)


def apply_region(config):
    """Register the Region setting and hide whichever region's tasks are not selected.

    Global tasks are appended to whatever `src/config.py` already registered rather than replacing it. That keeps upstream as the single source of truth for
    its own task list, and it keeps every existing position stable - desktop shortcuts and Windows scheduled tasks store a positional index into this list
    ("-t N"), so reordering it would silently repoint them at the wrong task.

    Args:
        config: The app config dict from `src/config.py`, mutated in place.
    """
    config.setdefault("global_configs", []).append(region_option)
    registered = config["onetime_tasks"]
    cn_tasks = [entry for entry in registered if entry[0].startswith(CN_TASK_PREFIX)]
    config["onetime_tasks"] = registered + GLOBAL_TASKS
    _hide_tasks(cn_tasks if current_region(config.get("config_folder", "configs")) == REGION_GLOBAL else GLOBAL_TASKS)
