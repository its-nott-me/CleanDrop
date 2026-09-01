import sys
import threading

from database import initialize_database
from scheduler import scheduler_loop, ai_loop


def main():
    print(
        "[CleanDrop] Scheduler started",
        file=sys.stderr
    )

    initialize_database()

    ai_thread = threading.Thread(
        target=ai_loop,
        daemon=True
    )

    ai_thread.start()

    scheduler_loop()


if __name__ == "__main__":
    main()