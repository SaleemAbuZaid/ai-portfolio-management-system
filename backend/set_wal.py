"""
Project: APEX AI Portfolio Management System
Course: Graduation Project / Engineering Project
Team Members:
- Saleem A. S. AbuZaid
- Rashad Naghdiyev
Advisor:
Prof.Dr. Selim Akyokuş
Description:
- Project source/configuration file supporting the APEX AI Portfolio Management System.
"""

import asyncio
import sqlite3
import os

def set_wal():
    db_path = "backend/apex_defense.db"
    if not os.path.exists(db_path):
        print(f"DB not found at {db_path}")
        return
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL;")
    cursor.execute("PRAGMA synchronous=NORMAL;")
    res = cursor.execute("PRAGMA journal_mode;").fetchone()
    print(f"Journal mode set to: {res[0]}")
    conn.close()

if __name__ == "__main__":
    set_wal()
