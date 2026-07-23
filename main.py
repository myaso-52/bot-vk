import vk_api
from vk_api.longpoll import VkLongPoll, VkEventType
from vk_api.keyboard import VkKeyboard, VkKeyboardColor
from src.config import VK_TOKEN
from src.db import init_db, get_balance, update_balance
import random
import json

# Инициализируем базу данных игроков
init_db()

# Подключаемся к API ВКонтакте
vk_session = vk_api.VkApi(token=VK_TOKEN)
longpoll = VkLongPoll(vk_session)
vk = vk_session.get_api()

def create_keyboard():
    """Создает удобные кнопки для игрока"""
    keyboard = VkKeyboard(one_time=False)
    
    # Первая строка кнопок
    keyboard.add_button('💰 Баланс', color=VkKeyboardColor.PRIMARY)
    keyboard.add_line() # Переход на следующую строку
    keyboard.add_button('🎲 Поставить 100 коинов', color=VkKeyboardColor.POSITIVE)
    keyboard.add_button('🎰 Поставить 500 коинов', color=VkKeyboardColor.NEGATIVE)
    
    return keyboard.get_keyboard()

def send_msg(user_id, text):
    """Функция отправки сообщения с кнопками"""
    vk.messages.send(
        user_id=user_id, 
        message=text, 
        random_id=0,
        keyboard=create_keyboard()
    )

print("🚀 Бот казино-ставок успешно запущен и слушает сервер ВК!")

# Главный цикл, который ждет сообщений от игроков
for event in longpoll.listen():
    if event.type == VkEventType.MESSAGE_NEW and event.to_me:
        msg = event.text.lower().strip()
        uid = event.user_id

        # Команда проверки баланса
        if msg == "💰 баланс" or msg == "баланс":
            bal = get_balance(uid)
            send_msg(uid, f"💳 Твой игровой счет: {bal} нищих коинов.\n\nЖми на кнопки ниже, чтобы сыграть!")

        # Логика ставок через кнопки
        elif "поставить" in msg:
            # Вытягиваем сумму ставки из текста кнопки
            try:
                bet = int([int(s) for s in msg.split() if s.isdigit()][0])
            except IndexError:
                send_msg(uid, "❌ Не удалось распознать сумму ставки. Используй кнопки!")
                continue

            current_bal = get_balance(uid)
            
            if current_bal < bet:
                send_msg(uid, f"❌ У тебя всего {current_bal} коинов. Ты слишком нищий для ставки в {bet}! Иди проси ежедневный бонус (скоро добавим).")
            else:
                # Шанс победы 45% (чтобы казино было в плюсе)
                win = random.choices([True, False], weights=[45, 55])[0]
                
                if win:
                    update_balance(uid, bet) # Прибавляем выигрыш
                    new_bal = get_balance(uid)
                    send_msg(uid, f"🎉 ФАРТАНУЛО! Ты выиграл {bet} коинов!\n💰 Твой новый баланс: {new_bal}")
                else:
                    update_balance(uid, -bet) # Списываем проигрыш
                    new_bal = get_balance(uid)
                    send_msg(uid, f"📉 СЛИВ! Минус {bet} коинов. Казино забрало твои гроши.\n💰 Остаток на счете: {new_bal}")
                    
        # Ответ на любое другое приветственное сообщение
        else:
            send_msg(uid, "👋 Привет в симуляторе ставок «Нищий»!\n\nКаждому новому игроку мы даем 1000 стартовых коинов. Проверь свой баланс по кнопке ниже!")

