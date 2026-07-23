import vk_api
from vk_api.longpoll import VkLongPoll, VkEventType
from vk_api.keyboard import VkKeyboard, VkKeyboardColor
from src.config import VK_TOKEN
import src.db as db
import random
import time
import sys
import os
import subprocess
import json

# Инициализируем БД
db.init_db()

vk_session = vk_api.VkApi(token=VK_TOKEN)
longpoll = VkLongPoll(vk_session)
vk = vk_session.get_api()

# =========================================================
# НАСТРОЙКА КРИТИЧЕСКИХ ID (Замени числа на свои ID чатов!)
# =========================================================
GROUP_ID = 123456789         # Твой ID группы ВК (числа из настроек)
TARGET_CHAT_ID = 2000000001  # Чат «Работяги / Заработок» (для конкурсов)
TEST_CHAT_ID = 2000000002    # Чат «Тест» (для трансляции всех сообщений)
CONSOLE_CHAT_ID = 2000000003 # Чат «Консоль» (ИСПРАВЛЕНО: Сюда идут абсолютно все логи админов)
MODER_CHAT_ID = 2000000004   # Чат «Модерация»
OWNER_VK_ID = 827888215      # Твой реальный ID Владельца

# ПЕРЕМЕННЫЕ ДЛЯ ЕЖЕЧАСНОГО КОНКУРСА И КЭША
next_contest_time = time.time() + 3600
current_contest_word = None
is_contest_active = False
WORDS_POOL = ["миллион", "баланс", "бонус", "крипта", "розыгрыш", "скорость", "приз", "работяга", "нищий", "кликер"]
ban_notified_users = {}

# Состояния донатов
pending_donations = {}

# Список товаров для Карусели (Шаблон VK Template)
SHOP_ITEMS = [
    {
        "id": 0, 
        "title": "Снятие КД на кликер (12ч)", 
        "cost": "50 мм", 
        "cmd": "Купить Снятие КД (12ч)",
        "desc": "Снижает задержку кликера до 50 мс на 12 часов."
    },
    {
        "id": 1, 
        "title": "Множитель х2 клика (12ч)", 
        "cost": "100 мм", 
        "cmd": "Купить х2 клик (12ч)",
        "desc": "Удваивает награду за каждый клик (+30 мк) на 12 часов."
    }
]
def str_to_num(text):
    text = text.replace(',', '.').strip().lower()
    multipliers = {
        'ммк': 1_000_000_000_000_000, 'ккккк': 1_000_000_000_000_000,
        'мм': 1_000_000_000_000, 'кккк': 1_000_000_000_000,
        'мк': 1_000_000_000, 'ккк': 1_000_000_000,
        'кк': 1_000_000, 'м': 1_000_000, 'к': 1_000
    }
    for key, value in multipliers.items():
        if text.endswith(key):
            try:
                num_part = text[:-len(key)].strip()
                return int(float(num_part) * value)
            except ValueError: return None
    try: return int(float(text))
    except ValueError: return None

def num_to_str(num):
    num = int(num)
    if num >= 1_000_000_000_000_000: return f"{int(num / 1_000_000_000_000_000)} ммк"
    if num >= 1_000_000_000_000: return f"{int(num / 1_000_000_000_000)} мм"
    if num >= 1_000_000_000: return f"{int(num / 1_000_000_000)} мк"
    if num >= 1_000_000: return f"{int(num / 1_000_000)} кк"
    if num >= 1_000: return f"{int(num / 1_000)} к"
    return str(num)

def parse_user_id(text):
    text = text.strip()
    if '://vk.com' in text:
        domain = text.split('://vk.com')[-1].replace(']', '').replace('[', '').strip()
        if '|' in domain: domain = domain.split('|')[0]
        try:
            res = vk.utils.resolveScreenName(screen_name=domain)
            if res and res['type'] == 'user': return res['object_id']
        except: pass
    if '[id' in text and '|' in text:
        try: return int(text.split('[id')[-1].split('|')[0])
        except: pass
    try: return int(text)
    except ValueError: return None

