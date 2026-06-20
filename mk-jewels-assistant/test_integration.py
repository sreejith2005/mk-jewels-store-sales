import os
import sys
import time

# Ensure we can import from mk-jewels-assistant modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from pipeline.session import FileSession
from config import Config

def run_integration_test():
    wav_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "test_clip.wav")
    if not os.path.exists(wav_file):
        print(f"FAIL: WAV file not found at {wav_file}")
        return

    print("Starting integration test with real Gemini API...")
    session = FileSession(
        wav_file_path=wav_file,
        salesperson_name="demo_salesperson"
    )
    
    session.start()
    
    # Wait for the session thread to complete (join with 120 second timeout)
    if session._thread:
        session._thread.join(timeout=120)
        if session._thread.is_alive():
            print("FAIL: Session thread did not complete within 120 seconds timeout.")
            session.stop()
            return
            
    try:
        # Assertions
        assert len(session.events) > 0, "No events were generated."
        
        assert len(session.transcript_log) == len(session.events), "transcript_log length does not match events length."
        
        required_keys = [
            "transcript", "objection_detected", "price_concern", 
            "certification_question", "upsell_miss", "knowledge_gap", 
            "intent_signal", "alert_priority", "reasoning"
        ]
        
        for idx, event in enumerate(session.events):
            missing_keys = [key for key in required_keys if key not in event]
            assert not missing_keys, f"Event at index {idx} is missing keys: {missing_keys}"
            
        db_path = Config.DB_PATH
        if not os.path.isabs(db_path):
            # db.py uses os.path.abspath(self.db_path), which resolves based on cwd.
            db_path = os.path.abspath(db_path)
            
        assert os.path.exists(db_path), f"SQLite DB file does not exist at {db_path}"
        
        db_events = session.db.get_session_events(session.session_id)
        assert len(db_events) == len(session.events), f"DB returned {len(db_events)} events, but session has {len(session.events)} events."
        
        print(f"PASS: Integration test completed successfully. Event count: {len(session.events)}")
        
    except AssertionError as e:
        print(f"FAIL: {e}")
    except Exception as e:
        print(f"FAIL: Unexpected error occurred: {e}")
    finally:
        session.stop()

if __name__ == "__main__":
    run_integration_test()
