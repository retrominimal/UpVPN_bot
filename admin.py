"""
Админ панель
"""

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database import db
import config


admin_router = Router()


class Broadcast(StatesGroup):
    waiting_for_message = State()


def is_admin(user_id: int) -> bool:
    """Проверка на админа"""
    return user_id in config.ADMIN_IDS


def admin_menu_kb():
    """Меню админа"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="Рассылка", callback_data="admin_broadcast")]
    ])


@admin_router.message(Command("admin"))
async def cmd_admin(message: Message):
    """Команда /admin"""
    if not is_admin(message.from_user.id):
        await message.answer("У вас нет доступа к админ панели")
        return
    
    await message.answer(
        "Админ панель",
        reply_markup=admin_menu_kb()
    )


@admin_router.callback_query(F.data == "admin_stats")
async def show_stats(callback: CallbackQuery):
    """Показать статистику"""
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    
    users_count = await db.get_users_count()
    servers_count = await db.get_servers_count()
    vpn_users_count = await db.get_vpn_users_count()
    
    stats_text = (
        f"Статистика бота:\n\n"
        f"Пользователей: {users_count}\n"
        f"Серверов: {servers_count}\n"
        f"VPN пользователей: {vpn_users_count}"
    )
    
    await callback.message.edit_text(
        stats_text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Назад", callback_data="admin_menu")]
        ])
    )
    await callback.answer()


@admin_router.callback_query(F.data == "admin_menu")
async def show_admin_menu(callback: CallbackQuery):
    """Показать меню админа"""
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    
    await callback.message.edit_text(
        "Админ панель",
        reply_markup=admin_menu_kb()
    )
    await callback.answer()


@admin_router.callback_query(F.data == "admin_broadcast")
async def start_broadcast(callback: CallbackQuery, state: FSMContext):
    """Начать рассылку"""
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    
    await callback.message.edit_text("Отправьте сообщение для рассылки:")
    await state.set_state(Broadcast.waiting_for_message)
    await callback.answer()


@admin_router.message(Broadcast.waiting_for_message)
async def process_broadcast(message: Message, state: FSMContext):
    """Обработать рассылку"""
    if not is_admin(message.from_user.id):
        return
    
    users = await db.get_all_users()
    
    await message.answer(f"Начинаю рассылку для {len(users)} пользователей...")
    
    success = 0
    failed = 0
    
    for user_id in users:
        try:
            await message.bot.copy_message(
                chat_id=user_id,
                from_chat_id=message.chat.id,
                message_id=message.message_id
            )
            success += 1
        except Exception:
            failed += 1
    
    await message.answer(
        f"Рассылка завершена!\n\n"
        f"Успешно: {success}\n"
        f"Ошибок: {failed}",
        reply_markup=admin_menu_kb()
    )
    
    await state.clear()
