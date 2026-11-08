# CampusPulse ⚡ Live Events & API Contract Workshop

This project implements the complete **API Contract** specified in the workshop screenshot, connecting both a live backend API and an interactive frontend.

---

## 📋 The API Contract Specification

| Method | Endpoint | Description | Authentication |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/events` | Browse events catalog with capacities and metadata | Public |
| `GET` | `/api/events/{id}` | Event details, registered attendee count & availability | Public |
| `POST` | `/api/registrations` | Create registration (**201 Created** or **409 Conflict**) | **Required** (`X-User-Id`) |
| `GET` | `/api/me/registrations` | Current user's registered passes | **Required** (`X-User-Id`) |
| `GET` | `/api/events/{id}/registrations` | Attendee list (**Owning organizer only**, 403 Forbidden otherwise) | **Required** (`X-User-Id`) |

> 🔒 **Authentication Rule**: Registration and private attendee lists require user identification passed via the `X-User-Id` request header (or `user_id` payload).

---

## 🌐 Base URLs & Architecture

The project supports dual operation modes:

1. **Live Remote API Backend**:
   - Base URL: `https://hello-world-workshop.onrender.com`
   - Real-time catalog of 17+ live events, workshop demo users, and verified pass reservations.
2. **Local Flask Backend (`backend/app.py`)**:
   - Running at: `http://127.0.0.1:5001`
   - Connected directly to your **Supabase database** (`user`, `events`, `registrations` tables).
   - Features built-in CORS middleware, authentication enforcement, and transparent remote proxying (`/api/remote/...`).

---

## 🚀 Running the Project

### Option A: Run the Full-Stack App (Backend + Frontend)
Activate the virtual environment and run the Flask app:

```bash
cd /Users/souvikbhattacharya/Desktop/workshop
./my-app/venv/bin/python backend/app.py
```

Then open your browser at:
👉 **[http://127.0.0.1:5001](http://127.0.0.1:5001)**

### Option B: Open the Frontend Standalone
You can also open [`frontend/index.html`](file:///Users/souvikbhattacharya/Desktop/workshop/frontend/index.html) directly in any modern browser or via VS Code Live Server.

---

## 🧪 Testing the Endpoints with cURL

### 1. Browse Events (`GET /api/events`)
```bash
curl -X GET https://hello-world-workshop.onrender.com/api/events
```

### 2. Event Details (`GET /api/events/{id}`)
```bash
curl -X GET https://hello-world-workshop.onrender.com/api/events/8415678e-2eeb-5fd4-82f5-ffec15121856
```

### 3. Create Registration (`POST /api/registrations`)
```bash
curl -X POST https://hello-world-workshop.onrender.com/api/registrations \
  -H "Content-Type: application/json" \
  -H "X-User-Id: 0d14cdaa-bdff-5670-8c81-f5dee3342e8c" \
  -d '{"event_id": "8415678e-2eeb-5fd4-82f5-ffec15121856"}'
```
*Response*: `201 Created` with pass record, or `409 Conflict` if already registered.

### 4. My Passes (`GET /api/me/registrations`)
```bash
curl -X GET https://hello-world-workshop.onrender.com/api/me/registrations \
  -H "X-User-Id: 0d14cdaa-bdff-5670-8c81-f5dee3342e8c"
```

### 5. Attendee List - Owning Organizer Only (`GET /api/events/{id}/registrations`)
```bash
# As the Owning Organizer (Returns 200 OK + attendee roster):
curl -X GET https://hello-world-workshop.onrender.com/api/events/8415678e-2eeb-5fd4-82f5-ffec15121856/registrations \
  -H "X-User-Id: 069ec420-b3f8-5206-9eee-179f9183253a"

# As a Student (Returns 403 Forbidden):
curl -X GET https://hello-world-workshop.onrender.com/api/events/8415678e-2eeb-5fd4-82f5-ffec15121856/registrations \
  -H "X-User-Id: 0d14cdaa-bdff-5670-8c81-f5dee3342e8c"
```

---

## 🎨 Interactive Frontend Features

- **Live Dynamic Cards**: Renders events fetched in real-time from the API.
- **1-Click RSVP**: Performs real `POST /api/registrations` with instant visual feedback and celebratory toasts.
- **Demo Persona Switcher**: Switch between Student and Organizer roles with live `X-User-Id` header injection.
- **My Passes Modal**: Displays digital ticket stubs from `GET /api/me/registrations`.
- **Organizer Console**: View attendee rosters from `GET /api/events/{id}/registrations` with 403 permission verification.
- **API Inspector Modal**: Test all 5 endpoints live right inside the web interface with single-click execution.
