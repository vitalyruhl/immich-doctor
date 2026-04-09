from __future__ import annotations

import logging


def configure_logging() -> None:
    logger = logging.getLogger("immich_doctor")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("%(levelname)s %(name)s: %(message)s")
        )
        logger.addHandler(handler)
    logger.propagate = False
