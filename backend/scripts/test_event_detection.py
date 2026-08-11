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
from app.services.ai_engine.event_detector import event_detector

test_cases = [
    ("Company reports record earnings and revenue growth", "Earnings"),
    ("XOM and CVX discuss potential merger details", "Merger/Acquisition"),
    ("SEC launches investigation into trading practices", "Regulatory"),
    ("Fed signals interest rates will remain unchanged", "Macro"),
    ("OPEC announces production cut to stabilize oil prices", "Supply Chain"),
    ("Ethereum mainnet upgrade scheduled for next month", "Crypto/Network"),
    ("Stock market closes slightly higher on Friday", "Market")
]

print("[SCAN] Testing Event Detection Logic...\n")

for text, expected in test_cases:
    category, keywords = event_detector.detect_event(text)
    status = "PASS" if category == expected else "FAIL"
    print(f"Text: {text[:50]}...")
    print(f"Result: {category} (Keywords: {keywords})")
    print(f"Status: {status}\n")

print("Testing complete.")
