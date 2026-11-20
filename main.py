from pathlib import Path
import zipfile, py_compile, os

base = Path("/mnt/data/ni_aeh_update")
(base / "bot").mkdir(parents=True, exist_ok=True)

main_py = r'''import os
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters
)
from bot.scanner import start_scanner_thread
from bot.db import (
    init_db, add_account, list_accounts, list_systems, add_system,
    rename_system, set_system_active, stats, list_users
)

ADMIN_IDS = {
    int(x.strip())
    for x in os.getenv("ADMIN_IDS", "").split(",")
    if x.strip().isdigit()
}
WAITING = "waiting"


def is_admin(uid):
    return uid in ADMIN_IDS


def kb(rows):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(text, callback_data=data) for text, data in row]
        for row in rows
    ])


def main_kb(uid):
    rows = [[(name, f"sys:{name}")]
            for name, active in list_systems() if active]
    rows.append([("📚 Tài khoản của tôi", "mine")])
    if is_admin(uid):
        rows.append([("🛠 Quản trị", "admin")])
    return kb(rows)


def admin_kb():
    return kb([
        [("⚙️ Quản lý hệ thống", "admin:systems")],
        [("👥 Thành viên", "admin:users")],
        [("📊 Thống kê", "admin:stats")],
        [("🏠 Trang chủ", "home")],
    ])


def systems_kb():
    return kb([
        [("➕ THÊM HỆ THỐNG", "admin:add")],
        [("✏️ CHỈNH SỬA HỆ THỐNG", "admin:edit")],
        [("⬅️ QUAY LẠI", "admin")],
    ])


def edit_systems_kb():
    rows = [[(f"{'🟢' if active else '🔴'} {name}", f"edit:{name}")]
            for name, active in list_systems()]
    rows.append([("⬅️ QUAY LẠI", "admin:systems")])
    return kb(rows)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "🤖 CHÀO MỪNG BẠN\nChọn hệ thống để đăng ký tài khoản:",
        reply_markup=main_kb(update.effective_user.id)
    )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "Đã hủy thao tác.",
        reply_markup=main_kb(update.effective_user.id)
    )


async def text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = context.user_data.get(WAITING)
    if not state:
        return

    if not is_admin(update.effective_user.id) and state.get("step") in {
        "new_system", "rename"
    }:
        context.user_data.clear()
        await update.message.reply_text("Bạn không có quyền thực hiện thao tác này.")
        return

    value = (update.message.text or "").strip()
    if not value or len(value) > 64:
        await update.message.reply_text(
            "Tên không hợp lệ. Vui lòng nhập lại (tối đa 64 ký tự) hoặc /cancel."
        )
        return

    if state["step"] == "account":
        state["account"] = value
        state["step"] = "confirm"
        await update.message.reply_text(
            f"Xác nhận đăng ký?\nHệ thống: {state['system']}\nTài khoản: {value}",
            reply_markup=kb([
                [("✅ Xác nhận", "confirm"), ("✏️ Nhập lại", "retry")],
                [("⬅️ QUAY LẠI", "home")],
            ])
        )

    elif state["step"] == "new_system":
        existing = {name.casefold() for name, _ in list_systems()}
        if value.casefold() in existing:
            await update.message.reply_text(
                f"⚠️ Hệ thống “{value}” đã tồn tại. Hãy nhập tên khác.",
                reply_markup=kb([[("⬅️ HỦY / QUAY LẠI", "admin:systems")]])
            )
            return

        state["name"] = value
        state["step"] = "new_system_preview"
        await update.message.reply_text(
            "📋 XEM TRƯỚC HỆ THỐNG MỚI\n\n"
            f"🏷 Tên hệ thống: {value}\n"
            "📌 Trạng thái: 🟢 Hoạt động\n\n"
            "Bạn xác nhận thêm hệ thống này chứ?",
            reply_markup=kb([
                [("✅ XÁC NHẬN", "system_add:confirm")],
                [("❌ HỦY", "system_add:cancel")],
            ])
        )

    elif state["step"] == "rename":
        state["new_name"] = value
        await update.message.reply_text(
            f"📋 XÁC NHẬN ĐỔI TÊN\n\n"
            f"Tên cũ: {state['old_name']}\nTên mới: {value}",
            reply_markup=kb([
                [("✅ XÁC NHẬN", "rename_yes")],
                [("❌ HỦY", "admin:edit")],
            ])
        )


async def callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data
    uid = q.from_user.id

    if data == "home":
        context.user_data.clear()
        await q.edit_message_text("🏠 TRANG CHỦ\nChọn hệ thống:", reply_markup=main_kb(uid))

    elif data.startswith("sys:"):
        system = data[4:]
        context.user_data[WAITING] = {"step": "account", "system": system}
        await q.edit_message_text(
            f"Bạn chọn {system}. Vui lòng nhập tên tài khoản "
            "(không nhập mật khẩu/OTP).",
            reply_markup=kb([[("⬅️ QUAY LẠI", "home")]])
        )

    elif data == "retry":
        system = context.user_data.get(WAITING, {}).get("system")
        if system:
            context.user_data[WAITING] = {"step": "account", "system": system}
        await q.edit_message_text(
            "Nhập lại tên tài khoản:",
            reply_markup=kb([[("⬅️ QUAY LẠI", "home")]])
        )

    elif data == "confirm":
        state = context.user_data.get(WAITING, {})
        if state.get("step") != "confirm":
            return
        add_account(uid, q.from_user.username or "", state["system"], state["account"])
        context.user_data.clear()
        await q.edit_message_text(
            "✅ Đăng ký tài khoản thành công. Lịch sử đã được lưu.",
            reply_markup=kb([
                [("📚 Tài khoản của tôi", "mine")],
                [("🏠 Trang chủ", "home")],
            ])
        )

    elif data == "mine":
        rows = list_accounts(uid)
        msg = "📚 TÀI KHOẢN ĐÃ ĐĂNG KÝ\n" + (
            "\n".join(f"• {system}: {account} — {created}"
                      for system, account, created in rows)
            if rows else "Bạn chưa có tài khoản nào."
        )
        await q.edit_message_text(
            msg[:4000], reply_markup=kb([[("🏠 Trang chủ", "home")]])
        )

    elif data == "admin" and is_admin(uid):
        context.user_data.clear()
        await q.edit_message_text("🛠 QUẢN TRỊ HỆ THỐNG", reply_markup=admin_kb())

    elif data == "admin:systems" and is_admin(uid):
        context.user_data.clear()
        systems = list_systems()
        lines = [
            f"{'🟢' if active else '🔴'} {name} — "
            f"{'Hoạt động' if active else 'Đã tắt'}"
            for name, active in systems
        ]
        msg = "⚙️ QUẢN LÝ HỆ THỐNG\n\n" + (
            "\n".join(lines) if lines else "Chưa có hệ thống nào."
        )
        await q.edit_message_text(msg, reply_markup=systems_kb())

    elif data == "admin:add" and is_admin(uid):
        context.user_data[WAITING] = {"step": "new_system"}
        await q.edit_message_text(
            "➕ THÊM HỆ THỐNG\n\nNhập tên hệ thống mới (tối đa 64 ký tự).",
            reply_markup=kb([[("⬅️ HỦY / QUAY LẠI", "admin:systems")]])
        )

    elif data == "system_add:confirm" and is_admin(uid):
        state = context.user_data.get(WAITING, {})
        if state.get("step") != "new_system_preview":
            await q.edit_message_text(
                "Phiên thêm hệ thống đã hết hạn.",
                reply_markup=systems_kb()
            )
            return

        name = state.get("name", "").strip()
        existing = {system.casefold() for system, _ in list_systems()}
        if not name or name.casefold() in existing:
            context.user_data.clear()
            await q.edit_message_text(
                "⚠️ Tên hệ thống không hợp lệ hoặc đã tồn tại.",
                reply_markup=systems_kb()
            )
            return

        add_system(name)
        context.user_data.clear()
        await q.edit_message_text(
            f"✅ ĐÃ THÊM HỆ THỐNG: {name}\n"
            "Hệ thống đã được lưu vào cơ sở dữ liệu và sẽ hiển thị "
            "trong menu khách.",
            reply_markup=kb([
                [("⚙️ QUẢN LÝ HỆ THỐNG", "admin:systems")],
                [("🏠 TRANG CHỦ", "home")],
            ])
        )

    elif data == "system_add:cancel" and is_admin(uid):
        context.user_data.clear()
        await q.edit_message_text(
            "❌ Đã hủy thêm hệ thống. Dữ liệu chưa được lưu.",
            reply_markup=systems_kb()
        )

    elif data == "admin:edit" and is_admin(uid):
        context.user_data.clear()
        await q.edit_message_text(
            "✏️ CHỈNH SỬA HỆ THỐNG\nChọn hệ thống cần chỉnh sửa:",
            reply_markup=edit_systems_kb()
        )

    elif data.startswith("edit:") and is_admin(uid):
        name = data[5:]
        await q.edit_message_text(
            f"⚙️ QUẢN LÝ: {name}",
            reply_markup=kb([
                [("✏️ Đổi tên", f"rename:{name}")],
                [("🔄 Bật / Tắt", f"toggle:{name}")],
                [("⬅️ QUAY LẠI", "admin:edit")],
            ])
        )

    elif data.startswith("rename:") and is_admin(uid):
        old_name = data[7:]
        context.user_data[WAITING] = {"step": "rename", "old_name": old_name}
        await q.edit_message_text(
            f"Nhập tên mới cho {old_name}:",
            reply_markup=kb([[("⬅️ HỦY / QUAY LẠI", "admin:edit")]])
        )

    elif data == "rename_yes" and is_admin(uid):
        state = context.user_data.get(WAITING, {})
        if state.get("step") == "rename":
            new_name = state["new_name"]
            existing = {name.casefold() for name, _ in list_systems()}
            if new_name.casefold() in existing and new_name.casefold() != state["old_name"].casefold():
                await q.edit_message_text(
                    "⚠️ Tên hệ thống mới đã tồn tại.",
                    reply_markup=edit_systems_kb()
                )
                context.user_data.clear()
                return
            rename_system(state["old_name"], new_name)
        context.user_data.clear()
        await q.edit_message_text(
            "✅ Đã cập nhật tên hệ thống.",
            reply_markup=systems_kb()
        )

    elif data.startswith("toggle:") and is_admin(uid):
        name = data[7:]
        await q.edit_message_text(
            f"Xác nhận bật/tắt hệ thống {name}?",
            reply_markup=kb([
                [("✅ Xác nhận", f"toggle_yes:{name}")],
                [("❌ Hủy", "admin:edit")],
            ])
        )

    elif data.startswith("toggle_yes:") and is_admin(uid):
        name = data[len("toggle_yes:"):]
        set_system_active(name)
        await q.edit_message_text(
            "✅ Đã cập nhật trạng thái hệ thống.",
            reply_markup=systems_kb()
        )

    elif data == "admin:stats" and is_admin(uid):
        user_count, account_count = stats()
        await q.edit_message_text(
            f"📊 THỐNG KÊ\nThành viên: {user_count}\n"
            f"Tài khoản đã ghi nhận: {account_count}",
            reply_markup=kb([[("⬅️ QUAY LẠI", "admin")]])
        )

    elif data == "admin:users" and is_admin(uid):
        users = list_users()
        msg = "👥 THÀNH VIÊN\n" + (
            "\n".join(
                f"{i}. ID {user_id} — @{username or '(không username)'}"
                for i, (user_id, username) in enumerate(users, 1)
            ) if users else "Chưa có dữ liệu."
        )
        await q.edit_message_text(
            msg[:4000], reply_markup=kb([[("⬅️ QUAY LẠI", "admin")]])
        )


async def error_handler(update, context):
    print(f"Update error: {context.error!r}")


def main():
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("Thiếu biến môi trường BOT_TOKEN")

    init_db()
    start_scanner_thread()

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CallbackQueryHandler(callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_input))
    app.add_error_handler(error_handler)
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
'''

