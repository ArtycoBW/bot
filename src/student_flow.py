# src/student_flow.py
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

from .appwrite_client import get_repo
# хелпер, который достаёт список tg_user_id админов (см. admin_flow._get_admin_chat_ids)
from .admin_flow import _get_admin_chat_ids

import os
from datetime import datetime
import logging

# --- Google Sheets (опционально) ---
try:
    import gspread
    from google.oauth2.service_account import Credentials
except Exception:
    gspread = None
    Credentials = None

router = Router()

# ====================== ВОПРОСЫ АНКЕТЫ ======================
class StudentForm(StatesGroup):
    # основной сценарий
    full_name = State()
    group = State()
    email = State()
    birth_date = State()
    books = State()
    liked_recent_movie = State()
    about_you = State()
    after_university = State()
    red_diploma = State()
    science_interest = State()
    thesis_topic = State()
    thesis_description = State()
    analogs_pros_cons = State()
    planned_features = State()
    tech_stack = State()
    confirm = State()

    # единичное редактирование/сохраняем id редактируемой заявки
    editing = State()
    editing_existing = State()

# порядок полей для шага «Назад»
ORDER = [
    "full_name", "group", "email", "birthDate", "books", "likedRecentMovie",
    "aboutYou", "afterUniversity", "redDiploma", "scienceInterest",
    "thesisTopic", "thesisDescription", "analogsProsCons",
    "plannedFeatures", "techStack"
]

# ====================== СПРАВОЧНИК ПОЛЕЙ ======================
FIELDS = [
    ("full_name",         "ФИО",                     "Введите ФИО полностью"),
    ("group",             "Группа",                  "Укажите вашу группу (например, ВИС-41)"),
    ("email",             "Email",                   "Введите рабочий email"),
    ("birthDate",         "Дата рождения",           "Например, 26.02.2003"),
    ("books",             "Книги",                   "Какие книги вдохновляют? Какая последняя?"),
    ("likedRecentMovie",  "Фильм/сериал",            "Что понравилось из последнего?"),
    ("aboutYou",          "О студенте",              "Что ещё следует о вас знать?"),
    ("afterUniversity",   "После университета",      "Кем видите себя после выпуска?"),
    ("redDiploma",        "Красный диплом",          "Выберите вариант ниже"),
    ("scienceInterest",   "Научная деятельность",    "Выберите вариант ниже"),
    ("thesisTopic",       "Тема диплома",            "Введите название проекта"),
    ("thesisDescription", "Описание",                "Коротко опишите проект"),
    ("analogsProsCons",   "Аналоги (плюсы/минусы)",  "Какие есть аналоги, их плюсы и минусы"),
    ("plannedFeatures",   "Планируемый функционал",  "Перечень функций (и ролей, если есть)"),
    ("techStack",         "Стек технологий",         "На чем планируете писать"),
]
FIELD_LABEL = {k: label for k, label, _ in FIELDS}
FIELD_HINT  = {k: hint  for k, _, hint in FIELDS}

def start_reply_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="/start")]],
        resize_keyboard=True,
        one_time_keyboard=False,
    )

def ru_status(s: str) -> str:
    return {
        "pending":  "В ожидании",
        "approved": "Принята",
        "rejected": "Отклонена",
    }.get((s or "").lower(), s or "—")


# ====================== КНОПКИ ======================
def back_kb(prev_key: str | None):
    kb = InlineKeyboardBuilder()
    if prev_key:
        kb.button(text="⬅️ Назад", callback_data=f"student:back:{prev_key}")
        kb.adjust(1)
        return kb.as_markup()
    return None

def red_diploma_kb(prev_key: str | None):
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Да",  callback_data="student:redDiploma:yes")
    kb.button(text="❌ Нет", callback_data="student:redDiploma:no")
    kb.button(text="🤔 Не решил", callback_data="student:redDiploma:undecided")
    kb.adjust(3)
    if prev_key:
        kb.button(text="⬅️ Назад", callback_data=f"student:back:{prev_key}")
        kb.adjust(3, 1)
    return kb.as_markup()

def science_interest_kb(prev_key: str | None):
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Да",  callback_data="student:scienceInterest:yes")
    kb.button(text="❌ Нет", callback_data="student:scienceInterest:no")
    kb.button(text="🤔 Может быть", callback_data="student:scienceInterest:maybe")
    kb.adjust(3)
    if prev_key:
        kb.button(text="⬅️ Назад", callback_data=f"student:back:{prev_key}")
        kb.adjust(3, 1)
    return kb.as_markup()

