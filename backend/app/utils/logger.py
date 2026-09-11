import logging
import sys
from pathlib import Path
from app.config import settings

LOG_DIR = settings.DATA_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)


def get_logger(name: str = "quant") -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.DEBUG if settings.DEBUG else logging.INFO)

        fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(fmt)
        logger.addHandler(sh)

        try:
            fh = logging.FileHandler(LOG_DIR / "app.log", encoding="utf-8")
            fh.setFormatter(fmt)
            logger.addHandler(fh)
        except Exception:
            pass

        logger.propagate = False
    return logger


logger = get_logger()
