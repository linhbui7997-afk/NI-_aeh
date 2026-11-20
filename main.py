
import os
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from bot.db import (
    init_db,
    get_systems,
    add_system,
    rename_system,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_IDS = {
    int(x.strip())
    for x in os.getenv("ADMIN_IDS", "").split(",")
    if x.strip().isdigit()
}

# Các trạng thái nhập liệu
STATE_KEY = "admin_state"
TEMP_SYSTEM_KEY = "temp_system"


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def main_menu_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 DANH SÁCH HỆ THỐNG", callback_data="customer_systems")],
        [InlineKeyboardButton("⚙️ QUẢN LÝ HỆ THỐNG", callback_data="admin_systems")],
    ])


def systems_kb():
    keyboard = [
        [InlineKeyboardButton("➕ THÊM HỆ THỐNG", callback_data="system_add")],
        [InlineKeyboardButton("✏️ CHỈNH SỬA HỆ THỐNG", callback_data="system_edit")],
        [InlineKeyboardButton("⬅️ QUAY LẠI", callback_data="back_main")],
    ]
    return InlineKeyboardMarkup(keyboard)


def edit_systems_kb():
    systems = get_systems()
    keyboard = []

    for system in systems:
        name = system[1] if isinstance(system, (tuple, list)) else str(system)
        keyboard.append([
            InlineKeyboardButton(
                f"✏️ {name}",
                callback_data=f"system_rename:{name}"
            )
        ])

    keyboard.append([
        InlineKeyboardButton("⬅️ QUAY LẠI", callback_data="admin_systems")
    ])
    return InlineKeyboardMarkup(keyboard)


def confirm_add_kb():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ XÁC NHẬN THÊM", callback_data="system_add:confirm"),
            InlineKeyboardButton("❌ HỦY", callback_data="system_add:cancel"),
        ],
        [InlineKeyboardButton("⬅️ QUAY LẠI", callback_data="admin_systems")],
    ])


def confirm_rename_kb():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ XÁC NHẬN ĐỔI TÊN", callback_data="system_rename:confirm"),
            InlineKeyboardButton("❌ HỦY", callback_data="system_rename:cancel"),
        ],
        [InlineKeyboardButton("⬅️ QUAY LẠI", callback_data="system_edit")],
    ])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 HỆ THỐNG QUẢN LÝ CODE\n\nChọn chức năng bên dưới:",
        reply_markup=main_menu_kb(),
    )


async def show_admin_systems(query):
    systems = get_systems()
    lines = ["⚙️ QUẢN LÝ HỆ THỐNG", ""]

    if systems:
        for system in systems:
            name = system[1] if isinstance(system, (tuple, list)) else str(system)
            lines.append(f"🟢 {name} — ĐANG HOẠT ĐỘNG")
    else:
        lines.append("Chưa có hệ thống nào.")

    await query.edit_message_text(
        "\n".join(lines),
        reply_markup=systems_kb(),
    )


