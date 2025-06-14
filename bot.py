import discord
from discord import app_commands, ui
import os
import requests
import time
import threading
import asyncio
from flask import Flask
import json
import uuid
from datetime import datetime, timedelta, timezone

# --- CẤU HÌNH BOT VÀ CÁC HẰNG SỐ ---
TOKEN = os.getenv('DISCORD_TOKEN')
if not TOKEN:
    print("LỖI: Vui lòng thiết lập biến môi trường DISCORD_TOKEN.")
    exit()

# ### CHỨC NĂNG MỚI ### - CẤU HÌNH KEY
ADMIN_USER_ID = 123456789012345678  # <<< THAY ID CỦA BẠN VÀO ĐÂY
KEYS_FILE = 'keys.json'

ALLOWED_CHANNEL_ID = 1383289311289544824

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# --- QUẢN LÝ KEY (JSON) ---

def load_keys():
    """Tải key từ file JSON. Trả về dict rỗng nếu file không tồn tại."""
    try:
        with open(KEYS_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_keys(keys_data):
    """Lưu key vào file JSON."""
    with open(KEYS_FILE, 'w') as f:
        json.dump(keys_data, f, indent=4)

# --- WEB SERVER CHO UPTIME ROBOT ---
app = Flask(__name__)
@app.route('/')
def home():
    return "Bot is alive and ready for commands!"

def run_flask():
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)

# --- LOGIC GỬI NGL ---
def start_ngl_spam(username: str, message: str, count: int, progress_callback: callable):
    """Hàm thực thi NGL. `count` có thể là float('inf') để chạy vô hạn."""
    sent_count = 0
    failed_count = 0
    with requests.Session() as session:
        headers = {'Host': 'ngl.link', 'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36', 'referer': f'https://ngl.link/{username}'}
        while sent_count + failed_count < count:
            data = {'username': username, 'question': message, 'deviceId': '0'}
            try:
                response = session.post('https://ngl.link/api/submit', headers=headers, data=data, timeout=10)
                if response.status_code == 200: sent_count += 1
                else:
                    failed_count += 1
                    if failed_count % 10 == 0: time.sleep(5)
            except requests.exceptions.RequestException:
                failed_count += 1; time.sleep(2)
            progress_callback(sent_count, failed_count, count)
    if count != float('inf'):
        progress_callback(sent_count, failed_count, count, finished=True)

# --- GIAO DIỆN NGƯỜI DÙNG (MODAL VÀ VIEW) ---

class NGLConfigModal(ui.Modal, title='🚀 Cấu hình NGL Spamer'):
    """Biểu mẫu để cấu hình spam SAU KHI đã xác thực key."""
    username_input = ui.TextInput(label='👤 Tên người dùng NGL', placeholder='ví dụ: elonmusk', required=True, style=discord.TextStyle.short)
    message_input = ui.TextInput(label='💬 Nội dung tin nhắn', placeholder='Nội dung bạn muốn gửi...', required=True, style=discord.TextStyle.long, max_length=250)
    count_input = ui.TextInput(label='🔢 Số lần gửi (gõ "inf" để chạy vô hạn)', placeholder='ví dụ: 500 hoặc inf', required=True, max_length=10)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        ngl_username, message, count_str = self.username_input.value, self.message_input.value, self.count_input.value.strip().lower()
        count = float('inf') if count_str == 'inf' else (int(count_str) if count_str.isdigit() and int(count_str) > 0 else 0)
        if count == 0 and count_str != 'inf':
            await interaction.followup.send("❌ Lỗi: Số lượng không hợp lệ. Vui lòng nhập số lớn hơn 0 hoặc 'inf'.", ephemeral=True); return
        async def update_progress_embed(sent, failed, total, finished=False):
            is_infinite, color = (total == float('inf')), discord.Color.green() if finished else discord.Color.blue()
            title = "✅ Tác vụ Hoàn Thành!" if finished else "🏃 Đang thực thi..."
            embed = discord.Embed(title=title, description=f"Đang gửi tin nhắn tới **{ngl_username}**.", color=color)
            if is_infinite:
                embed.description += " (Chế độ vô hạn)"
                embed.add_field(name="Trạng thái", value="`♾️ Đang chạy không ngừng...`", inline=False)
                embed.add_field(name="✅ Đã gửi", value=f"{sent}", inline=True)
                embed.add_field(name="❌ Thất bại", value=f"{failed}", inline=True)
            else:
                progress, progress_bar = (sent + failed) / total, '█' * int(((sent + failed) / total) * 20) + '─' * (20 - int(((sent + failed) / total) * 20))
                embed.add_field(name="Tiến trình", value=f"`[{progress_bar}]` {int(progress * 100)}%", inline=False)
                embed.add_field(name="✅ Thành công", value=f"{sent}/{total}", inline=True)
                embed.add_field(name="❌ Thất bại", value=f"{failed}/{total}", inline=True)
            embed.set_footer(text=f"Yêu cầu bởi {interaction.user.display_name}")
            await interaction.edit_original_response(content=None, embed=embed)
        def thread_safe_callback(sent, failed, total, finished=False):
            asyncio.run_coroutine_threadsafe(update_progress_embed(sent, failed, total, finished), client.loop)
        threading.Thread(target=start_ngl_spam, args=(ngl_username, message, count, thread_safe_callback)).start()

