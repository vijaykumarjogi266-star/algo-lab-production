import re

with open("live_market_daemon.py", "r") as f:
    content = f.read()

# Add lock mechanism in main
main_block_old = """
def main():
    parser = argparse.ArgumentParser(description="Algo Lab EOD Live Market Daemon")
"""

main_block_new = """
import fcntl
import sys

def acquire_lock(lockfile="/tmp/algolab_daemon.lock"):
    lock_fd = open(lockfile, 'w')
    try:
        fcntl.lockf(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return lock_fd
    except IOError:
        print("[ERROR] Another instance of the daemon is already running. Exiting.")
        sys.exit(1)

def main():
    _lock = acquire_lock()
    parser = argparse.ArgumentParser(description="Algo Lab EOD Live Market Daemon")
"""

if "import fcntl" not in content:
    content = content.replace(main_block_old, main_block_new)

with open("live_market_daemon.py", "w") as f:
    f.write(content)
