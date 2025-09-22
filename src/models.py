from pydantic import BaseModel, EmailStr

class SubmissionIn(BaseModel):
    tg_user_id: str
    full_name: str
    group: str
    email: EmailStr
    thesis: str

class Decision(BaseModel):
    doc_id: str
    status: str   # "approved" | "rejected"
    comment: str = ""
    student_tg_id: str
