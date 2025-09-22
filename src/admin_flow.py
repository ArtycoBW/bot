from __future__ import annotations

import os
import logging
from typing import Optional, List

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext

from .appwrite_client import get_repo

try:
    import gspread
    from google.oauth2.service_account import Credentials
except Exception:
    gspread = None
    Credentials = None

router = Router()

# -----------------------------------------------------------------------------


class AdminState(StatesGroup):
    waiting_comment = State()      # для approve/reject
    waiting_group = State()
    waiting_note = State()         # для «просто комментария»


def _status_title(s: str) -> str:
    return {
        "pending": "⏳ В ожидании",
        "approved": "✅ Принятые",
        "rejected": "❌ Отклонённые",
    }.get(s, s)


def _safe_count(status: str) -> str:
    try:
        repo = get_repo()
        res = repo.list_submissions(status=status, page=1, page_size=1)
        return str(res.get("total", "?"))
    except Exception:
        return "?"


def _get_admin_chat_ids() -> List[int]:
    """
    Возвращает список tg_user_id всех админов.
    """
    repo = get_repo()
    try:
        docs = repo.db.list_documents(
            database_id=repo.db_id,
            collection_id=repo.admins_col,
        ).get("documents", [])
        ids: List[int] = []
        for d in docs:
            try:
                ids.append(int(str(d.get("tg_user_id", "")).strip()))
            except Exception:
                pass
        return ids
    except Exception:
        return []


# -------------------------- Google Sheets helpers ----------------------------
def _get_sheet():
    if gspread is None or Credentials is None:
        raise RuntimeError("gspread/google-auth не установлены в окружении")
    sheet_id = os.getenv("GOOGLE_SHEET_ID")
    tab_name = os.getenv("GOOGLE_SHEET_TAB", "Лист1")
    sa_path = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON_PATH", "./service_account.json")
    if not sheet_id:
        raise RuntimeError("GOOGLE_SHEET_ID не задан")
    if not os.path.exists(sa_path):
        raise RuntimeError(f"service_account.json не найден по пути: {sa_path}")

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_file(sa_path, scopes=scopes)
    client = gspread.authorize(creds)
    sh = client.open_by_key(sheet_id)
    try:
        ws = sh.worksheet(tab_name)
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet(title=tab_name, rows="2000", cols="40")
    return ws


def _header_indexes(ws) -> dict[str, int]:
    headers = ws.row_values(1)
    return {(h or "").strip().lower(): i + 1 for i, h in enumerate(headers)}


def update_sheet_status_and_comment(appwrite_id: str, new_status: Optional[str], comment: Optional[str]):
    """
    Обновляет статус/комментарий/Updated At в Sheets.
    Если new_status is None — меняем только комментарий и Updated At.
    """
    try:
        ws = _get_sheet()
        matches = ws.findall(appwrite_id)
        if not matches:
            logging.warning("[Sheets] Не нашёл строку с ID=%s — ничего не обновляю.", appwrite_id)
            return

        row = matches[0].row
        idx = _header_indexes(ws)

        status_col = idx.get("статус")
        comment_col = idx.get("комментарий")
        updated_at_col = idx.get("updated at")

        batch = []
        if new_status is not None and status_col:
            batch.append({"range": gspread.utils.rowcol_to_a1(row, status_col), "values": [[new_status]]})
        if comment is not None and comment_col:
            batch.append({"range": gspread.utils.rowcol_to_a1(row, comment_col), "values": [[comment]]})
        if updated_at_col:
            from datetime import datetime, timezone
            batch.append({
                "range": gspread.utils.rowcol_to_a1(row, updated_at_col),
                "values": [[datetime.now(timezone.utc).isoformat()]],
            })

        if batch:
            ws.batch_update(batch, value_input_option="RAW")
    except Exception as e:
        logging.exception("Не удалось обновить Google Sheets: %s", e)


# -----------------------------------------------------------------------------
# Клавиатуры для карточки
# -----------------------------------------------------------------------------
def admin_actions_kb(doc_id: str, back_status: str):
    """
    Кнопки под заявкой:
      Принять / Отклонить / Комментарий / Назад
    """
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Принять", callback_data=f"admin:decide:{doc_id}:approved:{back_status}:1")
    kb.button(text="❌ Отклонить", callback_data=f"admin:decide:{doc_id}:rejected:{back_status}:1")
    kb.button(text="💬 Комментарий", callback_data=f"admin:note:{doc_id}:{back_status}")
    kb.adjust(2, 1)
    kb.button(text="⬅️ Назад к списку", callback_data=f"admin:back:{back_status}")
    kb.adjust(1)
    return kb.as_markup()


