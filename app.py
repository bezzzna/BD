from pathlib import Path
import json
import os
from urllib import error, parse, request as urlrequest

from flask import Flask, abort, jsonify, request, send_from_directory

from db import get_connection, init_db, row_to_dict

ROOT = Path(__file__).parent
app = Flask(__name__)
CMS_BASE_URL = os.getenv("CMS_BASE_URL", "https://cms.sirius-prim.ru").rstrip("/")
CMS_TOKEN = os.getenv("CMS_TOKEN", "").strip()


def _extract_attributes(item):
    attrs = item.get("attributes")
    return attrs if isinstance(attrs, dict) else item


def _extract_relation_data(value):
    if isinstance(value, dict):
        rel_data = value.get("data")
        if isinstance(rel_data, dict):
            return _extract_attributes(rel_data)
    return {}


def _extract_relation_items(value):
    if isinstance(value, list):
        return [_extract_attributes(item) for item in value if isinstance(item, dict)]
    if not isinstance(value, dict):
        return []
    rel_data = value.get("data")
    if isinstance(rel_data, list):
        return [_extract_attributes(item) for item in rel_data if isinstance(item, dict)]
    if isinstance(rel_data, dict):
        return [_extract_attributes(rel_data)]
    # Strapi может вернуть relation как плоский объект без data.
    if "id" in value:
        return [_extract_attributes(value)]
    return []


def _normalize_application_item(item):
    attrs = _extract_attributes(item)
    program_items = _extract_relation_items(attrs.get("program"))
    program_titles = [p.get("title") or p.get("name") for p in program_items if p.get("title") or p.get("name")]
    form_data = attrs.get("formData") if isinstance(attrs.get("formData"), dict) else {}

    def _from_form(*keys):
        for key in keys:
            value = form_data.get(key)
            if value not in (None, ""):
                return value
        return None

    birth_date = attrs.get("snapshotBirthDate") or _from_form(
        "birthDate",
        "birth_date",
        "dateOfBirth",
        "Дата рождения",
        "дата рождения",
    )
    city = attrs.get("snapshotCity") or _from_form(
        "city",
        "town",
        "Город",
        "город",
    )

    # Отдаем только поля, которые используются в таблице участников.
    return {
        "id": item.get("id", attrs.get("id")),
        "fio": attrs.get("snapshotName"),
        "programs": ", ".join(program_titles) if program_titles else None,
        "program_list": program_titles,
        "birth_date": birth_date,
        "class": attrs.get("grade"),
        "school": attrs.get("school"),
        "city": city,
        "phone": attrs.get("snapshotPhone"),
        "phone_parent": attrs.get("parentPhone"),
        "email": attrs.get("snapshotEmail"),
    }


def _normalize_program_item(item, participants_count):
    attrs = _extract_attributes(item)
    return {
        "id": item.get("id", attrs.get("id")),
        "name": attrs.get("title") or attrs.get("name"),
        "category": attrs.get("category"),
        "date_start": attrs.get("startDate") or attrs.get("dateStart"),
        "date_end": attrs.get("endDate") or attrs.get("dateEnd"),
        "participants_count": participants_count,
        "format": attrs.get("subcategory"),
    }


def _fetch_cms(path, params=None):
    query = f"?{parse.urlencode(params, doseq=True)}" if params else ""
    url = f"{CMS_BASE_URL}{path}{query}"
    headers = {"Accept": "application/json"}
    if CMS_TOKEN:
        headers["Authorization"] = f"Bearer {CMS_TOKEN}"

    req = urlrequest.Request(url, headers=headers)
    try:
        with urlrequest.urlopen(req, timeout=20) as response:
            payload = response.read().decode("utf-8")
    except error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"CMS error {exc.code}: {details[:200]}") from exc
    except Exception as exc:
        raise RuntimeError(f"CMS unavailable: {exc}") from exc

    data = json.loads(payload)
    return data


