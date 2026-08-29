import os
import time
import json
import re
import requests
from datetime import datetime
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from openai import OpenAI
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)

# ==================== 設定區 ====================
OPENAI_API_KEY = "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"

FB_PAGE_ACCESS_TOKEN = "EAAT6l5wPNZBsBSbOZC5EDGBM24O1iHYrZCaXuYyYRKjmvNxexc71JdqEBAmuZA9UjpIzlZA9MZCfELjE2XaiYjhTqEdRNQZC1dOpregYZAArMFo9ka5GPxcZCIQUYoBeSaBGSNiwtyNcj2cD1C2aeFNZCKZCRWoZBrjL8NSlZBhbXdMbb7Ths3xuIOUiusODOfZCaJpF4g2ywj8ZBghMsRa38ZAZAMDFEUw6PflkkVONgJSPNaTwbahoZD"
FB_PAGE_ID = "1295182007241012"

# LINE Messaging API 憑證
LINE_CHANNEL_ACCESS_TOKEN = "8LFh0lL7rcc9+KtPiI4LWMeZ6wwk0hAXQrZ/PucBBFTZfacXuNiSe99g0lF6UhcUdqXXnR9s20jwQGPkmy6Th9VE2gt/l6odh9T+LSqFmpNXV52lr+eIq9+pXTksL8O+ARkPhhetiFO2AYK3caSplwdB04t89/1O/w1cDnyilFU="
LINE_CHANNEL_SECRET = "3608c5436067d9e8a4cafc9da1c2c04e"

# 初始化客戶端
openai_client = OpenAI(api_key=OPENAI_API_KEY)
line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

BACKUP_FILE = "post_backups.json"
TEMP_IMG_FILE = "temp_ai_image.png"

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

# ==================== 1. AI 創作與生圖模組 ====================
def generate_posts_and_prompts(user_prompt):
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "你是一個專業的粉專小編助理。請根據使用者的要求，產出 10 篇高品質的粉專貼文。\n"
                        "每一篇貼文必須嚴格包含兩部分：\n"
                        "1. 貼文內文（絕對不能有任何數字編號如 1. 2.，不能有『標題：』，直接從內文第一句開始，內容要豐富專業）\n"
                        "2. 一句精準流暢的英文 AI 生圖提示詞（Image Prompt，必須是具體描述科技、自動化、商業、未來感的英文畫面）\n"
                        "請用以下格式回傳每一篇：\n"
                        "[POST]\n"
                        "內文文字...\n"
                        "IMG: 英文生圖提示詞\n"
                        "[POST]\n"
                        "內文文字...\n"
                        "IMG: 英文生圖提示詞"
                    )
                },
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.8
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"[錯誤] 生成文案失敗: {e}")
        return ""

def generate_true_ai_image(prompt_text):
    try:
        encoded_prompt = requests.utils.quote(prompt_text)
        img_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1024&height=1024&nologo=true"
        
        img_data = requests.get(img_url, timeout=20).content
        with open(TEMP_IMG_FILE, "wb") as f:
            f.write(img_data)
        return TEMP_IMG_FILE
    except Exception as e:
        print(f"[錯誤] AI 生圖失敗: {e}")
        return None

# ==================== 2. 臉書圖文發布模組 ====================
def post_to_facebook_with_image_file(message, image_path):
    url = f"https://graph.facebook.com/v18.0/{FB_PAGE_ID}/photos"
    try:
        with open(image_path, 'rb') as img_file:
            files = {'source': img_file}
            data = {
                'caption': message,
                'access_token': FB_PAGE_ACCESS_TOKEN
            }
            response = requests.post(url, files=files, data=data)
            result = response.json()
            
        if 'id' in result or 'post_id' in result:
            print(f"[系統] 成功將「AI 繪圖文」發布到 Facebook 粉專！")
            return True
        else:
            print(f"[錯誤] FB 發布失敗: {result}")
            return False
    except Exception as e:
        print(f"[錯誤] 發布請求發生異常: {e}")
        return False