# ### CHỨC NĂNG MỚI ###
class KeyEntryModal(ui.Modal, title='🛡️ Xác thực Giấy phép'):
    """Biểu mẫu để người dùng nhập license key."""
    key_input = ui.TextInput(
        label='🔑 Mã kích hoạt',
        placeholder='Dán mã kích hoạt của bạn vào đây...',
        required=True,
        style=discord.TextStyle.short
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        key = self.key_input.value.strip().upper()
        keys = load_keys()
        
        if key not in keys:
            embed = discord.Embed(title="❌ Xác thực Thất bại", description="Mã kích hoạt không tồn tại hoặc đã bị vô hiệu hóa. Vui lòng liên hệ Admin.", color=discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        key_data = keys[key]
        now = datetime.now(timezone.utc)
        expires_at = datetime.fromisoformat(key_data['expires_at'])

        if now > expires_at:
            embed = discord.Embed(title="⌛ Mã Hết Hạn", description="Mã kích hoạt của bạn đã hết hạn. Vui lòng liên hệ Admin để gia hạn.", color=discord.Color.orange())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            # Dọn dẹp key hết hạn
            del keys[key]
            save_keys(keys)
            return
            
        # Nếu key hợp lệ, mở Modal cấu hình NGL
        await interaction.response.send_modal(NGLConfigModal())

class StartView(ui.View):
    """View chứa nút để mở Modal nhập key."""
    def __init__(self):
        super().__init__(timeout=None)
    
    @ui.button(label='Bắt đầu', style=discord.ButtonStyle.success, emoji='🚀', custom_id='start_key_entry_button')
    async def start_button(self, interaction: discord.Interaction, button: ui.Button):
        # Mở modal nhập key thay vì modal cấu hình
        await interaction.response.send_modal(KeyEntryModal())

# --- ĐỊNH NGHĨA LỆNH ---

@tree.command(name="start2", description="Bắt đầu tác vụ NGL với giao diện cấu hình.")
async def start2_command(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    if interaction.channel_id != ALLOWED_CHANNEL_ID:
        await interaction.followup.send(f"❌ Lệnh này chỉ có thể được sử dụng trong kênh <#{ALLOWED_CHANNEL_ID}>."); return
    embed = discord.Embed(
        title="🌟 NGL Spamer - Kích hoạt bằng Giấy phép",
        description="Chào mừng bạn đến với công cụ NGL.\n> Để tiếp tục, bạn cần có một mã kích hoạt (license key) hợp lệ. Nhấn nút **Bắt đầu** bên dưới để nhập mã của bạn.",
        color=discord.Color.purple()
    )
    embed.add_field(name="Làm thế nào để có mã?", value="Vui lòng liên hệ với **Admin** của server để nhận mã kích hoạt.", inline=False)
    embed.set_thumbnail(url="https://i.imgur.com/3Q3NSIa.png") # Một icon đẹp
    embed.set_footer(text="Bot by Gemlogin Tool - Yêu cầu mã để sử dụng")
    await interaction.followup.send(embed=embed, view=StartView())

# ### CHỨC NĂNG MỚI ###
@tree.command(name="nglkey", description="[ADMIN] Tạo một key kích hoạt mới.")
@app_commands.describe(duration="Thời hạn key (ví dụ: 7d, 24h, 30m). Mặc định là 7 ngày.")
async def generate_key(interaction: discord.Interaction, duration: str = "7d"):
    """Lệnh chỉ dành cho Admin để tạo key."""
    if interaction.user.id != ADMIN_USER_ID:
        embed = discord.Embed(title="🚫 Truy cập Bị từ chối", description="Bạn không có quyền sử dụng lệnh này.", color=discord.Color.dark_red())
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    # Phân tích thời hạn
    try:
        value = int(duration[:-1])
        unit = duration[-1].lower()
        if unit == 'd': delta = timedelta(days=value)
        elif unit == 'h': delta = timedelta(hours=value)
        elif unit == 'm': delta = timedelta(minutes=value)
        else: raise ValueError
    except (ValueError, IndexError):
        await interaction.response.send_message("❌ Định dạng thời gian không hợp lệ. Hãy dùng `d` (ngày), `h` (giờ), `m` (phút). Ví dụ: `7d`, `24h`.", ephemeral=True); return
    
    keys = load_keys()
    new_key = str(uuid.uuid4()).upper()
    created_at = datetime.now(timezone.utc)
    expires_at = created_at + delta
    
    keys[new_key] = {
        'created_at': created_at.isoformat(),
        'expires_at': expires_at.isoformat(),
        'created_by': interaction.user.id
    }
    save_keys(keys)
    
    # Tạo embed trả về CỰC ĐẸP
    embed = discord.Embed(
        title="🔑 Đã tạo Key thành công!",
        description="Mã kích hoạt đã được tạo và lưu trữ. Hãy giao mã này cho người dùng.",
        color=discord.Color.brand_green()
    )
    embed.add_field(name="Mã Kích Hoạt", value=f"```\n{new_key}\n```", inline=False)
    embed.add_field(name="🗓️ Có hiệu lực đến", value=f"<t:{int(expires_at.timestamp())}:F>", inline=True) # Dùng timestamp của Discord
    embed.add_field(name="⏳ Thời hạn", value=f"{value} { {'d': 'ngày', 'h': 'giờ', 'm': 'phút'}[unit] }", inline=True)
    embed.set_footer(text=f"Tạo bởi Admin: {interaction.user.display_name}")
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

# --- CÁC SỰ KIỆN CỦA BOT ---
@client.event
async def on_ready():
    client.add_view(StartView())
    await tree.sync()
    print(f'Logged in as {client.user} (ID: {client.user.id})')
    print('Bot is ready and slash commands are synced.')
    print("Starting Flask web server for Uptime Robot...")
    threading.Thread(target=run_flask, daemon=True).start()

# --- KHỞI CHẠY BOT ---
if __name__ == "__main__":
    client.run(TOKEN)
