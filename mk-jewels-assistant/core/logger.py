import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
LOG_DIR = Path("logs")
LOG_FILE = LOG_DIR / "app.log"


def _configure_logging() -> None:
    LOG_DIR.mkdir(exist_ok=True)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    formatter = logging.Formatter(LOG_FORMAT)

    if not any(
        isinstance(handler, RotatingFileHandler)
        and Path(handler.baseFilename) == LOG_FILE.resolve()
        for handler in root_logger.handlers
    ):
        file_handler = RotatingFileHandler(
            LOG_FILE,
            maxBytes=5_000_000,
            backupCount=3,
        )
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    if not any(type(handler) is logging.StreamHandler for handler in root_logger.handlers):
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        root_logger.addHandler(stream_handler)


def get_logger(name: str) -> logging.Logger:
    _configure_logging()
    return logging.getLogger(name)
