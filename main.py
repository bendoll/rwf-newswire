# import deps
import os
import asyncio
import logging
import textwrap
import re
from datetime import timezone
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
import discord
from PIL import Image
from escpos.printer import Network


# load config from .env
load_dotenv()
LOCAL_TZ = ZoneInfo(os.getenv("LOCAL_TIME_ZONE"))
TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_ID"))
PRINTER_IP = os.getenv("PRINTER_IP")
PRINTER_PORT = int(os.getenv("PRINTER_PORT", 9100))
PRINT_QUEUE_INTERVAL = int(os.getenv("PRINT_QUEUE_INTERVAL"))
PRINT_JOB_DELAY = int(os.getenv("PRINT_JOB_DELAY"))

# additional config
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HEADER_IMG = os.path.join(BASE_DIR, "img/Logo_Black.png")

logging.basicConfig(level=logging.INFO)


# convert UTC timestamp to local date and time
def format_date(dt):
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    local_date = dt.astimezone(LOCAL_TZ)
    return local_date.strftime("%Y-%m-%d")


def format_time(dt):
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    local_time = dt.astimezone(LOCAL_TZ)
    return local_time.strftime("%H:%M")


# text wrapping function
def wrap_text(text, width=48):
    return "\n".join(
        textwrap.wrap(text, width=width, break_long_words=False, break_on_hyphens=False)
    )


# scrub markdown links from embed description
def scrub_links(text):
    return re.sub(r"\[([^\]]+)\]\(([^)]+)\)", "", text)


# scrub bullet points from embed footer
def scrub_bullets(text):
    return re.sub(r"[●•◦▪▫]", "", text)


# scrub emojis
EMOJI_REGEX = re.compile(
    "["
    "\U0001f300-\U0001f5ff"  # symbols & pictographs
    "\U0001f600-\U0001f64f"  # emoticons
    "\U0001f680-\U0001f6ff"  # transport & map
    "\U0001f700-\U0001f77f"  # alchemical
    "\U0001f780-\U0001f7ff"  # geometric extended
    "\U0001f800-\U0001f8ff"  # supplemental arrows-C
    "\U0001f900-\U0001f9ff"  # supplemental symbols
    "\U0001fa00-\U0001fa6f"  # chess, etc.
    "\U0001fa70-\U0001faff"  # newer emojis
    "\U00002700-\U000027bf"  # dingbats
    "\U000024c2-\U0001f251"
    "]+",
    flags=re.UNICODE,
)


def scrub_emoji(text):
    return EMOJI_REGEX.sub("", text)


# scrub all the things
def sanitise(text):
    return scrub_emoji(scrub_bullets(scrub_links(text)))


# discord stuff
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)


def get_printer():
    return Network(PRINTER_IP, port=PRINTER_PORT)


def print_embed(date, time, title, description, footer):
    logging.info("Print job started...")

    # wrap sanitised text before printing
    _title = wrap_text(sanitise(title), width=48)
    _description = wrap_text(sanitise(description), width=48)
    _footer = wrap_text(sanitise(footer), width=48)

    # process header image
    img = Image.open(HEADER_IMG)
    target_width = 576
    img = img.resize((target_width, int(img.height * target_width / img.width)))
    img = img.convert("L")
    # apply thresholding
    # img = img.point(lambda x: 0 if x < 128 else 255, "1")
    # OR
    # apply dithering
    # img = img.convert("1")

    # initialise printer connection
    printer = get_printer()
    printer.open()

    # print all the things
    printer.image(img)
    printer.text("\n\n")
    printer.set(align="center", bold=True)
    printer.text("##### RAIDER.IO NEWSWIRE SPECIAL BULLETIN #####\n\n")
    printer.text(f"{date} - {time}\n\n")
    printer.set(align="left", bold=False)
    printer.text(_title + "\n")
    printer.text(_description + "\n\n")
    printer.text(_footer + "\n\n")
    printer.set(align="center", bold=True)
    printer.text("############# END OF TRANSMISSION #############\n\n\n\n")

    printer.cut()
    printer.close()

    logging.info("Print job completed")


# set up print queue worker
print_queue = asyncio.Queue()


async def printer_worker():
    while True:
        job = await print_queue.get()

        try:
            job_type = job["type"]

            if job_type == "embed":
                # Delay print 60 seconds
                await asyncio.sleep(PRINT_JOB_DELAY)

                await asyncio.to_thread(
                    print_embed,
                    job["date"],
                    job["time"],
                    job["title"],
                    job["description"],
                    job["footer"],
                )

        except Exception as e:
            logging.warning(f"Print job failed: {e}")

        finally:
            print_queue.task_done()

        # wait before processing next job
        await asyncio.sleep(PRINT_QUEUE_INTERVAL)


@client.event
async def on_ready():
    logging.info(f"Logged in as {client.user}")
    asyncio.create_task(printer_worker())


@client.event
async def on_message(message):
    if message.channel.id != CHANNEL_ID:
        return

    # if message.author.bot:
    #     return

    date = format_date(message.created_at)
    time = format_time(message.created_at)

    # print webhook embed content
    if message.embeds:
        await print_queue.put(
            {
                "type": "embed",
                "date": date,
                "time": time,
                "title": message.embeds[0].title or "",
                "description": message.embeds[0].description or "",
                "footer": message.embeds[0].footer.text or "",
            }
        )


client.run(TOKEN)
