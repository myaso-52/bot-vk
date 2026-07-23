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

# Инициализируем БД
db.init_db()

vk_session = vk_api.VkApi(token=VK_TOKEN)
longpoll = VkLongPoll(vk_session)
vk = vk_session.get_api()

# НАСТРОЙКА КРИТИЧЕСКИХ ID (Замени на свои цифры!)
GROUP_ID = 123456789         # Твой ID группы ВК (числа из настроек)
TARGET_CHAT_ID = 2000000001  # Чат «Работяги / Заработок» (для конкурсов)
TEST_CHAT_ID = 2000000002    # Чат «Тест» (для трансляции всех сообщений)
CONSOLE_CHAT_ID = 2000000003 # Чат «Консоль» (для логов админ-команд)
MODER_CHAT_ID = 2000000004   # Чат «Модерация» (для админ-состава)

# ПЕРЕМЕННЫЕ ДЛЯ ЕЖЕЧАСНОГО КОНКУРСА
next_contest_time = time.time() + 3600
current_contest_word = None
is_contest_active = False
WORDS_POOL = ["миллион", "баланс", "бонус", "крипта", "розыгрыш", "скорость", "приз", "работяга", "нищий", "кликер"]

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
    if num >= 1_000_000_000_000_000: return f"{num / 1_000_000_000_000_000:.2f} ммк"
    if num >= 1_000_000_000_000: return f"{num / 1_000_000_000_000:.2f} мм"
    if num >= 1_000_000_000: return f"{num / 1_000_000_000:.2f} мк"
    if num >= 1_000_000: return f"{num / 1_000_000:.2f} кк"
    if num >= 1_000: return f"{num / 1_000:.2f} к"
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

def get_user_mention(user_id):
    u_data = db.get_user(user_id)
    if u_data['nickname']: return f"[id{user_id}|{u_data['nickname']}]"
    try:
        vk_user = vk.users.get(user_ids=user_id)[0]
        return f"[id{user_id}|{vk_user['first_name']}]"
    except: return f"[id{user_id}|Игрок]"

def send_msg(chat_or_user_id, text, keyboard=None):
    params = {"random_id": 0, "message": text}
    if chat_or_user_id > 2000000000: params["peer_id"] = chat_or_user_id
    else: params["user_id"] = chat_or_user_id
    if keyboard: params["keyboard"] = keyboard
    try: vk.messages.send(**params)
    except Exception as e: print(f"Ошибка отправки: {e}")

def get_main_keyboard():
    kb = VkKeyboard(one_time=False)
    kb.add_button('💼 Работы', color=VkKeyboardColor.PRIMARY)
    kb.add_button('🕹 Мини-игры', color=VkKeyboardColor.PRIMARY)
    kb.add_line()
    kb.add_button('💰 Баланс', color=VkKeyboardColor.POSITIVE)
    kb.add_button('🎁 Бонус', color=VkKeyboardColor.POSITIVE)
    kb.add_line()
    kb.add_button('🛠 Тех. поддержка', color=VkKeyboardColor.SECONDARY)
    return kb.get_keyboard()

def get_games_keyboard():
    kb = VkKeyboard(one_time=False)
    kb.add_button('📱 Кликер', color=VkKeyboardColor.PRIMARY)
    kb.add_button('🕵‍♂ Загадки', color=VkKeyboardColor.PRIMARY)
    kb.add_button('💣 Мины', color=VkKeyboardColor.PRIMARY)
    kb.add_line()
    kb.add_button('⬅ Назад', color=VkKeyboardColor.SECONDARY)
    return kb.get_keyboard()

