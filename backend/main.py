"""
Project: APEX AI Portfolio Management System
Course: Graduation Project / Engineering Project
Team Members:
- Saleem A. S. AbuZaid
- Rashad Naghdiyev
Advisor:
Prof.Dr. Selim Akyokuş
Description:
- Compatibility entry point that exposes the FastAPI application from backend.app.main.
"""
import os
import sys

# Ensure the app directory is discoverable
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Proxy the actual FastAPI object for `uvicorn main:app`
from app.main import app

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=False)
