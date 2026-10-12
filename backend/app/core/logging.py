import logging
import sys

def setup_logging(level: str = "INFO") -> None:
    """Configures structured, clean logging for PayTrace backend."""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True,
    )
