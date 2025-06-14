import discord
from discord import app_commands
import os
import requests
import time
import threading
from flask import Flask

# --- CẤU HÌNH BOT DISCORD ---
# Lấy token từ biến môi trường trên Render.com
TOKEN = os.getenv('DISCORD_TOKEN') 
if not TOKEN:
    print("LỖI: Vui lòng thiết lập biến môi trường DISCORD_TOKEN.")
    exit()

# Cài đặt quyền (Intents) cho bot
intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# --- CÀI ĐẶT WEB SERVER (FLASK) ĐỂ UPTIME ROBOT PING ---
# Việc này giúp bot luôn chạy trên gói miễn phí của Render
app = Flask(__name__)

@app.route('/')
def home():
    """Trang chủ để Uptime Robot kiểm tra."""
    return "Bot is alive!"

def run_flask():
    """Chạy web server trên một luồng (thread) riêng biệt."""
    # Render sẽ tự động gán PORT, nếu không có thì dùng port 10000
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)

# --- LOGIC GỬI TIN NHẮN NGL (Được chuyển đổi từ code gốc) ---

def start_ngl_spam(interaction, nglusername: str, message: str, count: int):
    """
    Hàm thực thi việc gửi tin nhắn NGL.
    Hàm này được thiết kế để chạy trong một luồng riêng để không chặn bot Discord.
    """
    sent_count = 0
    not_sent_count = 0
    
    # Sử dụng context manager của client để đảm bảo nó được đóng đúng cách
    with requests.Session() as session:
        # Chuẩn bị headers một lần duy nhất
        headers = {
            'Host': 'ngl.link',
            'sec-ch-ua': '"Google Chrome";v="113", "Chromium";v="113", "Not-A.Brand";v="24"',
            'accept': '*/*',
            'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'x-requested-with': 'XMLHttpRequest',
            'sec-ch-ua-mobile': '?0',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36',
            'sec-ch-ua-platform': '"Windows"',
            'origin': 'https://ngl.link',
            'sec-fetch-site': 'same-origin',
            'sec-fetch-mode': 'cors',
            'sec-fetch-dest': 'empty',
            'referer': f'https://ngl.link/{nglusername}',
            'accept-language': 'en-US,en;q=0.9', # Dùng en-US để ổn định hơn
        }

        while sent_count < count:
            # Tạo payload cho mỗi request
            data = {
                'username': nglusername,
                'question': message,
                'deviceId': '0', # Có thể thay đổi giá trị này để tránh bị block, nhưng 0 vẫn ổn
                'gameSlug': '',
                'referrer': '',
            }

            try:
                response = session.post('https://ngl.link/api/submit', headers=headers, data=data)
                
                if response.status_code == 200:
                    sent_count += 1
                    not_sent_count = 0  # Reset bộ đếm lỗi khi thành công
                    print(f"[+] Sent {sent_count}/{count} to {nglusername}")

                    # Cập nhật thông báo trên Discord mỗi 5 tin nhắn hoặc khi hoàn thành
                    if sent_count % 5 == 0 or sent_count == count:
                        embed = discord.Embed(
                            title="🚀 NGL Progress",
                            description=f"Đang gửi tin nhắn tới **{nglusername}**...",
                            color=discord.Color.blue()
                        )
                        embed.add_field(name="Thành công", value=f"✅ {sent_count}/{count}", inline=True)
                        embed.add_field(name="Nội dung", value=f"```{message}```", inline=False)
                        # Cần chạy trong event loop của bot, nhưng không thể await trực tiếp từ thread.
                        # Do đó, sẽ chỉ cập nhật ở cuối. Tạm thời chỉ in ra console.
                        
                else:
                    not_sent_count += 1
                    print(f"[-] Failed to send. Status: {response.status_code}. Retries: {not_sent_count}")
                
                if not_sent_count >= 10:
                    print("[!] Too many failures. Waiting for 10 seconds...")
                    time.sleep(10)
                    not_sent_count = 0 # Reset lại để thử tiếp

            except requests.exceptions.RequestException as e:
                print(f"[!] An error occurred: {e}")
                not_sent_count += 1
                time.sleep(5) # Đợi một chút nếu có lỗi mạng
        
    print(f"Finished job for {nglusername}. Total sent: {sent_count}")
    # Tin nhắn cuối cùng sẽ được gửi từ coroutine gốc.
    return sent_count


# --- ĐỊNH NGHĨA LỆNH SLASH CHO BOT ---
@tree.command(name="ngl", description="Gửi tin nhắn ẩn danh tới người dùng NGL.")
@app_commands.describe(
    username="Tên người dùng NGL (ví dụ: 'elonmusk')",
    message="Nội dung tin nhắn bạn muốn gửi",
    count="Số lần gửi tin nhắn (tối đa 100 để tránh lạm dụng)"
)
async def ngl_command(interaction: discord.Interaction, username: str, message: str, count: int):
    # Giới hạn số lượng để tránh spam quá mức và bị block
    if count > 100:
        await interaction.response.send_message("Lỗi: Số lượng không được vượt quá 100.", ephemeral=True)
        return

    # Phản hồi ban đầu cho người dùng biết bot đã nhận lệnh
    initial_embed = discord.Embed(
        title="⏳ NGL Command Received",
        description=f"Chuẩn bị gửi **{count}** tin nhắn đến người dùng **{username}**.\nQuá trình này sẽ chạy ngầm.",
        color=discord.Color.orange()
    )
    await interaction.response.send_message(embed=initial_embed, ephemeral=True)

    # Chạy hàm spam trong một thread riêng để không block bot
    # Dùng lambda để truyền đối số vào hàm
    spam_thread = threading.Thread(
        target=start_ngl_spam, 
        args=(interaction, username, message, count)
    )
    spam_thread.start()

    # Bot vẫn hoạt động bình thường trong khi thread kia đang chạy
    # Vì hàm start_ngl_spam không thể trực tiếp 'await', chúng ta sẽ không cập nhật real-time.
    # Thay vào đó, sau một khoảng thời gian, chúng ta sẽ thông báo kết quả.
    # Đây là một cách đơn giản, một cách nâng cao hơn là dùng asyncio.Queue.
    
    # Đợi thread hoàn thành
    spam_thread.join()

    # Gửi thông báo hoàn thành
    final_embed = discord.Embed(
        title="✅ NGL Task Completed",
        description=f"Đã gửi thành công **{count}** tin nhắn đến người dùng **{username}**.",
        color=discord.Color.green()
    )
    final_embed.add_field(name="Nội dung đã gửi", value=f"```{message}```")
    await interaction.followup.send(embed=final_embed, ephemeral=True)

# --- SỰ KIỆN KHI BOT SẴN SÀNG ---
@client.event
async def on_ready():
    # Đồng bộ hóa cây lệnh với Discord
    await tree.sync()
    print(f'Logged in as {client.user} (ID: {client.user.id})')
    print('Bot is ready and slash commands are synced.')
    
    # Khởi động web server trong một luồng riêng
    print("Starting Flask web server for Uptime Robot...")
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True # Để thread tự tắt khi chương trình chính kết thúc
    flask_thread.start()

# --- KHỞI CHẠY BOT ---
if __name__ == "__main__":
    client.run(TOKEN)
