from pydantic import BaseModel, EmailStr
from typing import Optional

# Создание новой заявки
class SubmissionCreate(BaseModel):
    tg_user_id: str
    full_name: str
    group: str
    email: EmailStr
    birthDate: Optional[str] = None
    books: Optional[str] = None
    likedRecentMovie: Optional[str] = None
    aboutYou: Optional[str] = None
    afterUniversity: Optional[str] = None
    redDiploma: Optional[str] = None        # "yes" | "no" | "undecided"
    scienceInterest: Optional[str] = None   # "yes" | "no" | "maybe"
    thesisTopic: str
    thesisDescription: Optional[str] = None
    analogsProsCons: Optional[str] = None
    plannedFeatures: Optional[str] = None
    techStack: Optional[str] = None

# Частичное обновление заявки (в т.ч. админом)
class SubmissionUpdate(BaseModel):
    full_name: Optional[str] = None
    group: Optional[str] = None
    email: Optional[EmailStr] = None
    birthDate: Optional[str] = None
    books: Optional[str] = None
    likedRecentMovie: Optional[str] = None
    aboutYou: Optional[str] = None
    afterUniversity: Optional[str] = None
    redDiploma: Optional[str] = None
    scienceInterest: Optional[str] = None
    thesisTopic: Optional[str] = None
    thesisDescription: Optional[str] = None
    analogsProsCons: Optional[str] = None
    plannedFeatures: Optional[str] = None
    techStack: Optional[str] = None
    admin_comment: Optional[str] = None
    allow_student_reply: Optional[bool] = None
    admin_question: Optional[str] = None
    student_answer: Optional[str] = None
    status: Optional[str] = None            # "pending" | "approved" | "rejected"

# Решение по заявке
class Decision(BaseModel):
    doc_id: str
    status: str               # "approved" | "rejected"
    comment: str = ""
    student_tg_id: str

# Просто комментарий админа (без смены статуса)
class AdminNote(BaseModel):
    doc_id: str
    comment: str

# Тоггл разрешения ответа студента (чекбокс)
class AllowReplyToggle(BaseModel):
    doc_id: str
    allow: bool

# Вопрос админа студенту
class AdminQuestion(BaseModel):
    doc_id: str
    question: str
    allow_student_reply: bool = True

# Ответ студента админу
class StudentAnswer(BaseModel):
    doc_id: str
    tg_user_id: str
    answer: str