def start_continue_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="▶️ Продолжить", callback_data="student:begin")
    return kb.as_markup()

def confirm_menu_kb(editing: bool = False):
    kb = InlineKeyboardBuilder()
    kb.button(text=("💾 Сохранить изменения" if editing else "✅ Отправить"),
              callback_data="student:confirm:send")
    kb.button(text="✏️ Изменить ответы", callback_data="student:confirm:editmenu:1")
    kb.adjust(1)
    return kb.as_markup()

def edit_fields_menu_kb(page: int = 1, per_page: int = 6):
    total = len(FIELDS)
    pages = (total + per_page - 1) // per_page
    page = max(1, min(page, pages))
    start = (page - 1) * per_page
    chunk = FIELDS[start : start + per_page]

    kb = InlineKeyboardBuilder()
    for key, label, _ in chunk:
        kb.button(text=f"✏️ {label}", callback_data=f"student:edit:{key}")

    if pages > 1:
        if page > 1:
            kb.button(text="⬅️ Назад", callback_data=f"student:confirm:editmenu:{page-1}")
        kb.button(text=f"{page}/{pages}", callback_data="noop")
        if page < pages:
            kb.button(text="Вперёд ➡️", callback_data=f"student:confirm:editmenu:{page+1}")
        kb.adjust(3)

    kb.button(text="↩️ К проверке анкеты", callback_data="student:confirm:back")
    kb.adjust(1)
    return kb.as_markup()


# ====================== GOOGLE SHEETS ======================
def _get_sheet():
    if gspread is None or Credentials is None:
        raise RuntimeError("Зависимости gspread / google-auth не установлены.")

    sheet_id = os.getenv("GOOGLE_SHEET_ID")
    tab_name = os.getenv("GOOGLE_SHEET_TAB", "Лист1")
    sa_path  = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON_PATH", "./service_account.json")
    if not sheet_id:
        raise RuntimeError("GOOGLE_SHEET_ID не задан в .env")
    if not os.path.exists(sa_path):
        raise RuntimeError(f"Файл сервис-аккаунта не найден: {sa_path}")

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds  = Credentials.from_service_account_file(sa_path, scopes=scopes)
    client = gspread.authorize(creds)
    sh = client.open_by_key(sheet_id)
    try:
        ws = sh.worksheet(tab_name)
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet(title=tab_name, rows="2000", cols="30")

    if not ws.row_values(1):
        headers = [
            "timestamp","appwrite_id","tg_user_id","full_name","group","email",
            "birthDate","books","likedRecentMovie","aboutYou","afterUniversity",
            "redDiploma","scienceInterest","thesisTopic","thesisDescription",
            "analogsProsCons","plannedFeatures","techStack","status",
        ]
        ws.append_row(headers, value_input_option="RAW")
    return ws

def append_submission_to_sheet(appw_doc: dict):
    try:
        ws = _get_sheet()
        row = [
            datetime.now().isoformat(timespec="seconds"),
            appw_doc.get("$id",""), appw_doc.get("tg_user_id",""),
            appw_doc.get("full_name",""), appw_doc.get("group",""),
            appw_doc.get("email",""), appw_doc.get("birthDate",""),
            appw_doc.get("books",""), appw_doc.get("likedRecentMovie",""),
            appw_doc.get("aboutYou",""), appw_doc.get("afterUniversity",""),
            appw_doc.get("redDiploma",""), appw_doc.get("scienceInterest",""),
            appw_doc.get("thesisTopic",""), appw_doc.get("thesisDescription",""),
            appw_doc.get("analogsProsCons",""), appw_doc.get("plannedFeatures",""),
            appw_doc.get("techStack",""), appw_doc.get("status","pending"),
        ]
        ws.append_row(row, value_input_option="USER_ENTERED")
    except Exception as e:
        logging.exception("Не удалось записать заявку в Google Sheets: %s", e)


# ====================== ХЕЛПЕРЫ ======================
async def notify_admins(bot, text: str):
    """Оповестить всех админов (на базе admin_flow._get_admin_chat_ids)."""
    try:
        admin_ids = _get_admin_chat_ids()
        for aid in admin_ids:
            try:
                await bot.send_message(aid, text, parse_mode="HTML")
            except Exception:
                pass
    except Exception:
        pass

