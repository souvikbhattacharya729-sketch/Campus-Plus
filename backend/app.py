import os
import ssl
import json
import urllib.request
import urllib.error
import certifi
from flask import Flask, request, jsonify, send_file, Response
from supabase import create_client, Client
from postgrest import APIError
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Base directory paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.abspath(os.path.join(BASE_DIR, "../frontend"))
FRONTEND_STITCH_DIR = os.path.join(FRONTEND_DIR, "stitch_campus_event_explorer 2")

# Initialize Flask app
app = Flask(__name__, static_folder=FRONTEND_DIR)

# Remote reference base URL from workshop
REMOTE_BASE_URL = os.environ.get("REMOTE_BASE_URL", "https://hello-world-workshop.onrender.com")

# Initialize Supabase client
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in .env")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# SSL context with certifi for verified outbound HTTPS requests
ssl_context = ssl.create_default_context(cafile=certifi.where())


# ----------------------------------------------------
# CORS Middleware
# ----------------------------------------------------
@app.after_request
def add_cors_headers(response: Response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-User-Id, Authorization, Accept"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    return response


# ----------------------------------------------------
# Authentication Helper
# ----------------------------------------------------
def get_current_user_id() -> str | None:
    """Extract authenticated user ID from X-User-Id header or query / body parameter."""
    user_id = request.headers.get("X-User-Id")
    if not user_id:
        user_id = request.args.get("user_id")
    if not user_id and request.is_json and request.json:
        user_id = request.json.get("user_id")
    return user_id.strip() if user_id else None


# ----------------------------------------------------
# 1. GET /api/events - Browse events
# ----------------------------------------------------
@app.route("/api/events", methods=["GET", "OPTIONS"])
def get_events():
    if request.method == "OPTIONS":
        return "", 200

    try:
        limit = request.args.get("limit", default=100, type=int)
        offset = request.args.get("offset", default=0, type=int)

        query = supabase.table("events").select("*").range(offset, offset + limit - 1)
        response = query.execute()
        events = response.data or []

        # Count current registrations for each event so capacity is accurate
        regs_res = supabase.table("registrations").select("event_id").execute()
        reg_counts = {}
        for r in (regs_res.data or []):
            eid = r.get("event_id")
            if eid:
                reg_counts[eid] = reg_counts.get(eid, 0) + 1

        # Alias organizer_id to organiser_id and attach live capacity metrics
        for ev in events:
            eid = ev.get("id")
            cap = ev.get("capacity") or 50
            reg_cnt = reg_counts.get(eid, 0)
            ev["registered_count"] = reg_cnt
            ev["spots_remaining"] = max(0, cap - reg_cnt) if cap > 0 else 0
            if "organizer_id" in ev and "organiser_id" not in ev:
                ev["organiser_id"] = ev["organizer_id"]

        return jsonify(events), 200
    except APIError as e:
        return jsonify({"error": e.message}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ----------------------------------------------------
# 2. GET /api/events/{id} - Event details
# ----------------------------------------------------
@app.route("/api/events/<event_id>", methods=["GET", "OPTIONS"])
def get_event_detail(event_id):
    if request.method == "OPTIONS":
        return "", 200

    try:
        response = supabase.table("events").select("*").eq("id", event_id).execute()
        if not response.data or len(response.data) == 0:
            return jsonify({"error": f"Event with id '{event_id}' not found."}), 404

        event = response.data[0]
        if "organizer_id" in event and "organiser_id" not in event:
            event["organiser_id"] = event["organizer_id"]

        # Count current registrations for capacity stats
        regs = supabase.table("registrations").select("id").eq("event_id", event_id).execute()
        reg_cnt = len(regs.data or [])
        cap = event.get("capacity") or 50
        event["registered_count"] = reg_cnt
        event["spots_remaining"] = max(0, cap - reg_cnt) if cap > 0 else 0

        return jsonify(event), 200
    except APIError as e:
        return jsonify({"error": e.message}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ----------------------------------------------------
# 3. POST /api/registrations - Create registration (201 or 409)
# ----------------------------------------------------
@app.route("/api/registrations", methods=["POST", "OPTIONS"])
def create_registration():
    if request.method == "OPTIONS":
        return "", 200

    user_id = get_current_user_id()
    if not user_id:
        return jsonify({"error": "Select a user from the dropdown first. (X-User-Id header required)"}), 401

    body = request.get_json(silent=True) or {}
    event_id = body.get("event_id")

    if not event_id:
        return jsonify({"error": "event_id is required in request body."}), 400

    try:
        # Check event existence
        event_res = supabase.table("events").select("*").eq("id", event_id).execute()
        if not event_res.data:
            return jsonify({"error": f"Event '{event_id}' does not exist."}), 404
        
        event = event_res.data[0]
        capacity = event.get("capacity") or 0

        # Check existing registrations count for capacity
        regs_res = supabase.table("registrations").select("id").eq("event_id", event_id).execute()
        current_count = len(regs_res.data or [])

        if capacity > 0 and current_count >= capacity:
            return jsonify({
                "error": "Event is at full capacity. Cannot register.",
                "status": "FULL",
                "capacity": capacity,
                "registered_count": current_count,
                "spots_remaining": 0
            }), 409

        # Check for duplicate registration
        dup_res = supabase.table("registrations").select("id").eq("event_id", event_id).eq("user_id", user_id).execute()
        if dup_res.data and len(dup_res.data) > 0:
            return jsonify({
                "error": "User is already registered for this event.",
                "registration_id": dup_res.data[0]["id"],
                "registered_count": current_count,
                "spots_remaining": max(0, capacity - current_count) if capacity > 0 else 0,
                "capacity": capacity
            }), 409

        # Insert new registration
        insert_res = supabase.table("registrations").insert({
            "event_id": event_id,
            "user_id": user_id
        }).execute()

        new_reg = insert_res.data[0] if insert_res.data else {"event_id": event_id, "user_id": user_id}
        if "createdAt" not in new_reg:
            new_reg["createdAt"] = None

        new_reg["registered_count"] = current_count + 1
        new_reg["spots_remaining"] = max(0, capacity - (current_count + 1)) if capacity > 0 else 0
        new_reg["capacity"] = capacity

        return jsonify(new_reg), 201

    except APIError as e:
        return jsonify({"error": e.message}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ----------------------------------------------------
# 4. GET /api/me/registrations - Current user's registrations
# ----------------------------------------------------
@app.route("/api/me/registrations", methods=["GET", "OPTIONS"])
def get_my_registrations():
    if request.method == "OPTIONS":
        return "", 200

    user_id = get_current_user_id()
    if not user_id:
        return jsonify({"error": "Select a user from the dropdown first. (X-User-Id header required)"}), 401

    try:
        response = supabase.table("registrations").select("*").eq("user_id", user_id).execute()
        registrations = response.data or []
        for reg in registrations:
            if "createdAt" not in reg:
                reg["createdAt"] = None
        return jsonify(registrations), 200
    except APIError as e:
        return jsonify({"error": e.message}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ----------------------------------------------------
# 5. GET /api/events/{id}/registrations - Attendee list (owning organizer only)
# ----------------------------------------------------
@app.route("/api/events/<event_id>/registrations", methods=["GET", "OPTIONS"])
def get_event_attendees(event_id):
    if request.method == "OPTIONS":
        return "", 200

    user_id = get_current_user_id()
    if not user_id:
        return jsonify({"error": "Select a user from the dropdown first. (X-User-Id header required)"}), 401

    try:
        # Check event ownership
        event_res = supabase.table("events").select("*").eq("id", event_id).execute()
        if not event_res.data:
            return jsonify({"error": f"Event '{event_id}' not found."}), 404

        event = event_res.data[0]
        organizer_id = event.get("organizer_id") or event.get("organiser_id")

        if organizer_id != user_id:
            return jsonify({"error": "Only the owning organiser can view attendees."}), 403

        # Fetch attendee registrations
        regs_res = supabase.table("registrations").select("*").eq("event_id", event_id).execute()
        regs = regs_res.data or []
        for reg in regs:
            if "createdAt" not in reg:
                reg["createdAt"] = None

        return jsonify(regs), 200

    except APIError as e:
        return jsonify({"error": e.message}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ----------------------------------------------------
# 6. GET /api/users - List users (for demo persona switcher)
# ----------------------------------------------------
@app.route("/api/users", methods=["GET", "OPTIONS"])
def get_users():
    if request.method == "OPTIONS":
        return "", 200

    try:
        response = supabase.table("user").select("id, email, role").execute()
        return jsonify(response.data or []), 200
    except APIError as e:
        return jsonify({"error": e.message}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# In-memory registration tracker for proxy mode
remote_reg_counts = {}

# ----------------------------------------------------
# Transparent Remote Proxy for https://hello-world-workshop.onrender.com
# Enables browser to fetch from live Render backend without CORS restrictions!
# ----------------------------------------------------
@app.route("/api/remote/<path:subpath>", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])
def remote_proxy(subpath):
    if request.method == "OPTIONS":
        return "", 200

    target_url = f"{REMOTE_BASE_URL.rstrip('/')}/api/{subpath}"
    if request.query_string:
        target_url += f"?{request.query_string.decode('utf-8')}"

    headers = {"Accept": "application/json"}
    if "X-User-Id" in request.headers:
        headers["X-User-Id"] = request.headers["X-User-Id"]

    data = None
    posted_event_id = None
    if request.method in ["POST", "PUT", "PATCH"]:
        headers["Content-Type"] = "application/json"
        data = request.get_data()
        try:
            parsed_body = json.loads(data.decode("utf-8"))
            posted_event_id = parsed_body.get("event_id")
        except Exception:
            pass

    req = urllib.request.Request(target_url, data=data, headers=headers, method=request.method)

    try:
        with urllib.request.urlopen(req, context=ssl_context) as resp:
            content = resp.read()
            status_code = resp.status

            # Enrich response with live capacity metrics if applicable
            try:
                res_json = json.loads(content.decode("utf-8"))

                # If registration succeeded, record and return updated counts
                if subpath == "registrations" and request.method == "POST" and status_code == 201:
                    eid = posted_event_id or res_json.get("event_id")
                    if eid:
                        remote_reg_counts[eid] = remote_reg_counts.get(eid, 0) + 1
                        res_json["registered_count"] = remote_reg_counts[eid]
                        return jsonify(res_json), 201

                # If browsing events, enrich each event with registered_count and spots_remaining
                elif subpath == "events" and request.method == "GET" and isinstance(res_json, list):
                    for ev in res_json:
                        eid = ev.get("id")
                        cap = ev.get("capacity") or 50
                        reg_cnt = remote_reg_counts.get(eid, 0)
                        ev["registered_count"] = reg_cnt
                        ev["spots_remaining"] = max(0, cap - reg_cnt) if cap > 0 else 0
                    return jsonify(res_json), 200

                # If getting single event details
                elif subpath.startswith("events/") and request.method == "GET" and isinstance(res_json, dict):
                    eid = res_json.get("id")
                    cap = res_json.get("capacity") or 50
                    reg_cnt = remote_reg_counts.get(eid, 0)
                    res_json["registered_count"] = reg_cnt
                    res_json["spots_remaining"] = max(0, cap - reg_cnt) if cap > 0 else 0
                    return jsonify(res_json), 200

            except Exception:
                pass

            return Response(content, status=status_code, content_type="application/json")
    except urllib.error.HTTPError as err:
        err_content = err.read()
        return Response(err_content, status=err.code, content_type="application/json")
    except Exception as err:
        return jsonify({"error": f"Proxy error: {str(err)}"}), 502


# ----------------------------------------------------
# Serve Frontend
# ----------------------------------------------------
@app.route("/")
def serve_index():
    index_file = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_file):
        return send_file(index_file)
    stitch_file = os.path.join(FRONTEND_STITCH_DIR, "code.html")
    if os.path.exists(stitch_file):
        return send_file(stitch_file)
    return "<h1>CampusPulse API Live</h1><p>Visit /api/events for events.</p>"


@app.route("/frontend/<path:filename>")
def serve_frontend_assets(filename):
    file_path = os.path.join(FRONTEND_DIR, filename)
    if os.path.exists(file_path):
        return send_file(file_path)
    stitch_path = os.path.join(FRONTEND_STITCH_DIR, filename)
    if os.path.exists(stitch_path):
        return send_file(stitch_path)
    return "File not found", 404


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    print(f"🚀 CampusPulse API Backend running on http://127.0.0.1:{port}")
    print(f"   - Local endpoints:  http://127.0.0.1:{port}/api/events")
    print(f"   - Remote proxy:     http://127.0.0.1:{port}/api/remote/events")
    print(f"   - Live UI frontend: http://127.0.0.1:{port}/")
    app.run(host="0.0.0.0", port=port, debug=True)