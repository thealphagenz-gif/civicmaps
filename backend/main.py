from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

import sqlite3
import os
import uuid
from datetime import datetime


# ============================================================
# APP CONFIGURATION
# ============================================================

app = FastAPI(
    title="CivicMap Mumbai API",
    description="Backend for CivicMap Mumbai civic complaint system",
    version="1.0.0"
)


# ============================================================
# CORS
# ============================================================
#
# This allows the frontend running on localhost:8080
# to communicate with this backend running on port 8000.
#

app.add_middleware(
    CORSMiddleware,
    # The API does not use cookies/authentication, so the browser can call it
    # from the local frontend or a separately hosted static frontend.
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# FOLDERS
# ============================================================

BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

DATABASE = os.path.join(
    BASE_DIR,
    "civicmap.db"
)

UPLOAD_FOLDER = os.path.join(
    BASE_DIR,
    "uploads"
)


os.makedirs(
    UPLOAD_FOLDER,
    exist_ok=True
)


# ============================================================
# STATIC PHOTO ACCESS
# ============================================================

app.mount(
    "/uploads",
    StaticFiles(directory=UPLOAD_FOLDER),
    name="uploads"
)


# ============================================================
# DATABASE
# ============================================================

def get_db():

    connection = sqlite3.connect(
        DATABASE
    )

    connection.row_factory = sqlite3.Row

    return connection


def init_database():

    connection = get_db()

    cursor = connection.cursor()


    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reports (

            id TEXT PRIMARY KEY,

            title TEXT NOT NULL,

            description TEXT NOT NULL,

            category TEXT NOT NULL,

            authority TEXT,

            status TEXT NOT NULL,

            latitude REAL NOT NULL,

            longitude REAL NOT NULL,

            location TEXT,

            photo_count INTEGER DEFAULT 0,

            created_at TEXT NOT NULL

        )
    """)


    cursor.execute("""
        CREATE TABLE IF NOT EXISTS report_photos (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            report_id TEXT NOT NULL,

            filename TEXT NOT NULL,

            original_name TEXT,

            uploaded_at TEXT NOT NULL,

            FOREIGN KEY(report_id)
                REFERENCES reports(id)

        )
    """)


    connection.commit()

    connection.close()


init_database()


# ============================================================
# HEALTH CHECK
# ============================================================

@app.get("/")
def home():

    # Serve the CivicMap frontend from the same origin as the API.
    # This is the safest local/demo setup because the browser cannot
    # accidentally point the complaint request at a different server.
    index_file = os.path.join(
        os.path.dirname(BASE_DIR),
        "index.html"
    )

    if os.path.exists(index_file):
        return FileResponse(index_file)

    return {
        "message": "CivicMap Mumbai backend is running",
        "status": "online"
    }



# ============================================================
# HEALTH CHECK
# ============================================================

@app.get("/api/health")
def api_health():
    return {
        "status": "online",
        "service": "CivicMap Mumbai API"
    }

# ============================================================
# CREATE CIVIC COMPLAINT
# ============================================================

@app.post("/api/reports")
async def create_report(

    title: str = Form(...),

    description: str = Form(...),

    category: str = Form(...),

    authority: str = Form(""),

    latitude: float = Form(...),

    longitude: float = Form(...),

    location: str = Form(""),

    photos: list[UploadFile] | None = File(default=None)

):

    # --------------------------------------------------------
    # BASIC VALIDATION
    # --------------------------------------------------------

    title = title.strip()

    description = description.strip()

    category = category.strip()

    authority = authority.strip()

    location = location.strip()


    if not title:

        raise HTTPException(
            status_code=400,
            detail="Issue title is required."
        )


    if not description:

        raise HTTPException(
            status_code=400,
            detail="Issue description is required."
        )


    if not category:

        raise HTTPException(
            status_code=400,
            detail="Issue category is required."
        )


    # --------------------------------------------------------
    # GENERATE CIVICMAP COMPLAINT ID
    # --------------------------------------------------------

    year = datetime.now().year

    unique_number = str(
        uuid.uuid4().int
    )[:6]


    report_id = (
        f"MUM-{year}-{unique_number}"
    )


    created_at = datetime.now().isoformat(
        timespec="seconds"
    )


    # --------------------------------------------------------
    # SAVE REPORT
    # --------------------------------------------------------

    connection = get_db()

    cursor = connection.cursor()


    cursor.execute(
        """
        INSERT INTO reports (
            id,
            title,
            description,
            category,
            authority,
            status,
            latitude,
            longitude,
            location,
            photo_count,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            report_id,
            title,
            description,
            category,
            authority,
            "Reported",
            latitude,
            longitude,
            location,
            0,
            created_at
        )
    )


    # --------------------------------------------------------
    # SAVE PHOTOS
    # --------------------------------------------------------

    saved_photos = 0


    if photos:

        for photo in photos[:5]:

            if not photo.filename:

                continue


            # Allow only common image types

            allowed_types = {
                "image/jpeg",
                "image/png",
                "image/webp"
            }


            if photo.content_type not in allowed_types:

                continue


            extension = os.path.splitext(
                photo.filename
            )[1].lower()


            safe_filename = (
                f"{report_id}_"
                f"{uuid.uuid4().hex}"
                f"{extension}"
            )


            file_path = os.path.join(
                UPLOAD_FOLDER,
                safe_filename
            )


            contents = await photo.read()


            with open(
                file_path,
                "wb"
            ) as file:

                file.write(contents)


            cursor.execute(
                """
                INSERT INTO report_photos (
                    report_id,
                    filename,
                    original_name,
                    uploaded_at
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    report_id,
                    safe_filename,
                    photo.filename,
                    created_at
                )
            )


            saved_photos += 1


    # --------------------------------------------------------
    # UPDATE PHOTO COUNT
    # --------------------------------------------------------

    cursor.execute(
        """
        UPDATE reports
        SET photo_count = ?
        WHERE id = ?
        """,
        (
            saved_photos,
            report_id
        )
    )


    connection.commit()

    connection.close()


    # --------------------------------------------------------
    # RESPONSE TO FRONTEND
    # --------------------------------------------------------

    return {

        "success": True,

        "id": report_id,

        "title": title,

        "description": description,

        "category": category,

        "authority": authority,

        "status": "Reported",

        "latitude": latitude,

        "longitude": longitude,

        "location": location,

        "photo_count": saved_photos,

        "date": datetime.now().strftime(
            "%d %b %Y"
        )

    }


# ============================================================
# GET ONE COMPLAINT
# ============================================================

@app.get("/api/reports/{report_id}")
def get_report(
    report_id: str
):

    connection = get_db()

    cursor = connection.cursor()


    cursor.execute(
        """
        SELECT *
        FROM reports
        WHERE id = ?
        """,
        (report_id,)
    )


    report = cursor.fetchone()


    if not report:

        connection.close()

        raise HTTPException(
            status_code=404,
            detail="Complaint not found."
        )


    result = dict(report)


    # --------------------------------------------------------
    # GET PHOTOS
    # --------------------------------------------------------

    cursor.execute(
        """
        SELECT filename, original_name
        FROM report_photos
        WHERE report_id = ?
        """,
        (report_id,)
    )


    photos = cursor.fetchall()


    result["photos"] = [

        {
            "filename": p["filename"],

            "original_name":
                p["original_name"],

            "url":
                f"/uploads/{p['filename']}"

        }

        for p in photos

    ]


    connection.close()


    return result


# ============================================================
# GET ALL COMPLAINTS
# ============================================================

@app.get("/api/reports")
def get_reports():

    connection = get_db()

    cursor = connection.cursor()


    cursor.execute(
        """
        SELECT *
        FROM reports
        ORDER BY created_at DESC
        """
    )


    reports = cursor.fetchall()


    connection.close()


    return {

        "count": len(reports),

        "reports": [
            dict(report)
            for report in reports
        ]

    }

# ============================================================
# SERVE FRONTEND FROM FASTAPI (LOCAL/SELF-HOSTED MODE)
# ============================================================
# Serving the frontend from the same FastAPI origin removes the most common
# "Failed to fetch" cause: the browser cannot reach a separately-running
# frontend/backend origin or the API port is wrong. API routes above remain
# available because they are registered before this catch-all mount.

FRONTEND_DIR = os.path.dirname(BASE_DIR)

app.mount(
    "/",
    StaticFiles(directory=FRONTEND_DIR, html=True),
    name="frontend"
)


# ============================================================
# LOCAL LAUNCH
# ============================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8000,
        reload=True
    )
