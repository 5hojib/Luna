import contextlib
from asyncio import create_subprocess_exec, gather
from os import execl as osexecl
from sys import executable

from aiofiles import open as aiopen
from aiofiles.os import path as aiopath
from aiofiles.os import remove

from bot import LOGGER, intervals, scheduler
from bot.core.config_manager import Config
from bot.core.aeon_client import TgClient
from bot.helper.ext_utils.bot_utils import new_task, sync_to_async
from bot.helper.ext_utils.db_handler import database
from bot.helper.ext_utils.files_utils import clean_all
from bot.helper.telegram_helper.message_utils import send_message


@new_task
async def restart_bot(_, message):
    intervals["stopAll"] = True
    restart_message = await send_message(message, "Restarting...")
    if scheduler.running:
        scheduler.shutdown(wait=False)
    if qb := intervals["qb"]:
        qb.cancel()
    if st := intervals["status"]:
        for intvl in list(st.values()):
            intvl.cancel()
    await sync_to_async(clean_all)
    proc1 = await create_subprocess_exec(
        "pkill",
        "-9",
        "-f",
        "gunicorn|aria2c|qbittorrent-nox|ffmpeg|rclone|java|sabnzbdplus",
    )
    proc2 = await create_subprocess_exec("python3", "update.py")
    await gather(proc1.wait(), proc2.wait())
    async with aiopen(".restartmsg", "w") as f:
        await f.write(f"{restart_message.chat.id}\n{restart_message.id}\n")
    osexecl(executable, executable, "-m", "bot")


async def restart_notification():
    if await aiopath.isfile(".restartmsg"):
        with open(".restartmsg") as f:
            chat_id, msg_id = map(int, f)
    else:
        chat_id, msg_id = 0, 0

    async def send_incomplete_task_message(cid, msg):
        try:
            if msg.startswith("Restarted Successfully!"):
                await TgClient.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=msg_id,
                    text=msg,
                )
                await remove(".restartmsg")
            else:
                await TgClient.bot.send_message(
                    chat_id=cid,
                    text=msg,
                    disable_web_page_preview=True,
                    disable_notification=True,
                )
        except Exception as e:
            LOGGER.error(e)

    if Config.INCOMPLETE_TASK_NOTIFIER and Config.DATABASE_URL:
        if notifier_dict := await database.get_incomplete_tasks():
            for cid, data in notifier_dict.items():
                msg = (
                    "Restarted Successfully!" if cid == chat_id else "Bot Restarted!"
                )
                for tag, links in data.items():
                    msg += f"\n\n{tag}: "
                    for index, link in enumerate(links, start=1):
                        msg += f" <a href='{link}'>{index}</a> |"
                        if len(msg.encode()) > 4000:
                            await send_incomplete_task_message(cid, msg)
                            msg = ""
                if msg:
                    await send_incomplete_task_message(cid, msg)

    if await aiopath.isfile(".restartmsg"):
        with contextlib.suppress(Exception):
            await TgClient.bot.edit_message_text(
                chat_id=chat_id,
                message_id=msg_id,
                text="Restarted Successfully!",
            )
        await remove(".restartmsg")
