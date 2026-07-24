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

db.init_db()

# Твой рабочий токен сообщества ВКонтакте
VK_TOKEN = "vk1.a.4NLW0LW3cobhYjBFzUQ1uvIF8Zn93a7G9W--YJ-URTkk9tf9Qt7TCXYFGv1pQ-o17M_1oRUhJMEV53edLMcBKwIB9F3JIRJl-Vi0YXAAT26pOvv3_XY5Yc6wj6PQmt8p2BVheWDb4GKoIsjBkTT9pyVWWTK3qv0LZwZJv7FOFqczW5BAc7X9Hub2eaYgeWt9txSLeBYlbB-MiTG47JBKkQ"

# Настройки критических идентификаторов бота
GROUP_ID = 240438650         
TARGET_CHAT_ID = 2000000001  
TEST_CHAT_ID = 2000000002    
MODER_CHAT_ID = 2000000004   
CONSOLE_CHAT_ID = 2000000003 
OWNER_VK_ID = 827888215      

# Разрешенные ID чатов для работы команды «выгнать»
ALLOWED_KICK_CHATS = [2000000001, 2000000002, 2000000003, 2000000004]

vk_session = vk_api.VkApi(token=VK_TOKEN)
vk = vk_session.get_api()
longpoll = VkBotLongPoll(vk_session, GROUP_ID)

try:
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("ALTER TABLE users ADD COLUMN x2_until INTEGER DEFAULT 0")
    cursor.execute("ALTER TABLE users ADD COLUMN reg_date TEXT DEFAULT ''")
    cursor.execute("ALTER TABLE users ADD COLUMN has_legendary INTEGER DEFAULT 0")
    conn.commit()
    conn.close()
    print("⚠️ База данных успешно проверена и синхронизирована!")
except sqlite3.OperationalError:
    pass

next_contest_time = time.time() + 3600
current_contest_word = None
is_contest_active = False
WORDS_POOL = ["миллион", "баланс", "бонус", "крипта", "розыгрыш", "скорость", "приз", "работяга", "нищий", "кликер"]
ban_notified_users = {}
user_states = {}
pending_donations = {}
active_mines_games = {}

RIDDLES_POOL = [
    {"q": "Его не шьют, не кроят, а оно само на человеку растет. Что это?", "a": ["волосы", "волос"]},
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
    if isinstance(text, list):
        text = " ".join(text[1:])
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
    """Извлекает ID из любых упоминаний ВК, коротких имен и полных интернет-ссылок"""
    text = text.strip()
    if '://vk.com' in text:
        text = text.split('://vk.com')[-1].replace(']', '').replace('[', '').strip()
    if '@' in text:
        text = text.split('@')[-1].strip()
    if '[id' in text and '|' in text:
        try:
            return int(text.split('[id')[-1].split('|')[0])
        except: pass
    try:
        return int(text)
    except ValueError:
        try:
            res = vk.utils.resolveScreenName(screen_name=text)
            if res and res['type'] == 'user':
                return res['object_id']
        except:
            pass
    return None

def parse_target(parts, index, message_obj):
    if message_obj:
        if message_obj.get('reply_message'):
            return message_obj['reply_message']['from_id']
        if message_obj.get('fwd_messages') and isinstance(message_obj['fwd_messages'], list) and len(message_obj['fwd_messages']) > 0:
            return message_obj['fwd_messages'][0]['from_id']
    if len(parts) > index:
        return parse_user_id(parts[index])
    return None

def get_user_mention(user_id):
    u_data = db.get_user(user_id)
    if u_data and u_data.get('nickname'): return f"[id{user_id}|{u_data['nickname']}]"
    try:
        vk_user = vk.users.get(user_ids=user_id)
        return f"[id{user_id}|{vk_user[0]['first_name']}]"
    except: return f"[id{user_id}|Игрок]"

def send_msg(chat_or_user_id, text, keyboard=None, template=None):
    params = {"random_id": 0, "message": text, "peer_id": chat_or_user_id}
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

def get_support_keyboard():
    kb = VkKeyboard(inline=True)
    kb.add_open_link_button(label="👤 Связаться с Тех. Админом", link="https://vk.me")
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
            "buttons": [{"action": {"type": "text", "label": f"Получить {item['title']}"}}]
        })
    return {"type": "carousel", "elements": elements}

