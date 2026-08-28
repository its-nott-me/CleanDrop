import sys

from database import initialize_database
from scheduler import scheduler_loop


def main():
    print(
        "[CleanDrop] Scheduler started",
        file=sys.stderr
    )

    initialize_database()

    scheduler_loop()


if __name__ == "__main__":
    main()