import asyncio
import socket
import subprocess
import time
from pathlib import Path

from capture.mic_capture import MicCapture
from config import Config
from pipeline.session import FileSession, Session


APP_DIR = Path(__file__).parent


def _get_lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def main():
    run_mode = input(
        "Run mode: (1) Live mic  (2) Test with audio file  (3) Start dashboard server  (4) Generate end-of-day report  (5) Start live phone capture: "
    ).strip()

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
