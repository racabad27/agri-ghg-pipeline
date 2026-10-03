import logging

LOG_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"


def setup_logging(level: int = logging.INFO) -> None:
    """Print log messages to the terminal."""
    logging.basicConfig(level=level, format=LOG_FORMAT)


def get_logger(name: str) -> logging.Logger:
    """Return a logger named 'agri.<name>' so our messages are easy to find in logs."""
    return logging.getLogger(f"agri.{name}")