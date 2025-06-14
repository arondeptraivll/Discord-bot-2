import discord
from discord import app_commands
import os
import requests
import time
import threading
import asyncio  # <<< THÊM VÀO: Cần thiết cho việc giao tiếp giữa các luồng
from flask import Flask

# --- CẤU HÌNH BOT DISCORD ---
TOKEN = os.getenv('DISCORD_TOKEN') 
if not TOKEN:
    print("LỖI: Vui lòng thiết lập biến môi trường DISCORD_TOKEN.")
    exit()

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# --- CÀI ĐẶT WEB SERVER (FLASK) ---
app = Flask(__name__)
@app.route('/')
def home():
    return "Bot is alive!"

def run_flask():
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)

# --- LOGIC GỬI TIN NHẮN NGL (Đã sửa lỗi) ---

def start_ngl_spam(client, interaction, nglusername: str, message: str, count: int):
    """
    Hàm thực thi việc gửi tin nhắn NGL, chạy trong một luồng riêng.
    Khi hoàn thành, nó sẽ tự gửi thông báo kết quả trở lại Discord.
    """
    sent_count = 0
    not_sent_count = 0
    
    with requests.Session() as session:
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
            'accept-language': 'en-US,en;q=0.9',
        }

        while sent_count < count:
            data = {
                'username': nglusername,
                'question': message,
                'deviceId': '0',
                'gameSlug': '',
                'referrer': '',
            }

            try:
                response = session.post('https://ngl.link/api/submit', headers=headers, data=data, timeout=10) # Thêm timeout
                if response.status_code == 200:
                    sent_count += 1
                    not_sent_count = 0
                    print(f"[+] Sent {sent_count}/{count} to {nglusername}")
                else:
                    not_sent_count += 1
                    print(f"[-] Failed to send. Status: {response.status_code}. Retries: {not_sent_count}")
                
                if not_sent_count >= 10:
                    print("[!] Too many failures. Waiting for 10 seconds...")
                    time.sleep(10)
                    not_sent_count = 0

            except requests.exceptions.RequestException as e:
                print(f"[!] An error occurred: {e}")
                not_sent_count += 1
                time.sleep(5)
        
    print(f"Finished job for {nglusername}. Total sent: {sent_count}")

    # <<< THAY ĐỔI LỚN: Gửi thông báo hoàn thành từ luồng phụ >>>
    # Tạo Embed
    final_embed = discord.Embed(
        title="✅ NGL Task Completed",
        description=f"Đã gửi xong tin nhắn đến người dùng **{username}**.",
        color=discord.Color.green()
    )
    final_embed.add_field(name="Số lượng yêu cầu", value=f"`{count}`", inline=True)
    final_embed.add_field(name="Thành công", value=f"`{sent_count}`", inline=True)
    final_embed.add_field(name="Nội dung đã gửi", value=f"```{message}```", inline=False)
    final_embed.set_footer(text=f"Tác vụ được yêu cầu bởi {interaction.user.name}")
    
    # Tạo coroutine để gửi tin nhắn
    coro = interaction.followup.send(embed=final_embed, ephemeral=True)
    
    # Gửi coroutine vào event loop chính của bot một cách an toàn
    asyncio.run_coroutine_threadsafe(coro, client.loop)

# --- ĐỊNH NGHĨA LỆNH SLASH CHO BOT (Đã sửa lỗi) ---
@tree.command(name="ngl", description="Gửi tin nhắn ẩn danh tới người dùng NGL.")
@app_commands.describe(
    username="Tên người dùng NGL (ví dụ: 'elonmusk')",
    message="Nội dung tin nhắn bạn muốn gửi",
    count="Số lần gửi tin nhắn (tối đa 100)"
)
async def ngl_command(interaction: discord.Interaction, username: str, message: str, count: int):
    if count > 100:
        await interaction.response.send_message("Lỗi: Số lượng không được vượt quá 100.", ephemeral=True)
        return

    # Phản hồi ngay lập tức cho người dùng biết bot đã nhận lệnh
    initial_embed = discord.Embed(
        title="⏳ NGL Command Received",
        description=f"Đã nhận yêu cầu! Bắt đầu gửi **{count}** tin nhắn đến **{username}**.\nBạn sẽ nhận được thông báo khi hoàn thành.",
        color=discord.Color.orange()
    )
    await interaction.response.send_message(embed=initial_embed, ephemeral=True)

    # <<< THAY ĐỔI LỚN: KHÔNG DÙNG .join() NỮA >>>
    # Chạy hàm spam trong một luồng riêng và truyền các đối số cần thiết
    spam_thread = threading.Thread(
        target=start_ngl_spam, 
        args=(client, interaction, username, message, count) # Truyền client và interaction vào luồng
    )
    spam_thread.start()
    
    # Lệnh kết thúc ngay tại đây, giải phóng event loop của bot.
    # Bot sẽ tiếp tục hoạt động bình thường trong khi luồng spam chạy ngầm.

# --- SỰ KIỆN KHI BOT SẴN SÀNG ---
@client.event
async def on_ready():
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
