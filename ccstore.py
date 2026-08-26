"""ConsoliChrome object store — stylesheets as consolidated entities in SQLite.

A project accumulates imports. Each import is parsed into rules and
declarations (order-preserving). Entities are the consolidated view: one row
per (selector, context) across the latest import of every stylesheet name,
properties resolved by cascade order — later declaration wins, earlier values
kept with provenance and flagged overridden. At-rule blocks that aren't
media/supports wrappers (@keyframes, @font-face, ...) pass through verbatim.
"""

import json
import re
import sqlite3
import time
from bisect import bisect_right
from pathlib import Path
from threading import Lock

DB_PATH = Path(__file__).with_name("cc.db")
_lock = Lock()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS projects(
  id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS imports(
  id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL REFERENCES projects(id),
  name TEXT NOT NULL, raw_text TEXT NOT NULL, imported_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS rules(
  id INTEGER PRIMARY KEY, import_id INTEGER NOT NULL REFERENCES imports(id),
  order_idx INTEGER NOT NULL, selector TEXT NOT NULL,
  context TEXT NOT NULL DEFAULT '', line INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS declarations(
  id INTEGER PRIMARY KEY, rule_id INTEGER NOT NULL REFERENCES rules(id),
  order_idx INTEGER NOT NULL, property TEXT NOT NULL, value TEXT NOT NULL,
  line INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS raw_blocks(
  id INTEGER PRIMARY KEY, import_id INTEGER NOT NULL REFERENCES imports(id),
  order_idx INTEGER NOT NULL, header TEXT NOT NULL, body TEXT NOT NULL,
  context TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS entities(
  id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL REFERENCES projects(id),
  selector TEXT NOT NULL, context TEXT NOT NULL DEFAULT '',
  first_order INTEGER NOT NULL, blocks INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS entity_props(
  id INTEGER PRIMARY KEY, entity_id INTEGER NOT NULL REFERENCES entities(id),
  property TEXT NOT NULL, value TEXT NOT NULL, source_name TEXT NOT NULL,
  line INTEGER NOT NULL, overridden INTEGER NOT NULL DEFAULT 0,
  order_idx INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS decisions(
  id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL REFERENCES projects(id),
  kind TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_imports_project_name ON imports(project_id, name, id);
CREATE INDEX IF NOT EXISTS idx_rules_import ON rules(import_id, order_idx);
CREATE INDEX IF NOT EXISTS idx_declarations_rule ON declarations(rule_id, order_idx);
CREATE INDEX IF NOT EXISTS idx_raw_blocks_import ON raw_blocks(import_id, order_idx);
CREATE INDEX IF NOT EXISTS idx_entities_project ON entities(project_id);
CREATE INDEX IF NOT EXISTS idx_entity_props_entity ON entity_props(entity_id, order_idx);
CREATE INDEX IF NOT EXISTS idx_decisions_project ON decisions(project_id);
"""


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


# ---------- parsing ----------

_COMMENT_RE = re.compile(r"/\*.*?(?:\*/|\Z)", re.S)
_NON_NEWLINE_RE = re.compile(r"[^\n]")


def _blank_comments(text):
    return _COMMENT_RE.sub(
        lambda match: _NON_NEWLINE_RE.sub(" ", match.group()), text)


def _line_index(text):
    starts = [idx for idx, ch in enumerate(text) if ch == "\n"]
    return lambda pos: bisect_right(starts, pos) + 1


def _find_block_end(text, open_idx):
    depth, i, quote, n = 0, open_idx, "", len(text)
    while i < n:
        ch = text[i]
        if quote:
            if ch == quote and text[i - 1] != "\\":
                quote = ""
        elif ch in "\"'":
            quote = ch
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return n - 1


def _split_declarations(blanked, start, end, line_of):
    decls, cursor, i, quote, parens, braces = [], start, start, "", 0, 0

    def flush(upto):
        seg = blanked[cursor:upto]
        depth, q = 0, ""
        for k, ch in enumerate(seg):
            if q:
                if ch == q and seg[k - 1] != "\\":
                    q = ""
            elif ch in "\"'":
                q = ch
            elif ch == "(":
                depth += 1
            elif ch == ")":
                depth = max(0, depth - 1)
            elif ch == ":" and depth == 0:
                prop = seg[:k].strip().lower()
                value = seg[k + 1:].strip()
                if prop and value:
                    decls.append({"property": prop, "value": value,
                                  "line": line_of(cursor)})
                return

    while i < end:
        ch = blanked[i]
        if quote:
            if ch == quote and blanked[i - 1] != "\\":
                quote = ""
        elif ch in "\"'":
            quote = ch
        elif ch == "(":
            parens += 1
        elif ch == ")":
            parens = max(0, parens - 1)
        elif ch == "{":
            braces += 1
        elif ch == "}":
            braces = max(0, braces - 1)
        elif ch == ";" and parens == 0 and braces == 0:
            flush(i)
            cursor = i + 1
        i += 1
    flush(end)
    return decls


def parse_stylesheet(original):
    """Return (rules, raw_blocks); both carry an interleaved order index."""
    blanked = _blank_comments(original)
    line_of = _line_index(blanked)
    rules, raw_blocks = [], []
    counter = {"order": 0}

    def walk(start, end, context):
        i, cursor, quote, parens = start, start, "", 0
        while i < end:
            ch = blanked[i]
            if quote:
                if ch == quote and blanked[i - 1] != "\\":
                    quote = ""
            elif ch in "\"'":
                quote = ch
            elif ch == "(":
                parens += 1
            elif ch == ")":
                parens = max(0, parens - 1)
            elif ch == ";" and parens == 0:
                cursor = i + 1
            elif ch == "{" and parens == 0:
                header = " ".join(blanked[cursor:i].split())
                close = _find_block_end(blanked, i)
                if header.startswith("@media") or header.startswith("@supports"):
                    child = (context + " && " + header) if context else header
                    walk(i + 1, close, child)
                elif header.startswith("@"):
                    raw_blocks.append({
                        "order": counter["order"], "header": header,
                        "body": original[cursor:close + 1].strip(),
                        "context": context})
                    counter["order"] += 1
                elif header:
                    rules.append({
                        "order": counter["order"], "selector": header,
                        "context": context, "line": line_of(cursor),
                        "declarations": _split_declarations(
                            blanked, i + 1, close, line_of)})
                    counter["order"] += 1
                cursor = close + 1
                i = close
            i += 1

    walk(0, len(blanked), "")
    return rules, raw_blocks


# ---------- store operations ----------

def _project_id(conn, name, create=False):
    row = conn.execute("SELECT id FROM projects WHERE name=?", (name,)).fetchone()
    if row:
        return row["id"]
    if not create:
        return None
    cur = conn.execute("INSERT INTO projects(name, created_at) VALUES(?,?)",
                       (name, _now()))
    return cur.lastrowid


def _latest_imports(conn, project_id):
    return conn.execute(
        """SELECT i.* FROM imports i WHERE i.project_id=? AND i.id=(
             SELECT MAX(id) FROM imports WHERE project_id=? AND name=i.name)
           ORDER BY i.id""", (project_id, project_id)).fetchall()


def _rebuild_entities(conn, project_id):
    conn.execute("""DELETE FROM entity_props WHERE entity_id IN
                    (SELECT id FROM entities WHERE project_id=?)""", (project_id,))
    conn.execute("DELETE FROM entities WHERE project_id=?", (project_id,))
    merged, order = {}, 0
    for imp in _latest_imports(conn, project_id):
        decls_by_rule = {}
        for decl in conn.execute(
                """SELECT d.rule_id, d.property, d.value, d.line
                   FROM declarations d JOIN rules r ON r.id = d.rule_id
                   WHERE r.import_id=? ORDER BY d.rule_id, d.order_idx""",
                (imp["id"],)):
            decls_by_rule.setdefault(decl["rule_id"], []).append(decl)
        for rule in conn.execute(
                "SELECT id, selector, context FROM rules WHERE import_id=?"
                " ORDER BY order_idx", (imp["id"],)):
            key = (rule["selector"], rule["context"])
            ent = merged.setdefault(key, {"first": order, "blocks": 0, "props": {}})
            ent["blocks"] += 1
            for decl in decls_by_rule.get(rule["id"], ()):
                ent["props"].setdefault(decl["property"], []).append(
                    {"value": decl["value"], "source": imp["name"],
                     "line": decl["line"]})
            order += 1
    prop_rows = []
    for (selector, context), ent in merged.items():
        cur = conn.execute(
            """INSERT INTO entities(project_id, selector, context, first_order,
               blocks) VALUES(?,?,?,?,?)""",
            (project_id, selector, context, ent["first"], ent["blocks"]))
        entity_id, idx = cur.lastrowid, 0
        for prop, seen in ent["props"].items():
            for k, cand in enumerate(seen):
                prop_rows.append(
                    (entity_id, prop, cand["value"], cand["source"],
                     cand["line"], 0 if k == len(seen) - 1 else 1, idx))
                idx += 1
    conn.executemany(
        """INSERT INTO entity_props(entity_id, property, value, source_name,
           line, overridden, order_idx) VALUES(?,?,?,?,?,?,?)""", prop_rows)


def import_stylesheet(project, name, content):
    with _lock, _connect() as conn:
        project_id = _project_id(conn, project, create=True)
        rules, raw_blocks = parse_stylesheet(content)
        cur = conn.execute(
            "INSERT INTO imports(project_id, name, raw_text, imported_at)"
            " VALUES(?,?,?,?)", (project_id, name, content, _now()))
        import_id = cur.lastrowid
        decl_rows = []
        for rule in rules:
            rcur = conn.execute(
                "INSERT INTO rules(import_id, order_idx, selector, context,"
                " line) VALUES(?,?,?,?,?)",
                (import_id, rule["order"], rule["selector"], rule["context"],
                 rule["line"]))
            decl_rows.extend(
                (rcur.lastrowid, k, decl["property"], decl["value"],
                 decl["line"])
                for k, decl in enumerate(rule["declarations"]))
        conn.executemany(
            "INSERT INTO declarations(rule_id, order_idx, property, value,"
            " line) VALUES(?,?,?,?,?)", decl_rows)
        conn.executemany(
            "INSERT INTO raw_blocks(import_id, order_idx, header, body,"
            " context) VALUES(?,?,?,?,?)",
            [(import_id, block["order"], block["header"], block["body"],
              block["context"]) for block in raw_blocks])
        _rebuild_entities(conn, project_id)
        counts = conn.execute(
            """SELECT (SELECT COUNT(*) FROM entities WHERE project_id=:p) AS entities,
                      (SELECT COUNT(*) FROM entities WHERE project_id=:p AND blocks>1) AS merged""",
            {"p": project_id}).fetchone()
        return {"project": project, "name": name, "rules": len(rules),
                "rawBlocks": len(raw_blocks), "entities": counts["entities"],
                "merged": counts["merged"]}


def list_projects():
    with _lock, _connect() as conn:
        out = []
        for row in conn.execute("SELECT * FROM projects ORDER BY name"):
            latest = _latest_imports(conn, row["id"])
            stamp = max((i["imported_at"] for i in latest), default=None)
            decisions = conn.execute(
                "SELECT COUNT(*) AS n FROM decisions WHERE project_id=?",
                (row["id"],)).fetchone()["n"]
            out.append({"name": row["name"], "files": len(latest),
                        "lastImport": stamp, "decisions": decisions})
        return out


def database_overview():
    """Return a small, read-only summary for the local database manager."""
    info = {
        "status": "missing",
        "size": DB_PATH.stat().st_size if DB_PATH.exists() else 0,
        "modifiedAt": time.strftime(
            "%Y-%m-%dT%H:%M:%S",
            time.localtime(DB_PATH.stat().st_mtime),
        ) if DB_PATH.exists() else None,
        "projects": [],
    }
    if not DB_PATH.exists():
        return info

    try:
        with _lock, sqlite3.connect(
                f"file:{DB_PATH}?mode=ro", uri=True) as conn:
            conn.row_factory = sqlite3.Row
            check = conn.execute("PRAGMA quick_check").fetchone()
            if not check or check[0] != "ok":
                info.update(status="damaged", error=check[0] if check else
                            "SQLite could not verify the database.")
                return info
            info["status"] = "healthy"
            rows = conn.execute(
                """SELECT p.name, p.created_at,
                          (SELECT COUNT(DISTINCT name) FROM imports
                           WHERE project_id=p.id) AS files,
                          (SELECT COUNT(*) FROM imports
                           WHERE project_id=p.id) AS imports,
                          (SELECT MAX(imported_at) FROM imports
                           WHERE project_id=p.id) AS last_import,
                          (SELECT COUNT(*) FROM entities
                           WHERE project_id=p.id) AS entities,
                          (SELECT COUNT(*) FROM decisions
                           WHERE project_id=p.id) AS decisions
                   FROM projects p ORDER BY p.name""").fetchall()
            info["projects"] = [dict(row) for row in rows]
    except sqlite3.Error as exc:
        info.update(status="damaged", error=str(exc))
    return info


def delete_project(name):
    """Delete one project and every row owned by it, in one transaction."""
    with _lock, _connect() as conn:
        row = conn.execute(
            "SELECT id FROM projects WHERE name=?", (name,)).fetchone()
        if row is None:
            return None
        project_id = row["id"]
        counts = {
            "imports": conn.execute(
                "SELECT COUNT(*) FROM imports WHERE project_id=?",
                (project_id,)).fetchone()[0],
            "entities": conn.execute(
                "SELECT COUNT(*) FROM entities WHERE project_id=?",
                (project_id,)).fetchone()[0],
            "decisions": conn.execute(
                "SELECT COUNT(*) FROM decisions WHERE project_id=?",
                (project_id,)).fetchone()[0],
        }
        conn.execute(
            """DELETE FROM entity_props WHERE entity_id IN
                 (SELECT id FROM entities WHERE project_id=?)""",
            (project_id,))
        conn.execute("DELETE FROM entities WHERE project_id=?", (project_id,))
        conn.execute(
            """DELETE FROM declarations WHERE rule_id IN
                 (SELECT r.id FROM rules r JOIN imports i
                  ON i.id=r.import_id WHERE i.project_id=?)""",
            (project_id,))
        conn.execute(
            """DELETE FROM rules WHERE import_id IN
                 (SELECT id FROM imports WHERE project_id=?)""",
            (project_id,))
        conn.execute(
            """DELETE FROM raw_blocks WHERE import_id IN
                 (SELECT id FROM imports WHERE project_id=?)""",
            (project_id,))
        conn.execute("DELETE FROM imports WHERE project_id=?", (project_id,))
        conn.execute("DELETE FROM decisions WHERE project_id=?", (project_id,))
        conn.execute("DELETE FROM projects WHERE id=?", (project_id,))
        return counts


def entities(project, query="", limit=300):
    with _lock, _connect() as conn:
        project_id = _project_id(conn, project)
        if project_id is None:
            return {"total": 0, "shown": 0, "entities": []}
        where = "project_id=?"
        args = [project_id]
        if query:
            where += " AND (selector LIKE ? OR context LIKE ?)"
            args += [f"%{query}%", f"%{query}%"]
        total = conn.execute(
            f"SELECT COUNT(*) AS n FROM entities WHERE {where}", args).fetchone()["n"]
        rows = conn.execute(
            f"""SELECT * FROM entities WHERE {where}
                ORDER BY blocks DESC, first_order LIMIT ?""",
            args + [limit]).fetchall()
        out = []
        for row in rows:
            props = [dict(p) for p in conn.execute(
                "SELECT property, value, source_name, line, overridden FROM"
                " entity_props WHERE entity_id=? ORDER BY order_idx",
                (row["id"],))]
            out.append({"selector": row["selector"], "context": row["context"],
                        "blocks": row["blocks"], "props": props})
        return {"total": total, "shown": len(rows), "entities": out}


def resume(project):
    with _lock, _connect() as conn:
        project_id = _project_id(conn, project)
        if project_id is None:
            return None
        sources = [{"name": i["name"], "content": i["raw_text"]}
                   for i in _latest_imports(conn, project_id)]
        decisions = [{"kind": d["kind"], "payload": json.loads(d["payload"]),
                      "createdAt": d["created_at"]}
                     for d in conn.execute(
                         "SELECT * FROM decisions WHERE project_id=? ORDER BY id",
                         (project_id,))]
        return {"project": project, "sources": sources, "decisions": decisions}


def record_decision(project, kind, payload):
    with _lock, _connect() as conn:
        project_id = _project_id(conn, project, create=True)
        conn.execute(
            "INSERT INTO decisions(project_id, kind, payload, created_at)"
            " VALUES(?,?,?,?)", (project_id, kind, json.dumps(payload), _now()))
        return {"ok": True}


def emit_css(project):
    with _lock, _connect() as conn:
        project_id = _project_id(conn, project)
        if project_id is None:
            return None
        items = []
        for ent in conn.execute(
                "SELECT * FROM entities WHERE project_id=? ORDER BY first_order",
                (project_id,)):
            props = conn.execute(
                """SELECT property, value FROM entity_props
                   WHERE entity_id=? AND overridden=0 ORDER BY order_idx""",
                (ent["id"],)).fetchall()
            body = "\n".join(f"  {p['property']}: {p['value']};" for p in props)
            items.append((ent["first_order"], ent["context"],
                          f"{ent['selector']} {{\n{body}\n}}"))
        base = 10_000_000
        for imp in _latest_imports(conn, project_id):
            for block in conn.execute(
                    "SELECT * FROM raw_blocks WHERE import_id=? ORDER BY order_idx",
                    (imp["id"],)):
                items.append((base + block["order_idx"], block["context"],
                              block["body"]))
            base += 10_000_000
        items.sort(key=lambda item: item[0])
        out, open_parts = [], []
        for _, context, text in items:
            parts = context.split(" && ") if context else []
            if parts != open_parts:
                out.extend("}" for _ in open_parts)
                for part in parts:
                    out.append(part + " {")
                open_parts = parts
            if open_parts:
                text = "\n".join("  " + line for line in text.split("\n"))
            out.append(text)
            out.append("")
        out.extend("}" for _ in open_parts)
        return "\n".join(out).strip() + "\n"