# -----------------------------------------------------------------------------
# UI: меню/списки
# -----------------------------------------------------------------------------
async def _send_status_menu(msg_or_cb):
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    c_pending = _safe_count("pending")
    c_approved = _safe_count("approved")
    c_rejected = _safe_count("rejected")

    kb = InlineKeyboardBuilder()
    kb.button(text=f"⏳ В ожидании ({c_pending})", callback_data="admin:show:pending")
    kb.button(text=f"✅ Принятые ({c_approved})", callback_data="admin:show:approved")
    kb.button(text=f"❌ Отклонённые ({c_rejected})", callback_data="admin:show:rejected")
    kb.adjust(1)

    text = "<b>Панель администратора</b>\nВыберите статус для просмотра заявок:"
    if isinstance(msg_or_cb, Message):
        await msg_or_cb.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())
    else:
        await msg_or_cb.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())


async def _send_list_by_status(msg_or_cb, status: str, group: Optional[str] = None):
    repo = get_repo()
    res = repo.list_submissions(status=status, page=1, page_size=30, group=group)
    items = res.get("documents", [])

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    kb = InlineKeyboardBuilder()

    for doc in items:
        title = f"{doc.get('full_name','?')} | {doc.get('group','?')}"
        kb.button(text=title[:60], callback_data=f"admin:view:{doc['$id']}:{status}")

    kb.adjust(1)
    kb.button(text="🔎 Поиск по группе", callback_data=f"admin:search:{status}")
    kb.button(text="⬅️ Назад", callback_data="admin:menu")
    kb.adjust(1)

    header = f"<b>{_status_title(status)}</b> — найдено {res.get('total','?')}"
    if isinstance(msg_or_cb, Message):
        await msg_or_cb.answer(header, parse_mode="HTML", reply_markup=kb.as_markup())
    else:
        await msg_or_cb.message.edit_text(header, parse_mode="HTML", reply_markup=kb.as_markup())


# -----------------------------------------------------------------------------
# Handlers
# -----------------------------------------------------------------------------
@router.message(Command("admin"))
async def admin_entry(msg: Message):
    repo = get_repo()
    if not repo.is_admin(str(msg.from_user.id)):
        await msg.answer("Доступ запрещён.")
        return
    await _send_status_menu(msg)


@router.callback_query(F.data.startswith("admin:show:"))
async def admin_show(cb: CallbackQuery):
    _, _, status = cb.data.split(":")
    await _send_list_by_status(cb, status=status)
    await cb.answer()


@router.callback_query(F.data == "admin:menu")
async def admin_back(cb: CallbackQuery):
    await _send_status_menu(cb)
    await cb.answer()


@router.callback_query(F.data.startswith("admin:search:"))
async def admin_search(cb: CallbackQuery, state: FSMContext):
    _, _, status = cb.data.split(":")
    await state.update_data(status=status)
    await cb.message.answer("Введите название группы (например: ВИС-41):")
    await state.set_state(AdminState.waiting_group)
    await cb.answer()


@router.message(AdminState.waiting_group)
async def admin_search_group(msg: Message, state: FSMContext):
    data = await state.get_data()
    status = data.get("status", "pending")
    group = msg.text.strip()
    await state.clear()
    await _send_list_by_status(msg, status=status, group=group)


