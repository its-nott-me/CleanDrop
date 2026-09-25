import sys
import threading

from database import initialize_database
from scheduler import scheduler_loop, llm_watchdog_loop


def main():
    print(
        "[CleanDrop] Scheduler started",
        file=sys.stderr
    )

    initialize_database()

    watchdog_thread = threading.Thread(
        target=llm_watchdog_loop,
        daemon=True
    )

    watchdog_thread.start()

    scheduler_loop()


if __name__ == "__main__":
    main()