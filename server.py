"""Chromap — local color remapper. Run: python3 server.py"""

from collections import OrderedDict
from secrets import token_urlsafe
from threading import Lock

from flask import Flask, jsonify, request, send_from_directory

import ccstore
import colorlib
from palettes import THEME_LABELS, THEMES, SIMPLIFY_60

app = Flask(__name__, static_folder="static", static_url_path="")

MAX_CONTENT_CHARS = 4_000_000
MAX_CACHED_DOCUMENTS = 4

# A stylesheet is immutable after import. Interactive controls address this
# cache by id, so their cost follows the number of distinct colors rather than
# repeatedly uploading and scanning the whole source.
_documents = OrderedDict()
_documents_lock = Lock()


@app.get("/")
def index():
    return send_from_directory("static", "index.html")


@app.get("/samples/<path:name>")
def sample(name):
    return send_from_directory("samples", name)


@app.get("/mockups/<path:name>")
def mockup(name):
    return send_from_directory("mockups", name)


@app.get("/api/meta")
def meta():
    return jsonify({
        "themes": [
            {"id": tid, "label": THEME_LABELS[tid],
             "colors": [colorlib.rgb_to_hex(c) for c in colors]}
            for tid, colors in THEMES.items()
        ],
        "simplify": [colorlib.rgb_to_hex(c) for c in SIMPLIFY_60],
    })


def _content_or_error():
    data = request.get_json(silent=True) or {}
    content = data.get("content")
    if not isinstance(content, str):
        return None, (jsonify({"error": "No file content in the request. "
                               "Open a file first, then scan."}), 400)
    if len(content) > MAX_CONTENT_CHARS:
        return None, (jsonify({"error": "The file is over 4 MB of text. "
                               "Chromap holds the whole file in memory — "
                               "split it or trim it, then retry."}), 413)
    return data, None


def _cache_document(content):
    document_id = token_urlsafe(12)
    document = {"content": content, "entries": colorlib.scan(content)}
    with _documents_lock:
        _documents[document_id] = document
        while len(_documents) > MAX_CACHED_DOCUMENTS:
            _documents.popitem(last=False)
    return document_id, document


def _document_or_error(document_id):
    with _documents_lock:
        document = _documents.get(document_id)
        if document is not None:
            _documents.move_to_end(document_id)
    if document is None:
        return None, (jsonify({
            "error": "This stylesheet analysis expired. Remove and add the "
                     "stylesheet again, then retry."
        }), 404)
    return document, None


def _mapping_rows(document, mode, params, excluded):
    mapping = colorlib.build_mapping(
        document["entries"], mode, params, excluded)
    rows = []
    for entry in document["entries"]:
        if entry["key"] not in mapping:
            continue
        rows.append({
            "key": entry["key"],
            "fromHex": entry["hex"],
            "toHex": colorlib.rgb_to_hex(mapping[entry["key"]]),
            "count": entry["count"],
        })
    info = {}
    if mode == "theme":
        info["themeTable"] = [
            colorlib.rgb_to_hex(color)
            for color in colorlib.theme_preview_table(params)
        ]
    return rows, info


@app.post("/api/documents")
def create_document():
    data, err = _content_or_error()
    if err:
        return err
    document_id, document = _cache_document(data["content"])
    return jsonify({"documentId": document_id,
                    "entries": document["entries"]})


@app.post("/api/documents/<document_id>/map")
def map_document(document_id):
    document, err = _document_or_error(document_id)
    if err:
        return err
    data = request.get_json(silent=True) or {}
    try:
        rows, info = _mapping_rows(
            document,
            data.get("mode", "simplify"),
            data.get("params", {}),
            data.get("excluded", []),
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"mapping": rows,
                    "themeTable": info.get("themeTable")})


@app.post("/api/documents/<document_id>/export")
def export_document(document_id):
    document, err = _document_or_error(document_id)
    if err:
        return err
    data = request.get_json(silent=True) or {}
    raw_mapping = data.get("mapping", {})
    if not isinstance(raw_mapping, dict):
        return jsonify({"error": "The color mapping is invalid."}), 400
    mapping = {}
    for key, value in raw_mapping.items():
        if (not isinstance(key, str) or not isinstance(value, str)
                or not colorlib.is_six_digit_hex(value)):
            return jsonify({"error": "The color mapping is invalid."}), 400
        mapping[key] = tuple(
            int(value[index:index + 2], 16) for index in (1, 3, 5))
    return jsonify({"result": colorlib.rewrite(document["content"], mapping)})


@app.post("/api/scan")
def scan():
    data, err = _content_or_error()
    if err:
        return err
    entries = colorlib.scan(data["content"])
    return jsonify({"entries": entries})


@app.post("/api/transform")
def transform():
    data, err = _content_or_error()
    if err:
        return err
    try:
        rows, result, info = colorlib.transform(
            data["content"],
            data.get("mode", "simplify"),
            data.get("params", {}),
            data.get("excluded", []),
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    preview_html, truncated = colorlib.rewrite_annotated(
        data["content"],
        {row["key"]: tuple(
            int(row["toHex"][i:i + 2], 16) for i in (1, 3, 5))
         for row in rows},
    )
    return jsonify({"mapping": rows, "result": result,
                    "previewHtml": preview_html,
                    "previewTruncated": truncated,
                    "themeTable": info.get("themeTable")})


@app.get("/api/cc/projects")
def cc_projects():
    return jsonify({"projects": ccstore.list_projects()})


@app.post("/api/cc/import")
def cc_import():
    data, err = _content_or_error()
    if err:
        return err
    project = (data.get("project") or "workspace").strip() or "workspace"
    name = (data.get("name") or "pasted.css").strip() or "pasted.css"
    return jsonify(ccstore.import_stylesheet(project, name, data["content"]))


@app.get("/api/cc/entities")
def cc_entities():
    project = (request.args.get("project") or "").strip()
    query = (request.args.get("q") or "").strip()
    return jsonify(ccstore.entities(project, query))


@app.get("/api/cc/resume")
def cc_resume():
    project = (request.args.get("project") or "").strip()
    data = ccstore.resume(project)
    if data is None:
        return jsonify({"error": "No project with that name."}), 404
    return jsonify(data)


@app.post("/api/cc/decision")
def cc_decision():
    data = request.get_json(silent=True) or {}
    project = (data.get("project") or "workspace").strip() or "workspace"
    kind = str(data.get("kind") or "note")
    payload = data.get("payload")
    if not isinstance(payload, (dict, list)):
        return jsonify({"error": "Decision payload must be JSON."}), 400
    return jsonify(ccstore.record_decision(project, kind, payload))


@app.get("/api/cc/export")
def cc_export():
    project = (request.args.get("project") or "").strip()
    css = ccstore.emit_css(project)
    if css is None:
        return jsonify({"error": "No project with that name."}), 404
    return app.response_class(css, mimetype="text/css")


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5177, debug=False)