@router.callback_query(F.data.startswith("admin:view:"))
async def admin_view(cb: CallbackQuery):
    _, _, doc_id, status = cb.data.split(":")
    repo = get_repo()
    try:
        doc = repo.db.get_document(repo.db_id, repo.sub_col, doc_id)
    except Exception:
        await cb.answer("Не удалось загрузить документ", show_alert=True)
        return

    text = (
        f"<b>Заявка</b>\n\n"
        f"👤 ФИО: {doc.get('full_name','—')}\n"
        f"👥 Группа: {doc.get('group','—')}\n"
        f"📧 Email: {doc.get('email','—')}\n"
        f"📅 Дата рождения: {doc.get('birthDate','—')}\n\n"
        f"📚 Любимые книги: {doc.get('books','—')}\n"
        f"🎬 Любимый фильм/сериал: {doc.get('likedRecentMovie','—')}\n"
        f"ℹ️ Коротко о вас: {doc.get('aboutYou','—')}\n"
        f"🎓 Планы после университета: {doc.get('afterUniversity','—')}\n"
        f"🎖 Красный диплом: {doc.get('redDiploma','—')}\n"
        f"📑 Интерес к научной деятельности: {doc.get('scienceInterest','—')}\n\n"
        f"📝 Тема работы: {doc.get('thesisTopic','—')}\n"
        f"📄 Описание работы: {doc.get('thesisDescription','—')}\n"
        f"📊 Аналоги проекта: {doc.get('analogsProsCons','—')}\n"
        f"⚙️ Планируемый функционал: {doc.get('plannedFeatures','—')}\n"
        f"🖥️ Стек технологий: {doc.get('techStack','—')}\n\n"
        f"📌 Статус: {doc.get('status','—')}\n"
        f"💬 Комментарий: {doc.get('admin_comment','—')}"
    )

    await cb.message.edit_text(text, parse_mode="HTML", reply_markup=admin_actions_kb(doc_id, status))
    await cb.answer()


# --- Решение (approve/reject) ---
@router.callback_query(F.data.startswith("admin:decide:"))
async def admin_decide(cb: CallbackQuery, state: FSMContext):
    _, _, doc_id, decision, back_status, _ = cb.data.split(":")
    await state.update_data(doc_id=doc_id, decision=decision, back_status=back_status)
    await cb.message.answer("Напишите комментарий к решению (или '-' если без комментария).")
    await state.set_state(AdminState.waiting_comment)
    await cb.answer()


@router.message(AdminState.waiting_comment)
async def admin_comment(msg: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    repo = get_repo()
    doc_id = data["doc_id"]
    decision = data["decision"]
    comment = "" if msg.text.strip() == "-" else msg.text.strip()

    try:
        doc = repo.db.get_document(repo.db_id, repo.sub_col, doc_id)
    except Exception:
        await msg.answer("Не удалось получить документ.")
        await state.clear()
        return

    repo.update_submission_status(doc_id, decision, comment)
    update_sheet_status_and_comment(doc_id, decision, comment or None)

    # уведомление студенту
    student_tg = doc.get("tg_user_id")
    if student_tg:
        try:
            await bot.send_message(
                int(student_tg),
                f"📌 Решение по вашей заявке: <b>{'принята' if decision=='approved' else 'отклонена'}</b>\n"
                f"💬 Комментарий: {comment or '—'}",
                parse_mode="HTML",
            )
        except Exception:
            pass

    await msg.answer("Готово ✅")
    await state.clear()
    await _send_status_menu(msg)


# --- Просто комментарий (без смены статуса) ---
@router.callback_query(F.data.startswith("admin:note:"))
async def admin_note_ask(cb: CallbackQuery, state: FSMContext):
    _, _, doc_id, back_status = cb.data.split(":")
    await state.update_data(doc_id=doc_id, back_status=back_status)
    await cb.message.answer("Напишите комментарий (без изменения статуса).")
    await state.set_state(AdminState.waiting_note)
    await cb.answer()


@router.message(AdminState.waiting_note)
async def admin_note_save(msg: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    repo = get_repo()
    doc_id = data["doc_id"]
    note = msg.text.strip()

    try:
        # обновляем только комментарий
        repo.db.update_document(
            database_id=repo.db_id,
            collection_id=repo.sub_col,
            document_id=doc_id,
            data={"admin_comment": note},
        )
        update_sheet_status_and_comment(doc_id, None, note or None)

        # уведомим студента, что пришёл комментарий
        try:
            doc = repo.db.get_document(repo.db_id, repo.sub_col, doc_id)
            student_tg = doc.get("tg_user_id")
            if student_tg:
                await bot.send_message(
                    int(student_tg),
                    f"💬 Комментарий по вашей заявке: {note or '—'}",
                    parse_mode="HTML",
                )
        except Exception:
            pass

        await msg.answer("Комментарий сохранён ✅")
    except Exception:
        await msg.answer("Не удалось сохранить комментарий 😕")
    finally:
        await state.clear()
        await _send_status_menu(msg)


@router.callback_query(F.data.startswith("admin:back:"))
async def admin_back_to_list(cb: CallbackQuery):
    _, _, status = cb.data.split(":")
    await _send_list_by_status(cb, status=status)
    await cb.answer()
