"""Start everything with one command: FalkorDB, demo data, the built UI and the API.

    python run.py                 # http://127.0.0.1:8000
    python run.py --reset         # reload the Northwind and Bluefin demo graphs first
    python run.py --open          # also open the browser

Steps, each skipped when already satisfied:
  1. FalkorDB reachable? If not and it is local, `docker compose up -d falkordb`.
  2. web/dist missing or older than web/src? `npm ci` (if needed) and `npm run build`.
  3. Demo graph empty (or --reset)? Load the synthetic datasets.
  4. Serve the API and the UI from one uvicorn process.
"""
from __future__ import annotations

import argparse
import os
import shutil
import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"
DIST = WEB / "dist" / "index.html"
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass


def step(msg: str) -> None:
    print(f"[retract] {msg}", flush=True)


def reachable(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=1.5):
            return True
    except OSError:
        return False


def ensure_falkordb(start_docker: bool) -> None:
    host, port = os.getenv("FALKORDB_HOST", "localhost"), int(os.getenv("FALKORDB_PORT", "6379"))
    if reachable(host, port):
        step(f"FalkorDB is up at {host}:{port}")
        return
    if not start_docker or host not in ("localhost", "127.0.0.1"):
        sys.exit(f"[retract] FalkorDB is not reachable at {host}:{port}")
    if not shutil.which("docker"):
        sys.exit("[retract] FalkorDB is not running and docker is not installed. "
                 "Start FalkorDB yourself or install Docker.")
    step("starting FalkorDB with docker compose")
    subprocess.run(["docker", "compose", "up", "-d", "falkordb"], cwd=ROOT, check=True)
    for _ in range(60):
        if reachable(host, port):
            step(f"FalkorDB is up at {host}:{port}")
            return
        time.sleep(1)
    sys.exit("[retract] FalkorDB container started but the port never opened")


def ui_stale() -> bool:
    if not DIST.exists():
        return True
    built = DIST.stat().st_mtime
    inputs = [WEB / "index.html", WEB / "package.json", WEB / "vite.config.ts", *(WEB / "src").rglob("*")]
    return any(p.is_file() and p.stat().st_mtime > built for p in inputs)


def ensure_ui() -> None:
    if not ui_stale():
        step("UI build is up to date")
        return
    npm = shutil.which("npm")
    if not npm:
        if DIST.exists():
            step("npm not found; serving the existing (older) UI build")
            return
        sys.exit("[retract] the UI is not built and npm is not installed. Install Node.js 20+.")
    if not (WEB / "node_modules").exists():
        step("installing UI dependencies (npm ci)")
        subprocess.run([npm, "ci", "--no-audit", "--no-fund"], cwd=WEB, check=True)
    step("building the UI (npm run build)")
    subprocess.run([npm, "run", "build"], cwd=WEB, check=True)


def ensure_data(reset: bool) -> None:
    from retract.db import graph

    try:
        n = graph("northwind").query("MATCH (n) RETURN count(n)").result_set[0][0]
    except Exception:
        n = 0
    if n and not reset:
        step(f"demo graph present ({n} nodes); use --reset to reload")
        return
    from data.load import load_all

    step("loading demo data (Northwind + Bluefin)")
    for r in load_all():
        step(f"  {r['tenant']}: {r['claim_status']}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=int(os.getenv("PORT", "8000")))
    ap.add_argument("--reset", action="store_true", help="reload the demo graphs")
    ap.add_argument("--open", action="store_true", help="open the browser")
    ap.add_argument("--no-build", action="store_true", help="never run npm")
    ap.add_argument("--no-docker", action="store_true", help="never start FalkorDB with docker")
    args = ap.parse_args()

    if reachable("127.0.0.1" if args.host == "0.0.0.0" else args.host, args.port):
        sys.exit(f"[retract] port {args.port} is already in use (an older server?). Stop it, or use --port {args.port + 1}")
    ensure_falkordb(start_docker=not args.no_docker)
    if not args.no_build:
        ensure_ui()
    ensure_data(args.reset)

    from retract import llm

    step(f"LLM: {llm.provider() if llm.available() else 'none (rule-based extraction and phrasing)'}")
    url = f"http://{'127.0.0.1' if args.host == '0.0.0.0' else args.host}:{args.port}"
    step(f"RETRACT is at {url}")
    if args.open:
        webbrowser.open(url)

    import uvicorn

    uvicorn.run("api.main:app", host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