readme = """# Bản cập nhật menu quản lý hệ thống cho NI-_aeh

## File cần thay thế
- Thay file `main.py` hiện tại trong repository bằng file `main.py` trong gói này.
- Không cần thay `bot/db.py`: hàm `add_system()` hiện có đã ghi hệ thống vào SQLite.

## Tính năng
- Menu quản lý hệ thống có các nút THÊM HỆ THỐNG, CHỈNH SỬA HỆ THỐNG, QUAY LẠI.
- Thêm hệ thống theo luồng nhập tên -> xem trước -> xác nhận/hủy.
- Chỉ khi nhấn XÁC NHẬN mới ghi hệ thống vào SQLite.
- Menu khách lấy danh sách hệ thống đang hoạt động từ SQLite nên tự cập nhật.
- Có kiểm tra tên trùng và các nút quay lại/hủy trong luồng quản trị.

## Cấu hình Railway để dữ liệu không mất khi khởi động lại
1. Mở service bot trên Railway.
2. Thêm một Volume và mount tại `/data`.
3. Trong Variables đặt `DB_PATH=/data/bot.sqlite3`.
4. Giữ nguyên `BOT_TOKEN` và `ADMIN_IDS` đã cấu hình.
5. Deploy lại service.

**Quan trọng:** SQLite chỉ bền vững khi file DB nằm trên volume bền vững. Nếu không gắn volume, dữ liệu có thể mất khi Railway thay container.

## Biến môi trường
- `BOT_TOKEN`: token bot Telegram.
- `ADMIN_IDS`: Telegram user ID của admin, nhiều ID cách nhau bằng dấu phẩy.
- `DB_PATH`: đường dẫn SQLite; khuyến nghị `/data/bot.sqlite3` khi mount volume tại `/data`.

## Cách cập nhật GitHub
1. Tải và giải nén ZIP.
2. Mở repository `NI-_aeh`.
3. Thay `main.py` bằng `main.py` trong gói.
4. Commit/push thay đổi lên nhánh đang deploy (thường là `main`).
5. Railway sẽ tự build/deploy nếu service đã kết nối GitHub.
6. Kiểm tra Variables và Volume theo hướng dẫn trên.

Gói này chỉ thay đổi luồng quản lý hệ thống; không chứa BOT_TOKEN hay thông tin bí mật.
"""

(base / "main.py").write_text(main_py, encoding="utf-8")
(base / "README_CAP_NHAT.md").write_text(readme, encoding="utf-8")

# Compile syntax check
py_compile.compile(str(base / "main.py"), doraise=True)

zip_path = Path("/mnt/data/NI_aeh_cap_nhat_quan_ly_he_thong.zip")
with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
    z.write(base / "main.py", "main.py")
    z.write(base / "README_CAP_NHAT.md", "README_CAP_NHAT.md")

print(f"Created: {zip_path} ({zip_path.stat().st_size} bytes)")
