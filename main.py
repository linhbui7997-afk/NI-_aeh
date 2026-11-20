import os
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters
from bot.scanner import start_scanner_thread
from bot.db import init_db, add_account, list_accounts, list_systems, add_system, rename_system, set_system_active, stats, list_users

ADMIN_IDS = {int(x.strip()) for x in os.getenv('ADMIN_IDS', '').split(',') if x.strip().isdigit()}
WAITING = 'waiting'

def is_admin(uid): return uid in ADMIN_IDS
def kb(rows): return InlineKeyboardMarkup([[InlineKeyboardButton(t, callback_data=d) for t,d in row] for row in rows])
def main_kb(uid):
    rows = [[(s, f'sys:{s}')] for s, active in list_systems() if active]
    rows += [[('📚 Tài khoản của tôi','mine')], [('🛠 Quản trị','admin')]] if is_admin(uid) else [[('📚 Tài khoản của tôi','mine')]]
    return kb(rows)
def admin_kb():
    return kb([[('⚙️ Quản lý hệ thống','admin:systems')],[('👥 Thành viên','admin:users')],[('📊 Thống kê','admin:stats')],[('🏠 Trang chủ','home')]])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text('🤖 CHÀO MỪNG BẠN\nChọn hệ thống để đăng ký tài khoản:', reply_markup=main_kb(update.effective_user.id))
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text('Đã hủy thao tác.', reply_markup=main_kb(update.effective_user.id))
async def text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = context.user_data.get(WAITING)
    if not state: return
    value = update.message.text.strip()
    if not value or len(value) > 64:
        await update.message.reply_text('Tên tài khoản không hợp lệ. Nhập lại (tối đa 64 ký tự) hoặc /cancel.')
        return
    if state['step'] == 'account':
        state['account'] = value; state['step'] = 'confirm'
        await update.message.reply_text(f"Xác nhận đăng ký?\nHệ thống: {state['system']}\nTài khoản: {value}", reply_markup=kb([[('✅ Xác nhận','confirm'),('✏️ Nhập lại','retry')],[('↩️ Quay lại','home')]]))
    elif state['step'] == 'new_system' and is_admin(update.effective_user.id):
        add_system(value); context.user_data.clear()
        await update.message.reply_text(f'Đã thêm hệ thống: {value}', reply_markup=admin_kb())
    elif state['step'] == 'rename' and is_admin(update.effective_user.id):
        state['new_name'] = value
        await update.message.reply_text(f"Xác nhận đổi tên {state['old_name']} thành {value}?", reply_markup=kb([[('Xác nhận','rename_yes'),('Hủy','admin')]]))

async def callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer(); data = q.data; uid = q.from_user.id
    if data == 'home':
        context.user_data.clear(); await q.edit_message_text('Chọn hệ thống:', reply_markup=main_kb(uid))
    elif data.startswith('sys:'):
        system = data[4:]; context.user_data[WAITING] = {'step':'account','system':system}
        await q.edit_message_text(f'Bạn chọn {system}. Vui lòng nhập tên tài khoản (không nhập mật khẩu/OTP).', reply_markup=kb([[('↩️ Quay lại','home')]]))
    elif data == 'retry':
        s = context.user_data.get(WAITING, {}).get('system')
        if s: context.user_data[WAITING] = {'step':'account','system':s}
        await q.edit_message_text('Nhập lại tên tài khoản:', reply_markup=kb([[('↩️ Quay lại','home')]]))
    elif data == 'confirm':
        st = context.user_data.get(WAITING, {})
        if st.get('step') != 'confirm': return
        add_account(uid, q.from_user.username or '', st['system'], st['account'])
        context.user_data.clear()
        await q.edit_message_text('✅ Đăng ký tài khoản thành công. Lịch sử đã được lưu.', reply_markup=kb([[('📚 Tài khoản của tôi','mine')],[('🏠 Trang chủ','home')]]))
    elif data == 'mine':
        rows = list_accounts(uid)
        msg = '📚 TÀI KHOẢN ĐÃ ĐĂNG KÝ\n' + ('\n'.join(f"• {s}: {a} — {d}" for s,a,d in rows) if rows else 'Bạn chưa có tài khoản nào.')
        await q.edit_message_text(msg, reply_markup=kb([[('🏠 Trang chủ','home')]]))
    elif data == 'admin' and is_admin(uid):
        await q.edit_message_text('🛠 QUẢN TRỊ HỆ THỐNG', reply_markup=admin_kb())
    elif data == 'admin:systems' and is_admin(uid):
        rows = [[(f"{'🟢' if active else '🔴'} {name}", f'edit:{name}')] for name,active in list_systems()]
        rows += [[('➕ Thêm hệ thống','admin:add')],[('↩️ Quay lại','admin')]]
        await q.edit_message_text('Quản lý hệ thống:', reply_markup=kb(rows))
    elif data == 'admin:add' and is_admin(uid):
        context.user_data[WAITING] = {'step':'new_system'}
        await q.edit_message_text('Nhập tên hệ thống mới. /cancel để hủy.')
    elif data.startswith('edit:') and is_admin(uid):
        name = data[5:]
        await q.edit_message_text(f'Quản lý {name}:', reply_markup=kb([[('✏️ Đổi tên',f'rename:{name}')],[('Bật/Tắt',f'toggle:{name}')],[('↩️ Quay lại','admin:systems')]]))
    elif data.startswith('rename:') and is_admin(uid):
        old = data[7:]; context.user_data[WAITING] = {'step':'rename','old_name':old}
        await q.edit_message_text(f'Nhập tên mới cho {old}. /cancel để hủy.')
    elif data == 'rename_yes' and is_admin(uid):
        st = context.user_data.get(WAITING,{})
        if st.get('step') == 'rename': rename_system(st['old_name'], st['new_name'])
        context.user_data.clear(); await q.edit_message_text('Đã cập nhật tên hệ thống.', reply_markup=admin_kb())
    elif data.startswith('toggle:') and is_admin(uid):
        name = data[7:]
        await q.edit_message_text(f'Xác nhận bật/tắt hệ thống {name}?', reply_markup=kb([[('Xác nhận',f'toggle_yes:{name}'),('Hủy','admin:systems')]]))
    elif data.startswith('toggle_yes:') and is_admin(uid):
        set_system_active(data[11:]); await q.edit_message_text('Đã cập nhật trạng thái.', reply_markup=admin_kb())
    elif data == 'admin:stats' and is_admin(uid):
        u,a = stats(); await q.edit_message_text(f'📊 THỐNG KÊ\nThành viên: {u}\nTài khoản đã ghi nhận: {a}', reply_markup=admin_kb())
    elif data == 'admin:users' and is_admin(uid):
        users = list_users()
        msg = '👥 THÀNH VIÊN\n' + ('\n'.join(f'{i}. ID {u} — @{n or "(không username)"}' for i,(u,n) in enumerate(users,1)) if users else 'Chưa có dữ liệu.')
        await q.edit_message_text(msg[:4000], reply_markup=admin_kb())

async def error_handler(update, context): print(f'Update error: {context.error!r}')
def main():
    token = os.getenv('BOT_TOKEN')
    if not token: raise RuntimeError('Thiếu biến môi trường BOT_TOKEN')
    init_db()
    start_scanner_thread()
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler('start', start)); app.add_handler(CommandHandler('cancel', cancel))
    app.add_handler(CallbackQueryHandler(callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_input))
    app.add_error_handler(error_handler)
    app.run_polling(drop_pending_updates=True)
if __name__ == '__main__': main()