def _fetch_cms_all(path, base_params=None, page_size=200):
    params = dict(base_params or {})
    page = 1
    all_items = []

    while True:
        page_params = dict(params)
        page_params["pagination[page]"] = page
        page_params["pagination[pageSize]"] = page_size

        payload = _fetch_cms(path, page_params)
        items = payload.get("data", [])
        all_items.extend(items)

        meta = payload.get("meta", {})
        pagination = meta.get("pagination", {})
        page_count = pagination.get("pageCount")

        if page_count is not None:
            if page >= page_count:
                break
        elif len(items) < page_size:
            break

        page += 1

    return all_items


def sync_cms_to_db():
    programs = _fetch_cms_all("/api/programs", {"populate": "*"})
    applications = _fetch_cms_all("/api/applications", {"populate": "*"})

    with get_connection() as conn:
        conn.execute("DELETE FROM cms_programs")
        conn.execute("DELETE FROM cms_application_programs")
        conn.execute("DELETE FROM cms_applications")

        for item in programs:
            attrs = _extract_attributes(item)
            conn.execute(
                """
                INSERT INTO cms_programs
                    (cms_id, document_id, title, category, start_date, end_date, max_participants, registration_open, raw_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item.get("id"),
                    attrs.get("documentId") or item.get("documentId"),
                    attrs.get("title") or attrs.get("name"),
                    attrs.get("category"),
                    attrs.get("startDate") or attrs.get("dateStart"),
                    attrs.get("endDate") or attrs.get("dateEnd"),
                    attrs.get("maxParticipants"),
                    1 if attrs.get("registrationOpen") else 0,
                    json.dumps(item, ensure_ascii=False),
                ),
            )

        for item in applications:
            attrs = _extract_attributes(item)
            program_items = _extract_relation_items(attrs.get("program"))
            first_program = program_items[0] if program_items else {}
            application_id = item.get("id")
            conn.execute(
                """
                INSERT INTO cms_applications
                    (cms_id, document_id, application_status, confirmation_status, snapshot_name, snapshot_email, grade, program_document_id, program_title, raw_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    application_id,
                    attrs.get("documentId") or item.get("documentId"),
                    attrs.get("applicationStatus"),
                    attrs.get("confirmationStatus"),
                    attrs.get("snapshotName"),
                    attrs.get("snapshotEmail"),
                    attrs.get("grade"),
                    first_program.get("documentId"),
                    first_program.get("title") or first_program.get("name"),
                    json.dumps(item, ensure_ascii=False),
                ),
            )
            for program in program_items:
                program_document_id = program.get("documentId")
                if not program_document_id:
                    continue
                conn.execute(
                    """
                    INSERT OR IGNORE INTO cms_application_programs (application_id, program_document_id)
                    VALUES (?, ?)
                    """,
                    (application_id, program_document_id),
                )

    return {"programs": len(programs), "applications": len(applications)}


@app.before_request
def setup():
    if not hasattr(app, "_db_ready"):
        init_db()
        app._db_ready = True
    if not hasattr(app, "_cms_synced"):
        try:
            app._cms_sync_stats = sync_cms_to_db()
            app._cms_sync_error = None
        except RuntimeError as exc:
            app._cms_sync_stats = None
            app._cms_sync_error = str(exc)
        app._cms_synced = True
    if request.path.startswith("/api/") and request.method != "GET":
        abort(405, description="Разрешен только метод GET")


def _format_class(value):
    if value is None or value == "":
        return ""
    return f"{value} класс"


def _parse_program_ids(raw_ids):
    if not raw_ids:
        return []
    return [int(item) for item in str(raw_ids).split(",") if item.strip()]


def _program_ids_from_request(data):
    if "program_ids" in data:
        ids = data.get("program_ids") or []
        return [int(item) for item in ids if item is not None]
    if data.get("id_program") is not None:
        return [int(data["id_program"])]
    return None


