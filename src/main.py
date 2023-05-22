import logging
import os
import sys
from dotenv import load_dotenv

try:
    import coloredlogs
    coloredlogs.install(level=logging.INFO)
except ModuleNotFoundError:
    pass

if __name__ == "__main__":
    logger = logging.getLogger(__name__)
    if sys.platform not in ("win32", "cygwin", "cli"):
        import uvloop
        uvloop.install()
        logger.info("UNIX platform detected, using uvloop for asyncio...")

    env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "secrets.env"))
    if not load_dotenv(dotenv_path=env_path):
        raise RuntimeError(f"Unable to load secrets.env file: {env_path}")

    from bot import start_bot
    start_bot()