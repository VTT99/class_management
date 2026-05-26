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
    student_ids: List[int] = Field(default_factory=list)
    push_absent: bool = Field(
        default=False,
        description="If true, any student registered for this lesson but absent from student_ids is auto-registered to the next available class in the same course.",
    )


class LessonParticipation(BaseModel):
    lesson_id: int = Field(..., gt=0)


class PushItem(BaseModel):
    student_id: int = Field(..., gt=0)
    target_lesson_id: Optional[int] = Field(default=None, description="Lesson to push the absentee into; None leaves the credit unassigned.")


class ApplyPushes(BaseModel):
    items: List[PushItem] = Field(default_factory=list)


class CalendarGenerationRequest(BaseModel):
    months_ahead: int = Field(..., gt=0, le=24)


class NewLesson(BaseModel):
    course_id: int = Field(..., gt=0)
    start_datetime: str = Field(..., description="YYYY-MM-DD HH:MM:SS")
    end_datetime: str = Field(..., description="YYYY-MM-DD HH:MM:SS")


class SingleRegistration(BaseModel):
    student_id: int = Field(..., gt=0)
    lesson_id: int = Field(..., gt=0)
    payment_method: Optional[str] = Field(default=None, description="If set, also records a 1-class purchase row.")


class RegistrationStreak(BaseModel):
    student_id: int = Field(..., gt=0)
    lesson_id: int = Field(..., gt=0, description="Reference lesson; registers this + the next N-1 in the same course.")
    count: int = Field(..., gt=0, le=104)
    payment_method: Optional[str] = Field(default=None, description="If set, also records a purchase row of size `count`.")


class NewCourse(BaseModel):
    course_name: str = Field(..., min_length=1, max_length=120)
    active: bool = True


class ExtendCourse(BaseModel):
    course_id: int = Field(..., gt=0)
    weeks: int = Field(..., gt=0, le=104, description="Extend each detected weekly slot by this many weeks beyond the last occurrence.")


class LessonSpec(BaseModel):
    course_id: int = Field(..., gt=0)
    start_datetime: str = Field(..., description="YYYY-MM-DD HH:MM:SS")
    end_datetime: str = Field(..., description="YYYY-MM-DD HH:MM:SS")


class NewLessonsBulk(BaseModel):
    lessons: List[LessonSpec] = Field(..., min_length=1, max_length=500)