print("🚀 Бот 'Заработок | Бот нищий' запущен!")
for event in longpoll.listen():
    if event.type == VkEventType.MESSAGE_NEW and event.to_me:
        msg = event.text.strip()
        msg_lower = msg.lower()
        uid = event.user_id
        peer = event.peer_id
        user = db.get_user(uid)
        
        # --- ЧАТ «ТЕСТ»: ТРАНСЛЯЦИЯ ВСЕХ СООБЩЕНИЙ ---
        if TEST_CHAT_ID and peer != TEST_CHAT_ID and peer != CONSOLE_CHAT_ID and peer != MODER_CHAT_ID:
            mention = get_user_mention(uid)
            send_msg(TEST_CHAT_ID, f"📢 *{msg}* от {mention}")

        # --- СИСТЕМА ЖИВЫХ БАНОВ ---
        if user['is_perm_banned']: continue
        if user['ban_until'] > time.time():
            seconds_left = int(user['ban_until'] - time.time())
            hours = seconds_left // 3600
            minutes = (seconds_left % 3600) // 60
            seconds = seconds_left % 60
            send_msg(peer, f"⚠️ Вы были заблокированы в боте!\nРазблокировка через {hours:02d}:{minutes:02d}:{seconds:02d}\nПричина: {user['ban_reason']}")
            continue

        # --- КОНКУРС В ЧАТЕ РАБОТЯГ ---
        if peer == TARGET_CHAT_ID and time.time() >= next_contest_time and not is_contest_active:
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
        # ОБРАБОТКА ОБЫЧНЫХ КНОПОК И КОМАНД
        # =========================================================

        if msg_lower == "💰 баланс" or msg_lower == "баланс":
            send_msg(peer, f"👀 Ваш баланс: {num_to_str(user['balance'])}", get_main_keyboard())

        elif msg_lower == "🛠 тех. поддержка":
            support_text = "Тех. администратор отвечает в течении 12 часов!\nТех. администратор — [francescopapa|Агент Сенгоку]"
            send_msg(peer, support_text, get_main_keyboard())

        elif msg_lower == "🕹 mini-игры":
            send_msg(peer, "🕹 Выберите интересующую мини-игру из списка ниже:", get_games_keyboard())

        elif msg_lower == "⬅ назад":
            send_msg(peer, "⬅ Вы вернулись в главное меню:", get_main_keyboard())

        elif msg_lower == "📱 кликер" or msg_lower == "клик" or msg_lower == "📱 клик":
            now = time.time()
            has_no_cd = user['no_cd_until'] > now
            if not has_no_cd and (now - user['last_click']) < 3.0:
                left = 3.0 - (now - user['last_click'])
                send_msg(peer, f"⏳ Кулдаун! Подожди еще {left:.1f} сек. Или купи снятие КД в магазине за 50 мм!")
                continue
            db.update_user_field(uid, 'last_click', now)
            db.update_user_field(uid, 'clicks_count', user['clicks_count'] + 1)
            new_bal = db.add_balance(uid, 15_000_000_000)
            send_msg(peer, f"🎯 Клик! +15 мк.\n💰 Баланс: {num_to_str(new_bal)}")

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
                win_amount = random.randint(200_000_000_000, 300_000_000_000)
                txt = f"🎁 Ты забрал ежедневный бонус: {num_to_str(win_amount)}"
            elif win_type == 'med':
                win_amount = random.randint(500_000_000_000, 5_000_000_000_000)
                txt = f"🔥 Отлично! Ежедневный бонус принес тебе: {num_to_str(win_amount)}"
            elif win_type == 'high':
                win_amount = random.randint(10_000_000_000_000, 100_000_000_000_000)
                txt = f"💎 ВАУ! Крупный куш в бонусе: {num_to_str(win_amount)}"
            else:
                win_amount = 2_000_000_000_000
                txt = f"🎉 ЛЕГЕНДАРНО! Ты поймал 0.1% шанс и выиграл главный приз: 2 мм!"
            db.update_user_field(uid, 'last_daily', now)
            db.add_balance(uid, win_amount)
            send_msg(peer, txt)

        elif msg_lower == "💼 работы":
            send_msg(peer, "💼 Раздел находится в разработке! Ожидайте обновления механик.")
        elif msg_lower == "🕵 shadow загадки" or msg_lower == "🕵‍♂ загадки":
            send_msg(peer, "🕵‍♂ Загадки временно отключены на техническое обслуживание. Используй кликер!")
        elif msg_lower == "💣 мины":
            send_msg(peer, "💣 Игра 'Мины' (Сапер) настраивается администрацией. Скоро запуск!")
        elif msg_lower == "профиль":
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

        elif msg_lower.startswith("вывод"):
            parts = msg.split()
            if len(parts) < 2:
                send_msg(peer, "💡 Подсказка: Пиши правильно: вывод [сумма, например: 1мм]")
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
        # 🛡️ АДМИНИСТРАТИВНЫЙ БЛОК (РАСПРЕДЕЛЕНИЕ ДОСТУПА ПО ТЗ)
        # =========================================================

        elif msg_lower == "//help":
            r = user['moder_rank']
            txt = "📋 **СПРАВКА ПО КОМАНДАМ ДЛЯ ТВОЕЙ ДОЛЖНОСТИ:**\n\n"
            txt += "👤 **Ранг 0 (Игрок):**\n- баланс\n- профиль\n- +ник [имя]\n- вывод [сумма]\n- бонус\n\n"
            if r >= 1: txt += "🛡️ **Ранг 1 (Модератор):**\n- проф [ссылка]\n- баланс [ссылка]\n\n"
            if r >= 2: txt += "⚔️ **Ранг 2 (Администратор):**\n- //logs (просмотр выводов)\n\n"
            if r >= 3: txt += "🔥 **Ранг 3-4 (Гл. Админ / Зам):**\n- //ban [-1/0/дни] [ссылка] [причина]\n- //moder [ранг] [ссылка]\n\n"
            if r == 5: txt += "👑 **Ранг 5 (Разработчик):**\n- выдать [ссылка] [сумма]\n- //chatid\n- //update\n"
            send_msg(peer, txt)

        elif msg_lower.startswith(("проф ", "профиль ")) and user['moder_rank'] >= 1:
            parts = msg.split()
            target_id = parse_user_id(parts[1]) if len(parts) > 1 else None
            if not target_id:
                send_msg(peer, "❌ Подсказка: Укажи верную ссылку на игрока!")
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
            target_id = parse_user_id(parts[1]) if len(parts) > 1 else None
            if not target_id:
                send_msg(peer, "❌ Подсказка: Укажи верную ссылку!")
                continue
            t_user = db.get_user(target_id)
            send_msg(peer, f"🍻 Баланс пользователя {get_user_mention(target_id)} составляет: {num_to_str(t_user['balance'])}")

        elif msg_lower.startswith("выдать "):
            if user['moder_rank'] != 5:
                send_msg(peer, "❌ Ошибка доступа!")
                continue
            parts = msg.split()
            if len(parts) < 3:
                send_msg(peer, "❌ Подсказка: выдать [ссылка] [сумма]")
                continue
            target_id = parse_user_id(parts[1])
            amount = str_to_num(parts[2])
            if not target_id or amount is None or amount <= 0:
                send_msg(peer, "❌ Подсказка: Неверная сумма или ссылка!")
                continue
            db.add_balance(target_id, amount)
            t_mention = get_user_mention(target_id)
            send_msg(peer, f"✅ Вы успешно выдали {num_to_str(amount)} пользователю {t_mention}")
            if CONSOLE_CHAT_ID: send_msg(CONSOLE_CHAT_ID, f"🛠️ Разработчик {get_user_mention(uid)} выдал {num_to_str(amount)} пользователю {t_mention}")

        elif msg_lower.startswith("//moder "):
            parts = msg.split()
            if len(parts) < 3:
                send_msg(peer, "❌ Подсказка: //moder [ранг] [ссылка]")
                continue
            try: target_rank = int(parts[1])
            except ValueError:
                send_msg(peer, "❌ Неверный формат ранга!")
                continue
            target_id = parse_user_id(parts[2])
            if not target_id:
                send_msg(peer, "❌ Пользователь не найден!")
                continue
            if user['moder_rank'] == 5:
                if target_rank < -1 or target_rank > 4: continue
            elif user['moder_rank'] == 4:
                if target_rank < -1 or target_rank > 3: continue
            else: continue
            db.update_user_field(target_id, 'moder_rank', max(0, target_rank) if target_rank != -1 else 0)
            send_msg(peer, "успешно!")
            if CONSOLE_CHAT_ID: send_msg(CONSOLE_CHAT_ID, f"🛠️ Админ {get_user_mention(uid)} изменил ранг {get_user_mention(target_id)} на {target_rank}")

        elif msg_lower.startswith("//ban "):
            if user['moder_rank'] < 3:
                send_msg(peer, "❌ Доступ запрещен!")
                continue
            parts = msg.split()
            if len(parts) < 3:
                send_msg(peer, "❌ Подсказка: //ban [-1/0/дни] [ссылка] [причина]")
                continue
            try: days = int(parts[1])
            except ValueError: continue
            target_id = parse_user_id(parts[2])
            reason = " ".join(parts[3:]) if len(parts) > 3 else "Нарушение правил"
            if not target_id: continue
            if days == 0:
                db.update_user_field(target_id, 'ban_until', 0)
                db.update_user_field(target_id, 'is_perm_banned', 0)
                try: vk.groups.unban(group_id=GROUP_ID, user_id=target_id)
                except: pass
                send_msg(peer, "успешно!")
                if CONSOLE_CHAT_ID: send_msg(CONSOLE_CHAT_ID, f"🛠️ {get_user_mention(uid)} разбанил {get_user_mention(target_id)}")
            elif days == -1:
                db.update_user_field(target_id, 'is_perm_banned', 1)
                db.update_user_field(target_id, 'ban_reason', reason)
                try: vk.groups.ban(group_id=GROUP_ID, user_id=target_id, comment=reason, comment_visible=1)
                except: pass
                send_msg(peer, f"⛔ Пользователь забанен навсегда. Причина: {reason}")
                if CONSOLE_CHAT_ID: send_msg(CONSOLE_CHAT_ID, f"🛠️ ⛔ {get_user_mention(uid)} выдал ВЕЧНЫЙ БАН {get_user_mention(target_id)}. Причина: {reason}")
            elif days > 0:
                ban_time = time.time() + (days * 86400)
                db.update_user_field(target_id, 'ban_until', ban_time)
                db.update_user_field(target_id, 'ban_reason', reason)
                send_msg(peer, f"⏳ Пользователь заблокирован на {days} д. Причина: {reason}")
                if CONSOLE_CHAT_ID: send_msg(CONSOLE_CHAT_ID, f"🛠️ ⏳ {get_user_mention(uid)} забанил {get_user_mention(target_id)} на {days} д. Причина: {reason}")

        elif msg_lower == "//logs":
            if user['moder_rank'] < 2: continue
            logs = db.get_withdraw_logs(10)
            txt = "📋 ПОСЛЕДНИЕ 10 ВЫВОДОВ С БОТА:\n\n"
            for log in logs:
                t_str = time.strftime("%H:%M:%S", time.localtime(log[2]))
                txt += f"⏰ [{t_str}] ID {log[1]} ➡️ Вывел: {num_to_str(log[2])}\n"
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
