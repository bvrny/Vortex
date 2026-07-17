"""Run the simulator on a pty: `python -m simulator [--params FILE]`.

Prints the slave device path (e.g. /dev/pts/5); point the desktop app at it.
"""

import argparse
import os
import pty
from pathlib import Path

from simulator import SimDevice
from simulator.transport import serve


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--params", type=Path, default=None,
                    help="JSON file for PARAM_SAVE/PARAM_LOAD persistence")
    args = ap.parse_args()
    master, slave = pty.openpty()
    print(os.ttyname(slave), flush=True)
    serve(master, SimDevice(param_file=args.params))


if __name__ == "__main__":
    main()