async def show_greeting_and_outline(msg: Message):
    await msg.answer(
        "Приветствую! 👋\n\n"
        "Этот бот создан для приема заявок на мое руководство вашей дипломной работой 👩‍🏫.\n"
        "На данном этапе для меня важнее понимание общего направления ваших интересов в IT и желаемого результата ВКР, "
        "а не четкая формулировка темы. 🎯\n\n"
        'С примерной тематикой дипломных работ прошлых лет можно ознакомиться '
        '<a href="https://drive.google.com/drive/folders/1OBAJZr9PtM_QERUv_u3mfc8ycHuKSt4U?usp=drive_link">здесь</a>. 📚\n\n'
        "Успейте подать заявку до конца сентября, количество мест ограничено! ⏰😉\n\n"
        "Давайте заполним короткую анкету."
    )
    lst = "\n".join([f"• {FIELD_LABEL[k]}" for k, _, _ in FIELDS])
    await msg.answer(
        "Вам предстоит ответить на следующие вопросы:\n\n"
        f"{lst}\n\n"
        "Нажмите «Продолжить», чтобы начать.",
        reply_markup=start_continue_kb(),
    )

def validate_email(value: str) -> bool:
    return "@" in value and "." in value

def prev_key_of(key: str) -> str | None:
    try:
        i = ORDER.index(key)
        return ORDER[i-1] if i > 0 else None
    except ValueError:
        return None

async def ask_for_field(target_key: str, msg_or_cb, state: FSMContext):
    """Показать пользователю вопрос для поля (с кнопкой Назад)."""
    prev = prev_key_of(target_key)
    # установить нужный state
    mapping = {
        "full_name": StudentForm.full_name,
        "group": StudentForm.group,
        "email": StudentForm.email,
        "birthDate": StudentForm.birth_date,
        "books": StudentForm.books,
        "likedRecentMovie": StudentForm.liked_recent_movie,
        "aboutYou": StudentForm.about_you,
        "afterUniversity": StudentForm.after_university,
        "redDiploma": StudentForm.red_diploma,
        "scienceInterest": StudentForm.science_interest,
        "thesisTopic": StudentForm.thesis_topic,
        "thesisDescription": StudentForm.thesis_description,
        "analogsProsCons": StudentForm.analogs_pros_cons,
        "plannedFeatures": StudentForm.planned_features,
        "techStack": StudentForm.tech_stack,
    }
    await state.set_state(mapping[target_key])

    # текст вопроса
    prompts = {
        "full_name":          "👤 Введите *ФИО*:",
        "group":              "👥 Укажите вашу *группу* (например, ВИС-41):",
        "email":              "📧 Введите ваш *email*:",
        "birthDate":          "📅 Введите *дату рождения* (например, 26.02.2003):",
        "books":              "📚 Какие книги вдохновляют тебя? И какая последняя встретилась на пути твоём?",
        "likedRecentMovie":   "🎬 *Какой фильм/сериал из последнего вам понравился?*",
        "aboutYou":           "ℹ️ *Что ещё следует о вас знать?*",
        "afterUniversity":    "🎓 *Кем видите себя после окончания университета?*",
        "redDiploma":         "🎖 *Идёте на красный диплом?*",
        "scienceInterest":    "📑 *Есть ли желание заниматься научной деятельностью?*",
        "thesisTopic":        "📝 *Введите тему дипломной работы (название проекта)*:",
        "thesisDescription":  "📄 *Введите описание проекта:*",
        "analogsProsCons":    "📊 *Какие есть аналоги? Их плюсы и минусы:*",
        "plannedFeatures":    "⚙️ *Примерный перечень функционала (с ролями при наличии):*",
        "techStack":          "🖥️ *На чём планируете писать? (стек технологий)*:",
    }
    text = prompts[target_key]

    # отправка
    if target_key == "redDiploma":
        markup = red_diploma_kb(prev)
        if isinstance(msg_or_cb, Message):
            await msg_or_cb.answer(text, parse_mode="Markdown", reply_markup=markup)
        else:
            await msg_or_cb.message.edit_text(text, parse_mode="Markdown", reply_markup=markup)
    elif target_key == "scienceInterest":
        markup = science_interest_kb(prev)
        if isinstance(msg_or_cb, Message):
            await msg_or_cb.answer(text, parse_mode="Markdown", reply_markup=markup)
        else:
            await msg_or_cb.message.edit_text(text, parse_mode="Markdown", reply_markup=markup)
    else:
        markup = back_kb(prev)
        if isinstance(msg_or_cb, Message):
            await msg_or_cb.answer(text, parse_mode="Markdown", reply_markup=markup)
        else:
            await msg_or_cb.message.edit_text(text, parse_mode="Markdown", reply_markup=markup)