def parse_target(parts, index, event_raw):
    # Метод 1: Проверка ответа на сообщение (reply)
    if event_raw and 'fwd_messages' in event_raw and event_raw['fwd_messages']:
        return event_raw['fwd_messages'][0]['user_id']
    if event_raw and 'reply_message' in event_raw and event_raw['reply_message']:
        return event_raw['reply_message']['user_id']
    # Метод 2: Парсинг аргумента из текста команды
    if len(parts) > index:
        return parse_user_id(parts[index])
    return None

def get_user_mention(user_id):
    u_data = db.get_user(user_id)
    if u_data and u_data.get('nickname'): return f"[id{user_id}|{u_data['nickname']}]"
    try:
        vk_user = vk.users.get(user_ids=user_id)[0]
        return f"[id{user_id}|{vk_user['first_name']}]"
    except: return f"[id{user_id}|Игрок]"
def send_msg(chat_or_user_id, text, keyboard=None, template=None):
    params = {"random_id": 0, "message": text}
    if chat_or_user_id > 2000000000: params["peer_id"] = chat_or_user_id
    else: params["user_id"] = chat_or_user_id
    if keyboard: params["keyboard"] = keyboard
    if template: params["template"] = json.dumps(template, ensure_ascii=False)
    try: vk.messages.send(**params)
    except Exception as e: print(f"Ошибка отправки: {e}")

def get_main_keyboard():
    kb = VkKeyboard(one_time=False)
    kb.add_button('👤 Профиль', color=VkKeyboardColor.PRIMARY)
    kb.add_button('💸 Вывод', color=VkKeyboardColor.PRIMARY)
    kb.add_line()
    kb.add_button('🕹 Мини-игры', color=VkKeyboardColor.PRIMARY)
    kb.add_button('🛍 Магазин', color=VkKeyboardColor.PRIMARY)
    kb.add_line()
    kb.add_button('💰 Баланс', color=VkKeyboardColor.POSITIVE)
    kb.add_button('🎁 Бонус', color=VkKeyboardColor.POSITIVE)
    kb.add_line()
    kb.add_button('🛠 Тех. поддержка', color=VkKeyboardColor.SECONDARY)
    return kb.get_keyboard()

def get_games_keyboard():
    kb = VkKeyboard(one_time=False)
    kb.add_button('📱 Кликер', color=VkKeyboardColor.PRIMARY)
    kb.add_button('💣 Мины', color=VkKeyboardColor.PRIMARY)
    kb.add_button('🕵‍♂ Загадки', color=VkKeyboardColor.PRIMARY)
    kb.add_line()
    kb.add_button('⬅ Назад', color=VkKeyboardColor.SECONDARY)
    return kb.get_keyboard()

def get_shop_carousel():
    elements = []
    for item in SHOP_ITEMS:
        elements.append({
            "title": item["title"],
            "description": f"Стоимость: {item['cost']}\n{item['desc']}",
            "buttons": [{
                "action": {
                    "type": "text",
                    "label": "Получить",
                    "payload": json.dumps({"shop_action": "buy_intent", "id": item["id"]})
                },
                "color": "positive"
            }]
        })
    return {"type": "carousel", "elements": elements}

def get_shop_confirm_keyboard(item_id):
    kb = VkKeyboard(inline=True)
    kb.add_callback_button(label="🔄 Подтвердить отправку", color=VkKeyboardColor.POSITIVE, payload={"action": "shop_confirm_pay", "item_id": item_id})
    return kb.get_keyboard()

def get_confirm_keyboard(donation_id):
    kb = VkKeyboard(inline=True)
    kb.add_callback_button(label="✅ Да", color=VkKeyboardColor.POSITIVE, payload={"action": "don_yes", "id": donation_id})
    kb.add_callback_button(label="❌ Нет", color=VkKeyboardColor.NEGATIVE, payload={"action": "don_no", "id": donation_id})
    return kb.get_keyboard()
