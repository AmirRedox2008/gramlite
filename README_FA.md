# 📚 گرام‌لایت (GramLite) — مستندات کامل فارسی

> **گرام‌لایت** یک فریم‌ورک کامل و سبک برای ساخت ربات تلگرام است که **از صفر** نوشته شده است. تمام لایه‌ها — از کلاینت HTTP گرفته تا سیستم هندلر، ماشین حالت و میان‌افزار — در همین پروژه پیاده‌سازی شده‌اند.
>
> این مستندات مرجع کامل استفاده از کتابخانه است. نسخه انگلیسی: [README.md](README.md) | معماری داخلی: [ARCHITECTURE.md](ARCHITECTURE.md)

---

## 📖 فهرست مطالب

1. [ویژگی‌ها](#-ویژگیها)
2. [نصب](#-نصب)
3. [دریافت توکن از BotFather](#-دریافت-توکن-از-botfather)
4. [شروع سریع — اولین ربات در ۱۰ خط](#-شروع-سریع)
5. [هندلرها و فیلترها](#-هندلرها-و-فیلترها)
6. [کیبوردها (دکمه‌های شیشه‌ای و معمولی)](#-کیبوردها)
7. [ماشین حالت (FSM) — فرم‌های چندمرحله‌ای](#-ماشین-حالت-fsm)
8. [میان‌افزار (Middleware)](#-میانافزار-middleware)
9. [مدیریت خطاها](#-مدیریت-خطاها)
10. [کار با فایل‌ها (ارسال و دانلود)](#-کار-با-فایلها)
11. [پیام‌های طولانی](#-پیامهای-طولانی)
12. [مدیریت گروه و کانال](#-مدیریت-گروه-و-کانال)
13. [نسخه Async](#-نسخه-async)
14. [وبهوک (Webhook)](#-وبهوک-webhook)
15. [مرجع متدهای پرکاربرد](#-مرجع-متدهای-پرکاربرد)
16. [ابزارهای کمکی](#-ابزارهای-کمکی)
17. [تنظیمات پیشرفته](#-تنظیمات-پیشرفته)
18. [اجرای تست‌ها](#-اجرای-تستها)
19. [ساختار پروژه](#-ساختار-پروژه)
20. [انتشار در گیت‌هاب و رزومه](#-انتشار-در-گیتهاست-و-رزومه)

---

## ✨ ویژگی‌ها

- 🔌 **کلاینت کامل Bot API** — لانگ‌پولینگ، وبهوک، آپلود/دانلود فایل، تلاش مجدد خودکار روی خطا و مدیریت Flood Control (429)
- 🎯 **هندلرهای دکوریتوری** — `@bot.message_handler`، `@bot.callback_query_handler` و ۱۰ نوع رویداد دیگر
- 🧲 **فیلترهای قدرتمند و قابل ترکیب** — `commands`، `regexp`، `content_types`، `chat_types`، `state` و فیلتر سفارشی
- 🧠 **ماشین حالت (FSM) داخلی** — با سه نوع ذخیره‌ساز: حافظه، فایل JSON و Redis
- 🧱 **میان‌افزار** — زنجیره‌ای، قبل از همه هندلرها (لاگ، ضد اسپم، بن و...)
- ⚡ **نسخه Async** — همان API در حالت غیرهمزمان با aiohttp
- 🚦 **مدیریت خودکار محدودیت نرخ** — استثنای `RateLimitError` با `retry_after`
- 🧵 **Dispatch چندنخی** — اجرای موازی هندلرها با یک پارامتر
- 🛠 **ابزارهای کمکی** — تقسیم پیام بلند، escape کردن HTML/Markdown، دیپ‌لینک
- 🧪 **۱۴۲ تست خودکار** — بدون نیاز به اینترنت و توکن
- 📦 **بسته‌بندی استاندارد** — `pyproject.toml`، تایپ‌هینت کامل، CI آماده

---

## 📦 نصب

```bash
# نصب از سورس (حالت توسعه)
pip install -e .

# فقط نسخه همزمان (sync) — وابستگی: requests
pip install gramlite

# + پشتیبانی Async — وابستگی اضافه: aiohttp
pip install "gramlite[async]"

# + ذخیره‌ساز Redis برای FSM
pip install "gramlite[redis]"
```

پایتون **3.10 به بالا** لازم است.

---

## 🤖 دریافت توکن از BotFather

1. در تلگرام به [@BotFather](https://t.me/BotFather) پیام بدهید
2. دستور `/newbot` را بزنید و یک نام و نام کاربری انتخاب کنید
3. توکن را کپی کنید — چیزی شبیه `123456789:AAHfJ9x...`
4. توکن را **هرگز** مستقیم در کد کامیت نکنید؛ از متغیر محیطی استفاده کنید:

```python
import os
TOKEN = os.environ["BOT_TOKEN"]
```

---

## 🚀 شروع سریع

```python
from gramlite import Bot

bot = Bot("YOUR-BOT-TOKEN")

@bot.message_handler(commands=["start", "help"])
def welcome(message):
    bot.reply_to(message, f"سلام {message.from_user.first_name}! 👋")

@bot.message_handler(func=lambda m: True, content_types=["text"])
def echo(message):
    bot.reply_to(message, message.text)

if __name__ == "__main__":
    bot.infinity_polling()
```

فقط همین! اجرا کنید:

```bash
python bot.py
```

> 💡 تفاوت `polling()` و `infinity_polling()`: دومی بعد از هر خطای شبکه، خودش را با تأخیر تصاعدی دوباره راه‌اندازی می‌کند — برای اجرای دائمی روی سرور مناسب‌تر است.

---

## 🎯 هندلرها و فیلترها

### انواع رویداد (Update)

| دکوریتور | رویداد |
|---|---|
| `@bot.message_handler(...)` | پیام جدید |
| `@bot.edited_message_handler(...)` | ویرایش پیام |
| `@bot.channel_post_handler(...)` | پست جدید کانال |
| `@bot.callback_query_handler(...)` | کلیک روی دکمه شیشه‌ای |
| `@bot.inline_query_handler(...)` | جستجوی اینلاین (`@yourbot متن`) |
| `@bot.poll_handler(...)` | تغییر وضعیت نظرسنجی |
| `@bot.poll_answer_handler(...)` | رأی کاربر در نظرسنجی |
| `@bot.my_chat_member_handler(...)` | تغییر وضعیت خود ربات در چت (بن/آنبن شدن و...) |
| `@bot.chat_member_handler(...)` | تغییر وضعیت اعضا (ورود/خروج/ارتقا) |
| `@bot.chat_join_request_handler(...)` | درخواست عضویت در گروه/کانال |
| `@bot.pre_checkout_query_handler(...)` | پیش‌پرداخت پرداخت تلگرام |

### فیلترهای `message_handler`

| فیلتر | نوع | توضیح | مثال |
|---|---|---|---|
| `commands` | لیست | فرمان‌های اسلش‌دار | `commands=["start", "help"]` |
| `regexp` | str / Pattern | جستجوی الگو در متن | `regexp=r"(?i)سلام\|hello"` |
| `content_types` | لیست | نوع محتوا | `content_types=["photo", "video"]` |
| `chat_types` | لیست | نوع چت | `chat_types=["group", "supergroup"]` |
| `func` | تابع | شرط دلخواه روی پیام | `func=lambda m: m.chat.id == ADMIN_ID` |
| `custom_filter` | BaseFilter | فیلتر کلاس‌محور و قابل استفاده مجدد | `custom_filter=AdminFilter()` |
| `state` | State / str | فقط در آن حالت FSM فعال شود | `state=Form.name` یا `state="*"` |
| `pass_args` | bool | آرگومان‌های بعد از فرمان پاس داده شود | `/ban 123456` |

نوع چت‌ها: `"private"`، `"group"`، `"supergroup"`، `"channel"`
انواع محتوا: `"text"`، `"photo"`، `"video"`، `"audio"`، `"voice"`، `"document"`، `"sticker"`، `"animation"`، `"contact"`، `"location"`، `"venue"`، `"poll"`، `"dice"`، `"new_chat_members"` و... (مقدار ویژه `"all"` یعنی همه)

### نمونه‌های کوتاه

```python
# ۱) فرمان با آرگومان: /ban 123456
@bot.message_handler(commands=["ban"], pass_args=True, chat_types=["group", "supergroup"])
def ban(message, *args):
    user_id = int(args[0])
    bot.ban_chat_member(message.chat.id, user_id)
    bot.reply_to(message, f"کاربر <code>{user_id}</code> بن شد 🔨")

# ۲) فیلتر الگویی — هر متنی که «قیمت» داشته باشد
@bot.message_handler(regexp=r"قیمت")
def price(message):
    bot.reply_to(message, "لیست قیمت‌ها: ...")

# ۳) فقط عکس در چت خصوصی
@bot.message_handler(content_types=["photo"], chat_types=["private"])
def on_photo(message):
    # message.photo لیستی از سایزهاست؛ آخرین بزرگ‌ترین است
    bot.reply_to(message, f"عکس گرفتم! سایز: {message.photo[-1].width}x{message.photo[-1].height}")

# ۴) خوش‌آمدگویی به عضو جدید گروه
@bot.message_handler(content_types=["new_chat_members"])
def welcome_new(message):
    for user in message.new_chat_members:
        bot.reply_to(message, f"خوش اومدی {user.full_name}! 🎉")

# ۵) دکوریتورهای قابل انبار شدن — یک تابع، چند شرط
@bot.message_handler(commands=["hello"])
@bot.message_handler(func=lambda m: "👋" in (m.text or ""))
def hi(message):
    bot.reply_to(message, "سلام روی تو!")
```

> **ترتیب مهم است:** اولین هندلری که با فیلترهاش مطابقت داشته باشد اجرا می‌شود و بقیه بررسی نمی‌شوند. پس هندلرهای خاص را قبل از هندلر عمومی (مثل echo) ثبت کنید.

---

## ⌨️ کیبوردها

### کیبورد معمولی (Reply Keyboard) — جای کیبورد گوشی می‌نشیند

```python
from gramlite import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove

@bot.message_handler(commands=["menu"])
def menu(message):
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2).add(
        "📋 منوی غذا",       # رشته‌ها خودکار تبدیل به دکمه می‌شوند
        "🛒 سبد خرید",
        "📞 ارسال شماره",    # در ردیف‌های دوتایی چیده می‌شوند
    )
    bot.send_message(message.chat.id, "یکی را انتخاب کنید:", reply_markup=kb)

@bot.message_handler(commands=["share_phone"])
def share_phone(message):
    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True).add(
        KeyboardButton("📱 اشتراک‌گذاری شماره", request_contact=True),
        KeyboardButton("📍 اشتراک‌گذاری لوکیشن", request_location=True),
    )
    bot.send_message(message.chat.id, "لطفاً شماره‌ات را بفرست:", reply_markup=kb)

@bot.message_handler(content_types=["contact"])
def got_phone(message):
    bot.reply_to(message, f"شماره‌ات: {message.contact.phone_number}")
    bot.send_message(message.chat.id, "ممنون! ✅", reply_markup=ReplyKeyboardRemove())
```

### کیبورد شیشه‌ای (Inline Keyboard) — چسبیده به پیام

```python
from gramlite import InlineKeyboardMarkup, InlineKeyboardButton

@bot.message_handler(commands=["tickets"])
def tickets(message):
    kb = (
        InlineKeyboardMarkup(row_width=2)   # هر ردیف ۲ دکمه
        .add(
            InlineKeyboardButton("🎫 ۱ بلیت", callback_data="buy:1"),
            InlineKeyboardButton("🎫🎫 ۲ بلیت", callback_data="buy:2"),
        )
        .row(InlineKeyboardButton("🌐 سایت ما", url="https://example.com"))
    )
    bot.send_message(message.chat.id, "چند بلیت می‌خواهید؟", reply_markup=kb)

# دریافت کلیک — فیلتر regexp روی callback_data اعمال می‌شود
@bot.callback_query_handler(regexp=r"^buy:")
def on_buy(call):
    qty = call.data.split(":")[1]
    bot.answer_callback_query(call.id, text=f"{qty} بلیت اضافه شد! ✅")
    bot.edit_message_text(
        f"سفارش شما: {qty} بلیت 🎉",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
    )
```

> 💡 همیشه بعد از کلیک، `answer_callback_query` را صدا بزنید تا چرخاننده تلگرام متوقف شود (و اگر `text` بدهید، یک اعلان کوچک نمایش داده می‌شود).

## 🧠 ماشین حالت (FSM)

FSM برای **فرم‌های چندمرحله‌ای** است: اول اسم، بعد سن، بعد تأیید... هندلری که فیلتر `state=` دارد فقط وقتی اجرا می‌شود که کاربر در آن حالت باشد.

### مثال کامل — فرم ثبت‌نام

```python
from gramlite import Bot, State, StateGroup, JSONFileStorage

# ذخیره‌ساز فایل: بعد از ری‌استارت بات، حالت کاربران حفظ می‌شود
bot = Bot("YOUR-BOT-TOKEN", storage=JSONFileStorage("states.json"))

class Form(StateGroup):
    """حالت‌ها خودکار نام‌گذاری می‌شوند: Form.name و Form.age"""
    name = State()
    age = State()

@bot.message_handler(commands=["form"])
def start_form(message):
    bot.set_state(message.from_user.id, Form.name, message.chat.id)
    bot.reply_to(message, "اسم‌ت چیه؟")

@bot.message_handler(state=Form.name, content_types=["text"])
def get_name(message):
    # ذخیره داده در حالت فعلی
    bot.update_state_data(message.from_user.id, chat_id=message.chat.id, name=message.text)
    bot.set_state(message.from_user.id, Form.age, message.chat.id)
    bot.reply_to(message, "خوشحال شدم! چند سالته؟")

@bot.message_handler(state=Form.age, content_types=["text"])
def get_age(message):
    data = bot.get_state_data(message.from_user.id, message.chat.id)
    bot.reset_state(message.from_user.id, message.chat.id)   # بازگشت به حالت عادی
    bot.reply_to(message, f"ثبت شد ✅\nاسم: {data.get('name')} | سن: {message.text}")

# state="*" یعنی «در هر حالتی» — برای دکمه لغو عالی است
@bot.message_handler(commands=["cancel"], state="*")
def cancel(message):
    bot.clear_state_data(message.from_user.id, message.chat.id)
    bot.reply_to(message, "لغو شد. ❌")
```

### متدهای FSM روی بات

| متد | کار |
|---|---|
| `bot.set_state(user_id, state, chat_id)` | رفتن به یک حالت |
| `bot.get_state(user_id, chat_id)` | خواندن حالت فعلی (str یا None) |
| `bot.reset_state(user_id, chat_id)` | پاک کردن حالت |
| `bot.update_state_data(user_id, chat_id=..., **data)` | ذخیره/به‌روزرسانی داده |
| `bot.get_state_data(user_id, chat_id)` | خواندن همه داده‌های حالت (dict) |
| `bot.clear_state_data(user_id, chat_id)` | پاک کردن حالت + داده |

### سه ذخیره‌ساز موجود

```python
from gramlite import MemoryStorage, JSONFileStorage
from gramlite.fsm import RedisStorage

Bot(TOKEN)                                    # MemoryStorage — پیش‌فرض، با ری‌استارت پاک می‌شود
Bot(TOKEN, storage=JSONFileStorage("f.json")) # فایل — سبک و بدون وابستگی
Bot(TOKEN, storage=RedisStorage(url="redis://localhost:6379/0"))  # پروداکشن
```

---

## 🧱 میان‌افزار (Middleware)

میان‌افزار **دور تمام هندلرها** اجرا می‌شود — برای لاگ، کنترل اسپم، بن و مجوزدهی. اگر `next_()` را صدا نزنید، هندلرها اصلاً اجرا نمی‌شوند (قطع زنجیره).

```python
import time

_last_seen = {}

# ۱) لاگ همه پیام‌ها
@bot.register_middleware(update_types=["message"])
def logger_mw(message, next_):
    print(f"[LOG] {message.from_user.id} -> {message.chat.id}")
    next_()   # ادامه زنجیره

# ۲) کنترل اسپم — حداکثر ۱ پیام در ۳ ثانیه
@bot.register_middleware(update_types=["message"])
def flood_gate(message, next_):
    uid = message.from_user.id if message.from_user else 0
    now = time.monotonic()
    if now - _last_seen.get(uid, 0) < 3:
        bot.reply_to(message, "آروم‌تر! ⏳")
        return            # next_() صدا زده نشد → هندلرها اجرا نمی‌شوند
    _last_seen[uid] = now
    next_()

# ۳) در نسخه Async هم همین‌طور، فقط تابع async می‌شود:
# @bot.register_middleware(update_types=["message"])
# async def gate(message, next_):
#     if banned(message): return
#     await next_()
```

### فیلتر سفارشی کلاس‌محور (قابل استفاده مجدد)

```python
from gramlite.handlers import BaseFilter

ADMINS = {123456789}

class AdminFilter(BaseFilter):
    name = "AdminFilter"
    def check(self, message) -> bool:
        return bool(message.from_user) and message.from_user.id in ADMINS

@bot.message_handler(commands=["panel"], custom_filter=AdminFilter())
def panel(message):
    bot.reply_to(message, "به پنل مدیریت خوش آمدی 🛠")

# می‌توانید چند فیلتر را با هم ترکیب کنید:
@bot.message_handler(commands=["kick"], custom_filter=[AdminFilter(), SomeOtherFilter()])
def kick(message): ...
```

---

## 🚨 مدیریت خطاها

### گرفتن خطاهای هندلرها

```python
@bot.exception_handler
def on_error(payload, exception):
    logging.exception("خطا هنگام پردازش: %s", exception)
```

### سلسله‌مراتب استثناها

```
TelegramError                     # والد همه خطاها
├── NetworkError                  # قطعی شبکه / DNS / تایم‌اوت
├── ApiHTTPError                  # پاسخ HTTP نامعتبر
└── ApiTelegramError              # خود API خطا برگرداند (کد + توضیح)
    ├── InvalidTokenError         # 401/404 — توکن اشتباه
    ├── BotBlockedError           # 403 — ربات بلاک شده
    └── RateLimitError            # 429 — محدودیت نرخ، شامل retry_after
```

```python
import time
from gramlite import RateLimitError, TelegramError

def safe_send(chat_id, text):
    try:
        bot.send_message(chat_id, text)
    except RateLimitError as e:
        time.sleep(e.retry_after or 5)      # تلگرام گفته چند ثانیه صبر کنی
        bot.send_message(chat_id, text)
    except TelegramError as e:
        logging.error("خطای API: %s", e)
```

> ✅ نکته: کلاینت خودش روی خطاهای موقت (429 و 502/504) تا ۳ بار با تأخیر تصاعدی تلاش مجدد می‌کند؛ `RateLimitError` فقط وقتی پرتاب می‌شود که همه تلاش‌ها تمام شده باشد.

---

## 📂 کار با فایل‌ها

### ارسال — چهار روش (مسیر، URL، file_id، آبجکت فایل)

```python
bot.send_photo(chat_id, "images/cat.jpg", caption="گربه 🐱")          # ۱) مسیر فایل
bot.send_photo(chat_id, "https://example.com/cat.jpg")                # ۲) اینترنت
bot.send_photo(chat_id, "AgACAgIAAx...file_id")                       # ۳) file_id قبلی
bot.send_document(chat_id, open("report.pdf", "rb"), caption="گزارش") # ۴) آبجکت فایل

bot.send_video(chat_id, "clip.mp4")
bot.send_audio(chat_id, "song.mp3", caption="آهنگ جدید 🎵")
bot.send_voice(chat_id, "voice.ogg")
bot.send_animation(chat_id, "funny.gif")
bot.send_sticker(chat_id, "CAACAg...")
bot.send_media_group(chat_id, [...])                                   # آلبوم
```

### دانلود فایل ارسالی کاربر

```python
@bot.message_handler(content_types=["photo"])
def save_photo(message):
    file = bot.get_file(message.photo[-1].file_id)   # بزرگ‌ترین سایز
    data = bot.download_file(file)                    # bytes
    with open(f"photos/{message.message_id}.jpg", "wb") as f:
        f.write(data)
    bot.reply_to(message, "ذخیره شد ✅")
```

---

## 📏 پیام‌های طولانی

تلگرام هر پیام را به ۴۰۹۶ کاراکتر محدود می‌کند. دو راه‌حل داخلی:

```python
# راه ۱ — خودکار: در صورت نیاز به چند پیام تقسیم می‌شود
bot.send_long_message(chat_id, very_long_text)

# راه ۲ — دستی: تقسیم هوشمند (حتی وسط بلوک کد نمی‌بُرد)
from gramlite import split_text
for part in split_text(very_long_text):
    bot.send_message(chat_id, part)
```

---

## 👮 مدیریت گروه و کانال

```python
# محدودسازی / بن / آنبن
bot.ban_chat_member(chat_id, user_id)                    # بن کامل
bot.unban_chat_member(chat_id, user_id)                  # رفع بن
bot.restrict_chat_member(chat_id, user_id, permissions)  # میوت و محدودیت
bot.promote_chat_member(chat_id, user_id, can_delete_messages=True)  # ادمین کردن

# اطلاعات چت
chat  = bot.get_chat(chat_id)
count = bot.get_chat_member_count(chat_id)
admins = bot.get_chat_administrators(chat_id)            # لیست ChatMember

# تنظیمات گروه
bot.set_chat_title(chat_id, "گروه جدید 🎯")
bot.set_chat_description(chat_id, "گروه رسمی ما")

# لینک دعوت
link = bot.export_chat_invite_link(chat_id)

# درخواست عضویت (وقتی گروه «تأیید عضویت» دارد)
@bot.chat_join_request_handler()
def on_join_request(req):
    bot.approve_chat_join_request(req.chat.id, req.from_user.id)
    bot.send_message(req.chat.id, f"خوش اومدی {req.from_user.full_name}! 🎉")

# بن/آنبن شدن خودِ ربات را بفهم
@bot.my_chat_member_handler()
def on_status_change(update):
    old, new = update.old_chat_member.status, update.new_chat_member.status
    if old != "kicked" and new == "kicked":
        print("ربات بن شد!")
```

---

## ⚡ نسخه Async

همان API، فقط غیرهمزمان — برای ربات‌های پرترافیک و اتصال به سرویس‌های AI. با `pip install "gramlite[async]"` فعال می‌شود.

```python
import asyncio
from gramlite import AsyncBot

bot = AsyncBot("YOUR-BOT-TOKEN")

@bot.message_handler(commands=["start"])
async def start(message):
    await bot.reply_to(message, "سلام از نسخه async! ⚡")

@bot.message_handler(content_types=["text"])
async def echo(message):
    await bot.send_chat_action(message.chat.id, "typing")   # «در حال نوشتن...»
    await asyncio.sleep(1)                                   # شبیه‌سازی کار سنگین
    await bot.reply_to(message, message.text)

async def main():
    async with bot:            # مدیریتم پاکسازی سشن aiohttp
        await bot.infinity_polling()

asyncio.run(main())
```

---

## 🌐 وبهوک (Webhook)

به‌جای پولینگ، تلگرام آپدیت‌ها را به سرور شما POST می‌کند — سریع‌تر و کم‌هزینه‌تر برای پروداکشن. نمونه کامل در `examples/webhook_flask.py`:

```python
from flask import Flask, request
from gramlite import Bot

bot = Bot("YOUR-BOT-TOKEN")
app = Flask(__name__)

@app.route("/webhook", methods=["POST"])
def webhook():
    bot.process_webhook_update(request.get_json(force=True))
    return "ok"

# ثبت وبهوک — یک بار کافی است (secret_token برای امنیت)
bot.set_webhook(
    url="https://example.com/webhook",     # حتماً HTTPS
    secret_token="my-secret-42",
    drop_pending_updates=True,
)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8443)
```

> 💡 در وبهوک، `process_webhook_update` هر آپدیت را همان‌طور که هندلرها انتظار دارند پردازش می‌کند — بدون هیچ تغییری در کد هندلرها.

---

## 📮 مرجع متدهای پرکاربرد

| دسته | متدها |
|---|---|
| **متن** | `send_message` ، `reply_to` ، `edit_message_text` ، `delete_message` ، `send_long_message` |
| **رسانه** | `send_photo` ، `send_video` ، `send_audio` ، `send_voice` ، `send_document` ، `send_animation` ، `send_sticker` ، `send_video_note` ، `send_media_group` |
| **تعاملی** | `send_poll` ، `stop_poll` ، `send_dice` 🎲 ، `send_chat_action` |
| **مکان و مخاطب** | `send_location` ، `send_venue` ، `send_contact` |
| **فایل** | `get_file` ، `download_file` ، `download_file_url` |
| **کیبورد و کال‌بک** | `answer_callback_query` ، `answer_inline_query` |
| **پرداخت** | `answer_pre_checkout_query` |
| **گروه/کانال** | `get_chat` ، `get_chat_member` ، `get_chat_administrators` ، `get_chat_member_count` ، `ban_chat_member` ، `unban_chat_member` ، `restrict_chat_member` ، `promote_chat_member` ، `set_chat_title` ، `set_chat_description` ، `set_chat_permissions` ، `leave_chat` |
| **لینک دعوت** | `export_chat_invite_link` ، `create_chat_invite_link` ، `revoke_chat_invite_link` ، `approve_chat_join_request` ، `decline_chat_join_request` |
| **پین** | `pin_chat_message` ، `unpin_chat_message` |
| **پروفایل** | `get_me` ، `get_user_profile_photos` |
| **پیکربندی بات** | `set_my_commands` ، `set_my_name` ، `set_my_description` ، `set_webhook` ، `delete_webhook` ، `get_webhook_info` |
| **FSM** | `set_state` ، `get_state` ، `reset_state` ، `update_state_data` ، `get_state_data` ، `clear_state_data` |

---

## 🧰 ابزارهای کمکی

```python
from gramlite import escape_html, escape_markdown, split_text, create_deep_link, ParseMode

escape_html("<b>علی</b>")            # &lt;b&gt;علی&lt;/b&gt; — ضد تزریق HTML
escape_markdown("متن * ویژه", version=2)  # ایمن‌سازی برای MarkdownV2

create_deep_link("mybot", "ref123")   # https://t.me/mybot?start=ref123
# داخل ربات: @bot.message_handler(commands=["start"], pass_args=True)
#           args[0] == "ref123"  ← سیستم دعوت دوست بسازید!

ParseMode.HTML                        # "HTML" — بگذارید در Bot(parse_mode=...)
```

---

## ⚙️ تنظیمات پیشرفته

```python
from gramlite import Bot, ParseMode
from gramlite.log import setup_logging

setup_logging()   # لاگ تمیز و استاندارد برای کل کتابخانه

bot = Bot(
    token="YOUR-BOT-TOKEN",
    parse_mode=ParseMode.HTML,    # همه send_message ها پیش‌فرض HTML می‌شوند
    threaded=True,                # هندلرها موازی روی ۸ نخ اجرا شوند
    num_workers=8,
    timeout=30.0,                 # تایم‌اوت درخواست‌ها
    max_retries=3,                # تلاش مجدد خودکار
    storage=JSONFileStorage("fsm.json"),
)

# مدیریت چرخه حیات با context manager
with bot:
    bot.polling()                 # با Ctrl+C تمیز بسته می‌شود
bot.stop_polling()                # از نخ دیگر: توقف نرم حلقه پولینگ
```

---

## 🧪 اجرای تست‌ها

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

۱۴۲ تست — همه **آفلاین** و بدون نیاز به توکن یا اینترنت (با تست‌دابل‌های ساختگی به‌جای سرور تلگرام). تست Redis فقط اگر redis نصب و در دسترس باشد اجرا می‌شود.

---

## 🗂 ساختار پروژه

```
gramlite/
├── src/gramlite/
│   ├── __init__.py        # خروجی‌های عمومی + import تنبل AsyncBot
│   ├── bot.py             # کلاس Bot — ۹۰ متد عمومی
│   ├── async_bot.py       # AsyncBot — همتای غیرهمزمان
│   ├── api_client.py      # کلاینت HTTP + retry و مدیریت 429
│   ├── polling.py         # حلقه getUpdates (معمولی و infinity)
│   ├── handlers.py        # Handler، فیلترها، رجیستری (sync + async)
│   ├── fsm.py             # State، StateGroup، سه ذخیره‌ساز
│   ├── middleware.py      # زنجیره میان‌افزار (sync + async)
│   ├── types.py           # ۵۰+ مدل داده تلگرام + کیبوردها
│   ├── exceptions.py      # سلسله‌مراتب خطاها
│   ├── utils.py           # split_text، escape، deep link
│   └── log.py             # setup_logging
├── examples/              # ۶ نمونه آماده اجرا
├── tests/                 # ۱۴۲ تست آفلاین
└── pyproject.toml
```

نمونه‌های آماده در پوشه `examples/`:

| فایل | چی یاد می‌گیرید |
|---|---|
| `echo_bot.py` | شروع سریع، فیلتر func |
| `inline_keyboard_bot.py` | کیبورد شیشه‌ای + کال‌بک |
| `fsm_bot.py` | فرم چندمرحله‌ای فارسی |
| `middleware_bot.py` | لاگ، ضد اسپم، فیلتر ادمین |
| `async_echo_bot.py` | نسخه Async |
| `webhook_flask.py` | وبهوک با Flask |

---

