"""
Обработчики команд бота
"""

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import uuid
from database import db
from xray_client import XrayClient
import config


router = Router()


class AddServer(StatesGroup):
    waiting_for_ip = State()
    waiting_for_username = State()
    waiting_for_password = State()


class AddVpnUser(StatesGroup):
    server_id = State()
    waiting_for_username = State()
    waiting_for_password = State()


def main_menu_kb():
    """Главное меню"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Мои серверы", callback_data="my_servers")],
        [InlineKeyboardButton(text="Добавить сервер", callback_data="add_server")]
    ])


def servers_kb(servers):
    """Клавиатура со списком серверов"""
    buttons = []
    for server in servers:
        buttons.append([InlineKeyboardButton(
            text=f"{server['server_ip']}",
            callback_data=f"server_{server['id']}"
        )])
    buttons.append([InlineKeyboardButton(text="Назад", callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def server_users_kb(server_id, vpn_users):
    """Клавиатура с пользователями сервера"""
    buttons = []
    for vpn_user in vpn_users:
        buttons.append([InlineKeyboardButton(
            text=vpn_user['email'],
            callback_data=f"vpnuser_{vpn_user['id']}"
        )])
    buttons.append([InlineKeyboardButton(text="Добавить пользователя", callback_data=f"add_vpnuser_{server_id}")])
    buttons.append([InlineKeyboardButton(text="Назад", callback_data="my_servers")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def back_to_server_kb(server_id):
    """Кнопка назад к серверу"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Назад", callback_data=f"server_{server_id}")]
    ])


@router.message(Command("start"))
async def cmd_start(message: Message):
    """Команда /start"""
    await db.add_user(message.from_user.id, message.from_user.username)
    await message.answer(
        "Добро пожаловать!\n\nВы можете управлять своими VPN серверами.",
        reply_markup=main_menu_kb()
    )


@router.callback_query(F.data == "menu")
async def show_menu(callback: CallbackQuery):
    """Показать главное меню"""
    await callback.message.edit_text(
        "Главное меню",
        reply_markup=main_menu_kb()
    )
    await callback.answer()


@router.callback_query(F.data == "my_servers")
async def show_servers(callback: CallbackQuery):
    """Показать список серверов"""
    servers = await db.get_user_servers(callback.from_user.id)
    
    if not servers:
        await callback.message.edit_text(
            "У вас пока нет серверов",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Добавить сервер", callback_data="add_server")],
                [InlineKeyboardButton(text="Назад", callback_data="menu")]
            ])
        )
    else:
        await callback.message.edit_text(
            "Ваши серверы:",
            reply_markup=servers_kb(servers)
        )
    await callback.answer()


@router.callback_query(F.data == "add_server")
async def add_server_start(callback: CallbackQuery, state: FSMContext):
    """Начать добавление сервера"""
    await callback.message.edit_text("Введите IP адрес сервера:")
    await state.set_state(AddServer.waiting_for_ip)
    await callback.answer()


@router.message(AddServer.waiting_for_ip)
async def add_server_ip(message: Message, state: FSMContext):
    """Получить IP сервера"""
    await state.update_data(server_ip=message.text)
    await message.answer("Введите имя пользователя для SSH (обычно root):")
    await state.set_state(AddServer.waiting_for_username)


@router.message(AddServer.waiting_for_username)
async def add_server_username(message: Message, state: FSMContext):
    """Получить username"""
    await state.update_data(username=message.text)
    await message.answer("Введите пароль для SSH:")
    await state.set_state(AddServer.waiting_for_password)


@router.message(AddServer.waiting_for_password)
async def add_server_password(message: Message, state: FSMContext):
    """Получить пароль и развернуть сервер"""
    data = await state.get_data()
    server_ip = data['server_ip']
    username = data['username']
    password = message.text
    
    await message.answer("Подключаюсь к серверу и разворачиваю Xray...")
    
    try:
        # Создаем клиент и разворачиваем Xray
        client = XrayClient(
            server_ip=server_ip,
            username=username,
            password=password,
            sni=config.DEFAULT_SNI
        )
        
        # Деплой
        await message.answer("Устанавливаю Xray на сервер...")
        server_info = client.deploy()
        
        # Создаем первого пользователя
        random_email = f"user_{uuid.uuid4().hex[:8]}@vpn.local"
        user = client.add_user(random_email)
        
        if user and 'vless_link' in user:
            # Сохраняем сервер в БД
            server_id = await db.add_server(message.from_user.id, server_ip)
            
            # Сохраняем пользователя
            await db.add_vpn_user(
                server_id=server_id,
                email=user['email'],
                uuid=user['uuid'],
                vless_link=user['vless_link']
            )
            
            await message.answer(
                f"Сервер успешно развернут!\n\n"
                f"IP: {server_ip}\n"
                f"Создан пользователь: {user['email']}\n\n"
                f"VLESS ключ:\n<code>{user['vless_link']}</code>",
                parse_mode="HTML",
                reply_markup=main_menu_kb()
            )
        else:
            await message.answer(
                "Ошибка при создании пользователя",
                reply_markup=main_menu_kb()
            )
    
    except Exception as e:
        await message.answer(
            f"Ошибка при развертывании сервера:\n{str(e)}",
            reply_markup=main_menu_kb()
        )
    
    await state.clear()