async def show_customer_systems(query):
    systems = get_systems()
    lines = ["📋 DANH SÁCH HỆ THỐNG", ""]

    if systems:
        for system in systems:
            name = system[1] if isinstance(system, (tuple, list)) else str(system)
            lines.append(f"🟢 {name}")
    else:
        lines.append("Hiện chưa có hệ thống.")

    await query.edit_message_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ QUAY LẠI", callback_data="back_main")]
        ]),
    )


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    if data == "back_main":
        context.user_data.pop(STATE_KEY, None)
        context.user_data.pop(TEMP_SYSTEM_KEY, None)
        await query.edit_message_text(
            "🤖 HỆ THỐNG QUẢN LÝ CODE\n\nChọn chức năng:",
            reply_markup=main_menu_kb(),
        )
        return

    if data == "customer_systems":
        await show_customer_systems(query)
        return

    if data == "admin_systems":
        if not is_admin(user_id):
            await query.answer("Bạn không có quyền quản trị!", show_alert=True)
            return
        context.user_data.pop(STATE_KEY, None)
        context.user_data.pop(TEMP_SYSTEM_KEY, None)
        await show_admin_systems(query)
        return

    if data == "system_add":
        if not is_admin(user_id):
            await query.answer("Bạn không có quyền quản trị!", show_alert=True)
            return

        context.user_data[STATE_KEY] = "new_system"
        context.user_data.pop(TEMP_SYSTEM_KEY, None)

        await query.edit_message_text(
            "➕ THÊM HỆ THỐNG\n\n"
            "Vui lòng nhập tên hệ thống mới.\n"
            "Ví dụ: ABCBET\n\n"
            "Nhấn HỦY để quay lại.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ HỦY", callback_data="admin_systems")]
            ]),
        )
        return

    if data == "system_add:confirm":
        if not is_admin(user_id):
            return

        name = context.user_data.get(TEMP_SYSTEM_KEY)
        if not name:
            await query.edit_message_text(
                "Không tìm thấy tên hệ thống cần thêm.",
                reply_markup=systems_kb(),
            )
            return

        try:
            add_system(name)
            await query.edit_message_text(
                f"✅ ĐÃ THÊM HỆ THỐNG: {name}\n\n"
                "Hệ thống đã được lưu vào cơ sở dữ liệu.",
                reply_markup=systems_kb(),
            )
        except Exception:
            logger.exception("Không thể thêm hệ thống")
            await query.edit_message_text(
                "❌ Không thể thêm hệ thống. Vui lòng kiểm tra cơ sở dữ liệu.",
                reply_markup=systems_kb(),
            )

        context.user_data.pop(STATE_KEY, None)
        context.user_data.pop(TEMP_SYSTEM_KEY, None)
        return

    if data == "system_add:cancel":
        context.user_data.pop(STATE_KEY, None)
        context.user_data.pop(TEMP_SYSTEM_KEY, None)
        await show_admin_systems(query)
        return

    if data == "system_edit":
        if not is_admin(user_id):
            await query.answer("Bạn không có quyền quản trị!", show_alert=True)
            return

        context.user_data[STATE_KEY] = "edit_system"
        await query.edit_message_text(
            "✏️ CHỈNH SỬA HỆ THỐNG\n\nChọn hệ thống muốn đổi tên:",
            reply_markup=edit_systems_kb(),
        )
        return

    if data.startswith("system_rename:") and data not in (
        "system_rename:confirm",
        "system_rename:cancel",
    ):
        if not is_admin(user_id):
            return

        old_name = data.split(":", 1)[1]
        context.user_data["old_system_name"] = old_name
        context.user_data[STATE_KEY] = "rename_system"

        await query.edit_message_text(
            f"✏️ ĐỔI TÊN HỆ THỐNG\n\n"
            f"Tên hiện tại: {old_name}\n\n"
            "Hãy nhập tên mới:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ HỦY", callback_data="system_edit")]
            ]),
        )
        return

    if data == "system_rename:confirm":
        if not is_admin(user_id):
            return

        old_name = context.user_data.get("old_system_name")
        new_name = context.user_data.get(TEMP_SYSTEM_KEY)

        if not old_name or not new_name:
            await query.edit_message_text(
                "❌ Thiếu thông tin đổi tên.",
                reply_markup=systems_kb(),
            )
            return

        try:
            rename_system(old_name, new_name)
            await query.edit_message_text(
                f"✅ ĐÃ ĐỔI TÊN HỆ THỐNG\n\n"
                f"{old_name} ➜ {new_name}",
                reply_markup=systems_kb(),
            )
        except Exception:
            logger.exception("Không thể đổi tên hệ thống")
            await query.edit_message_text(
                "❌ Không thể đổi tên. Vui lòng kiểm tra cơ sở dữ liệu.",
                reply_markup=systems_kb(),
            )

        context.user_data.pop(STATE_KEY, None)
        context.user_data.pop(TEMP_SYSTEM_KEY, None)
        context.user_data.pop("old_system_name", None)
        return

    if data == "system_rename:cancel":
        context.user_data.pop(STATE_KEY, None)
        context.user_data.pop(TEMP_SYSTEM_KEY, None)
        context.user_data.pop("old_system_name", None)
        await show_admin_systems(query)
        return


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not is_admin(user_id):
        return

    state = context.user_data.get(STATE_KEY)
    name = update.message.text.strip()

    if not name:
        await update.message.reply_text("Tên không được để trống. Vui lòng nhập lại.")
        return

    if state == "new_system":
        existing = get_systems()
        existing_names = [
            item[1] if isinstance(item, (tuple, list)) else str(item)
            for item in existing
        ]

        if any(x.lower() == name.lower() for x in existing_names):
            await update.message.reply_text(
                "⚠️ Hệ thống này đã tồn tại. Vui lòng nhập tên khác."
            )
            return

        context.user_data[TEMP_SYSTEM_KEY] = name
        context.user_data[STATE_KEY] = "new_system_preview"

        await update.message.reply_text(
            "🔍 XÁC NHẬN THÊM HỆ THỐNG\n\n"
            f"Tên hệ thống: {name}\n"
            "Trạng thái sau khi thêm: 🟢 ĐANG HOẠT ĐỘNG\n\n"
            "Bạn có muốn lưu hệ thống này không?",
            reply_markup=confirm_add_kb(),
        )
        return

    if state == "rename_system":
        old_name = context.user_data.get("old_system_name")

        if not old_name:
            context.user_data.pop(STATE_KEY, None)
            await update.message.reply_text("Không tìm thấy hệ thống cần đổi tên.")
            return

        existing = get_systems()
        existing_names = [
            item[1] if isinstance(item, (tuple, list)) else str(item)
            for item in existing
        ]

        if any(x.lower() == name.lower() and x.lower() != old_name.lower()
               for x in existing_names):
            await update.message.reply_text(
                "⚠️ Tên hệ thống này đã được sử dụng. Hãy nhập tên khác."
            )
            return

        context.user_data[TEMP_SYSTEM_KEY] = name
        context.user_data[STATE_KEY] = "rename_preview"

        await update.message.reply_text(
            "🔍 XÁC NHẬN ĐỔI TÊN\n\n"
            f"Tên cũ: {old_name}\n"
            f"Tên mới: {name}\n\n"
            "Bạn có muốn xác nhận không?",
            reply_markup=confirm_rename_kb(),
        )
        return


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "Đã hủy thao tác.",
        reply_markup=main_menu_kb(),
    )


def main():
    if not BOT_TOKEN:
        raise RuntimeError("Thiếu BOT_TOKEN trong biến môi trường.")

    init_db()

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    logger.info("Bot đang chạy...")
    app.run_polling()


if __name__ == "__main__":
    main()
