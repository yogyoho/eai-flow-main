"""uvicorn entrypoint for the management API.

Run standalone:
    cd skills/custom/contract-price-analysis
    PYTHONPATH=. python -m scripts.server.main

Or via uvicorn directly:
    PYTHONPATH=. uvicorn scripts.server.app:app --port 8010 --reload
"""

import uvicorn


def main():
    uvicorn.run("scripts.server.app:app", host="0.0.0.0", port=8010, reload=False)


if __name__ == "__main__":
    main()
