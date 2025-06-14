import discord
from discord import app_commands, ui # Thêm ui để sử dụng View, Modal, Button
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
                    # Nếu thất bại liên tục, có thể NGL đã chặn, nên dừng lại một chút
                    if failed_count % 10 == 0: 
                        time.sleep(5)
            except requests.exceptions.RequestException:
                failed_count += 1
                time.sleep(2)
            
            # Gọi lại để cập nhật tiến trình trên Discord
            progress_callback(sent_count, failed_count, count)
    
    # Báo cáo cuối cùng
    progress_callback(sent_count, failed_count, count, finished=True)

# --- GIAO DIỆN NGƯỜI DÙNG (MODAL VÀ VIEW) ---

class NGLConfigModal(ui.Modal, title='📝 Cấu hình NGL Spamer'):
    """Biểu mẫu (Modal) để người dùng nhập thông tin."""
    
    # Input cho Username
    username_input = ui.TextInput(
        label='👤 Tên người dùng NGL',
        placeholder='ví dụ: elonmusk',
        required=True,
        style=discord.TextStyle.short
    )
    
    # Input cho Nội dung tin nhắn
    message_input = ui.TextInput(
        label='💬 Nội dung tin nhắn',
        placeholder='Nội dung bạn muốn gửi...',
        required=True,
        style=discord.TextStyle.long, # Cho phép nhập nhiều dòng
        max_length=250
    )
    
    # Input cho Số lượng
    count_input = ui.TextInput(
        label='🔢 Số lần gửi (tối đa 100)',
        placeholder='ví dụ: 50',
        required=True,
        max_length=3
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        """Hàm được gọi khi người dùng nhấn nút 'Submit' trên biểu mẫu."""
        
        # Lấy giá trị từ các ô input
        ngl_username = self.username_input.value
        message = self.message_input.value
        
        # Kiểm tra và chuyển đổi 'count' thành số
        try:
            count = int(self.count_input.value)
            if not (1 <= count <= 100):
                await interaction.response.send_message("❌ Lỗi: Số lượng phải từ 1 đến 100.", ephemeral=True)
                return
        except ValueError:
            await interaction.response.send_message("❌ Lỗi: Số lượng phải là một con số hợp lệ.", ephemeral=True)
            return

        # Phản hồi ban đầu để người dùng biết bot đã nhận lệnh và đang xử lý
        await interaction.response.send_message("🚀 Chuẩn bị khởi chạy... Vui lòng đợi.", ephemeral=True)

        # ---- Hàm nội bộ để cập nhật tiến trình ----
        async def update_progress_embed(sent, failed, total, finished=False):
            """Hàm async để chỉnh sửa tin nhắn Embed với tiến trình mới nhất."""
            progress = (sent + failed) / total
            progress_bar = '█' * int(progress * 20) + '─' * (20 - int(progress * 20))

            if finished:
                color = discord.Color.green()
                title = "✅ Tác vụ Hoàn Thành!"
            else:
                color = discord.Color.blue()
                title = "🏃 Đang thực thi... "
            
            embed = discord.Embed(
                title=title,
                description=f"Đang gửi tin nhắn tới **{ngl_username}**.",
                color=color
            )
            embed.add_field(name="Tiến trình", value=f"`[{progress_bar}]` {int(progress * 100)}%", inline=False)
            embed.add_field(name="✅ Thành công", value=f"{sent}/{total}", inline=True)
            embed.add_field(name="❌ Thất bại", value=f"{failed}/{total}", inline=True)
            embed.set_footer(text=f"Yêu cầu bởi {interaction.user.display_name}")

            # Chỉnh sửa tin nhắn gốc mà người dùng đã thấy ("Chuẩn bị khởi chạy...")
            await interaction.edit_original_response(content=None, embed=embed)

        # ---- Hàm gọi lại (callback) an toàn cho luồng ----
        def thread_safe_callback(sent, failed, total, finished=False):
            """Hàm này được luồng spam gọi. Nó sẽ lên lịch chạy hàm async trên luồng chính của bot."""
            # Tạo một coroutine để chạy trên luồng chính
            coro = update_progress_embed(sent, failed, total, finished)
            # Lên lịch để coroutine đó chạy an toàn trên event loop của bot
            asyncio.run_coroutine_threadsafe(coro, client.loop)

        # Khởi chạy luồng xử lý spam và truyền hàm callback vào
        spam_thread = threading.Thread(
            target=start_ngl_spam,
            args=(ngl_username, message, count, thread_safe_callback)
        )
        spam_thread.start()


class StartView(ui.View):
    """View chứa nút để mở Modal cấu hình."""
    def __init__(self):
        super().__init__(timeout=None) # timeout=None để view không bị vô hiệu hóa

    @ui.button(label='🚀 Bắt đầu Cấu hình', style=discord.ButtonStyle.primary, custom_id='start_config_button')
    async def start_button(self, interaction: discord.Interaction, button: ui.Button):
        # Khi nút được nhấn, mở Modal NGLConfigModal
        await interaction.response.send_modal(NGLConfigModal())

# --- ĐỊNH NGHĨA LỆNH SLASH /start2 (ĐÃ SỬA LỖI) ---
@tree.command(name="start2", description="Bắt đầu tác vụ NGL với giao diện cấu hình.")
async def start2_command(interaction: discord.Interaction):
    """Lệnh chính để bắt đầu quy trình."""
    
    # ### SỬA LỖI ###
    # Trì hoãn phản hồi ngay lập tức để tránh lỗi timeout 3 giây.
    # ephemeral=True sẽ làm cho cả thông báo "Thinking..." và các tin nhắn followup sau đó
    # chỉ hiển thị cho người dùng gọi lệnh.
    await interaction.response.defer(ephemeral=True)

    # 1. Kiểm tra kênh
    if interaction.channel.id != ALLOWED_CHANNEL_ID:
        # ### SỬA LỖI ###
        # Sử dụng `followup.send()` để gửi tin nhắn sau khi đã defer().
        await interaction.followup.send(
            f"❌ Lệnh này chỉ có thể được sử dụng trong kênh <#{ALLOWED_CHANNEL_ID}>."
        )
        return
    
    # 2. Hiển thị View với nút "Bắt đầu"
    embed = discord.Embed(
        title="🌟 Chào mừng đến với NGL Spamer",
        description="Nhấn nút bên dưới để mở biểu mẫu và cấu hình thông tin cần thiết.",
        color=discord.Color.purple()
    )
    embed.set_footer(text="Bot by Gemlogin Tool.")
    
    # ### SỬA LỖI ###
    # Sử dụng `followup.send()` để gửi phản hồi chính.
    await interaction.followup.send(embed=embed, view=StartView())


# --- CÁC SỰ KIỆN CỦA BOT ---
@client.event
async def on_ready():
    # Thêm View vào bot để nó hoạt động sau khi khởi động lại
    # Điều này quan trọng để các nút cũ vẫn hoạt động
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
