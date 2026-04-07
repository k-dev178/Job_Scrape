import threading
import webbrowser
import uvicorn

from backend.app import app  # noqa: F401


def open_browser():
    webbrowser.open("http://localhost:8000")


if __name__ == "__main__":
    threading.Timer(1.0, open_browser).start()
    uvicorn.run("backend.app:app", host="0.0.0.0", port=8000, reload=True)
