import logging
import sys

# Configure a basic logger that outputs JSON-like logs for easier parsing.
logger = logging.getLogger("ai_interview_backend")
logger.setLevel(logging.INFO)

handler = logging.StreamHandler(sys.stdout)
formatter = logging.Formatter(
    '{"time": "%(asctime)s", "level": "%(levelname)s", "name": "%(name)s", "message": "%(message)s"}'
)
handler.setFormatter(formatter)
logger.addHandler(handler)
