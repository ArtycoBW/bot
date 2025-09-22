from appwrite.client import Client
from appwrite.services.databases import Databases
from appwrite.query import Query
from .config import Settings
from typing import Optional, Dict, Any


class AppwriteRepo:
    def __init__(self):

        self.client = Client()
        self.client.set_endpoint(Settings.APPWRITE_ENDPOINT)
        self.client.set_project(Settings.APPWRITE_PROJECT_ID)
        self.client.set_key(Settings.APPWRITE_API_KEY)

        self.db = Databases(self.client)

        self.db_id: str = Settings.APPWRITE_DATABASE_ID
        self.sub_col: str = Settings.APPWRITE_COLLECTION_SUBMISSIONS
        self.admins_col: str = Settings.APPWRITE_COLLECTION_ADMINS

        if not self.db_id:
            raise RuntimeError("Не задан APPWRITE_DATABASE_ID")
        if not self.sub_col:
            raise RuntimeError("Не задан APPWRITE_COLLECTION_SUBMISSIONS")
        if not self.admins_col:
            print("⚠️ APPWRITE_COLLECTION_ADMINS не задан — is_admin() всегда будет False")

    def get_submission_by_user(self, tg_user_id: str) -> Optional[Dict[str, Any]]:
        """Получить заявку по Telegram user id"""
        res = self.db.list_documents(
            database_id=self.db_id,
            collection_id=self.sub_col,
            queries=[Query.equal("tg_user_id", [tg_user_id]), Query.limit(1)],
        )
        docs = res.get("documents", [])
        return docs[0] if docs else None

    def create_submission(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Создать заявку. Статус по умолчанию — pending."""
        payload = dict(payload)  
        payload.setdefault("status", "pending")
        payload.pop("created_at", None)
        payload.pop("updated_at", None)

        return self.db.create_document(
            database_id=self.db_id,
            collection_id=self.sub_col,
            document_id="unique()",
            data=payload,
        )

    def list_submissions(
        self,
        status: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
        group: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Список заявок с фильтрами по статусу/группе и пагинацией."""
        queries = [Query.limit(page_size), Query.offset((page - 1) * page_size)]
        if status:
            queries.append(Query.equal("status", [status]))
        if group:
            queries.append(Query.equal("group", [group]))

        return self.db.list_documents(
            database_id=self.db_id,
            collection_id=self.sub_col,
            queries=queries,
        )

    def update_submission_status(self, doc_id: str, status: str, comment: str = "") -> Dict[str, Any]:
        """Обновить статус и комментарий администратора."""
        return self.db.update_document(
            database_id=self.db_id,
            collection_id=self.sub_col,
            document_id=doc_id,
            data={
                "status": status,
                "admin_comment": comment or "",
            },
        )

    def is_admin(self, tg_user_id: str) -> bool:
        """Проверка — пользователь админ?"""
        if not self.admins_col:
            return False

        try:
            res = self.db.list_documents(
                database_id=self.db_id,
                collection_id=self.admins_col,
                queries=[Query.equal("tg_user_id", [tg_user_id]), Query.limit(1)],
            )
            return bool(res.get("documents"))
        except Exception:
            return False

_repo_singleton: Optional[AppwriteRepo] = None

def get_repo() -> AppwriteRepo:
    global _repo_singleton
    if _repo_singleton is None:
        _repo_singleton = AppwriteRepo()
    return _repo_singleton
