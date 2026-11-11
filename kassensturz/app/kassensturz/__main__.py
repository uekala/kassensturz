import logging
import os
import signal

import uvicorn

logging.basicConfig(level=os.environ.get("KASSENSTURZ_LOG", "INFO"), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logging.getLogger("fints").setLevel(logging.WARNING)

if __name__ == "__main__":
    # uvicorn fährt bei SIGTERM sauber herunter und löst das Signal danach noch
    # einmal aus. Ohne eigenen Empfänger beendet das den Prozess mit Code 143,
    # und der Supervisor meldet „SIGTERM nicht behandelt“. So endet er mit 0.
    signal.signal(signal.SIGTERM, lambda *_: None)
    uvicorn.run("kassensturz.main:app", host=os.environ.get("KASSENSTURZ_HOST", "0.0.0.0"),
                port=int(os.environ.get("KASSENSTURZ_PORT", "8099")),
                log_level="warning", proxy_headers=False,
                # Below the Supervisor's default stop timeout of 10 seconds, so a
                # cold backup never has to kill the app mid-write.
                timeout_graceful_shutdown=5)
