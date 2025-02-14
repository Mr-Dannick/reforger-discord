import logging
from logging.handlers import RotatingFileHandler
import config

# Set up logging
logger = logging.getLogger('TMuxBot')
logger.setLevel(logging.INFO)
handler = RotatingFileHandler(config.LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=5)  # 5MB per file, keep 5 files
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)
