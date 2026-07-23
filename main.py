import vk_api
from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType
from vk_api.keyboard import VkKeyboard, VkKeyboardColor
import src.db as db
import sqlite3
import random
import time
import sys
import os
import subprocess
import json

# Инициализируем БД
db.init_db()

# СТРОГО ОБЕРНУТЫЙ ТОКЕН В КАВЫЧКИ (ИСПРАВЛЕНО!)
VK_TOKEN = "vk1.a.4NLW0LW3cobhYjBFzUQ1uvIF8Zn93a7G9W--YJ-URTkk9tf9Qt7TCXYFGv1pQ-o17M_1oRUhJMEV53edLMcBKwIB9F3JIRJl-Vi0YXAAT26pOvv3_XY5Yc6wj6PQmt8p2BVheWDb4GKoIsjBkTT9pyVWWTK3qv0LZwZJv7FOFqczW5BAc7X9Hub2eaYgeWt9txSLeBYlbB-MiTG47JBKkQ"

# =========================================================
# НАСТРОЙКА КРИТИЧЕСКИХ ID (Замени числа на свои ID чатов!)
# =========================================================
GROUP_ID = 123456789         # Твой ID группы ВК (числа из настроек)
TARGET_CHAT_ID = 2000000001  # Чат «Работяги / Бот заработок» (от сообщества)
TEST_CHAT_ID = 2000000002    # Чат «Тест / бот заработок» (для тестов)
MODER_CHAT_ID = 2000000004   # Чат «Модерация / Бот заработок» (для админов)
CONSOLE_CHAT_ID = 2000000003 # Чат «Консоль / Бот заработок» (для логов админов)
OWNER_VK_ID = 827888215      # Твой реальный ID Владельца

vk_session = vk_api.VkApi(token=VK_TOKEN)
vk = vk_session.get_api()
longpoll = VkBotLongPoll(vk_session, GROUP_ID)

# Авто-добавление отсутствующей колонки x2_until в базу данных при старте скрипта
try:
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("ALTER TABLE users ADD COLUMN x2_until INTEGER DEFAULT 0")
    conn.commit()
    conn.close()
    print("⚠️ Колонка x2_until успешно добавлена в структуру БД!")
except sqlite3.OperationalError:
    pass

# ПЕРЕМЕННЫЕ ДЛЯ ЕЖЕЧАСНОГО КОНКУРСА И КЭША
next_contest_time = time.time() + 3600
current_contest_word = None
is_contest_active = False
WORDS_POOL = ["миллион", "баланс", "бонус", "крипта", "розыгрыш", "скорость", "приз", "работяга", "нищий", "кликер"]
ban_notified_users = {}

user_states = {}
pending_donations = {}
active_mines_games = {}

# База интересных загадок со средним уровнем сложности по ТЗ (+40 мк)
RIDDLES_POOL = [
    {"q": "Его не шьют, не кроят, а оно само на человеке растет. Что это?", "a": ["волосы", "волос"]},
    {"q": "В каком море нет воды?", "a": ["в сухом", "сухом", "на карте", "карта", "карт"]},
    {"q": "Один глаз, один рог, но не носорог. Кто это?", "a": ["корова из-за угла", "корова за углом", "корова"]},
    {"q": "Что всегда увеличивается и никогда не уменьшается в жизни человека?", "a": ["возраст", "года", "год"]},
    {"q": "Оно всегда перед нами, но мы не можем его увидеть. Что это?", "a": ["будущее"]},
    {"q": "У какого слона нет хобота?", "a": ["у шахматного", "шахматный", "шахматы"]},
    {"q": "Чем больше из нее берешь, тем больше она становится. Что это?", "a": ["яма"]},
    {"q": "Что может путешествовать по миру, оставаясь в одном и том же углу?", "a": ["почтовая марка", "марка"]},
    {"q": "Что разбивается, но никогда не падает, и что падает, но никогда не разбивается?", "a": ["сердце и давление", "сердце давление", "давление и сердце"]},
    {"q": "Что может говорить на всех языках мира без обучения?", "a": ["эхо"]}
]
# Список товаров для Карусели Магазина
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

def parse_target(parts, index, message_obj):
    if message_obj:
        if message_obj.get('reply_message'):
            return message_obj['reply_message']['from_id']
        if message_obj.get('fwd_messages'):
            return message_obj['fwd_messages']['from_id']
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
    params["peer_id"] = chat_or_user_id
    if keyboard: params["keyboard"] = keyboard
    if template: params["template"] = json.dumps(template, ensure_ascii=False)
    try: vk.messages.send(**params)
    except Exception as e: print(f"Ошибка отправки сообщений: {e}")

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

