"""`make serve`: resolve the snapshot and serve the API on localhost."""

import uvicorn

from common_cause.api import create_app

if __name__ == "__main__":
    uvicorn.run(create_app(), host="127.0.0.1", port=8000)
