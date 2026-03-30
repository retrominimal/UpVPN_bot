"""
Модели базы данных
"""

import asyncpg
from typing import Optional, List, Dict
import config


class Database:
    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None
    
    async def connect(self):
        """Подключение к БД"""
        self.pool = await asyncpg.create_pool(
            host=config.DB_HOST,
            port=config.DB_PORT,
            database=config.DB_NAME,
            user=config.DB_USER,
            password=config.DB_PASSWORD
        )
        await self.create_tables()
    
    async def close(self):
        """Закрытие подключения"""
        if self.pool:
            await self.pool.close()
    
    async def create_tables(self):
        """Создание таблиц"""
        async with self.pool.acquire() as conn:
            # Таблица пользователей бота
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    username VARCHAR(255),
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)
            
            # Таблица серверов
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS servers (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT REFERENCES users(user_id) ON DELETE CASCADE,
                    server_ip VARCHAR(255) NOT NULL,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)
            
            # Таблица VPN пользователей на серверах
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS vpn_users (
                    id SERIAL PRIMARY KEY,
                    server_id INTEGER REFERENCES servers(id) ON DELETE CASCADE,
                    email VARCHAR(255) NOT NULL,
                    uuid VARCHAR(255) NOT NULL,
                    vless_link TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)
    
    # === USERS ===
    async def add_user(self, user_id: int, username: str = None):
        """Добавить пользователя"""
        async with self.pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO users (user_id, username) VALUES ($1, $2) ON CONFLICT (user_id) DO NOTHING",
                user_id, username
            )
    
    async def get_all_users(self) -> List[int]:
        """Получить всех пользователей"""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("SELECT user_id FROM users")
            return [row['user_id'] for row in rows]
    
    async def get_users_count(self) -> int:
        """Количество пользователей"""
        async with self.pool.acquire() as conn:
            return await conn.fetchval("SELECT COUNT(*) FROM users")
    
    # === SERVERS ===
    async def add_server(self, user_id: int, server_ip: str) -> int:
        """Добавить сервер"""
        async with self.pool.acquire() as conn:
            return await conn.fetchval(
                "INSERT INTO servers (user_id, server_ip) VALUES ($1, $2) RETURNING id",
                user_id, server_ip
            )
    
    async def get_user_servers(self, user_id: int) -> List[Dict]:
        """Получить серверы пользователя"""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, server_ip, created_at FROM servers WHERE user_id = $1 ORDER BY created_at DESC",
                user_id
            )
            return [dict(row) for row in rows]
    
    async def get_server(self, server_id: int) -> Optional[Dict]:
        """Получить сервер по ID"""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM servers WHERE id = $1",
                server_id
            )
            return dict(row) if row else None
    
    async def get_servers_count(self) -> int:
        """Количество серверов"""
        async with self.pool.acquire() as conn:
            return await conn.fetchval("SELECT COUNT(*) FROM servers")
    
    # === VPN USERS ===
    async def add_vpn_user(self, server_id: int, email: str, uuid: str, vless_link: str):
        """Добавить VPN пользователя"""
        async with self.pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO vpn_users (server_id, email, uuid, vless_link) VALUES ($1, $2, $3, $4)",
                server_id, email, uuid, vless_link
            )
    
    async def get_server_vpn_users(self, server_id: int) -> List[Dict]:
        """Получить VPN пользователей сервера"""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, email, uuid, vless_link, created_at FROM vpn_users WHERE server_id = $1 ORDER BY created_at",
                server_id
            )
            return [dict(row) for row in rows]
    
    async def get_vpn_user(self, vpn_user_id: int) -> Optional[Dict]:
        """Получить VPN пользователя по ID"""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM vpn_users WHERE id = $1",
                vpn_user_id
            )
            return dict(row) if row else None
    
    async def get_vpn_users_count(self) -> int:
        """Количество VPN пользователей"""
        async with self.pool.acquire() as conn:
            return await conn.fetchval("SELECT COUNT(*) FROM vpn_users")


db = Database()
