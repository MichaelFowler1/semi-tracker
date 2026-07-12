"""Flask server for the semiconductor stock tracker.

Serves the dashboard and a small JSON API. The first request kicks off a
background data refresh if no cache exists yet; after that, refreshes are
manual (button in the UI) so we never hammer the data sources.
"""

import threading

from flask import Flask, jsonify, render_template

import fetcher

app = Flask(__name__)
app.config["TEMPLATES_AUTO_RELOAD"] = True


def _start_refresh():
    if not fetcher.progress["running"]:
        threading.Thread(target=fetcher.refresh, daemon=True).start()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/data")
def data():
    cache = fetcher.load_cache()
    if cache is None:
        _start_refresh()
    return jsonify({"cache": cache, "progress": fetcher.progress})


@app.route("/api/refresh", methods=["POST"])
def refresh():
    _start_refresh()
    return jsonify({"started": True})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5057)
