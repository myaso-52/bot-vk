import sqlite3
import os

# СТРОГО СОВПАДАЕТ С ПУТЕМ ИЗ MAIN.PY
DB_PATH = "database.db"

def init_db():
    """Создает таблицу пользователей и логов со всеми нужными полями для main.py"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Создаем таблицу пользователей со ВСЕМИ колонками из main.py
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            balance INTEGER DEFAULT 0,
            moder_rank INTEGER DEFAULT 0,
            clicks_count INTEGER DEFAULT 0,
            last_click REAL DEFAULT 0.0,
            last_daily REAL DEFAULT 0.0,
            total_withdrawn INTEGER DEFAULT 0,
            is_perm_banned INTEGER DEFAULT 0,
            ban_until REAL DEFAULT 0.0,
            ban_reason TEXT DEFAULT '',
            nickname TEXT DEFAULT 'Игрок',
            no_cd_until REAL DEFAULT 0.0,
            x2_until INTEGER DEFAULT 0
        )
    ''')
    
    # Создаем таблицу логов вывода, которую запрашивает команда //logs и вывод
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS withdraw_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount INTEGER,
            timestamp REAL
        )
    ''')
    
    conn.commit()
    conn.close()

def get_user(user_id):
    """Возвращает ВСЮ строку пользователя в виде словаря (user['balance'], user['moder_rank'] и т.д.)"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # КРИТИЧЕСКИ ВАЖНО: делает из строк словари!
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    
    # Если пользователя нет в базе — автоматически регистрируем его со всеми полями
    if row is None:
        cursor.execute('''
            INSERT INTO users (
                user_id, balance, moder_rank, clicks_count, last_click, 
                last_daily, total_withdrawn, is_perm_banned, ban_until, 
                ban_reason, nickname, no_cd_until, x2_until
            ) VALUES (?, 0, 0, 0, 0.0, 0.0, 0, 0, 0.0, '', 'Игрок', 0.0, 0)
        ''', (user_id,))
        conn.commit()
        
        # Берем только что созданного юзера
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        
    conn.close()
    return dict(row)

def update_user_field(user_id, field_name, value):
    """Универсальная функция обновления любого текстового или числового поля в БД"""
    # Защита от инъекций (field_name проверяем по списку разрешенных колонок)
    allowed_fields = [
        'balance', 'moder_rank', 'clicks_count', 'last_click', 
        'last_daily', 'total_withdrawn', 'is_perm_banned', 
        'ban_until', 'ban_reason', 'nickname', 'no_cd_until', 'x2_until'
    ]
    if field_name not in allowed_fields:
        return
        
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Сначала проверяем существование пользователя, чтобы не было багов
    get_user(user_id)
    
    cursor.execute(f"UPDATE users SET {field_name} = ? WHERE user_id = ?", (value, user_id))
    conn.commit()
    conn.close()

def add_balance(user_id, amount):
    """Изменяет баланс игрока на указанную сумму (+ или -) и возвращает новый баланс"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Проверяем существование пользователя
    get_user(user_id)
    
    cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    
    # Получаем новый баланс для возврата в main.py
    cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    new_balance = cursor.fetchone()[0]
    
    conn.close()
    return new_balance

def add_withdraw_log(user_id, amount):
    """Записывает лог вывода средств в базу данных"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO withdraw_logs (user_id, amount, timestamp) VALUES (?, ?, ?)", (user_id, amount, time.time()))
    conn.commit()
    conn.close()
