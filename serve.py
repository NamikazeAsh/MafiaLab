from __future__ import annotations

import argparse
import sys
import webbrowser

from mafia.setup import load_env
from mafia.web.runner import GameRunner
from mafia.web.server import create_server


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    load_env()
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--log-dir", default="logs")
    ap.add_argument("--open", action="store_true", help="open the browser")
    args = ap.parse_args()

    runner = GameRunner(args.log_dir)
    server = create_server(runner, args.log_dir, args.port)
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    print(f"Mafia viewer running at {url}  (Ctrl+C to stop)", flush=True)
    if args.open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        runner.stop()
        print("\nBye.")


if __name__ == "__main__":
    main()
