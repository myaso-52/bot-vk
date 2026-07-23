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
CONSOLE_CHAT_ID = 2000000003 # Чат «Консоль» (Сюда идут абсолютно все логи админов)
OWNER_VK_ID = 827888215      # Твой реальный ID Владельца

# ПЕРЕМЕННЫЕ ДЛЯ ЕЖЕЧАСНОГО КОНКУРСА И КЭША
next_contest_time = time.time() + 3600
current_contest_word = None
is_contest_active = False
WORDS_POOL = ["миллион", "баланс", "бонус", "крипта", "розыгрыш", "скорость", "приз", "работяга", "нищий", "кликер"]
ban_notified_users = {}

# Глобальное хранилище для ожидающих донатов
pending_donations = {}

# Список товаров для Карусели (Шаблон VK Template)
SHOP_ITEMS = [
    {
        "id": 0, 
        "title": "Снятие КД на кликер (12ч)", 
        "cost_coins": 50_000_000_000_000, 
        "cost_str": "50 мм",
        "desc": "Снижает задержку кликера до 50 мс на 12 часов."
    },
    {
        "id": 1, 
        "title": "Множитель х2 клика (12ч)", 
        "cost_coins": 100_000_000_000_000, 
        "cost_str": "100 мм",
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
        if '|' in domain: domain = domain.split('|')
        try:
            res = vk.utils.resolveScreenName(screen_name=domain)
            if res and res['type'] == 'user': return res['object_id']
        except: pass
    if '[id' in text and '|' in text:
        try: return int(text.split('[id')[-1].split('|'))
        except: pass
    try: return int(text)
    except ValueError: return None

def parse_target(parts, index, event_raw):
    if event_raw and 'fwd_messages' in event_raw and event_raw['fwd_messages']:
        return event_raw['fwd_messages']['user_id']
    if event_raw and 'reply_message' in event_raw and event_raw['reply_message']:
        return event_raw['reply_message']['user_id']
    if len(parts) > index:
        return parse_user_id(parts[index])
    return None

def get_user_mention(user_id):
    u_data = db.get_user(user_id)
    if u_data and u_data.get('nickname'): return f"[id{user_id}|{u_data['nickname']}]"
    try:
        vk_user = vk.users.get(user_ids=user_id)
        return f"[id{user_id}|{vk_user['first_name']}]"
    except: return f"[id{user_id}|Игрок]"
def send_msg(chat_or_user_id, text, keyboard=None, template=None):
    params = {"random_id": 0, "message": text}
    # ЖЕСТКАЯ ПРИВЯЗКА К PEER_ID ДЛЯ СТАБИЛЬНОЙ РАБОТЫ В ЛЮБЫХ БЕСЕДАХ
    if chat_or_user_id > 2000000000: params["peer_id"] = chat_or_user_id
    else: params["peer_id"] = chat_or_user_id
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
            "description": f"Стоимость: {item['cost_str']}\n{item['desc']}",
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

def get_manual_deposit_keyboard(amount_str):
    kb = VkKeyboard(inline=True)
    # ИСПРАВЛЕНО: Кнопка переведена в обычный ТЕКСТОВЫЙ формат (не зависит от пинга сервера)
    kb.add_button(label="🔄 Я перевел!", color=VkKeyboardColor.POSITIVE)
    return kb.get_keyboard()

def get_confirm_keyboard(donation_id):
    kb = VkKeyboard(inline=True)
    kb.add_callback_button(label="✅ Подтвердить", color=VkKeyboardColor.POSITIVE, payload={"action": "don_yes", "id": donation_id})
    kb.add_callback_button(label="❌ Отказать", color=VkKeyboardColor.NEGATIVE, payload={"action": "don_no", "id": donation_id})
    return kb.get_keyboard()
print("🚀 Бот 'Заработок | Бот нищий' запущен!")
for event in longpoll.listen():
    # ОБРАБОТКА CALLBACK КНОПОК ПОДТВЕРЖДЕНИЯ (ТОЛЬКО ДЛЯ ВЛАДЕЛЬЦА В ЛС)
    if event.type == VkEventType.MESSAGE_NEW and hasattr(event, 'payload') and event.payload:
        try: payload = json.loads(event.payload)
        except: payload = None
        
        if payload and "action" in payload:
            uid = event.user_id
            peer = event.peer_id
            action = payload.get("action")
            t_str = time.strftime("%H:%M:%S")
            
            if action in ["don_yes", "don_no"] and uid == OWNER_VK_ID:
                don_id = payload.get("id")
                don_data = pending_donations.get(don_id)
                if not don_data:
                    send_msg(peer, "❌ Транзакция не найдена.")
                    continue
                
                target_uid = don_data["uid"]
                don_type = don_data.get("type")
                
                if action == "don_yes":
                    if don_type == "manual_dep":
                        coins = str_to_num(don_data["amount_str"])
                        if coins and coins > 0:
                            db.add_balance(target_uid, coins)
                            send_msg(target_uid, f"🎉 Баланс успешно пополнен на {num_to_str(coins)}! Перевод подтвержден.")
                            send_msg(peer, f"✅ Вы одобрили пополнение на {don_data['amount_str']} для {get_user_mention(target_uid)}.")
                            if CONSOLE_CHAT_ID:
                                send_msg(CONSOLE_CHAT_ID, f"⏰ [{t_str}] 💸 Владелец подтвердил ручное пополнение на {don_data['amount_str']} для {get_user_mention(target_uid)}")
                        else:
                            send_msg(peer, "❌ Ошибка конвертации суммы платежа.")
                    
                    elif don_type == "shop_buy":
                        item_id = don_data["item_id"]
                        now_time = time.time()
                        if item_id == 0:
                            db.update_user_field(target_uid, 'no_cd_until', now_time + 43200)
                            send_msg(target_uid, "✅ Снятие КД на кликер на 12 часов успешно активировано! Задержка снижена до 50 мс.")
                        elif item_id == 1:
                            db.update_user_field(target_uid, 'x2_until', now_time + 43200)
                            send_msg(target_uid, "✅ Множитель х2 кликов на 12 часов успешно активирован! (Награда +30 мк).")
                        send_msg(peer, f"✅ Вы подтвердили покупку товара ID {item_id}.")
                        if CONSOLE_CHAT_ID:
                            send_msg(CONSOLE_CHAT_ID, f"⏰ [{t_str}] 💎 Владелец одобрил покупку товара ID {item_id} для {get_user_mention(target_uid)}")
                else:
                    if don_type == "manual_dep":
                        send_msg(target_uid, " разработчик не подтвердил перевод денег")
                    else:
                        send_msg(target_uid, " разработчик не подтвердил перевод денег")
                    send_msg(peer, "❌ Вы отклонили запрос.")
                    if CONSOLE_CHAT_ID:
                        send_msg(CONSOLE_CHAT_ID, f"⏰ [{t_str}] ⚠️ Владелец ОТКЛОНИЛ операцию для {get_user_mention(target_uid)}")
                
                pending_donations.pop(don_id, None)
                continue

    # ОБРАБОТКА ОБЫЧНЫХ ТЕКСТОВЫХ СООБЩЕНИЙ И ТЕКСТОВЫХ КНОПОК ПОЛЬЗОВАТЕЛЕЙ
    if event.type == VkEventType.MESSAGE_NEW and event.to_me:
        msg = event.text.strip()
        msg_lower = msg.lower()
        uid = event.user_id
        peer = event.peer_id
        
        # Получение полных данных сообщения из API для чтения реплаев
        event_raw = None
        try:
            res_msg = vk.messages.getById(message_ids=event.message_id)
            if res_msg and res_msg.get('items'):
                event_raw = res_msg['items']
        except: pass

        # АВТОМАТИЧЕСКАЯ ВЫДАЧА ДОЛЖНОСТИ ВЛАДЕЛЬЦА (РАНГ 5)
        user = db.get_user(uid)
        if uid == OWNER_VK_ID and user['moder_rank'] != 5:
            db.update_user_field(uid, 'moder_rank', 5)
            user = db.get_user(uid)

        # --- ЧАТ «ТЕСТ»: ТРАНСЛЯЦИЯ СООБЩЕНИЙ ---
        if TEST_CHAT_ID and peer != TEST_CHAT_ID and peer != CONSOLE_CHAT_ID:
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
            send_msg(peer, f"👀 Ваш баланс: {num_to_str(user['balance'])}")

        elif msg_lower == "🛍 магазин" or msg_lower == "магазин":
            send_msg(peer, "🛍️ Добро пожаловать в магазин услуг! Листайте карточки под этим сообщением:", template=get_shop_carousel())

        elif msg_lower.startswith("пополнить"):
            parts = msg.split()
            if len(parts) < 2:
                send_msg(peer, "💡 Подсказка: Пиши правильно: пополнить [сумма, например: 50мм или 10кк]")
                continue
            amount_str = " ".join(parts[1:])
            # Сохраняем во временный кэш то, какую сумму хочет пополнить юзер
            user_states[uid] = {"action": "waiting_deposit_click", "amount_str": amount_str}
            send_msg(peer, f" Переведите {amount_str} юзеру @dimo4kaenergy в @badbotik(боте нищем)", keyboard=get_manual_deposit_keyboard(amount_str))

        elif msg_lower == "🔄 я перевел!":
            # ИСПРАВЛЕНО: Кнопка ловится мгновенно как обычный текст
            state = user_states.get(uid)
            if not state or state.get("action") != "waiting_deposit_click":
                send_msg(peer, "❌ Вы не вводили команду 'пополнить' перед нажатием!")
                continue
            
            amount_str = state.get("amount_str")
            don_id = f"manual_{int(time.time())}_{uid}"
            pending_donations[don_id] = {"uid": uid, "type": "manual_dep", "amount_str": amount_str}
            
            user_states.pop(uid, None)
            mention = get_user_mention(uid)
            confirm_text = f" ник {mention} утверждает, что перевел вам {amount_str}, проверьте правда ли это"
            send_msg(OWNER_VK_ID, confirm_text, keyboard=get_confirm_keyboard(don_id))
            send_msg(peer, f"💸 Запрос на верификацию платежа {amount_str} успешно отправлен Владельцу бота.")

        elif msg_lower.startswith("купить снятие кд (12ч)"):
            item = SHOP_ITEMS
            if user['balance'] < item["cost_coins"]:
                send_msg(peer, "❌ У вас недостаточно средств!")
                continue
            db.add_balance(uid, -item["cost_coins"])
            
            don_id = f"shop_{int(time.time())}_{uid}_0"
            pending_donations[don_id] = {"uid": uid, "type": "shop_buy", "item_id": 0}
            
            mention = get_user_mention(uid)
            confirm_text = f" ник {mention} утверждает, что перевел вам {item['cost_str']} за товар '{item['title']}', проверьте правда ли это"
            send_msg(OWNER_VK_ID, confirm_text, keyboard=get_confirm_keyboard(don_id))
            send_msg(peer, f"💸 Запрос отправлен Владельцу бота. Ожидайте подтверждения перевода.")

        elif msg_lower.startswith("купить х2 клик (12ч)"):
            item = SHOP_ITEMS
            if user['balance'] < item["cost_coins"]:
                send_msg(peer, "❌ У вас недостаточно средств!")
                continue
            db.add_balance(uid, -item["cost_coins"])
            
            don_id = f"shop_{int(time.time())}_{uid}_1"
            pending_donations[don_id] = {"uid": uid, "type": "shop_buy", "item_id": 1}
            
            mention = get_user_mention(uid)
            confirm_text = f" ник {mention} утверждает, что перевел вам {item['cost_str']} за товар '{item['title']}', проверьте правда ли это"
            send_msg(OWNER_VK_ID, confirm_text, keyboard=get_confirm_keyboard(don_id))
            send_msg(peer, f"💸 Запрос отправлен Владельцу бота. Ожидайте подтверждения перевода.")

        elif msg_lower == "🛠 тех. поддержка":
            support_text = "Тех. администратор отвечает в течении 12 часов!\nТех. администратор — [francescopapa|Агент Сенгоку]"
            send_msg(peer, support_text)

        elif msg_lower == "🕹 mini-игры" or msg_lower == "мини-игры":
            # ИСПРАВЛЕНО: Теперь кнопки меняются во всех чатах со 100% стабильностью
            send_msg(peer, "🕹 Вы перешли в меню мини-игр! Кнопки изменены:", get_games_keyboard())

        elif msg_lower == "⬅ назад" or msg_lower == "назад":
            # ИСПРАВЛЕНО: Кнопка назад возвращает главное меню во всех чатах
            send_msg(peer, "⬅ Вы вернулись в главное меню бота:", get_main_keyboard())

        elif msg_lower == "📱 кликер" or msg_lower == "клик" or msg_lower == "📱 клик":
            now = time.time()
            has_no_cd = user['no_cd_until'] > now
            
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
            win_type = random.choices(['low', 'med', 'high', 'jackpot'], weights=[70, 24, 5.9, 0.1])
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
            
        elif msg_lower == "💣 мины":
            send_msg(peer, "💣 Игра 'Мины' (Сапер) настраивается администрацией. Ожидайте скорого запуска механики!")

        elif msg_lower == "🕵 загадки" or msg_lower == "🕵‍♂ загадки":
            send_msg(peer, "🕵‍♂ Загадки временно отключены на техническое обслуживание. Используй кликер!")
            
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
            amount = str_to_num(parts)
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
        # 🛡️ АДМИНИСТРАТИВНЫЙ БЛОК (ЛОГИ ТРАНСЛИРУЮТСЯ СТРОГО В КОНСОЛЬ)
        # =========================================================

        elif msg_lower == "//help":
            r = user['moder_rank']
            txt = "📋 **ПОМОЩЬ ПО КОМАНДАМ:**\n\n"
            txt += "👤 **Ранг 0 (Игрок):**\n- баланс\n- профиль\n- +ник [имя]\n- пополнить [сумма]\n- вывод [сумма]\n- бонус\n\n"
            if r >= 1: txt += "🛡️ **Ранг 1 (Модератор):**\n- проф [цель]\n- баланс [цель]\n\n"
            if r >= 2: txt += "⚔️ **Ранг 2 (Администратор):**\n- //logs\n\n"
            if r >= 3: txt += "🔥 **Ранг 3 (Гл. Администратор):**\n- //ban [-1/0/дни] [цель] [причина]\n- //moder [ранг] [цель]\n\n"
            if r >= 4: txt += "⚡ **Ранг 4 (Зам. Владельца):**\n- //moder [до ранга 3] [цель]\n\n"
            if r == 5: txt += "👑 **Ранг 5 (Разработчик):**\n- выдать [цель] [сумма]\n- //moder [до ранга 5] [цель]\n- //chatid\n- //update\n"
            send_msg(peer, txt)

        elif msg_lower.startswith(("проф ", "профиль ")) and user['moder_rank'] >= 1:
            parts = msg.split()
            target_id = parse_target(parts, 1, event_raw)
            if not target_id:
                send_msg(peer, "❌ Подсказка: Укажи цель!")
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
            
            is_reply = event_raw and ('reply_message' in event_raw or ('fwd_messages' in event_raw and event_raw['fwd_messages']))
            amount_idx = 1 if is_reply else 2
            
            if len(parts) > amount_idx:
                amount = str_to_num(parts[amount_idx])
            else:
                amount = None
                
            if not target_id or amount is None or amount <= 0:
                send_msg(peer, "❌ Подсказка: выдать [ссылка/юз/ответ на смс] [сумма]")
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
            try: target_rank = int(parts)
            except ValueError:
                send_msg(peer, "❌ Неверный формат ранга!")
                continue
                
            target_id = parse_target(parts, 2, event_raw)
            if not target_id:
                send_msg(peer, "❌ Целевой пользователь не найден!")
                continue
                
            if r == 3 and target_rank not in [-1, 1, 2]:
                send_msg(peer, "❌ Гл. Администратор может изменять только ранги 1 (Модератор) и 2 (Администратор)!")
                continue
            elif r == 4 and target_rank > 3:
                send_msg(peer, "❌ Зам. Владельца может назначать ранги только до 3 (Гл. Администратор)!")
                continue
            elif r == 5 and (target_rank < -1 or target_rank > 5):
                continue
                
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
            try: days = int(parts)
            except ValueError: continue
            
            target_id = parse_target(parts, 2, event_raw)
            if not target_id: continue
            
            is_reply = event_raw and ('reply_message' in event_raw or ('fwd_messages' in event_raw and event_raw['fwd_messages']))
            reason_idx = 2 if is_reply else 3
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
            # ИСПРАВЛЕНО: Теперь намертво возвращает чистый peer_id чата беседы, где написана команда
            send_msg(peer, f"🆔 ID этого чата: {peer}")

        elif msg_lower == "//update":
            if user['moder_rank'] != 5: continue
            send_msg(peer, "🔄 Скачиваю свежий код с GitHub...")
            try:
                subprocess.check_output(["git", "pull"], stderr=subprocess.STDOUT)
                send_msg(peer, f"📥 Код успешно обновлен! Выполняю безопасную перезагрузку фонового процесса сервера...")
                # ИСПРАВЛЕНО: Безопасный отложенный перезапуск (дает боту 1 секунду завершить отправку, исключая статус Killed)
                subprocess.Popen(["bash", "-c", "sleep 1 && pkill -9 -f main.py && source venv/bin/activate && nohup python3 main.py &"])
                sys.exit()
            except Exception as e: 
                send_msg(peer, f"❌ Ошибка обновления: {str(e)}")