def get_mines_keyboard(game_id):
    kb = VkKeyboard(inline=True)
    for i in range(1, 10):
        kb.add_callback_button(label=str(i), color=VkKeyboardColor.SECONDARY, payload={"action": "mine_click", "cell": i, "game_id": game_id})
        if i % 3 == 0 and i < 9: kb.add_line()
    return kb.get_keyboard()

for event in longpoll.listen():
    if event.type == VkBotEventType.MESSAGE_EVENT:
        payload = event.payload
        if payload and "action" in payload:
            uid = event.user_id
            peer = event.peer_id
            action = payload.get("action")
            
            if action == "mine_click":
                # Сапер работает строго в ЛС
                if peer > 2000000000: continue
                game_id = payload.get("game_id")
                cell = payload.get("cell")
                game = active_mines_games.get(game_id)
                if not game or game["uid"] != uid: continue
                    
                field = game["field"]
                result = field[cell - 1]
                
                try: vk.messages.sendMessageEventAnswer(event_id=event.event_id, user_id=uid, peer_id=peer)
                except: pass
                
                if result == "win_60":
                    db.add_balance(uid, 60_000_000_000)
                    send_msg(peer, f"💎 Супер-приз! Ты открыл ячейку и выиграл **+60 мк** на баланс! 💰", get_main_keyboard())
                elif result == "win_40":
                    db.add_balance(uid, 40_000_000_000)
                    send_msg(peer, f"🎉 Отлично! Ты открыл ячейку и выиграл **+40 мк** на баланс! 💎", get_main_keyboard())
                else:
                    send_msg(peer, f"💥 **БУМ!** Ты наступил на мину и взорвался! Игра окончена. 💀", get_main_keyboard())
                active_mines_games.pop(game_id, None)
                continue
    if event.type == VkBotEventType.MESSAGE_NEW:
        message_obj = event.obj.message
        uid = message_obj['from_id']
        if uid <= 0: continue
        
        msg = message_obj['text'].strip()
        msg_lower = msg.lower()
        peer = message_obj['peer_id']
        t_str_now = time.strftime("%H:%M:%S")

        event_raw = None
        try:
            res_msg = vk.messages.get_by_id(message_ids=message_obj['id'])
            if res_msg and res_msg.get('items'): event_raw = res_msg['items'][0]
        except: pass

        user = db.get_user(uid)
        if not user: continue

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
                send_msg(peer, f"🎉 Верно, {get_user_mention(uid)}! Ты правильно отгадал загадку и заработал **+40 мк** на баланс! 🧠", get_main_keyboard())
                continue
            else:
                if msg_lower not in ["загадки", "🕹 mini-игры", "мини-игры", "назад", "⬅ назад"]:
                    user_states.pop(uid, None)  
                    send_msg(peer, f"❌ {get_user_mention(uid)}, ты не угадал! Правильный ответ был: «{state['answers']}». Повезет в другой раз! 🤫", get_main_keyboard())
                    continue

        if msg_lower in ["начать", "старт", "привет"]:
            welcome_text = (
                f"👋 Добро пожаловать, {get_user_mention(uid)}!\n\n"
                f"🤖 Я — игровой бот-кликер, интегрированный с «Бот нищий» (@badbotik).\n"
                f"💰 Здесь ты можешь кликать, угадывать загадки и выводить реальные монеты!\n\n"
                f"👇 Используй удобное кнопочное меню ниже для управления:"
            )
            send_msg(peer, welcome_text, get_main_keyboard())
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
            send_msg(peer, f"👀 Ваш баланс: {num_to_str(user['balance'])}", get_main_keyboard())

        elif msg_lower in ["профиль", "👤 профиль", "проф", "проф я"]:
            # Просмотр своего профиля или чужого по ссылке/юзернейму
            target_id = uid
            if len(parts) > 1 and parts.lower() not in ["я"]:
                parsed = parse_target(parts, 1, event_raw)
                if parsed: target_id = parsed
                
            t_user = db.get_user(target_id)
            ranks = {0: "Игрок", 1: "Модератор", 2: "Администратор", 3: "Главный Администратор", 4: "Заместитель Владельца", 5: "Владелец"}
            clicks = t_user.get('clicks_count', 0)
            withdrawn = t_user.get('total_withdrawn', 0)
            reg = t_user.get('reg_date') if t_user.get('reg_date') else time.strftime("%d.%m.%Y")
            award = "♠️ THE LEGENDARY " if t_user.get('has_legendary', 0) == 1 else ""
            
            profile_card = (
                f"🌎 Профиль пользователя\n"
                f"🍭 Имя пользователя: {get_user_mention(target_id)}\n"
                f"👹 Ранг: {award}{ranks.get(t_user['moder_rank'], 'Игрок')}\n"
                f"🍻 Баланс: {num_to_str(t_user['balance'])}\n"
                f"🏀 Кликов в боте: {clicks}\n"
                f"🧠 Всего выведено: {num_to_str(withdrawn)}\n"
                f"💀 Дата регистрации в боте: {reg}"
            )
            send_msg(peer, profile_card, get_main_keyboard())
            continue

        elif msg_lower.startswith("вывод"):
            if len(parts) < 2:
                send_msg(peer, "💡 Подсказка: вывод [сумма]", get_main_keyboard())
                continue
            amount = str_to_num(parts[1])
            if amount and amount > 0 and user['balance'] >= amount:
                # Мгновенно списываем баланс в боте
                db.add_balance(uid, -amount)
                db.update_user_field(uid, 'total_withdrawn', user['total_withdrawn'] + amount)
                db.add_withdraw_log(uid, amount)
                
                # Имитация автоматического перевода на стороннее API
                send_msg(peer, f"✅ Вывод обработан! С вашего баланса списано {num_to_str(amount)}. Вам были переведены данные деньги в нищем! 💸", get_main_keyboard())
            else:
                send_msg(peer, "❌ Недостаточно средств на балансе или сумма указана неверно!", get_main_keyboard())
            continue

        elif msg_lower == "🛍 магазин" or msg_lower == "магазин":
            send_msg(peer, "🛍️ Добро пожаловать в магазин услуг! Листайте карточки под этим сообщением:", template=get_shop_carousel())

        elif msg_lower.startswith("получить снятие кд на кликер"):
            item = SHOP_ITEMS[0]
            if user['balance'] < item["cost_coins"]: 
                send_msg(peer, "❌ У вас недостаточно средств!", get_main_keyboard())
                continue
            db.add_balance(uid, -item["cost_coins"])
            db.update_user_field(uid, 'no_cd_until', time.time() + 43200)
            send_msg(peer, "✅ Списание успешно! Снятие КД на кликер на 12 часов успешно активировано!", get_main_keyboard())
        elif msg_lower.startswith("получить множитель х2 кл"):
            item = SHOP_ITEMS[1]
            if user['balance'] < item["cost_coins"]: 
                send_msg(peer, "❌ У вас недостаточно средств!", get_main_keyboard())
                continue
            db.add_balance(uid, -item["cost_coins"])
            db.update_user_field(uid, 'x2_until', time.time() + 43200)
            send_msg(peer, "✅ Списание успешно! Множитель х2 кликов на 12 часов успешно активирован!", get_main_keyboard())

        elif msg_lower == "🕹 mini-игры" or msg_lower == "мини-игры":
            games_text = (
                f"🎲 **СПИСОК МИНИ-ИГР:**\n\n"
                f"• Клик - доход 15мк за клик (доступно раз в 3 секунды) [Работает Везде]\n\n"
                f"• Загадки - 40мк за отгаданную загадку (без ограничений) [Только в ЛС]\n\n"
                f"• Бонус - бонус раз в день от 1мк до 5мм [Работает Везде]\n\n"
                f"• Сапер - перед тобой открывается 3х3 меню, твоя задача выбрать, а дальше уже судьба решит. Среди них прячутся как бомбы, так и призы 40мк, 60мк (без ограничений) [Только в ЛС]\n\n"
                f"• Каждый час в официальном чате Бота проходит мини-игра, в которой надо быстрее написать слово и получить 1мм."
            )
            send_msg(peer, games_text, get_games_keyboard())
            continue

        elif msg_lower == "⬅ назад" or msg_lower == "назад":
            send_msg(peer, "⬅ Вы вернулись в главное меню бота:", get_main_keyboard())

        elif msg_lower in ["📱 кликер", "клик", "📱 клик"]:
            now = time.time()
            has_no_cd = user['no_cd_until'] > now
            required_cd = 0.05 if has_no_cd else 3.0
            if (now - user['last_click']) < required_cd: continue
            db.update_user_field(uid, 'last_click', now)
            db.update_user_field(uid, 'clicks_count', user['clicks_count'] + 1)
            is_x2 = user.get('x2_until', 0) > now
            click_reward = 30_000_000_000 if is_x2 else 15_000_000_000
            new_bal = db.add_balance(uid, click_reward)
            send_msg(peer, f"🎯 Клик! +{num_to_str(click_reward)}\n💰 Баланс: {num_to_str(new_bal)}", get_main_keyboard())

        elif msg_lower in ["💣 мины", "мины"]:
            if peer > 2000000000:
                send_msg(peer, "❌ Игра 'Мины' (Сапер) доступна только в Личных Сообщениях бота!", get_main_keyboard())
                continue
            game_id = f"game_{uid}_{int(time.time())}"
            pool = ["win_60", "win_40", "bomb", "bomb", "bomb", "bomb", "bomb", "bomb", "bomb"]
            random.shuffle(pool)
            active_mines_games[game_id] = {"uid": uid, "field": pool}
            send_msg(peer, "💣 **МИНИ-ИГРА 'МИНЫ' (САПЕР 3х3)**\n\nНажми на любую ячейку на инлайн-клавиатуре:", keyboard=get_mines_keyboard(game_id))
            continue

        elif msg_lower in ["🕵 загадки", "загадки"]:
            if peer > 2000000000:
                send_msg(peer, "❌ Мини-игра 'Загадки' доступна только в Личных Сообщениях бота!", get_main_keyboard())
                continue
            riddle = random.choice(RIDDLES_POOL)
            user_states[uid] = {"action": "waiting_riddle_answer", "answers": riddle["a"]}
            send_msg(peer, f"🕵️‍♂️ **ЗАГАДКА (+40 мк)**\n\n{riddle['q']}\n\n⚠️ Внимание: у тебя есть ровно 1 попытка!")
            continue

        elif msg_lower in ["🎁 бонус", "бонус"]:
            now = time.time()
            if (now - user['last_daily']) < 86400: 
                send_msg(peer, "❌ Вы уже забирали ежедневный бонус! Приходите завтра.", get_main_keyboard())
                continue
            win_amount = int(random.randint(1_000, 5_000) * 1_000_000_000)
            db.update_user_field(uid, 'last_daily', now)
            db.add_balance(uid, win_amount)
            send_msg(peer, f"🎁 Ежедневный бонус: {num_to_str(win_amount)}", get_main_keyboard())

        elif msg_lower in ["🛠 тех. поддержка", "тех. поддержка", "поддержка", "техподдержка"]:
            send_msg(peer, "⚠️ Тех. Администратор отвечает в течении 12 часов!\n\n👇 Нажми на белую кнопку ниже для перехода:", keyboard=get_support_keyboard())
            continue

        elif msg_lower.startswith("выгнать") and user['moder_rank'] >= 1:
            chat_idx = peer - 2000000000
            if peer not in ALLOWED_KICK_CHATS:
                send_msg(peer, "❌ Исключение участников работает только в официальных чатах бота!", get_main_keyboard())
                continue
            target_id = parse_target(parts, 1, event_raw)
            if target_id:
                try:
                    vk.messages.removeChatUser(chat_id=chat_idx, user_id=target_id)
                    send_msg(peer, f"✅ Пользователь {get_user_mention(target_id)} успешно исключен модератором из беседы.", get_main_keyboard())
                except Exception as e:
                    send_msg(peer, f"❌ Ошибка исключения! Проверьте, есть ли у бота права Администратора в чате. Лог: {e}", get_main_keyboard())
            continue
        elif msg_lower == "📋список команд" or msg_lower == "список команд":
            r = user['moder_rank']
            txt = "📋 **СПИСОК ДОСТУПНЫХ ВАМ КОМАНД:**\n\n- баланс\n- профиль [ссылка/юз]\n- вывод [сумма]\n- бонус\n"
            if r >= 1: txt += "\n⚠️ **РАНГ МОДЕРАТОР [1+]:**\n- bal [ссылка/юз] — чужой баланс\n- выгнать [ссылка/юз] — кик из чата\n"
            if r >= 2: txt += "\n🍀 **РАНГ АДМИНИСТРАТОР [2+]:**\n- //logs — последние 10 выводов\n- //giveaward [ссылка/юз] — выдать легендарный статус\n"
            if r >= 3: txt += "\n👹 **РАНГ ГЛ. АДМИНИСТРАТОР [3+]:**\n- //ban [1-365] [ссылка/юз] [причина]\n- //ban 0 [ссылка/юз] — разбан\n- //ban -1 [ссылка/юз] [причина] — пермач\n- //moder [0-2] [ссылка/юз] — назначить админов\n- //moder -1 [ссылка/юз] — снять админа\n"
            if r >= 4: txt += "\n🏆 **РАНГ ЗАМ. ВЛАДЕЛЬЦА [4+]:**\n- //moder [0-3] [ссылка/юз] — управление гл. админами\n- //set0 [nk/cl/bl/rg/vv/all] [ссылка/юз] — обнуление\n"
            if r == 5: txt += "\n🎱 **РАНГ ВЛАДЕЛЕЦ [5]:**\n- пополнить [ссылка/юз] [сумма] — выдать деньги\n- //moder [0-5] [ссылка/юз] — управление со-владельцами\n- //chatid — узнать ID беседы\n- //update — жесткий перезапуск бота\n"
            send_msg(peer, txt, get_main_keyboard())
            continue

        elif msg_lower.startswith("bal ") and user['moder_rank'] >= 1:
            target_id = parse_target(parts, 1, event_raw)
            if target_id: send_msg(peer, f"🍻 Баланс игрока {get_user_mention(target_id)}: {num_to_str(db.get_user(target_id)['balance'])}", get_main_keyboard())

        elif msg_lower == "//logs" and user['moder_rank'] >= 2:
            logs = db.get_last_logs(10)
            if not logs: send_msg(peer, "📋 Логи выводов чисты.", get_main_keyboard())
            else:
                txt = "📋 **ПОСЛЕДНИЕ 10 ВЫВОДОВ СЕРВЕРА:**\n\n"
                for l in logs: txt += f"• Юзер: [id{l['user_id']}|Игрок] | Сумма: {num_to_str(l['amount'])}\n"
                send_msg(peer, txt, get_main_keyboard())

        elif msg_lower.startswith("//giveaward ") and user['moder_rank'] >= 2:
            target_id = parse_target(parts, 1, event_raw)
            if target_id:
                db.update_user_field(target_id, 'has_legendary', 1)
                send_msg(peer, f"✅ Игроку {get_user_mention(target_id)} успешно присвоена метка ♠️ THE LEGENDARY!", get_main_keyboard())

        elif msg_lower.startswith("//ban ") and user['moder_rank'] >= 3:
            if len(parts) < 3: continue
            try: days = int(parts[1])
            except: continue
            target_id = parse_target(parts, 2, event_raw)
            if target_id:
                if days == 0:
                    db.update_user_field(target_id, 'ban_until', 0.0)
                    db.update_user_field(target_id, 'is_perm_banned', 0)
                    send_msg(peer, f"✅ Игрок {get_user_mention(target_id)} успешно разблокирован.", get_main_keyboard())
                elif days == -1:
                    reason = " ".join(parts[3:]) if len(parts) > 3 else "Не указана"
                    db.update_user_field(target_id, 'is_perm_banned', 1)
                    db.update_user_field(target_id, 'ban_reason', reason)
                    send_msg(peer, f"💀 Игрок {get_user_mention(target_id)} ЗАБЛОКИРОВАН НАВСЕГДА! Причина: {reason}", get_main_keyboard())
                else:
                    reason = " ".join(parts[3:]) if len(parts) > 3 else "Не указана"
                    ban_time = time.time() + (days * 86400)
                    db.update_user_field(target_id, 'ban_until', ban_time)
                    db.update_user_field(target_id, 'ban_reason', reason)
                    send_msg(peer, f"⚠️ Игрок {get_user_mention(target_id)} забанен на {days} дней. Причина: {reason}", get_main_keyboard())

        elif msg_lower.startswith("//moder ") and user['moder_rank'] >= 3:
            if len(parts) < 3: continue
            try: rank = int(parts[1])
            except: continue
            target_id = parse_target(parts, 2, event_raw)
            if target_id:
                # Ограничение должностей по ТЗ
                if user['moder_rank'] == 3 and rank > 2: continue
                if user['moder_rank'] == 4 and rank > 3: continue
                final_rank = max(0, rank) if rank != -1 else 0
                db.update_user_field(target_id, 'moder_rank', final_rank)
                send_msg(peer, f"✅ Должность игрока {get_user_mention(target_id)} обновлена до уровня: {final_rank}", get_main_keyboard())

        elif msg_lower.startswith("//set0 ") and user['moder_rank'] >= 4:
            if len(parts) < 2: continue
            mode = parts[1].lower()
            target_id = parse_target(parts, 2, event_raw)
            if not target_id: continue
            if mode == "nk": db.update_user_field(target_id, 'nickname', 'Игрок')
            elif mode == "cl": db.update_user_field(target_id, 'clicks_count', 0)
            elif mode == "bl": db.update_user_field(target_id, 'balance', 0)
            elif mode == "rg": db.update_user_field(target_id, 'reg_date', time.strftime("%d.%m.%Y"))
            elif mode == "vv": db.update_user_field(target_id, 'total_withdrawn', 0)
            elif mode == "all":
                db.update_user_field(target_id, 'nickname', 'Игрок')
                db.update_user_field(target_id, 'clicks_count', 0)
                db.update_user_field(target_id, 'balance', 0)
                db.update_user_field(target_id, 'reg_date', time.strftime("%d.%m.%Y"))
                db.update_user_field(target_id, 'total_withdrawn', 0)
            send_msg(peer, f"✅ Операция //set0 {mode} успешно выполнена для {get_user_mention(target_id)}.", get_main_keyboard())

        elif msg_lower.startswith("пополнить ") and user['moder_rank'] == 5:
            target_id = parse_target(parts, 1, event_raw)
            if target_id and len(parts) > 2:
                amount = str_to_num(parts[2])
                if amount:
                    db.add_balance(target_id, amount)
                    send_msg(peer, f"✅ Выдано {num_to_str(amount)} на игровой баланс {get_user_mention(target_id)}", get_main_keyboard())

        elif msg_lower == "//chatid" and user['moder_rank'] == 5:
            send_msg(peer, f"⚙️ ID текущей беседы: {peer}", get_main_keyboard())

        elif msg_lower == "//update" and user['moder_rank'] == 5:
            send_msg(peer, "🔄 Выполняю принудительный перезапуск ядра по ТЗ...", get_main_keyboard())
            try:
                subprocess.Popen(["bash", "-c", "sleep 1 && pkill -9 -f main.py && git pull && source venv/bin/activate && nohup python3 main.py &"])
                sys.exit()
            except: pass
