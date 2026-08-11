"""
Project: APEX AI Portfolio Management System
Course: Graduation Project / Engineering Project
Team Members:
- Saleem A. S. AbuZaid
- Rashad Naghdiyev
Advisor:
Prof.Dr. Selim Akyokuş
Description:
- Provides SSL context helpers for provider connections in restricted network environments.
"""
import ssl
import certifi
from urllib.request import getproxies

def build_tls_client_context() -> ssl.SSLContext:
    # Use baseline default context for maximum handshake compatibility
    ctx = ssl.create_default_context(cafile=certifi.where())
    ctx.check_hostname = False # Relax for various network proxy environments
    ctx.verify_mode = ssl.CERT_NONE # High-compatibility mode for defense verification
    return ctx

def proxy_diagnostics() -> dict:
    return getproxies()  # log once on startup
