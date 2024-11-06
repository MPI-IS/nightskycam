from typing import Callable, Optional

from nightskycam_focus import adapter
from nightskyrunner.config import Config

_adapter_initialized: bool = False


def _configured(config: Config, key: str) -> bool:
    if key not in config.keys():
        return False
    if str(config[key]) in ("None", ""):
        return False
    return True


def focus_configured(config: Config) -> bool:
    return _configured(config, "focus")


def aperture_configured(config: Config, active: bool) -> bool:
    if active:
        return _configured(config, "active_aperture")
    else:
        return _configured(config, "inactive_aperture")


def _set(
    config: Config, f: Callable[[int], None], key: str, first_attempt: bool
) -> None:
    global _adapter_initialized
    if not _adapter_initialized:
        adapter.init_adapter()
        _adapter_initialized = True
    try:
        f(int(config[key]))  # type: ignore
    except Exception as e:
        if first_attempt:
            adapter.idle_adapter()
            _adapter_initialized = False
            _set(config, f, key, False)
        else:
            raise e


def set_focus(config: Config) -> Optional[str]:
    try:
        _set(config, adapter.set_focus, "focus", True)
    except Exception as e:
        return str(e)
    return None


def set_aperture(config: Config, active: bool) -> Optional[str]:
    try:
        _set(
            config,
            adapter.set_aperture,
            "active_aperture" if active else "inactive_aperture",
            True,
        )
    except Exception as e:
        return str(e)
    return None
