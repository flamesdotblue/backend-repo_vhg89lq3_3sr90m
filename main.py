import os
from datetime import datetime, date
from typing import List, Optional, Literal, Any, Dict

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from bson import ObjectId

from database import db, create_document, get_documents
from schemas import CampusUser, Event, AttendanceRecord, AttendanceOverride


app = FastAPI(title="Campus Portal API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -----------------------------
# Helpers
# -----------------------------

def serialize_id(doc: Dict[str, Any]) -> Dict[str, Any]:
    if not doc:
        return doc
    d = dict(doc)
    if "_id" in d:
        d["id"] = str(d.pop("_id"))
    # Convert datetime/date to isoformat for JSON safety
    for k, v in list(d.items()):
        if isinstance(v, (datetime, date)):
            d[k] = v.isoformat()
    return d


def oid(id_str: str) -> ObjectId:
    try:
        return ObjectId(id_str)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid ID format")


# -----------------------------
# Health & meta
# -----------------------------

@app.get("/")
def read_root():
    return {"message": "Campus Portal API running"}


@app.get("/test")
def test_database():
    """Test endpoint to check if database is available and accessible"""
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }

    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Set"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:80]}"
        else:
            response["database"] = "⚠️  Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:80]}"

    response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"
    return response


class SchemaField(BaseModel):
    name: str
    type: str
    required: bool = True
    description: Optional[str] = None


@app.get("/schema")
def get_schema():
    """Expose basic schema info for viewer/tools"""
    return {
        "campususer": CampusUser.model_json_schema(),
        "event": Event.model_json_schema(),
        "attendancerecord": AttendanceRecord.model_json_schema(),
        "attendanceoverride": AttendanceOverride.model_json_schema(),
    }


# -----------------------------
# Auth (demo)
# -----------------------------

class DemoLoginRequest(BaseModel):
    role: Literal["student", "teacher"]
    name: str
    email: EmailStr
    mobile: Optional[str] = None
    roll: Optional[str] = None


@app.post("/auth/demo-login")
def demo_login(payload: DemoLoginRequest):
    """
    Demo login: upsert user by email and return user record.
    """
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")

    existing = db.campususer.find_one({"email": payload.email})
    data = payload.model_dump()
    data["updated_at"] = datetime.utcnow()

    if existing:
        db.campususer.update_one({"_id": existing["_id"]}, {"$set": data})
        user = db.campususer.find_one({"_id": existing["_id"]})
    else:
        user_id = create_document("campususer", CampusUser(**data))
        user = db.campususer.find_one({"_id": ObjectId(user_id)})

    return serialize_id(user)


# -----------------------------
# Users
# -----------------------------

class UpdateUserRequest(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    mobile: Optional[str] = None
    roll: Optional[str] = None


@app.put("/users/{user_id}")
def update_user(user_id: str, payload: UpdateUserRequest):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    updates = {k: v for k, v in payload.model_dump(exclude_none=True).items()}
    if not updates:
        return {"updated": False}
    updates["updated_at"] = datetime.utcnow()
    result = db.campususer.update_one({"_id": oid(user_id)}, {"$set": updates})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    doc = db.campususer.find_one({"_id": oid(user_id)})
    return serialize_id(doc)


# -----------------------------
# Events CRUD
# -----------------------------

class EventCreateRequest(BaseModel):
    title: str
    description: Optional[str] = None
    date: datetime
    location: Optional[str] = None
    created_by_role: Literal["teacher", "student"] = "teacher"


@app.get("/events")
def list_events(limit: int = Query(100, ge=1, le=500)):
    docs = db.event.find({}).sort("date", 1).limit(limit)
    return [serialize_id(d) for d in docs]


@app.post("/events")
def create_event(payload: EventCreateRequest):
    event_id = create_document("event", Event(**payload.model_dump()))
    doc = db.event.find_one({"_id": ObjectId(event_id)})
    return serialize_id(doc)


@app.put("/events/{event_id}")
def update_event(event_id: str, payload: EventCreateRequest):
    result = db.event.update_one({"_id": oid(event_id)}, {"$set": payload.model_dump()})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Event not found")
    doc = db.event.find_one({"_id": oid(event_id)})
    return serialize_id(doc)


@app.delete("/events/{event_id}")
def delete_event(event_id: str):
    result = db.event.delete_one({"_id": oid(event_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Event not found")
    return {"deleted": True}


# -----------------------------
# Attendance
# -----------------------------

class AttendanceMark(BaseModel):
    roll: str
    status: Literal["present", "absent"]


class AttendanceMarkRequest(BaseModel):
    date: date
    entries: List[AttendanceMark]


@app.post("/attendance/mark")
def mark_attendance(payload: AttendanceMarkRequest):
    if not payload.entries:
        raise HTTPException(status_code=400, detail="No entries to mark")
    inserted_ids = []
    for e in payload.entries:
        doc = AttendanceRecord(roll=e.roll, status=e.status, attendance_date=payload.date, marked_by_role="teacher")
        ins_id = create_document("attendancerecord", doc)
        inserted_ids.append(ins_id)
    return {"inserted": len(inserted_ids), "ids": inserted_ids}


@app.get("/attendance/recent")
def recent_attendance(limit: int = Query(20, ge=1, le=200)):
    docs = db.attendancerecord.find({}).sort("attendance_date", -1).limit(limit)
    return [serialize_id(d) for d in docs]


class ManualPercentageRequest(BaseModel):
    roll: str
    manual_percentage: float


@app.post("/attendance/manual-percentage")
def set_manual_percentage(payload: ManualPercentageRequest):
    existing = db.attendanceoverride.find_one({"roll": payload.roll})
    if existing:
        db.attendanceoverride.update_one({"_id": existing["_id"]}, {"$set": payload.model_dump()})
        doc = db.attendanceoverride.find_one({"_id": existing["_id"]})
    else:
        ins_id = create_document("attendanceoverride", AttendanceOverride(**payload.model_dump()))
        doc = db.attendanceoverride.find_one({"_id": ObjectId(ins_id)})
    return serialize_id(doc)


@app.get("/attendance/summary")
def attendance_summary(roll: str = Query(..., description="Student roll number")):
    """Compute present/absent counts and percentage, honoring manual override if set."""
    total_present = db.attendancerecord.count_documents({"roll": roll, "status": "present"})
    total_absent = db.attendancerecord.count_documents({"roll": roll, "status": "absent"})
    total = total_present + total_absent
    percentage = (total_present / total * 100.0) if total > 0 else 0.0
    override = db.attendanceoverride.find_one({"roll": roll})
    if override and isinstance(override.get("manual_percentage"), (int, float)):
        percentage = float(override["manual_percentage"])
    return {
        "roll": roll,
        "presentDays": total_present,
        "absentDays": total_absent,
        "percentage": round(percentage, 2)
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
