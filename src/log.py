import logging
from config import CONFIG_YAML

log_level = CONFIG_YAML["LOGGER"]["level"]
log_file = CONFIG_YAML["LOGGER"]["dir"] + CONFIG_YAML["LOGGER"]["file"]

handler = logging.FileHandler(log_file)
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
handler.setFormatter(formatter)

logger = logging.getLogger("info_logger")
logger.handlers.clear()
logger.propagate = False
logger.setLevel(log_level)
logger.addHandler(handler)