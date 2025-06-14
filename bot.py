import discord
from discord import app_commands, ui
import os
import requests
import time
import threading
import asyncio
from flask import Flask

# --- CẤU HÌNH BOT VÀ CÁC HẰNG SỐ ---
TOKEN = os.getenv('DISCORD_TOKEN')
if not TOKEN:
    print("LỖI: Vui lòng thiết lập biến môi trường DISCORD_TOKEN.")
    exit()

# ID Kênh được phép sử dụng lệnh
ALLOWED_CHANNEL_ID = 1383289311289544824 

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# --- WEB SERVER CHO UPTIME ROBOT ---
app = Flask(__name__)
@app.route('/')
def home():
    return "Bot is alive and ready for commands!"

def run_flask():
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)

# --- LOGIC GỬI NGL ĐÃ TÁI CẤU TRÚC ĐỂ GỌI LẠI (CALLBACK) ---

def start_ngl_spam(username: str, message: str, count: int, progress_callback: callable):
    """
    Hàm thực thi NGL, được thiết kế để gọi lại hàm `progress_callback` để cập nhật tiến trình.
    """
    sent_count = 0
    failed_count = 0
    
    with requests.Session() as session:
        headers = { 'Host': 'ngl.link', 'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36', 'referer': f'https://ngl.link/{username}' }
        
        while sent_count + failed_count < count:
            data = { 'username': username, 'question': message, 'deviceId': '0' }
            
            try:
                response = session.post('https://ngl.link/api/submit', headers=headers, data=data, timeout=10)
                if response.status_code == 200:
                    sent_count += 1
                else:
                    failed_count += 1
                    if failed_count % 10 == 0: 
                        time.sleep(5)
            except requests.exceptions.RequestException:
                failed_count += 1
                time.sleep(2)
            
            progress_callback(sent_count, failed_count, count)
    
    progress_callback(sent_count, failed_count, count, finished=True)

# --- GIAO DIỆN NGƯỜI DÙNG (MODAL VÀ VIEW) ---

class NGLConfigModal(ui.Modal, title='📝 Cấu hình NGL Spamer'):
    """Biểu mẫu (Modal) để người dùng nhập thông tin."""
    
    username_input = ui.TextInput(label='👤 Tên người dùng NGL', placeholder='ví dụ: elonmusk', required=True, style=discord.TextStyle.short)
    message_input = ui.TextInput(label='💬 Nội dung tin nhắn', placeholder='Nội dung bạn muốn gửi...', required=True, style=discord.TextStyle.long, max_length=250)
    count_input = ui.TextInput(label='🔢 Số lần gửi (tối đa 100)', placeholder='ví dụ: 50', required=True, max_length=3)
    
    async def on_submit(self, interaction: discord.Interaction):
        """Hàm được gọi khi người dùng nhấn nút 'Submit' trên biểu mẫu."""

        # === SỬA LỖI TIMEOUT QUAN TRỌNG ===
        # Defer ngay lập tức để tránh lỗi "Unknown Interaction" khi bot cần thời gian xử lý.
        # Thao tác này sẽ hiển thị "Bot is thinking..." cho người dùng.
        await interaction.response.defer(ephemeral=True, thinking=True)
        
        ngl_username = self.username_input.value
        message = self.message_input.value
        
        try:
            count = int(self.count_input.value)
            if not (1 <= count <= 100):
                # Sử dụng followup.send vì đã defer
                await interaction.followup.send("❌ Lỗi: Số lượng phải từ 1 đến 100.", ephemeral=True)
                return
        except ValueError:
            await interaction.followup.send("❌ Lỗi: Số lượng phải là một con số hợp lệ.", ephemeral=True)
            return

        # ---- Hàm nội bộ để cập nhật tiến trình ----
        async def update_progress_embed(sent, failed, total, finished=False):
            """Hàm async để chỉnh sửa tin nhắn Embed với tiến trình mới nhất."""
            progress = (sent + failed) / total
            progress_bar = '█' * int(progress * 20) + '─' * (20 - int(progress * 20))
            color = discord.Color.green() if finished else discord.Color.blue()
            title = "✅ Tác vụ Hoàn Thành!" if finished else "🏃 Đang thực thi..."
            
            embed = discord.Embed(title=title, description=f"Đang gửi tin nhắn tới **{ngl_username}**.", color=color)
            embed.add_field(name="Tiến trình", value=f"`[{progress_bar}]` {int(progress * 100)}%", inline=False)
            embed.add_field(name="✅ Thành công", value=f"{sent}/{total}", inline=True)
            embed.add_field(name="❌ Thất bại", value=f"{failed}/{total}", inline=True)
            embed.set_footer(text=f"Yêu cầu bởi {interaction.user.display_name}")

            # Chỉnh sửa phản hồi gốc (thay thế tin "Thinking...").
            await interaction.edit_original_response(content=None, embed=embed)

        # ---- Hàm gọi lại (callback) an toàn cho luồng ----
        def thread_safe_callback(sent, failed, total, finished=False):
            coro = update_progress_embed(sent, failed, total, finished)
            asyncio.run_coroutine_threadsafe(coro, client.loop)

        # Khởi chạy luồng xử lý spam và truyền hàm callback vào
        spam_thread = threading.Thread(target=start_ngl_spam, args=(ngl_username, message, count, thread_safe_callback))
        spam_thread.start()


class StartView(ui.View):
    """View chứa nút để mở Modal cấu hình."""
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label='🚀 Bắt đầu Cấu hình', style=discord.ButtonStyle.primary, custom_id='start_config_button')
    async def start_button(self, interaction: discord.Interaction, button: ui.Button):
        # Mở Modal khi nhấn nút. Đây là một phản hồi tức thì và vẫn có thể
        # bị timeout nếu nền tảng quá lag, nhưng không có cách nào defer() được.
        await interaction.response.send_modal(NGLConfigModal())

# --- ĐỊNH NGHĨA LỆNH SLASH /start2 ---
@tree.command(name="start2", description="Bắt đầu tác vụ NGL với giao diện cấu hình.")
async def start2_command(interaction: discord.Interaction):
    """Lệnh chính để bắt đầu quy trình."""
    await interaction.response.defer(ephemeral=True)

    if interaction.channel.id != ALLOWED_CHANNEL_ID:
        await interaction.followup.send(f"❌ Lệnh này chỉ có thể được sử dụng trong kênh <#{ALLOWED_CHANNEL_ID}>.")
        return
    
    embed = discord.Embed(title="🌟 Chào mừng đến với NGL Spamer", description="Nhấn nút bên dưới để mở biểu mẫu và cấu hình thông tin cần thiết.", color=discord.Color.purple())
    embed.set_footer(text="Bot by Gemlogin Tool.")
    
    await interaction.followup.send(embed=embed, view=StartView())


# --- CÁC SỰ KIỆN CỦA BOT ---
@client.event
async def on_ready():
    client.add_view(StartView())
    await tree.sync()
    print(f'Logged in as {client.user} (ID: {client.user.id})')
    print('Bot is ready and slash commands are synced.')
    
    print("Starting Flask web server for Uptime Robot...")
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()

# --- KHỞI CHẠY BOT ---
if __name__ == "__main__":
    client.run(TOKEN)
