import logging
import os

import uvicorn

logging.basicConfig(level=os.environ.get("KASSENSTURZ_LOG", "INFO"), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logging.getLogger("fints").setLevel(logging.WARNING)

if __name__ == "__main__":
    uvicorn.run("kassensturz.main:app", host=os.environ.get("KASSENSTURZ_HOST", "0.0.0.0"),
                port=int(os.environ.get("KASSENSTURZ_PORT", "8099")),
                log_level="warning", proxy_headers=False,
                # Below the Supervisor's default stop timeout of 10 seconds, so a
                # cold backup never has to kill the app mid-write.
                timeout_graceful_shutdown=5)
