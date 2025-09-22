from aiogram.utils.keyboard import InlineKeyboardBuilder
from typing import List, Dict, Any

def confirm_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="Отправить ✅", callback_data="student:confirm:yes")
    kb.button(text="Сбросить ↩️", callback_data="student:confirm:reset")
    kb.adjust(2)
    return kb.as_markup()

def admin_filters_kb(cur_status: str):
    kb = InlineKeyboardBuilder()
    for s, title in [("pending", "⏳ В ожидании"), ("approved", "✅ Принятые"), ("rejected", "❌ Отклонённые")]:
        prefix = "• " if s == cur_status else ""
        kb.button(text=f"{prefix}{title}", callback_data=f"admin:filter:{s}:1")
    kb.adjust(1)
    return kb.as_markup()

def admin_list_kb(items: List[Dict[str, Any]], status: str, page: int, page_size: int):
    kb = InlineKeyboardBuilder()
    for doc in items:
        title = f"{doc.get('full_name','?')} | {doc.get('group','?')}"
        kb.button(text=title[:64], callback_data=f"admin:view:{doc['$id']}:{status}:{page}")
    kb.adjust(1)
    nav = InlineKeyboardBuilder()
    prev_p = max(1, page - 1)
    next_p = page + 1
    nav.button(text="◀️", callback_data=f"admin:page:{status}:{prev_p}")
    nav.button(text=f"Стр. {page}", callback_data="admin:noop")
    nav.button(text="▶️", callback_data=f"admin:page:{status}:{next_p}")
    nav.adjust(3)
    return kb.as_markup(), nav.as_markup()

def decision_kb(doc_id: str, status: str, page: int):
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Принять", callback_data=f"admin:decide:{doc_id}:approved:{status}:{page}")
    kb.button(text="❌ Отклонить", callback_data=f"admin:decide:{doc_id}:rejected:{status}:{page}")
    kb.button(text="⬅️ Назад", callback_data=f"admin:back:{status}")  
    kb.adjust(2, 1)
    return kb.as_markup()

def student_menu_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="📄 Моя заявка", callback_data="student:menu:view")
    kb.button(text="✏️ Изменить", callback_data="student:menu:edit")
    kb.button(text="❌ Отменить", callback_data="student:menu:cancel")
    # kb.button(text="ℹ️ Помощь", url="https://t.me/ArtycoB")  
    kb.adjust(2, 2)
    return kb.as_markup()