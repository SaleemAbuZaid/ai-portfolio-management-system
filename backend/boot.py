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
import os
import sys
import time

print("--- APEX BOOT SEQUENCE START ---")
print(f"Python: {sys.version}")
print(f"CWD: {os.getcwd()}")

print("Importing app.main...")
try:
    from app.main import app
    print("app.main imported successfully.")
except Exception as e:
    print(f"CRITICAL IMPORT ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

import uvicorn
print("Starting Uvicorn...")
uvicorn.run(app, host="127.0.0.1", port=8000, log_level="debug")
