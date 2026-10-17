"""Dev entry point — `python run_api.py`, or press Debug in the IDE.

Same FastAPI app as the shell launcher, run single-process so breakpoints in
``busfactor/`` fire. FalkorDB must be up first (``make up``, or the shared
"API - debug (Python)" configuration starts it for you).
"""

import uvicorn

from busfactor.api import app

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")
