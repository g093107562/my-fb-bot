import os
import json
import requests
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from openai import OpenAI
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)

# ==================== 設定區 ====================
OPENAI_API_KEY = "sk-proj-D_PAkkCJs0qA97-fxsfoM2HQ9med"
FB_PAGE_ACCESS_TOKEN = "EAAT615wPNZBsBSbOZC5EDGBM2401i"
FB_PAGE_ID = "1295182007241012"

# LINE Messaging API 憑證
LINE_CHANNEL_ACCESS_TOKEN = "8LFh0l7rcc9+KtPiI4LWMeZ6v"
LINE_CHANNEL_SECRET = "3608c5436067d9e8a4cafc9da1c2c046"

# 初始化客戶端
openai_client = OpenAI(api_key=OPENAI_API_KEY)
line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

BACKUP_FILE = "post_backups.json"

def load_backups():
    if os.path.exists(BACKUP_FILE):
        try:
            with open(BACKUP_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_backups(backups):
    with open(BACKUP_FILE, "w", encoding="utf-8") as f:
        json.dump(backups, f, ensure_ascii=False, indent=4)

@app.route("/", methods=['GET', 'POST'])
def home():
    if request.method == 'POST':
        return 'OK', 200
    return "FB Auto Publisher Bot is running!"

@app.route("/callback", methods=['GET', 'POST'])
def callback():
    # 支援 LINE 驗證的 GET 請求
    if request.method == 'GET':
        return 'Hello from LINE Bot callback!', 200
        
    signature = request.headers.get('X-Line-Signature', '')
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK', 200

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_text = event.message.text
    
    if user_text == "測試":
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="機器人運行中，隨時可以幫您發文！")
        )
        return

    try:
        # 使用 OpenAI 生成貼文內容
        response = openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "你是一個專業的社群小編，請根據使用者的主題寫出一篇吸引人的 Facebook 貼文，包含適當的 Emoji 與 Hashtag。"},
                {"role": "user", "content": user_text}
            ]
        )
        post_content = response.choices[0].message.content

        # 發布到 Facebook 粉絲專頁
        url = f"https://graph.facebook.com/v18.0/{FB_PAGE_ID}/feed"
        payload = {
            'message': post_content,
            'access_token': FB_PAGE_ACCESS_TOKEN
        }
        fb_response = requests.post(url, data=payload)
        res_data = fb_response.json()

        if 'id' in res_data:
            reply_text = f"✅ 已經成功發布到 Facebook 粉絲專頁！\n\n【貼文內容】：\n{post_content}"
        else:
            reply_text = f"❌ 發布失敗，FB 回傳錯誤：{res_data}"

    except Exception as e:
        reply_text = f"⚠️ 發生錯誤：{str(e)}"

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply_text)
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