async def show_summary(msg_or_cb, data: dict, editing: bool = False):
    text = (
        "🗂 <b>Проверьте анкету</b>\n\n"
        f"👤 ФИО: {data.get('full_name','—')}\n"
        f"👥 Группа: {data.get('group','—')}\n"
        f"📧 Email: {data.get('email','—')}\n"
        f"📅 Дата рождения: {data.get('birthDate','—')}\n\n"
        f"📚 Книги: {data.get('books','—')}\n"
        f"🎬 Фильм/сериал: {data.get('likedRecentMovie','—')}\n"
        f"ℹ️ О студенте: {data.get('aboutYou','—')}\n"
        f"🎓 После университета: {data.get('afterUniversity','—')}\n"
        f"🎖 Красный диплом: {data.get('redDiploma','—')}\n"
        f"📑 Научная деятельность: {data.get('scienceInterest','—')}\n\n"
        f"📝 Тема: {data.get('thesisTopic','—')}\n"
        f"📄 Описание: {data.get('thesisDescription','—')}\n"
        f"📊 Аналоги: {data.get('analogsProsCons','—')}\n"
        f"⚙️ Функционал: {data.get('plannedFeatures','—')}\n"
        f"🖥️ Стек: {data.get('techStack','—')}\n"
    )
    markup = confirm_menu_kb(editing=editing)
    if isinstance(msg_or_cb, Message):
        await msg_or_cb.answer(text, reply_markup=markup, parse_mode="HTML")
    else:
        await msg_or_cb.message.edit_text(text, reply_markup=markup, parse_mode="HTML")


# ====================== СЦЕНАРИЙ ======================
@router.message(CommandStart())
async def start(msg: Message, state: FSMContext):
    await state.clear()
    repo = get_repo()
    existing = repo.get_submission_by_user(str(msg.from_user.id))
    if existing and existing.get("status") in ("pending", "approved"):
        st = existing["status"]
        await msg.answer(
            f"У вас уже есть заявка со статусом: *{st}*.\n"
            f"Если нужно переотправить — напишите /start позже, когда статус будет `rejected`.",
            parse_mode="Markdown",
        )
        return
    await show_greeting_and_outline(msg)

@router.callback_query(F.data == "student:begin")
async def begin_flow(cb: CallbackQuery, state: FSMContext):
    await ask_for_field("full_name", cb, state)
    await cb.answer()

# ----- шаги (текстовые поля) -----
@router.message(StudentForm.full_name)
async def step_full_name(msg: Message, state: FSMContext):
    await state.update_data(full_name=msg.text.strip())
    await ask_for_field("group", msg, state)

@router.message(StudentForm.group)
async def step_group(msg: Message, state: FSMContext):
    await state.update_data(group=msg.text.strip())
    await ask_for_field("email", msg, state)

@router.message(StudentForm.email)
async def step_email(msg: Message, state: FSMContext):
    value = msg.text.strip()
    if not validate_email(value):
        await msg.answer("Похоже на некорректный email, попробуйте ещё раз.", reply_markup=back_kb(prev_key_of("email")))
        return
    await state.update_data(email=value)
    await ask_for_field("birthDate", msg, state)

@router.message(StudentForm.birth_date)
async def step_birth_date(msg: Message, state: FSMContext):
    await state.update_data(birthDate=msg.text.strip())
    await ask_for_field("books", msg, state)

@router.message(StudentForm.books)
async def step_books(msg: Message, state: FSMContext):
    await state.update_data(books=msg.text.strip())
    await ask_for_field("likedRecentMovie", msg, state)

@router.message(StudentForm.liked_recent_movie)
async def step_movie(msg: Message, state: FSMContext):
    await state.update_data(likedRecentMovie=msg.text.strip())
    await ask_for_field("aboutYou", msg, state)

@router.message(StudentForm.about_you)
async def step_about(msg: Message, state: FSMContext):
    await state.update_data(aboutYou=msg.text.strip())
    await ask_for_field("afterUniversity", msg, state)

@router.message(StudentForm.after_university)
async def step_after_uni(msg: Message, state: FSMContext):
    await state.update_data(afterUniversity=msg.text.strip())
    await ask_for_field("redDiploma", msg, state)

