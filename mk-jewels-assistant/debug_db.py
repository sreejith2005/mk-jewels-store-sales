import os
import sqlite3
from pathlib import Path
from config import Config

def main():
    print("Config.DB_PATH:", Config.DB_PATH)
    resolved_path = Path(Config.DB_PATH).resolve()
    print("Resolved Path:", resolved_path)
    
    if os.path.exists(Config.DB_PATH):
        print(f"File exists. Size: {os.path.getsize(Config.DB_PATH)} bytes")
        
        try:
            conn = sqlite3.connect(Config.DB_PATH)
            cursor = conn.cursor()
            
            try:
                cursor.execute("SELECT COUNT(*) FROM sessions")
                sessions_count = cursor.fetchone()[0]
                print(f"Row count of sessions table: {sessions_count}")
            except Exception as e:
                print(f"Error querying sessions table: {e}")
                
            try:
                cursor.execute("SELECT COUNT(*) FROM events")
                events_count = cursor.fetchone()[0]
                print(f"Row count of events table: {events_count}")
            except Exception as e:
                print(f"Error querying events table: {e}")
            
            conn.close()
        except Exception as e:
            print("Error connecting to database:", e)
    else:
        print("File does not exist at Config.DB_PATH")
        
    print("\nSearching for 'sessions.db' in the project root...")
    project_root = Path('.').resolve()
    matches = list(project_root.rglob('sessions.db'))
    if matches:
        for match in matches:
            print(f"Found: {match}")
    else:
        print("No matches found for 'sessions.db'")

if __name__ == "__main__":
    main()
