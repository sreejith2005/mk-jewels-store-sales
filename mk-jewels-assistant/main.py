import asyncio
import socket
import sys
import time

from capture.mic_capture import MicCapture
from config import Config
from pipeline.session import FileSession, Session


def main():
    run_mode = input(
        "Run mode: (1) Live mic  (2) Test with audio file  (3) Start dashboard server  (4) Generate end-of-day report  (5) Start live phone capture: "
    ).strip()

    if run_mode == "3":
        from dashboard.server import app

        app.run(port=5000)
        return

    if not Config.GEMINI_API_KEY:
        print(
            "Error: GEMINI_API_KEY is not set. Add it to your environment or .env file.",
            file=sys.stderr,
        )
        sys.exit(1)

    if run_mode == "5":
        asyncio.run(start_live_phone_capture())
        return

    if run_mode == "4":
        from reports.daily_report import generate_daily_report

        generate_daily_report()
        return

    if run_mode == "2":
        wav_file_path = input("Enter WAV file path: ").strip().strip('"')
        salesperson_name = input("Enter salesperson name: ").strip()
        session = FileSession(
            wav_file_path=wav_file_path,
            salesperson_name=salesperson_name,
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

    local_ip = socket.gethostbyname(socket.gethostname())
    print(f"Open this URL on your phone: http://{local_ip}:5000/recorder?name=YourName")

    websocket_server = WebSocketAudioServer()
    flask_server = asyncio.to_thread(
        app.run,
        host="0.0.0.0",
        port=5000,
        use_reloader=False,
    )

    await asyncio.gather(websocket_server.start(), flask_server)


if __name__ == "__main__":
    main()
