"""
Campus Portal Database Schemas

Define MongoDB collection schemas using Pydantic models. Each model name maps to a
collection with the lowercase class name.

Examples:
- CampusUser -> "campususer"
- Event -> "event"
- AttendanceRecord -> "attendancerecord"
- AttendanceOverride -> "attendanceoverride"
"""

from datetime import date as DateType, datetime as DateTimeType
from typing import Literal, Optional
from pydantic import BaseModel, Field, EmailStr


class CampusUser(BaseModel):
    """
    Users of the campus portal (demo auth)
    Collection: "campususer"
    """
    role: Literal["student", "teacher"] = Field(..., description="User role")
    name: str = Field(..., description="Full name")
    email: EmailStr = Field(..., description="Email address")
    mobile: Optional[str] = Field(None, description="Mobile number")
    roll: Optional[str] = Field(None, description="Roll number for students")


class Event(BaseModel):
    """
    Campus events created by teachers and visible to all
    Collection: "event"
    """
    title: str = Field(..., description="Event title")
    description: Optional[str] = Field(None, description="Event details")
    date: DateTimeType = Field(..., description="Event date/time (ISO)")
    location: Optional[str] = Field(None, description="Location or venue")
    created_by_role: Literal["teacher", "student"] = Field("teacher", description="Who created the event")


class AttendanceRecord(BaseModel):
    """
    Daily attendance entries marked by teachers
    Collection: "attendancerecord"
    """
    roll: str = Field(..., description="Student roll number")
    attendance_date: DateType = Field(..., description="Attendance date (YYYY-MM-DD)")
    status: Literal["present", "absent"] = Field(..., description="Attendance status")
    marked_by_role: Literal["teacher"] = Field("teacher", description="Marker role")


class AttendanceOverride(BaseModel):
    """
    Manual percentage overrides per student (set by teachers)
    Collection: "attendanceoverride"
    """
    roll: str = Field(..., description="Student roll number")
    manual_percentage: float = Field(..., ge=0, le=100, description="Manual attendance percentage")