# ----- выборы -----
@router.callback_query(F.data.startswith("student:redDiploma"))
async def step_red_diploma(cb: CallbackQuery, state: FSMContext):
    choice = cb.data.split(":")[-1]
    data = await state.get_data()
    if data.get("editing_field") == "redDiploma":
        await state.update_data(redDiploma=choice, editing_field=None)
        await state.set_state(StudentForm.confirm)
        await cb.message.edit_reply_markup()
        await show_summary(cb, await state.get_data(), editing=bool(data.get("_editing_doc_id")))
        await cb.answer("Обновлено")
        return
    await state.update_data(redDiploma=choice)
    await ask_for_field("scienceInterest", cb, state)
    await cb.answer()

@router.callback_query(F.data.startswith("student:scienceInterest"))
async def step_science(cb: CallbackQuery, state: FSMContext):
    choice = cb.data.split(":")[-1]
    data = await state.get_data()
    if data.get("editing_field") == "scienceInterest":
        await state.update_data(scienceInterest=choice, editing_field=None)
        await state.set_state(StudentForm.confirm)
        await cb.message.edit_reply_markup()
        await show_summary(cb, await state.get_data(), editing=bool(data.get("_editing_doc_id")))
        await cb.answer("Обновлено")
        return
    await state.update_data(scienceInterest=choice)
    await ask_for_field("thesisTopic", cb, state)
    await cb.answer()

# ----- остальные текстовые -----
@router.message(StudentForm.thesis_topic)
async def step_topic(msg: Message, state: FSMContext):
    await state.update_data(thesisTopic=msg.text.strip())
    await ask_for_field("thesisDescription", msg, state)

@router.message(StudentForm.thesis_description)
async def step_description(msg: Message, state: FSMContext):
    await state.update_data(thesisDescription=msg.text.strip())
    await ask_for_field("analogsProsCons", msg, state)

@router.message(StudentForm.analogs_pros_cons)
async def step_analogs(msg: Message, state: FSMContext):
    await state.update_data(analogsProsCons=msg.text.strip())
    await ask_for_field("plannedFeatures", msg, state)

@router.message(StudentForm.planned_features)
async def step_features(msg: Message, state: FSMContext):
    await state.update_data(plannedFeatures=msg.text.strip())
    await ask_for_field("techStack", msg, state)

@router.message(StudentForm.tech_stack)
async def step_stack(msg: Message, state: FSMContext):
    await state.update_data(techStack=msg.text.strip())
    data = await state.get_data()
    await state.set_state(StudentForm.confirm)
    await show_summary(msg, data, editing=bool(data.get("_editing_doc_id")))

# ----- универсальный «Назад» -----
@router.callback_query(F.data.startswith("student:back:"))
async def on_back(cb: CallbackQuery, state: FSMContext):
    target_key = cb.data.split(":")[-1]
    await ask_for_field(target_key, cb, state)
    await cb.answer()

