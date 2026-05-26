from datetime import date, time
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

DAYS_OF_WEEK = {
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
}


class StudentQuery(BaseModel):
    student_id: int = Field(..., gt=0)


class NewStudent(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    parent_contact: str = Field(..., min_length=1, max_length=200)
    gender: str = Field(..., description="One of: F, M, Other")
    payment_method: str = Field(..., min_length=1)
    referee: Optional[str] = None

    @field_validator("gender")
    @classmethod
    def gender_must_be_known(cls, v: str) -> str:
        if v not in {"F", "M", "Other"}:
            raise ValueError("gender must be one of: F, M, Other")
        return v


class CourseSearchQuery(BaseModel):
    course_name_partial: str = Field(..., min_length=1)


class NewRegistration(BaseModel):
    student_id: int = Field(..., gt=0)
    course_id: int = Field(..., gt=0)
    day_of_week: str = Field(..., description="Full day name, e.g. 'Monday'")
    start_time: time
    number_of_lessons: int = Field(..., gt=0, le=200)
    first_lesson_date: Optional[date] = None

    @field_validator("day_of_week")
    @classmethod
    def day_must_be_known(cls, v: str) -> str:
        if v not in DAYS_OF_WEEK:
            raise ValueError(f"day_of_week must be one of: {sorted(DAYS_OF_WEEK)}")
        return v


class AttendanceRequest(BaseModel):
    lesson_id: int = Field(..., gt=0)
    student_id: int = Field(..., gt=0)


class BulkAttendanceRequest(BaseModel):
    lesson_id: int = Field(..., gt=0)
    student_ids: List[int] = Field(..., min_length=1)


class LessonParticipation(BaseModel):
    lesson_id: int = Field(..., gt=0)


class CalendarGenerationRequest(BaseModel):
    months_ahead: int = Field(..., gt=0, le=24)
