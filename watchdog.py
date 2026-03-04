import subprocess
import time
import logging
import sys
import os

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | WATCHDOG | %(message)s",
)

ENGINE_FILE = "run_live.py"
RESTART_DELAY = 5


def run_engine():

    while True:

        # Respect kill switch
        if os.path.exists("kill.switch"):
            logging.warning("Kill switch detected. Watchdog stopping.")
            break

        logging.info("Starting trading engine...")

        try:

            process = subprocess.Popen(
                [sys.executable, ENGINE_FILE]
            )

            process.wait()

            if os.path.exists("kill.switch"):
                logging.warning("Engine stopped due to kill switch.")
                break

            logging.warning("Engine stopped unexpectedly.")

        except Exception as e:

            logging.error(f"Engine crash detected: {e}")

        logging.info(f"Restarting in {RESTART_DELAY} seconds...")

        time.sleep(RESTART_DELAY)


if __name__ == "__main__":

    run_engine()