def _set_participant_programs(conn, participant_id, program_ids):
    conn.execute(
        "DELETE FROM participant_programs WHERE id_participant = ?",
        (participant_id,),
    )
    for program_id in program_ids:
        conn.execute(
            """
            INSERT OR IGNORE INTO participant_programs (id_participant, id_program)
            VALUES (?, ?)
            """,
            (participant_id, program_id),
        )
    # Сохраняем первую программу в legacy-поле для совместимости с DB Browser
    legacy_program = program_ids[0] if program_ids else None
    conn.execute(
        "UPDATE programParticipants SET id_program = ? WHERE id_participant = ?",
        (legacy_program, participant_id),
    )


# --- Участники ---

PARTICIPANT_SELECT = """
    SELECT
        p.id_participant AS id,
        p.fio,
        p.birthDate AS birth_date,
        p.class AS class_num,
        p.school,
        p.city,
        p.phone,
        p.phoneParent AS phone_parent,
        p.email,
        GROUP_CONCAT(DISTINCT pr.name) AS programs,
        GROUP_CONCAT(DISTINCT pr.id_program) AS program_ids
    FROM programParticipants p
    LEFT JOIN participant_programs link ON p.id_participant = link.id_participant
    LEFT JOIN programs pr ON link.id_program = pr.id_program
    GROUP BY p.id_participant
"""


def _participant_payload(row):
    data = row_to_dict(row)
    data["class"] = _format_class(data.pop("class_num", None))
    data["program_ids"] = _parse_program_ids(data.pop("program_ids", None))
    return data


@app.get("/api/participants")
def list_participants():
    with get_connection() as conn:
        rows = conn.execute(f"{PARTICIPANT_SELECT} ORDER BY p.id_participant").fetchall()
    return jsonify([_participant_payload(r) for r in rows])


@app.get("/api/applications")
def list_applications():
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                raw_json
            FROM cms_applications
            ORDER BY cms_id
            """
        ).fetchall()
    payload = []
    for row in rows:
        item = json.loads(row["raw_json"])
        payload.append(_normalize_application_item(item))
    return jsonify(payload)


@app.get("/api/sync-cms")
def sync_cms():
    try:
        stats = sync_cms_to_db()
        return jsonify({"ok": True, **stats})
    except RuntimeError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 502


@app.get("/api/participants/<int:item_id>")
def get_participant(item_id):
    with get_connection() as conn:
        row = conn.execute(
            f"{PARTICIPANT_SELECT} WHERE p.id_participant = ?",
            (item_id,),
        ).fetchone()
    if not row:
        abort(404, description="Участник не найден")
    return jsonify(_participant_payload(row))


@app.post("/api/participants")
def create_participant():
    data = request.get_json(silent=True) or {}
    required = ("fio",)
    if not all(data.get(field) for field in required):
        abort(400, description="Поле fio обязательно")

    program_ids = _program_ids_from_request(data)

    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO programParticipants
                (fio, birthDate, class, school, city, phone, phoneParent, email, id_program)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data.get("fio"),
                data.get("birth_date"),
                data.get("class"),
                data.get("school"),
                data.get("city"),
                data.get("phone"),
                data.get("phone_parent"),
                data.get("email"),
                None,
            ),
        )
        item_id = cursor.lastrowid
        if program_ids is not None:
            _set_participant_programs(conn, item_id, program_ids)
        row = conn.execute(
            f"{PARTICIPANT_SELECT} WHERE p.id_participant = ?",
            (item_id,),
        ).fetchone()
    return jsonify(_participant_payload(row)), 201


def _build_update(data, field_map):
    updates = {db_col: data[api_key] for api_key, db_col in field_map.items() if api_key in data}
    if not updates:
        abort(400, description="Нет полей для обновления")
    return updates


@app.put("/api/participants/<int:item_id>")
def update_participant(item_id):
    data = request.get_json(silent=True) or {}
    updates = _build_update(
        data,
        {
            "fio": "fio",
            "birth_date": "birthDate",
            "class": "class",
            "school": "school",
            "city": "city",
            "phone": "phone",
            "phone_parent": "phoneParent",
            "email": "email",
        },
    )
    set_clause = ", ".join(f"{column} = ?" for column in updates)
    values = list(updates.values()) + [item_id]

    with get_connection() as conn:
        result = conn.execute(
            f"UPDATE programParticipants SET {set_clause} WHERE id_participant = ?",
            values,
        )
        if result.rowcount == 0:
            abort(404, description="Участник не найден")
        program_ids = _program_ids_from_request(data)
        if program_ids is not None:
            _set_participant_programs(conn, item_id, program_ids)
        row = conn.execute(
            f"{PARTICIPANT_SELECT} WHERE p.id_participant = ?",
            (item_id,),
        ).fetchone()
    return jsonify(_participant_payload(row))


@app.delete("/api/participants/<int:item_id>")
def delete_participant(item_id):
    with get_connection() as conn:
        result = conn.execute(
            "DELETE FROM programParticipants WHERE id_participant = ?",
            (item_id,),
        )
    if result.rowcount == 0:
        abort(404, description="Участник не найден")
    return "", 204


# --- Программы ---

PROGRAM_SELECT = """
    SELECT
        p.id_program AS id,
        p.name,
        p.category,
        p.dateStart AS date_start,
        p.dateEnd AS date_end,
        p.format,
        COUNT(link.id_participant) AS participants_count
    FROM programs p
    LEFT JOIN participant_programs link ON p.id_program = link.id_program
    GROUP BY p.id_program
