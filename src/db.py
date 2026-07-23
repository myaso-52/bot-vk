import sqlite3
import os

DB_PATH = "data/database.db"

def init_db():
    """Создает папку data и таблицу пользователей, если их нет"""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            balance INTEGER DEFAULT 1000
        )
    ''')
    conn.commit()
    conn.close()

def get_balance(user_id):
    """Получает баланс игрока. Если игрока нет — регистрирует и дает 1000 коинов"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    
    if row is None:
        cursor.execute("INSERT INTO users (user_id, balance) VALUES (?, ?)", (user_id, 1000))
        conn.commit()
        balance = 1000
    else:
        balance = row[0]
        
    conn.close()
    return balance

def update_balance(user_id, amount):
    """Изменяет баланс (amount может быть + или -)"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    get_balance(user_id) 
    cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()

