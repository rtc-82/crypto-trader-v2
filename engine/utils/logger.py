import logging
import logging.handlers
import os


def setup_logger(
    name: str = "trading_engine",
    log_file: str = "logs/engine.log",
    level: int = logging.INFO,
) -> logging.Logger:
    """
    Configure and return the main trading engine logger.

    Features
    --------
    • Rotating log files
    • Console + file logging
    • Safe handler initialization
    • UTF-8 encoding (important on Windows)
    • Prevent duplicate handlers
    """

    os.makedirs(os.path.dirname(log_file), exist_ok=True)

    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = False

    # Prevent duplicate handlers on reload
    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Rotating file handler (10MB x 5 files)
    file_handler = logging.handlers.RotatingFileHandler(
        filename=log_file,
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )

    file_handler.setFormatter(formatter)
    file_handler.setLevel(level)

    # Console output
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(level)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    logger.info("Logger initialized")

    return logger