# ==================== 3. 定時自動發送排程任務（改為每天中午 12 點） ====================
def scheduled_publisher_job():
    backups = load_backups()
    if not backups:
        print("[排程] 目前備案庫中沒有貼文可發布。")
        return

    current_post = backups.pop(0)
    save_backups(backups)

    print(f"[排程] 開始執行每日中午自動發布... 剩餘備案數: {len(backups)}")
    
    msg = current_post["message"]
    img_prompt = current_post.get("img_prompt", "futuristic technology automation digital business concept")
    
    if "請您提供具體" in msg or len(msg) < 10:
        print("[排程] 偵測到無效廢文，自動跳過。")
        return

    print(f"[排程] 正在透過 AI 繪製專屬配圖...")
    img_path = generate_true_ai_image(img_prompt)

    if img_path and os.path.exists(img_path):
        success = post_to_facebook_with_image_file(msg, img_path)
    else:
        print("[排程] AI 圖片生成失敗，改為純文字發布。")
        url = f"https://graph.facebook.com/v18.0/{FB_PAGE_ID}/feed"
        res = requests.post(url, data={'message': msg, 'access_token': FB_PAGE_ACCESS_TOKEN}).json()
        success = 'id' in res or 'post_id' in res

    if success:
        print("[排程] 每日定時備案自動發布成功！")
    else:
        print("[排程] 每日定時備案自動發布失敗。")

scheduler = BackgroundScheduler()
# 設定為每天中午 12:00 執行
scheduler.add_job(scheduled_publisher_job, 'cron', hour=12, minute=0)
scheduler.start()


# ==================== 4. LINE 互動對話邏輯 ====================
@app.route("/", methods=['GET'])
def home():
    return "S.XIN 雲端自動化小幫手運行中！"

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature', '')
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_text = event.message.text.strip()
    reply_token = event.reply_token
    user_id = event.source.user_id
    
    if any(k in user_text for k in ["查看備案", "備案狀態", "查看庫存", "剩餘"]):
        backups = load_backups()
        reply_msg = f"📦 目前備案庫中共有 {len(backups)} 篇待發布貼文。"
        line_bot_api.reply_message(reply_token, TextSendMessage(text=reply_msg))
        return

    if any(k in user_text for k in ["備案", "10", "十", "貼文", "圖", "生成", "發", "文案", "幫我", "AI"]):
        line_bot_api.reply_message(
            reply_token,
            TextSendMessage(text="收到！正在為您重新構思文案並進行『AI 專屬繪圖』，請稍候...")
        )
        
        raw_output = generate_posts_and_prompts(user_text)
        posts_raw = raw_output.split("[POST]")
        new_backups = []
        
        for item in posts_raw:
            if "IMG:" in item:
                parts = item.split("IMG:")
                msg_part = parts[0].strip()
                img_part = parts[1].strip()
                msg_clean = re.sub(r'^\d+[\.\、\s]+', '', msg_part).strip()
                
                if len(msg_clean) > 10 and "請您提供具體" not in msg_clean:
                    new_backups.append({
                        "message": msg_clean,
                        "img_prompt": img_part
                    })
            
        save_backups(new_backups)
        
        line_bot_api.push_message(
            user_id, 
            TextSendMessage(text=f"✅ 成功存入 {len(new_backups)} 篇全新「AI 繪圖文」備案！（目前庫存總數：{len(new_backups)} 篇）\n\n系統已設定為【每天中午 12:00】自動發布一篇到粉專！")
        )
        return

    else:
        try:
            response = openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": "你是一位聰明、熱情、講話親切又像真人般的 S.XIN 娛樂城貼身小幫手，請用溫暖自然口語回答。"
                    },
                    {"role": "user", "content": user_text}
                ],
                temperature=0.8
            )
            ai_reply = response.choices[0].message.content
            line_bot_api.reply_message(reply_token, TextSendMessage(text=ai_reply))
        except Exception as e:
            line_bot_api.reply_message(reply_token, TextSendMessage(text="哎呀，我剛剛恍神了一下，您剛說什麼？"))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
