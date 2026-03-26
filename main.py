import logging

from hsc_tracker.config import load_config
from hsc_tracker.logging_setup import configure_logging
from hsc_tracker.monitor import HSCTrackerService

logger = logging.getLogger(__name__)


def main() -> None:
    configure_logging()
    config = load_config()
    service = HSCTrackerService(config)
    try:
        service.run_forever()
    except KeyboardInterrupt:
        logger.info("Interrupted by user; exiting")


if __name__ == "__main__":
    main()