"""


@app.get("/api/programs")
def list_programs():
    with get_connection() as conn:
        cms_rows = conn.execute(
            """
            SELECT
                cp.raw_json,
                COUNT(cap.application_id) AS participants_count
            FROM cms_programs cp
            LEFT JOIN cms_application_programs cap ON cap.program_document_id = cp.document_id
            GROUP BY cp.cms_id
            ORDER BY cp.cms_id
            """
        ).fetchall()
        if cms_rows:
            payload = []
            for row in cms_rows:
                item = json.loads(row["raw_json"])
                payload.append(_normalize_program_item(item, row["participants_count"]))
            return jsonify(payload)

        rows = conn.execute(f"{PROGRAM_SELECT} ORDER BY p.id_program").fetchall()
    return jsonify([row_to_dict(row) for row in rows])


@app.get("/api/programs/<int:item_id>")
def get_program(item_id):
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT
                cp.raw_json,
                (
                    SELECT COUNT(*)
                    FROM cms_application_programs cap
                    WHERE cap.program_document_id = cp.document_id
                ) AS participants_count
            FROM cms_programs cp
            WHERE cms_id = ?
            """,
            (item_id,),
        ).fetchone()
        if not row:
            row = conn.execute(
                f"{PROGRAM_SELECT} WHERE p.id_program = ?",
                (item_id,),
            ).fetchone()
        else:
            item = json.loads(row["raw_json"])
            return jsonify(_normalize_program_item(item, row["participants_count"]))
    if not row:
        abort(404, description="Программа не найдена")
    return jsonify(row_to_dict(row))


@app.post("/api/programs")
def create_program():
    data = request.get_json(silent=True) or {}
    if not data.get("name"):
        abort(400, description="Поле name обязательно")

    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO programs (name, category, dateStart, dateEnd, format)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                data.get("name"),
                data.get("category"),
                data.get("date_start"),
                data.get("date_end"),
                data.get("format"),
            ),
        )
        item_id = cursor.lastrowid
        row = conn.execute(
            f"{PROGRAM_SELECT} WHERE p.id_program = ?",
            (item_id,),
        ).fetchone()
    return jsonify(row_to_dict(row)), 201