def get_manual_deposit_keyboard():
    kb = VkKeyboard(inline=True)
    kb.add_button(label="🔄 Я перевел!", color=VkKeyboardColor.POSITIVE)
    return kb.get_keyboard()

def get_owner_confirm_keyboard():
    kb = VkKeyboard(one_time=True)
    kb.add_button(label="✅ Подтвердить перевод", color=VkKeyboardColor.POSITIVE)
    kb.add_button(label="❌ Отказать в переводе", color=VkKeyboardColor.NEGATIVE)
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
                    "label": f"Получить {item['title']}"
                }
            }]
        })
    return {"type": "carousel", "elements": elements}

def get_mines_keyboard(game_id):
    kb = VkKeyboard(inline=True)
    for i in range(1, 10):
        kb.add_callback_button(label=str(i), color=VkKeyboardColor.SECONDARY, payload={"action": "mine_click", "cell": i, "game_id": game_id})
        if i % 3 == 0:
            kb.add_line()
    return kb.get_keyboard()
print("🚀 Бот 'Заработок | Бот нищий' запущен через VkBotLongPoll!")
for event in longpoll.listen():
    if event.type == VkBotEventType.MESSAGE_NEW and hasattr(event, 'payload') and event.payload:
        try: payload = json.loads(event.payload)
        except: payload = None
        
        if payload and "action" in payload:
            uid = event.user_id
            peer = event.peer_id
            action = payload.get("action")
            t_str_now = time.strftime("%H:%M:%S")
            
            if action == "mine_click":
                game_id = payload.get("game_id")
                cell = payload.get("cell")
                game = active_mines_games.get(game_id)
                if not game or game["uid"] != uid: continue
                    
                field = game["field"]
                result = field[cell - 1]
                idx_50 = field.index("win_50") + 1
                idx_15 = field.index("win_15") + 1
                location_text = f"\n\n🔍 Карта поля: ячейка {idx_50} [50 мк], ячейка {idx_15} [15 мк], остальные [Бомбы 💥]"
                
                if result == "win_50":
                    db.add_balance(uid, 50_000_000_000)
                    send_msg(peer, f"🎉 Ура, {get_user_mention(uid)}! Ты угадал супер-ячейку и выиграл **+50 мк** на баланс! 💰{location_text}")
                elif result == "win_15":
                    db.add_balance(uid, 15_000_000_000)
                    send_msg(peer, f"💎 Отлично, {get_user_mention(uid)}! Ты открыл ячейку с призом и выиграл **+15 мк** на баланс! 💰{location_text}")
                else:
                    send_msg(peer, f"💥 **БУМ!** {get_user_mention(uid)}, ты наступил на мину и взорвался! Игра окончена. 💀{location_text}")
                active_mines_games.pop(game_id, None)
                continue

            if action in ["don_yes", "don_no"] and uid == OWNER_VK_ID:
                don_id = payload.get("id")
                don_data = pending_donations.get(don_id)
                if not don_data: continue
                target_uid = don_data["uid"]
                
                if action == "don_yes":
                    coins = str_to_num(don_data["amount_str"])
                    if coins and coins > 0:
                        db.add_balance(target_uid, coins)
                        send_msg(don_data["peer_id"], f"🎉 Баланс успешно пополнен на {num_to_str(coins)}! Перевод подтвержден.")
                        send_msg(OWNER_VK_ID, "Успешно подтверждено!")
                        if CONSOLE_CHAT_ID:
                            send_msg(CONSOLE_CHAT_ID, f"⏰ [{t_str_now}] 💸 Владелец подтвердил ручное пополнение на {don_data['amount_str']} для {get_user_mention(target_uid)}")
                else:
                    send_msg(don_data["peer_id"], " разработчик не подтвердил перевод денег")
                    send_msg(OWNER_VK_ID, "Успешно отклонено!")
                    if CONSOLE_CHAT_ID:
                        send_msg(CONSOLE_CHAT_ID, f"⏰ [{t_str_now}] ⚠️ Владелец ОТКЛОНИЛ операцию пополнения для {get_user_mention(target_uid)}")
                pending_donations.pop(don_id, None)
                continue
    if event.type == VkBotEventType.MESSAGE_NEW:
        message_obj = event.obj.message
        msg = message_obj['text'].strip()
        msg_lower = msg.lower()
        uid = message_obj['from_id']
        peer = message_obj['peer_id']
        t_str_now = time.strftime("%H:%M:%S")

        event_raw = None
        try:
            res_msg = vk.messages.getById(message_ids=message_obj['id'])
            if res_msg and res_msg.get('items'): event_raw = res_msg['items']
        except: pass

        user = db.get_user(uid)
        if uid == OWNER_VK_ID and user['moder_rank'] != 5:
            db.update_user_field(uid, 'moder_rank', 5)
            user = db.get_user(uid)

        if TEST_CHAT_ID and peer != TEST_CHAT_ID and peer != CONSOLE_CHAT_ID and peer != MODER_CHAT_ID:
            t_str_log = time.strftime("%H.%M.%S")
            send_msg(TEST_CHAT_ID, f"[{t_str_log}] {msg} от {get_user_mention(uid)}")

        if user['is_perm_banned']: continue
        if user['ban_until'] > time.time():
            now = time.time()
            if uid not in ban_notified_users or (now - ban_notified_users[uid]) > 300:
                ban_notified_users[uid] = now
                seconds_left = int(user['ban_until'] - now)
                hours, minutes, seconds = seconds_left // 3600, (seconds_left % 3600) // 60, seconds_left % 60
                send_msg(peer, f"⚠️ Вы были заблокированы в боте!\nРазблокировка через {hours:02d}:{minutes:02d}:{seconds:02d}\nПричина: {user['ban_reason']}")
            continue

        state = user_states.get(uid)
        if state and state.get("action") == "waiting_riddle_answer":
            if msg_lower in state["answers"]:
                user_states.pop(uid, None)
                db.add_balance(uid, 40_000_000_000)
                send_msg(peer, f"🎉 Верно, {get_user_mention(uid)}! Ты правильно отгадал загадку и заработал **+40 мк** на баланс! 🧠")
                continue
            else:
                if msg_lower != "загадки" and msg_lower != "🕹 mini-игры":
                    send_msg(peer, "❌ Неверно! Попробуй подумать еще раз и напиши другой вариант.")
                    continue

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
        parts = msg.split()
        
        if msg_lower == "💰 баланс" or msg_lower == "баланс":
            send_msg(peer, f"👀 Ваш баланс: {num_to_str(user['balance'])}")

        elif msg_lower == "🛍 магазин" or msg_lower == "магазин":
            send_msg(peer, "🛍️ Добро пожаловать в магазин услуг! Листайте карточки под этим сообщением:", template=get_shop_carousel())

        elif msg_lower.startswith("получить снятие кд на кликер"):
            item = SHOP_ITEMS
            if user['balance'] < item["cost_coins"]: send_msg(peer, "❌ У вас недостаточно средств!"); continue
            db.add_balance(uid, -item["cost_coins"])
            db.update_user_field(uid, 'no_cd_until', time.time() + 43200)
            send_msg(peer, "✅ Списание успешно! Снятие КД на кликер на 12 часов успешно активировано! Задержка снижена до 50 мс.")

        elif msg_lower.startswith("получить множитель х2 кл"):
            item = SHOP_ITEMS
            if user['balance'] < item["cost_coins"]: send_msg(peer, "❌ У вас недостаточно средств!"); continue
            db.add_balance(uid, -item["cost_coins"])
            db.update_user_field(uid, 'x2_until', time.time() + 43200)
            send_msg(peer, "✅ Списание успешно! Множитель х2 кликов на 12 часов успешно активирован! Награда: +30 мк за клик.")

        elif msg_lower.startswith("пополнить"):
            if len(parts) < 2: send_msg(peer, "💡 Подсказка: пополнить [сумма]"); continue
            amount_str = " ".join(parts[1:])
            user_states[uid] = {"action": "waiting_deposit_click", "amount_str": amount_str, "peer_id": peer}
            send_msg(peer, f" Переведите {amount_str} юзеру @dimo4kaenergy в @badbotik(боте нищем)", keyboard=get_manual_deposit_keyboard())

        elif "я перевел" in msg_lower:
            state = user_states.get(uid)
            if not state or state.get("action") != "waiting_deposit_click": send_msg(peer, "❌ Вы не вводили команду 'пополнить' перед подтверждением!"); continue
            amount_str = state.get("amount_str")
            don_id = f"don_{uid}"
            pending_donations[don_id] = {"uid": uid, "amount_str": amount_str, "peer_id": state["peer_id"]}
            user_states.pop(uid, None)
            send_msg(OWNER_VK_ID, f" ник {get_user_mention(uid)} утверждает, что перевел вам {amount_str}, проверьте правда ли это", keyboard=get_owner_confirm_keyboard())
            send_msg(peer, f"💸 Запрос на верификацию платежа {amount_str} успешно отправлен Владельцу бота.")

        elif msg_lower == "✅ подтвердить перевод" and uid == OWNER_VK_ID:
            don_id = next((k for k in pending_donations.keys() if k.startswith("don_")), None)
            if not don_id: continue
            don_data = pending_donations[don_id]
            coins = str_to_num(don_data["amount_str"])
            if coins and coins > 0:
                db.add_balance(don_data["uid"], coins)
                send_msg(don_data["peer_id"], f"🎉 Баланс успешно пополнен на {num_to_str(coins)}! Перевод подтвержден.")
                send_msg(OWNER_VK_ID, "Успешно подтверждено!")
                if CONSOLE_CHAT_ID: send_msg(CONSOLE_CHAT_ID, f"💡 [{t_str_now}] 💸 Владелец подтвердил ручное пополнение на {don_data['amount_str']} для {get_user_mention(don_data['uid'])}")
            pending_donations.pop(don_id, None)

        elif msg_lower == "❌ отказать в переводе" and uid == OWNER_VK_ID:
            don_id = next((k for k in pending_donations.keys() if k.startswith("don_")), None)
            if not don_id: continue
            don_data = pending_donations[don_id]
            send_msg(don_data["peer_id"], " разработчик не подтвердил перевод денег")
            send_msg(OWNER_VK_ID, "Успешно отклонено!")
            if CONSOLE_CHAT_ID: send_msg(CONSOLE_CHAT_ID, f"⏰ [{t_str_now}] ⚠️ Владелец ОТКЛОНИЛ операцию пополнения для {get_user_mention(don_data['uid'])}")
            pending_donations.pop(don_id, None)

        elif msg_lower == "🕹 mini-игры" or msg_lower == "мини-игры":
            txt_menu = "🕹 **СПИСОК ДОСТУПНЫХ МИНИ-ИГР:**\n\n📱 [Команда: клик] — Кликай и зарабатывай копейки!\n💣 [Команда: мины] — Сыграть в классического сапера 3х3 на удачу!\n🕵 [Команда: загадки] — Отгадывай интересные слова админов (+40 мк)!\n\nНапиши название или команду нужной игры текстом в чат!"
            send_msg(peer, txt_menu, get_games_keyboard())

        elif msg_lower == "⬅ назад" or msg_lower == "назад":
            send_msg(peer, "⬅ Вы вернулись в главное меню бота:", get_main_keyboard())

        elif msg_lower == "📱 кликер" or msg_lower == "клик" or msg_lower == "📱 клик":
            now = time.time()
            has_no_cd = user['no_cd_until'] > now
            required_cd = 0.05 if has_no_cd else 3.0
            if (now - user['last_click']) < required_cd: continue
            db.update_user_field(uid, 'last_click', now)
            db.update_user_field(uid, 'clicks_count', user['clicks_count'] + 1)
            is_x2 = user.get('x2_until', 0) > now
            click_reward = 30_000_000_000 if is_x2 else 15_000_000_000
            new_bal = db.add_balance(uid, click_reward)
            send_msg(peer, f"🎯 Клик! +{num_to_str(click_reward)}\n💰 Баланс: {num_to_str(new_bal)}")

        elif msg_lower == "💣 мины" or msg_lower == "мины":
            game_id = f"game_{uid}_{int(time.time())}"
            pool = ["win_50", "win_15", "bomb", "bomb", "bomb", "bomb", "bomb", "bomb", "bomb"]
            random.shuffle(pool)
            active_mines_games[game_id] = {"uid": uid, "field": pool}
            send_msg(peer, "💣 **МИНИ-ИГРА 'МИНЫ' (САПЕР 3х3)**\n\nНажми на любую цифру:", keyboard=get_mines_keyboard(game_id))
            continue

        elif msg_lower == "🕵 загадки" or msg_lower == "загадки":
            riddle = random.choice(RIDDLES_POOL)
            user_states[uid] = {"action": "waiting_riddle_answer", "answers": riddle["a"]}
            send_msg(peer, f"🕵️‍♂️ **ЗАГАДКА (+40 мк)**\n\n{riddle['q']}")
            continue

        elif msg_lower == "🎁 бонус" or msg_lower == "бонус":
            now = time.time()
            if (now - user['last_daily']) < 86400: continue
            win_amount = int(random.randint(200, 300) * 1_000_000_000)
            db.update_user_field(uid, 'last_daily', now)
            db.add_balance(uid, win_amount)
            send_msg(peer, f"🎁 Ежедневный бонус: {num_to_str(win_amount)}")
            
        elif msg_lower == "профиль" or msg_lower == "👤 профиль":
            ranks = {0: "Игрок", 1: "Модератор", 2: "Администратор", 3: "Гл. Администратор", 4: "Зам. Владельца", 5: "Владелец"}
            profile_card = f"🌎 Профиль {get_user_mention(uid)}\n👹 {ranks.get(user['moder_rank'], 'Игрок')}\n🍻 Баланс: {num_to_str(user['balance'])}"
            send_msg(peer, profile_card, get_main_keyboard())

        elif msg_lower.startswith("+ник "):
            new_nick = msg[5:].strip()
            db.update_user_field(uid, 'nickname', new_nick)
            send_msg(peer, f"✅ Ник изменен на: {new_nick}")

        elif msg_lower.startswith("вывод") or msg_lower == "💸 вывод":
            if len(parts) < 2: continue
            amount = str_to_num(parts)
            if amount and user['balance'] >= amount:
                db.add_balance(uid, -amount)
                db.update_user_field(uid, 'total_withdrawn', user['total_withdrawn'] + amount)
                db.add_withdraw_log(uid, amount)
                send_msg(peer, f"💸 Запрос на вывод {num_to_str(amount)} успешно зафиксирован!")
        # АДМИНИСТРАТИВНЫЙ БЛОК
        elif msg_lower == "//help":
            r = user['moder_rank']
            txt = "📋 **ПОМОЩЬ ПО КОМАНДАМ:**\n\n- баланс\n- профиль\n- пополнить [сумма]\n- вывод [сумма]\n"
            if r == 5: txt += "- выдать [цель] [сумма]\n- //chatid\n- //update\n"
            send_msg(peer, txt)

        elif msg_lower.startswith(("проф ", "профиль ")) and user['moder_rank'] >= 1:
            target_id = parse_target(parts, 1, message_obj)
            if target_id: send_msg(peer, f"🌎 Игрок: {get_user_mention(target_id)}\n💰 Баланс: {num_to_str(db.get_user(target_id)['balance'])}")

        elif msg_lower.startswith("баланс ") and user['moder_rank'] >= 1:
            target_id = parse_target(parts, 1, message_obj)
            if target_id: send_msg(peer, f"🍻 Баланс: {num_to_str(db.get_user(target_id)['balance'])}")

        elif msg_lower.startswith("выдать "):
            if user['moder_rank'] != 5: continue
            target_id = parse_target(parts, 1, message_obj)
            is_reply = message_obj and (message_obj.get('reply_message') or message_obj.get('fwd_messages'))
            amount_idx = 1 if is_reply else 2
            
            if len(parts) > amount_idx:
                amount = str_to_num(parts[amount_idx])
                if target_id and amount:
                    db.add_balance(target_id, amount)
                    send_msg(peer, f"✅ Выдано {num_to_str(amount)} для {get_user_mention(target_id)}")
                    if CONSOLE_CHAT_ID: send_msg(CONSOLE_CHAT_ID, f"⏰ [{t_str_now}] 🛠️ Выдано {num_to_str(amount)} для {get_user_mention(target_id)}")

        elif msg_lower.startswith("//moder "):
            if user['moder_rank'] < 3: continue
            try: target_rank = int(parts)
            except: continue
            target_id = parse_target(parts, 2, message_obj)
            if target_id:
                final_rank = max(0, target_rank) if target_rank != -1 else 0
                db.update_user_field(target_id, 'moder_rank', final_rank)
                send_msg(peer, "успешно!")

        elif msg_lower.startswith("//ban "):
            if user['moder_rank'] < 3: continue
            try: days = int(parts)
            except: continue
            target_id = parse_target(parts, 2, message_obj)
            if target_id:
                ban_time = time.time() + (days * 86400) if days > 0 else -1
                db.update_user_field(target_id, 'ban_until', ban_time)
                send_msg(peer, "успешно!")

        elif msg_lower == "//logs" and user['moder_rank'] >= 2:
            send_msg(peer, "📋 Логи выводов доступны в БД.")

        elif msg_lower == "//chatid" and user['moder_rank'] == 5:
            send_msg(peer, f"{peer}")

        elif msg_lower == "//update" and user['moder_rank'] == 5:
            send_msg(peer, "🔄 Выполняю принудительный перезапуск по ТЗ...")
            try:
                # Требуемый синтаксис обновления по твоему ТЗ
                subprocess.Popen(["bash", "-c", "sleep 1 && pkill -9 -f main.py && git pull && source venv/bin/activate && nohup python3 main.py &"])
                sys.exit()
            except: pass