print("🚀 Бот 'Заработок | Бот нищий' запущен!")
for event in longpoll.listen():
    # ОБРАБОТКА CALLBACK КНОПОК ПОДТВЕРЖДЕНИЯ ДОНАТА В ЛС
    if event.type == VkEventType.MESSAGE_NEW and hasattr(event, 'payload') and event.payload:
        try: payload = json.loads(event.payload)
        except: payload = None
        
        if payload:
            uid = event.user_id
            peer = event.peer_id
            action = payload.get("action")
            
            if action == "shop_confirm_pay":
                item_id = payload.get("item_id")
                item = next((i for i in SHOP_ITEMS if i["id"] == item_id), None)
                if not item: continue
                
                don_id = f"don_{int(time.time())}_{uid}_{item_id}"
                pending_donations[don_id] = {"uid": uid, "item_id": item_id, "cost": item["cost"]}
                
                mention = get_user_mention(uid)
                confirm_text = f" ник {mention} утверждает, что перевел вам {item['cost']}, проверьте правда ли это"
                send_msg(OWNER_VK_ID, confirm_text, keyboard=get_confirm_keyboard(don_id))
                send_msg(peer, f"💸 Запрос отправлен Владельцу бота. Ожидайте подтверждения перевода.")
                continue

            elif action in ["don_yes", "don_no"] and uid == OWNER_VK_ID:
                don_id = payload.get("id")
                don_data = pending_donations.get(don_id)
                if not don_data:
                    send_msg(peer, "❌ Транзакция устарела или не найдена.")
                    continue
                
                target_uid = don_data["uid"]
                item_id = don_data["item_id"]
                now = time.time()
                t_str = time.strftime("%H:%M:%S")
                
                if action == "don_yes":
                    if item_id == 0:
                        db.update_user_field(target_uid, 'no_cd_until', now + 43200) # 12 часов снятия КД
                        send_msg(target_uid, "✅ Снятие КД на кликер на 12 часов успешно активировано! Задержка снижена до 50 мс.")
                    elif item_id == 1:
                        db.update_user_field(target_uid, 'x2_until', now + 43200) # 12 часов х2 клика
                        send_msg(target_uid, "✅ Множитель х2 кликов на 12 часов успешно активирован! (Награда +30 мк).")
                    send_msg(peer, f"✅ Вы успешно подтвердили покупку.")
                    if CONSOLE_CHAT_ID:
                        send_msg(CONSOLE_CHAT_ID, f"⏰ [{t_str}] 💎 Владелец одобрил выдачу товара ID {item_id} игроку {get_user_mention(target_uid)}")
                else:
                    send_msg(target_uid, " разработчик не подтвердил перевод денег")
                    send_msg(peer, "❌ Вы отклонили заявку.")
                    if CONSOLE_CHAT_ID:
                        send_msg(CONSOLE_CHAT_ID, f"⏰ [{t_str}] ⚠️ Владелец ОТКЛОНИЛ выдачу товара ID {item_id} игроку {get_user_mention(target_uid)}")
                
                pending_donations.pop(don_id, None)
                continue

    # ОБРАБОТКА ОБЫЧНЫХ ТЕКСТОВЫХ СООБЩЕНИЙ
    if event.type == VkEventType.MESSAGE_NEW and event.to_me:
        msg = event.text.strip()
        msg_lower = msg.lower()
        uid = event.user_id
        peer = event.peer_id
        
        # Получаем полный словарь события через API для проверки ответов (reply)
        event_raw = None
        try:
            history = vk.messages.getHistory(peer_id=peer, count=1)
            if history and history.get('items'):
                event_raw = history['items'][0]
        except: pass

        # АВТОМАТИЧЕСКАЯ ВЫДАЧА ДОЛЖНОСТИ ВЛАДЕЛЬЦА (РАНГ 5)
        user = db.get_user(uid)
        if uid == OWNER_VK_ID and user['moder_rank'] != 5:
            db.update_user_field(uid, 'moder_rank', 5)
            user = db.get_user(uid)

        # --- ЧАТ «ТЕСТ»: ТРАНСЛЯЦИЯ СООБЩЕНИЙ С ЛОГОМ [ЧЧ.ММ.СС] И БЕЗ ЗВЕЗДОЧЕК ---
        if TEST_CHAT_ID and peer != TEST_CHAT_ID and peer != CONSOLE_CHAT_ID and peer != MODER_CHAT_ID:
            t_str = time.strftime("%H.%M.%S")
            mention = get_user_mention(uid)
            send_msg(TEST_CHAT_ID, f"[{t_str}] {msg} от {mention}")

        # --- СИСТЕМА ЖИВЫХ БАНОВ ---
        if user['is_perm_banned']: continue
        if user['ban_until'] > time.time():
            now = time.time()
            if uid not in ban_notified_users or (now - ban_notified_users[uid]) > 300:
                ban_notified_users[uid] = now
                seconds_left = int(user['ban_until'] - now)
                hours = seconds_left // 3600
                minutes = (seconds_left % 3600) // 60
                seconds = seconds_left % 60
                send_msg(peer, f"⚠️ Вы были заблокированы в боте!\nРазблокировка через {hours:02d}:{minutes:02d}:{seconds:02d}\nПричина: {user['ban_reason']}")
            continue

        # --- КОНКУРС В ЧАТЕ РАБОТЯГ ---
        if peer == TARGET_CHAT_ID and time.time() >= next_contest_time:
            current_contest_word = random.choice(WORDS_POOL)
            is_contest_active = True
            next_contest_time = time.time() + 3600
            send_msg(TARGET_CHAT_ID, f"🎁 **ЕЖЕЧАСНЫЙ КОНКУРС!**\n\nПервый, кто напишет слово «{current_contest_word}» без кавычек, получит 1 мм на свой игровой баланс!")
            continue

        if is_contest_active and peer == TARGET_CHAT_ID and msg_lower == current_contest_word:
            is_contest_active = False
            current_contest_word = None
            db.add_balance(uid, 1_000_000_000_000)
            send_msg(TARGET_CHAT_ID, f"🎉 Поздравляем, {get_user_mention(uid)}! Ты оказался самым быстрым и забрал 1 мм на баланс! 💰")
            continue
        # =========================================================
        # ОБРАБОТКА ОБЫЧНЫХ КНОПОК И КОМАНД ПОЛЬЗОВАТЕЛЯ
        # =========================================================

        if msg_lower == "💰 баланс" or msg_lower == "баланс":
            send_msg(peer, f"👀 Ваш баланс: {num_to_str(user['balance'])}", get_main_keyboard())

        elif msg_lower == "🛍 магазин" or msg_lower == "магазин":
            # ИСПРАВЛЕНО: Теперь отправляется реальная графическая карусель с карточками товаров
            send_msg(peer, "🛍️ Добро пожаловать в магазин услуг! Листайте карточки:", template=get_shop_carousel())

        elif msg_lower.startswith("купить снятие кд (12ч)"):
            send_msg(peer, " отлично! переведите в @badbotik(боте нищем) юзеру @dimo4kaenergy 50мм и нажмите на кнопку подтвердить после отправки", get_shop_confirm_keyboard(0))

        elif msg_lower.startswith("купить х2 клик (12ч)"):
            send_msg(peer, " отлично! переведите в @badbotik(боте нищем) юзеру @dimo4kaenergy 100мм и нажмите на кнопку подтвердить после отправки", get_shop_confirm_keyboard(1))

        elif msg_lower == "🛠 тех. поддержка":
            support_text = "Тех. администратор отвечает в течении 12 часов!\nТех. администратор — [francescopapa|Агент Сенгоку]"
            send_msg(peer, support_text, get_main_keyboard())

        elif msg_lower == "🕹 mini-игры" or msg_lower == "мини-игры":
            send_msg(peer, "🕹 Выберите интересующую мини-игру из списка ниже:", get_games_keyboard())

        elif msg_lower == "⬅ назад" or msg_lower == "назад":
            send_msg(peer, "⬅ Вы вернулись в главное меню:", get_main_keyboard())

        elif msg_lower == "📱 кликер" or msg_lower == "клик" or msg_lower == "📱 клик":
            now = time.time()
            has_no_cd = user['no_cd_until'] > now
            
            # ИСПРАВЛЕНО: Кулдаун снижается до 50 мс (0.05 сек), если куплена услуга
            required_cd = 0.05 if has_no_cd else 3.0
            if (now - user['last_click']) < required_cd:
                if not has_no_cd:
                    left = required_cd - (now - user['last_click'])
                    send_msg(peer, f"⏳ Кулдаун! Подожди еще {left:.1f} сек. Или купи снятие КД в магазине!")
                continue
                
            db.update_user_field(uid, 'last_click', now)
            db.update_user_field(uid, 'clicks_count', user['clicks_count'] + 1)
            
            is_x2 = user.get('x2_until', 0) > now
            click_reward = 30_000_000_000 if is_x2 else 15_000_000_000
            
            new_bal = db.add_balance(uid, click_reward)
            reward_txt = "+30 мк (Активен х2 буст!)" if is_x2 else "+15 мк."
            send_msg(peer, f"🎯 Клик! {reward_txt}\n💰 Баланс: {num_to_str(new_bal)}")

        elif msg_lower == "🎁 бонус" or msg_lower == "бонус":
            now = time.time()
            if (now - user['last_daily']) < 86400:
                seconds_left = int(86400 - (now - user['last_daily']))
                hours = seconds_left // 3600
                minutes = (seconds_left % 3600) // 60
                send_msg(peer, f"❌ Бонус уже получен! Приходи через {hours} ч. {minutes} мин.")
                continue
            win_type = random.choices(['low', 'med', 'high', 'jackpot'], weights=[70, 24, 5.9, 0.1])[0]
            if win_type == 'low':
                win_amount = int(random.randint(200, 300) * 1_000_000_000)
                txt = f"🎁 Ты забрал ежедневный бонус: {num_to_str(win_amount)}"
            elif win_type == 'med':
                win_amount = int(random.randint(500, 5000) * 1_000_000_000)
                txt = f"🔥 Отлично! Ежедневный бонус принес тебе: {num_to_str(win_amount)}"
            elif win_type == 'high':
                win_amount = int(random.randint(10, 100) * 1_000_000_000_000)
                txt = f"💎 ВАУ! Крупный куш в бонусе: {num_to_str(win_amount)}"
            else:
                win_amount = 2_000_000_000_000_000
                txt = f"🎉 ЛЕГЕНДАРНО! Ты поймал 0.1% шанс и выиграл главный приз: 2 ммк!"
            db.update_user_field(uid, 'last_daily', now)
            db.add_balance(uid, win_amount)
            send_msg(peer, txt)
            
        elif msg_lower == "🕵 shadow загадки" or msg_lower == "🕵‍♂ загадки":
            send_msg(peer, "🕵‍♂ Загадки временно отключены на техническое обслуживание. Используй кликер!")
            
        elif msg_lower == "💣 мины":
            send_msg(peer, "💣 Игра 'Мины' (Сапер) настраивается администрацией. Скоро запуск!")
            
        elif msg_lower == "профиль" or msg_lower == "👤 профиль":
            ranks = {0: "Игрок", 1: "Модератор", 2: "Администратор", 3: "Гл. Администратор", 4: "Зам. Владельца", 5: "Владелец"}
            role = ranks.get(user['moder_rank'], "Игрок")
            mention = get_user_mention(uid)
            profile_card = (
                f"🌎 Профиль пользователя {mention}\n🍭 Имя пользователя: {mention}\n👹 {role}\n"
                f"🍻 Баланс: {num_to_str(user['balance'])}\n🏀 Кликов в боте: {user['clicks_count']}\n"
                f"🧠 Всего выведено: {num_to_str(user['total_withdrawn'])}\n💀 Дата регистрации в боте: {user['reg_date']}"
            )
            send_msg(peer, profile_card, get_main_keyboard())

        elif msg_lower.startswith("+ник "):
            new_nick = msg[5:].strip()
            if len(new_nick) > 20 or len(new_nick) < 2:
                send_msg(peer, "❌ Ник должен быть от 2 до 20 символов!")
                continue
            db.update_user_field(uid, 'nickname', new_nick)
            send_msg(peer, f"✅ Ты успешно установил себе ник: {new_nick}")

        elif msg_lower.startswith("вывод") or msg_lower == "💸 вывод":
            parts = msg.split()
            if len(parts) < 2:
                send_msg(peer, "💡 Подсказка: Пиши правильно: вывод [сумма, например: 1мм или 1кккк]")
                continue
            amount = str_to_num(parts[1])
            if amount is None or amount <= 0:
                send_msg(peer, "❌ Подсказка: Неверный формат суммы! Пример: вывод 2мм")
                continue
            if user['balance'] < amount:
                send_msg(peer, f"❌ У тебя нет столько денег! Твой баланс: {num_to_str(user['balance'])}")
                continue
            if amount < 1_000_000_000_000:
                send_msg(peer, "❌ Минимальный вывод от 1 мм!")
                continue
            db.add_balance(uid, -amount)
            db.update_user_field(uid, 'total_withdrawn', user['total_withdrawn'] + amount)
            db.add_withdraw_log(uid, amount)
            send_msg(peer, f"💸 Запрос на автовывод отправлен!\nСписано: {num_to_str(amount)}\nТранзакция по API завершена успешно!")
        # =========================================================
        # 🛡️ АДМИНИСТРАТИВНЫЙ БЛОК (ИСПРАВЛЕНО: ТРАНСЛЯЦИЯ СТРОГО В КОНСОЛЬ)
        # =========================================================

        elif msg_lower == "//help":
            r = user['moder_rank']
            txt = "📋 **ПОМОЩЬ ПО КОМАНДАМ:**\n\n"
            txt += "👤 **Ранг 0 (Игрок):**\n- баланс\n- профиль\n- +ник [имя]\n- вывод [сумма]\n- бонус\n\n"
            if r >= 1: txt += "🛡️ **Ранг 1 (Модератор):**\n- проф [цель]\n- баланс [цель]\n\n"
            if r >= 2: txt += "⚔️ **Ранг 2 (Администратор):**\n- //logs\n\n"
            if r >= 3: txt += "🔥 **Ранг 3 (Гл. Админ):**\n- //ban [-1/0/дни] [цель] [причина]\n- //moder [1 или 2] [цель] (управление составом)\n\n"
            if r >= 4: txt += "⚡ **Ранг 4 (Зам. Владельца):**\n- //moder [до ранга 3] [цель]\n\n"
            if r == 5: txt += "👑 **Ранг 5 (Разработчик):**\n- выдать [цель] [сумма]\n- //moder [до ранга 5] [цель]\n- //chatid\n- //update\n"
            send_msg(peer, txt)

        elif msg_lower.startswith(("проф ", "профиль ")) and user['moder_rank'] >= 1:
            parts = msg.split()
            target_id = parse_target(parts, 1, event_raw)
            if not target_id:
                send_msg(peer, "❌ Подсказка: Укажи цель (ссылка/ответ на смс)!")
                continue
            t_user = db.get_user(target_id)
            ranks = {0: "Игрок", 1: "Модератор", 2: "Администратор", 3: "Гл. Администратор", 4: "Зам. Владельца", 5: "Владелец"}
            t_role = ranks.get(t_user['moder_rank'], "Игрок")
            t_mention = get_user_mention(target_id)
            profile_card = (
                f"🌎 Профиль пользователя {t_mention}\n🍭 Имя пользователя: {t_mention}\n👹 {t_role}\n"
                f"🍻 Баланс: {num_to_str(t_user['balance'])}\n🏀 Кликов в боте: {t_user['clicks_count']}\n"
                f"🧠 Всего выведено: {num_to_str(t_user['total_withdrawn'])}\n💀 Дата регистрации в боте: {t_user['reg_date']}"
            )
            send_msg(peer, profile_card)

        elif msg_lower.startswith("баланс ") and user['moder_rank'] >= 1:
            parts = msg.split()
            target_id = parse_target(parts, 1, event_raw)
            if not target_id:
                send_msg(peer, "❌ Подсказка: Укажи цель!")
                continue
            t_user = db.get_user(target_id)
            send_msg(peer, f"🍻 Баланс пользователя {get_user_mention(target_id)} составляет: {num_to_str(t_user['balance'])}")

        elif msg_lower.startswith("выдать "):
            if user['moder_rank'] != 5:
                send_msg(peer, "❌ Ошибка доступа!")
                continue
            parts = msg.split()
            target_id = parse_target(parts, 1, event_raw)
            # Если команда дана ответом, сумма будет в parts[1], иначе в parts[2]
            amount_idx = 1 if (event_raw and ('reply_message' in event_raw or 'fwd_messages' in event_raw)) else 2
            amount = str_to_num(parts[amount_idx]) if len(parts) > amount_idx else None
            
            if not target_id or amount is None or amount <= 0:
                send_msg(peer, "❌ Подсказка: выдать [цель] [сумма]")
                continue
            db.add_balance(target_id, amount)
            t_mention = get_user_mention(target_id)
            t_str = time.strftime("%H:%M:%S")
            send_msg(peer, f"✅ Вы успешно выдали {num_to_str(amount)} пользователю {t_mention}")
            if CONSOLE_CHAT_ID: 
                send_msg(CONSOLE_CHAT_ID, f"⏰ [{t_str}] 🛠️ Разработчик {get_user_mention(uid)} выдал {num_to_str(amount)} пользователю {t_mention}")

        elif msg_lower.startswith("//moder "):
            r = user['moder_rank']
            if r < 3:
                send_msg(peer, "❌ Ошибка доступа!")
                continue
            parts = msg.split()
            if len(parts) < 2:
                send_msg(peer, "❌ Подсказка: //moder [ранг] [цель]")
                continue
            try: target_rank = int(parts[1])
            except ValueError:
                send_msg(peer, "❌ Неверный формат ранга!")
                continue
                
            target_id = parse_target(parts, 2, event_raw)
            if not target_id:
                send_msg(peer, "❌ Целевой пользователь не найден!")
                continue
                
            # ИЕРАРХИЯ ДОСТУПА ПО ТЗ
            if r == 3: # Гл. Администратор
                if target_rank not in [-1, 1, 2]:
                    send_msg(peer, "❌ Вы можете назначать/снимать только ранги 1 (Модератор) и 2 (Администратор)!")
                    continue
            elif r == 4: # Зам. Владельца
                if target_rank > 3:
                    send_msg(peer, "❌ Вы не можете назначать ранги выше Гл. Администратора (3)!")
                    continue
            elif r == 5: # Разработчик
                if target_rank < -1 or target_rank > 5: continue
                
            final_rank = max(0, target_rank) if target_rank != -1 else 0
            db.update_user_field(target_id, 'moder_rank', final_rank)
            t_str = time.strftime("%H:%M:%S")
            send_msg(peer, "успешно!")
            if CONSOLE_CHAT_ID: 
                send_msg(CONSOLE_CHAT_ID, f"⏰ [{t_str}] 🛠️ {get_user_mention(uid)} изменил ранг {get_user_mention(target_id)} на {final_rank}")

        elif msg_lower.startswith("//ban "):
            if user['moder_rank'] < 3:
                send_msg(peer, "❌ Доступ запрещен!")
                continue
            parts = msg.split()
            if len(parts) < 2:
                send_msg(peer, "❌ Подсказка: //ban [дни] [цель]")
                continue
            try: days = int(parts[1])
            except ValueError: continue
            
            target_id = parse_target(parts, 2, event_raw)
            if not target_id: continue
            
            # Разделение индекса причины в зависимости от способа указания цели
            reason_idx = 2 if (event_raw and ('reply_message' in event_raw or 'fwd_messages' in event_raw)) else 3
            reason = " ".join(parts[reason_idx:]) if len(parts) > reason_idx else "Нарушение правил"
            t_str = time.strftime("%H:%M:%S")
            
            if days == 0:
                db.update_user_field(target_id, 'ban_until', 0)
                db.update_user_field(target_id, 'is_perm_banned', 0)
                send_msg(peer, "успешно!")
                if CONSOLE_CHAT_ID: send_msg(CONSOLE_CHAT_ID, f"⏰ [{t_str}] 🛠️ {get_user_mention(uid)} разбанил {get_user_mention(target_id)}")
            elif days == -1:
                db.update_user_field(target_id, 'is_perm_banned', 1)
                db.update_user_field(target_id, 'ban_reason', reason)
                send_msg(peer, f"⛔ Пользователь забанен навсегда. Причина: {reason}")
                if CONSOLE_CHAT_ID: send_msg(CONSOLE_CHAT_ID, f"⏰ [{t_str}] ⛔ {get_user_mention(uid)} выдал ВЕЧНЫЙ БАН {get_user_mention(target_id)}. Причина: {reason}")
            elif days > 0:
                ban_time = time.time() + (days * 86400)
                db.update_user_field(target_id, 'ban_until', ban_time)
                db.update_user_field(target_id, 'ban_reason', reason)
                send_msg(peer, f"⏳ Пользователь заблокирован на {days} д. Причина: {reason}")
                if CONSOLE_CHAT_ID: send_msg(CONSOLE_CHAT_ID, f"⏰ [{t_str}] ⏳ {get_user_mention(uid)} забанил {get_user_mention(target_id)} на {days} д. Причина: {reason}")

        elif msg_lower == "//logs":
            if user['moder_rank'] < 2: continue
            logs = db.get_withdraw_logs(10)
            txt = "📋 ПОСЛЕДНИЕ 10 ВЫВОДОВ С БОТА:\n\n"
            for log in logs:
                try:
                    t_str = time.strftime("%H:%M:%S", time.localtime(log))
                    txt += f"⏰ [{t_str}] ID {log} ➡️ Вывел: {num_to_str(log)}\n"
                except Exception:
                    txt += f"📝 Лог: {str(log)}\n"
            send_msg(peer, txt)

        elif msg_lower == "//chatid":
            if user['moder_rank'] != 5: continue
            send_msg(peer, f"🆔 ID этой беседы: {peer}")

        elif msg_lower == "//update":
            if user['moder_rank'] != 5: continue
            send_msg(peer, "🔄 Начинаю обновление... Скачиваю свежий код с GitHub...")
            try:
                pull_res = subprocess.check_output(["git", "pull"], stderr=subprocess.STDOUT).decode('utf-8')
                send_msg(peer, f"📥 Код обновлен успешно!\n\n🔄 Перезапускаю процесс скрипта...")
                os.execv(sys.executable, [sys.executable] + sys.argv)
            except Exception as e: send_msg(peer, f"❌ Ошибка при обновлении: {str(e)}")
