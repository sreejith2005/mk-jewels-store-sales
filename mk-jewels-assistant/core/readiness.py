import threading

from core.logger import get_logger


logger = get_logger(__name__)
_ready = threading.Event()


def set_ready():
    _ready.set()
    logger.info("System ready - all models loaded")


def is_ready() -> bool:
    return _ready.is_set()


def wait_until_ready(timeout=300):
    return _ready.wait(timeout=timeout)
