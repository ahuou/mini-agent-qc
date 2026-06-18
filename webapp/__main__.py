"""`python -m webapp` -> launch the dashboard on http://127.0.0.1:8000."""

from __future__ import annotations

import os


def main() -> None:
    import uvicorn
    host = os.getenv("QC_WEB_HOST", "127.0.0.1")
    port = int(os.getenv("QC_WEB_PORT", "8000"))
    print(f"QC Agent Console -> http://{host}:{port}  (Ctrl-C to stop)")
    uvicorn.run("webapp.server:app", host=host, port=port, log_level="warning")


if __name__ == "__main__":
    main()
