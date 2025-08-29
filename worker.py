# worker.py
import time, sys
from notify import run_scan_once

if __name__ == "__main__":
    print("Worker started.", flush=True)
    while True:
        try:
            n = run_scan_once()
            if n:
                print(f"Notified: {n}", flush=True)
        except Exception as e:
            print("Worker error:", e, file=sys.stderr, flush=True)
        time.sleep(60)  # verifica a cada 60s