@router.callback_query(F.data.startswith("server_"))
async def show_server(callback: CallbackQuery):
    """Показать сервер и его пользователей"""
    server_id = int(callback.data.split("_")[1])
    server = await db.get_server(server_id)
    
    if not server:
        await callback.answer("Сервер не найден", show_alert=True)
        return
    
    vpn_users = await db.get_server_vpn_users(server_id)
    
    await callback.message.edit_text(
        f"Сервер: {server['server_ip']}\n\nПользователи:",
        reply_markup=server_users_kb(server_id, vpn_users)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("vpnuser_"))
async def show_vpn_user(callback: CallbackQuery):
    """Показать VLESS ключ пользователя"""
    vpn_user_id = int(callback.data.split("_")[1])
    vpn_user = await db.get_vpn_user(vpn_user_id)
    
    if not vpn_user:
        await callback.answer("Пользователь не найден", show_alert=True)
        return
    
    server = await db.get_server(vpn_user['server_id'])
    
    await callback.message.edit_text(
        f"Пользователь: {vpn_user['email']}\n"
        f"Сервер: {server['server_ip']}\n\n"
        f"VLESS ключ:\n<code>{vpn_user['vless_link']}</code>",
        parse_mode="HTML",
        reply_markup=back_to_server_kb(vpn_user['server_id'])
    )
    await callback.answer()


@router.callback_query(F.data.startswith("add_vpnuser_"))
async def add_vpn_user_start(callback: CallbackQuery, state: FSMContext):
    """Начать добавление VPN пользователя"""
    server_id = int(callback.data.split("_")[2])
    await state.update_data(server_id=server_id)
    await callback.message.edit_text("Введите имя пользователя для SSH:")
    await state.set_state(AddVpnUser.waiting_for_username)
    await callback.answer()


@router.message(AddVpnUser.waiting_for_username)
async def add_vpn_user_username(message: Message, state: FSMContext):
    """Получить username для SSH"""
    await state.update_data(username=message.text)
    await message.answer("Введите пароль для SSH:")
    await state.set_state(AddVpnUser.waiting_for_password)


@router.message(AddVpnUser.waiting_for_password)
async def add_vpn_user_password(message: Message, state: FSMContext):
    """Получить пароль и создать пользователя"""
    data = await state.get_data()
    server_id = data['server_id']
    username = data['username']
    password = message.text
    
    server = await db.get_server(server_id)
    
    if not server:
        await message.answer("Сервер не найден", reply_markup=main_menu_kb())
        await state.clear()
        return
    
    await message.answer("Создаю пользователя...")
    
    try:
        # Подключаемся к серверу
        client = XrayClient(
            server_ip=server['server_ip'],
            username=username,
            password=password,
            sni=config.DEFAULT_SNI
        )
        
        # Создаем пользователя с рандомным email
        random_email = f"user_{uuid.uuid4().hex[:8]}@vpn.local"
        user = client.add_user(random_email)
        
        if user and 'vless_link' in user:
            # Сохраняем в БД
            await db.add_vpn_user(
                server_id=server_id,
                email=user['email'],
                uuid=user['uuid'],
                vless_link=user['vless_link']
            )
            
            await message.answer(
                f"Пользователь создан!\n\n"
                f"Email: {user['email']}\n\n"
                f"VLESS ключ:\n<code>{user['vless_link']}</code>",
                parse_mode="HTML",
                reply_markup=back_to_server_kb(server_id)
            )
        else:
            await message.answer(
                "Ошибка при создании пользователя",
                reply_markup=back_to_server_kb(server_id)
            )
    
    except Exception as e:
        await message.answer(
            f"Ошибка:\n{str(e)}",
            reply_markup=back_to_server_kb(server_id)
        )
    
    await state.clear()
