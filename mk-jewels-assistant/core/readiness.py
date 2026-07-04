import threading

from core.logger import get_logger


logger = get_logger(__name__)
_ready = threading.Event()
MODELS_READY = False


def set_ready():
    global MODELS_READY
    MODELS_READY = True
    _ready.set()
    logger.info("System ready - all models loaded")


def set_not_ready():
    global MODELS_READY
    MODELS_READY = False
    _ready.clear()


def is_ready() -> bool:
    return MODELS_READY and _ready.is_set()


def wait_until_ready(timeout=300):
    return _ready.wait(timeout=timeout)
