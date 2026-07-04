import asyncio
import argparse
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

from capture.mic_capture import MicCapture
from config import Config
from core.logger import get_logger
from pipeline.session import FileSession, Session


APP_DIR = Path(__file__).parent
logger = get_logger(__name__)
RUN_MODE_PROMPT = (
    "Run mode: (1) Live mic  (2) Test with audio file  "
    "(3) Start dashboard server  (4) Generate end-of-day report  "
    "(5) Start live phone capture: "
)


def _get_lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def resolve_run_mode(
    argv: list[str] | None = None,
    environ: dict[str, str] | None = None,
) -> str:
    """Resolve run mode from CLI, environment, or the interactive prompt."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", help="Run mode: 1, 2, 3, 4, or 5")
    args = parser.parse_args(argv)

    if args.mode is not None:
        return args.mode.strip()

    environment = os.environ if environ is None else environ
    env_mode = environment.get("RUN_MODE")
    if env_mode is not None:
        return env_mode.strip()

    return input(RUN_MODE_PROMPT).strip()


def main(argv: list[str] | None = None):
    Config.validate_pipeline()

    run_mode = resolve_run_mode(argv)

    if run_mode == "3":
        if Config.PIPELINE_MODE == "demo":
            from dashboard.server import app

            print("Starting dashboard server in demo mode using Flask's built-in server.")
            app.run(port=Config.FLASK_PORT, debug=False)
        else:
            print("Starting dashboard server in production mode using Gunicorn.")
            subprocess.Popen(
                [
                    "gunicorn",
                    "-c",
                    "dashboard/gunicorn_config.py",
                    "dashboard.server:app",
                ],
                cwd=APP_DIR,
            )
        return

    Config.validate()

    if run_mode in {"1", "2", "5"}:
        from core.readiness import set_not_ready, set_ready, wait_until_ready
        from transcription.local_pipeline import load_models

        logger.info("Loading models - server will not accept connections until ready")
        success = load_models()
        if not success:
            set_not_ready()
            logger.critical(
                "Model warmup check failed - aborting startup instead of serving half-loaded."
            )
            raise RuntimeError("Model warmup failed")
        set_ready()
        wait_until_ready(timeout=0)
        logger.info("All models loaded - starting servers")

    if run_mode == "5":
        asyncio.run(start_live_phone_capture())
        return

    if run_mode == "4":
        from reports.daily_report import generate_daily_report

        generate_daily_report()
        return

    if run_mode == "2":
        wav_file_path = input("Enter WAV file path: ").strip().strip('"')
        simulate_realtime_input = input(
            "Simulate real-time delays? (y/n, default n):"
        ).strip().lower()
        salesperson_name = input("Enter salesperson name: ").strip()
        session = FileSession(
            wav_file_path=wav_file_path,
            salesperson_name=salesperson_name,
            simulate_realtime=simulate_realtime_input == "y",
        )
    else:
        print("Available microphones:")
        MicCapture.list_devices()

        device_index = int(input("Enter device index: ").strip())
        salesperson_name = input("Enter salesperson name: ").strip()

        session = Session(
            salesperson_name=salesperson_name,
            device_index=device_index,
        )

    session.start()
    try:
        while session._thread and session._thread.is_alive():
            print("Running... press Ctrl+C to stop")
            time.sleep(10)
    except KeyboardInterrupt:
        pass
    finally:
        session.stop()
        print(f"Session ended. Events logged: {len(session.events)}")


async def start_live_phone_capture():
    from capture.ws_receiver import WebSocketAudioServer
    from dashboard.server import app
    from scheduler import start_scheduler, stop_scheduler

    local_ip = _get_lan_ip()
    print(
        f"Open this URL on your phone: "
        f"http://{local_ip}:{Config.FLASK_PORT}/recorder?name=YourName"
    )

    websocket_server = WebSocketAudioServer()
    flask_server = asyncio.to_thread(
        app.run,
        host="0.0.0.0",  # binds all interfaces for LAN access.
        port=Config.FLASK_PORT,
        use_reloader=False,
    )

    scheduler = start_scheduler()
    try:
        await asyncio.gather(websocket_server.start(), flask_server)
    finally:
        stop_scheduler(scheduler)


if __name__ == "__main__":
    main()