@app.put("/api/programs/<int:item_id>")
def update_program(item_id):
    data = request.get_json(silent=True) or {}
    updates = _build_update(
        data,
        {
            "name": "name",
            "category": "category",
            "date_start": "dateStart",
            "date_end": "dateEnd",
            "format": "format",
        },
    )
    set_clause = ", ".join(f"{column} = ?" for column in updates)
    values = list(updates.values()) + [item_id]

    with get_connection() as conn:
        result = conn.execute(
            f"UPDATE programs SET {set_clause} WHERE id_program = ?",
            values,
        )
        if result.rowcount == 0:
            abort(404, description="Программа не найдена")
        row = conn.execute(
            f"{PROGRAM_SELECT} WHERE p.id_program = ?",
            (item_id,),
        ).fetchone()
    return jsonify(row_to_dict(row))


@app.delete("/api/programs/<int:item_id>")
def delete_program(item_id):
    with get_connection() as conn:
        result = conn.execute("DELETE FROM programs WHERE id_program = ?", (item_id,))
    if result.rowcount == 0:
        abort(404, description="Программа не найдена")
    return "", 204


# --- Мероприятия ---

EVENT_SELECT = """
    SELECT
        e.id_event AS id,
        e.name,
        e.event_date,
        e.place,
        e.participants_count,
        e.id_program,
        pr.name AS program
    FROM events e
    LEFT JOIN programs pr ON e.id_program = pr.id_program
"""


@app.get("/api/events")
def list_events():
    with get_connection() as conn:
        rows = conn.execute(f"{EVENT_SELECT} ORDER BY e.id_event").fetchall()
    return jsonify([row_to_dict(r) for r in rows])


@app.get("/api/events/<int:item_id>")
def get_event(item_id):
    with get_connection() as conn:
        row = conn.execute(
            f"{EVENT_SELECT} WHERE e.id_event = ?",
            (item_id,),
        ).fetchone()
    if not row:
        abort(404, description="Мероприятие не найдено")
    return jsonify(row_to_dict(row))


@app.post("/api/events")
def create_event():
    data = request.get_json(silent=True) or {}
    if not data.get("name"):
        abort(400, description="Поле name обязательно")

    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO events (name, event_date, id_program, place, participants_count)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                data.get("name"),
                data.get("event_date"),
                data.get("id_program"),
                data.get("place"),
                data.get("participants_count"),
            ),
        )
        item_id = cursor.lastrowid
        row = conn.execute(
            f"{EVENT_SELECT} WHERE e.id_event = ?",
            (item_id,),
        ).fetchone()
    return jsonify(row_to_dict(row)), 201


@app.put("/api/events/<int:item_id>")
def update_event(item_id):
    data = request.get_json(silent=True) or {}
    updates = _build_update(
        data,
        {
            "name": "name",
            "event_date": "event_date",
            "id_program": "id_program",
            "place": "place",
            "participants_count": "participants_count",
        },
    )
    set_clause = ", ".join(f"{column} = ?" for column in updates)
    values = list(updates.values()) + [item_id]

    with get_connection() as conn:
        result = conn.execute(
            f"UPDATE events SET {set_clause} WHERE id_event = ?",
            values,
        )
        if result.rowcount == 0:
            abort(404, description="Мероприятие не найдено")
        row = conn.execute(
            f"{EVENT_SELECT} WHERE e.id_event = ?",
            (item_id,),
        ).fetchone()
    return jsonify(row_to_dict(row))


@app.delete("/api/events/<int:item_id>")
def delete_event(item_id):
    with get_connection() as conn:
        result = conn.execute("DELETE FROM events WHERE id_event = ?", (item_id,))
    if result.rowcount == 0:
        abort(404, description="Мероприятие не найдено")
    return "", 204


# --- Статика ---

@app.get("/")
def index():
    return send_from_directory(ROOT, "index.html")


@app.get("/<path:filename>")
def static_files(filename):
    if filename.startswith("api"):
        abort(404)
    file_path = ROOT / filename
    if not file_path.is_file():
        abort(404)
    return send_from_directory(ROOT, filename)


@app.errorhandler(400)
@app.errorhandler(404)
def handle_error(error):
    description = getattr(error, "description", str(error))
    return jsonify({"error": description}), error.code


if __name__ == "__main__":
    init_db()
    app.run(host="127.0.0.1", port=5000, debug=True)