# ====================== ЭКРАН ПОДТВЕРЖДЕНИЯ / РЕДАКТИРОВАНИЕ ======================
@router.callback_query(F.data == "student:confirm:back")
async def confirm_back(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await state.set_state(StudentForm.confirm)
    await show_summary(cb, data, editing=bool(data.get("_editing_doc_id")))
    await cb.answer()

@router.callback_query(F.data.startswith("student:confirm:editmenu:"))
async def confirm_edit_menu(cb: CallbackQuery):
    page = int(cb.data.split(":")[-1])
    await cb.message.edit_reply_markup(reply_markup=edit_fields_menu_kb(page))
    await cb.answer()

@router.callback_query(F.data.startswith("student:edit:"))
async def choose_field_to_edit(cb: CallbackQuery, state: FSMContext):
    key = cb.data.split(":")[-1]
    if key == "redDiploma":
        await state.update_data(editing_field="redDiploma")
        await cb.message.edit_text(
            f"Изменить: <b>{FIELD_LABEL[key]}</b>\nВыберите вариант:",
            parse_mode="HTML",
            reply_markup=red_diploma_kb(prev_key_of("redDiploma")),
        )
        await cb.answer()
        return
    if key == "scienceInterest":
        await state.update_data(editing_field="scienceInterest")
        await cb.message.edit_text(
            f"Изменить: <b>{FIELD_LABEL[key]}</b>\nВыберите вариант:",
            parse_mode="HTML",
            reply_markup=science_interest_kb(prev_key_of("scienceInterest")),
        )
        await cb.answer()
        return

    await state.update_data(editing_field=key)
    await state.set_state(StudentForm.editing)
    await cb.message.edit_text(
        f"✏️ Отправьте новое значение для поля <b>{FIELD_LABEL[key]}</b>\n\n"
        f"<i>{FIELD_HINT.get(key,'')}</i>",
        parse_mode="HTML",
        reply_markup=back_kb(prev_key_of(key)),
    )
    await cb.answer()

@router.message(StudentForm.editing)
async def save_edited_value(msg: Message, state: FSMContext):
    data = await state.get_data()
    field = data.get("editing_field")
    if not field:
        await state.set_state(StudentForm.confirm)
        await show_summary(msg, await state.get_data(), editing=bool(data.get("_editing_doc_id")))
        return

    val = msg.text.strip()
    if field == "email" and not validate_email(val):
        await msg.answer("Некорректный email, попробуйте ещё раз.", reply_markup=back_kb(prev_key_of("email")))
        return

    await state.update_data(**{field: val, "editing_field": None})
    await state.set_state(StudentForm.confirm)
    await show_summary(msg, await state.get_data(), editing=bool(data.get("_editing_doc_id")))

# ====================== ОТПРАВКА / СОХРАНЕНИЕ ======================
@router.callback_query(F.data.startswith("student:confirm"))
async def confirm_handler(cb: CallbackQuery, state: FSMContext):
    parts = cb.data.split(":")
    action = parts[-1] if len(parts) >= 3 else ""

    if action == "reset":
        await state.clear()
        await ask_for_field("full_name", cb, state)
        await cb.answer()
        return

    if action.startswith("editmenu"):
        page = int(action.split(":")[-1]) if ":" in action else 1
        await cb.message.edit_reply_markup(reply_markup=edit_fields_menu_kb(page))
        await cb.answer()
        return

    if action == "send":
        data = await state.get_data()
        repo = get_repo()

        payload = {
            "tg_user_id": str(cb.from_user.id),
            "full_name": data.get("full_name"),
            "group": data.get("group"),
            "email": data.get("email"),
            "birthDate": data.get("birthDate"),
            "books": data.get("books"),
            "likedRecentMovie": data.get("likedRecentMovie"),
            "aboutYou": data.get("aboutYou"),
            "afterUniversity": data.get("afterUniversity"),
            "redDiploma": data.get("redDiploma"),
            "scienceInterest": data.get("scienceInterest"),
            "thesisTopic": data.get("thesisTopic"),
            "thesisDescription": data.get("thesisDescription"),
            "analogsProsCons": data.get("analogsProsCons"),
            "plannedFeatures": data.get("plannedFeatures"),
            "techStack": data.get("techStack"),
        }

        editing_doc_id = data.get("_editing_doc_id")
        if editing_doc_id:
            # обновление существующей
            repo.db.update_document(
                database_id=repo.db_id,
                collection_id=repo.sub_col,
                document_id=editing_doc_id,
                data=payload,
            )
            # уведомим администраторов
            await notify_admins(
                cb.bot,
                "✏️ <b>Заявка обновлена</b>\n"
                f"ФИО: {payload.get('full_name','—')}\n"
                f"Группа: {payload.get('group','—')}\n"
                f"Email: {payload.get('email','—')}\n\n"
                "Открыть панель: /admin"
            )
            await state.clear()
            await cb.message.edit_text(
                "💾 <b>Изменения сохранены!</b>\n\nДоступные действия:",
                reply_markup=student_menu_kb(),
                parse_mode="HTML",
            )
            await cb.answer("Сохранено")
            return

        # новая заявка
        payload["status"] = "pending"
        created = repo.create_submission(payload)

        # в Sheets
        payload_with_ids = dict(payload)
        payload_with_ids["$id"] = created.get("$id")
        append_submission_to_sheet(payload_with_ids)

        # уведомим администраторов
        await notify_admins(
            cb.bot,
            "🆕 <b>Новая заявка</b>\n"
            f"ФИО: {payload.get('full_name','—')}\n"
            f"Группа: {payload.get('group','—')}\n"
            f"Email: {payload.get('email','—')}\n\n"
            "Открыть панель: /admin"
        )

        await state.clear()
        await cb.message.edit_text(
            "✅ <b>Анкета отправлена!</b>\n\n"
            f"Статус: ⏳ {ru_status('pending')}\n"
            "О решении придёт уведомление.\n\n"
            "Доступные действия:",
            reply_markup=student_menu_kb(),
            parse_mode="HTML",
        )
        await cb.answer("Отправлено")
        return

# ====================== МЕНЮ СТУДЕНТА ======================
@router.callback_query(F.data == "student:menu:view")
async def view_submission(cb: CallbackQuery):
    repo = get_repo()
    doc = repo.get_submission_by_user(str(cb.from_user.id))
    if not doc:
        await cb.answer("У вас нет заявки.", show_alert=True)
        return

    status_ru = ru_status(doc.get("status"))
    admin_comment = doc.get("admin_comment")
    admin_comment = admin_comment if (isinstance(admin_comment, str) and admin_comment.strip()) else "нет"

    text = (
        "📄 <b>Ваша заявка</b>\n\n"
        f"👤 ФИО: {doc.get('full_name','—')}\n"
        f"👥 Группа: {doc.get('group','—')}\n"
        f"📧 Email: {doc.get('email','—')}\n"
        f"📅 Дата рождения: {doc.get('birthDate','—')}\n\n"
        f"📚 Книги: {doc.get('books','—')}\n"
        f"🎬 Фильм/сериал: {doc.get('likedRecentMovie','—')}\n"
        f"ℹ️ О студенте: {doc.get('aboutYou','—')}\n"
        f"🎓 После университета: {doc.get('afterUniversity','—')}\n"
        f"🎖 Красный диплом: {doc.get('redDiploma','—')}\n"
        f"📑 Научная деятельность: {doc.get('scienceInterest','—')}\n\n"
        f"📝 Тема: {doc.get('thesisTopic','—')}\n"
        f"📄 Описание: {doc.get('thesisDescription','—')}\n"
        f"📊 Аналоги: {doc.get('analogsProsCons','—')}\n"
        f"⚙️ Функционал: {doc.get('plannedFeatures','—')}\n"
        f"🖥️ Стек: {doc.get('techStack','—')}\n\n"
        f"📌 Статус: {status_ru}\n"
        f"💬 Комментарий администратора: {admin_comment}"
    )

    await cb.message.edit_text(text, parse_mode="HTML", reply_markup=student_menu_kb())
    await cb.answer()

@router.callback_query(F.data == "student:menu:edit")
async def edit_submission(cb: CallbackQuery, state: FSMContext):
    """Загружаем текущую заявку и переходим сразу на экран подтверждения для точечного редактирования."""
    repo = get_repo()
    doc = repo.get_submission_by_user(str(cb.from_user.id))
    if not doc:
        await cb.answer("У вас нет заявки.", show_alert=True)
        return

    preload = {
        "full_name":         doc.get("full_name",""),
        "group":             doc.get("group",""),
        "email":             doc.get("email",""),
        "birthDate":         doc.get("birthDate",""),
        "books":             doc.get("books",""),
        "likedRecentMovie":  doc.get("likedRecentMovie",""),
        "aboutYou":          doc.get("aboutYou",""),
        "afterUniversity":   doc.get("afterUniversity",""),
        "redDiploma":        doc.get("redDiploma",""),
        "scienceInterest":   doc.get("scienceInterest",""),
        "thesisTopic":       doc.get("thesisTopic",""),
        "thesisDescription": doc.get("thesisDescription",""),
        "analogsProsCons":   doc.get("analogsProsCons",""),
        "plannedFeatures":   doc.get("plannedFeatures",""),
        "techStack":         doc.get("techStack",""),
        "_editing_doc_id":   doc.get("$id"),
    }
    await state.clear()
    await state.update_data(**preload)
    await state.set_state(StudentForm.confirm)

    await cb.message.edit_text("Загружаю вашу анкету…")
    await show_summary(cb, preload, editing=True)
    await cb.answer()

@router.callback_query(F.data == "student:menu:cancel")
async def cancel_submission(cb: CallbackQuery):
    repo = get_repo()
    doc = repo.get_submission_by_user(str(cb.from_user.id))
    if not doc:
        await cb.answer("У вас нет заявки.", show_alert=True)
        return

    repo.db.delete_document(repo.db_id, repo.sub_col, doc["$id"])
    await cb.message.edit_text("❌ Ваша заявка удалена.\n\nВы можете заполнить её заново через /start.")
    await cb.answer("Удалено")
