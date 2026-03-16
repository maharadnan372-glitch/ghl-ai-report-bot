import requests
import json
from datetime import datetime, timedelta
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from openai import OpenAI
import os

# Use GitHub Secrets (environment variables)
GHL_V1_KEY = os.environ["GHL_V1_API_KEY"]
GHL_V2_TOKEN = os.environ["GHL_V2_TOKEN"]
LOCATION_ID = os.environ["LOCATION_ID"]
XAI_KEY = os.environ["XAI_API_KEY"]
GMAIL_EMAIL = os.environ["GMAIL_EMAIL"]
GMAIL_PASS = os.environ["GMAIL_APP_PASSWORD"]
REPORT_TO = os.environ["REPORT_EMAIL"]

client = OpenAI(api_key=XAI_KEY, base_url="https://api.x.ai/v1")

def get_recent_conversations(hours=3):
    since = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
    url = "https://services.leadconnectorhq.com/conversations/search"
    headers = {
        "Authorization": f"Bearer {GHL_V2_TOKEN}",
        "Version": "2021-04-15",
        "Accept": "application/json"
    }
    params = {"locationId": LOCATION_ID, "sort": "desc", "sortBy": "last_message_date", "limit": 50}
    resp = requests.get(url, headers=headers, params=params)
    data = resp.json()
    conversations = data.get("conversations", [])
    recent = []
    for conv in conversations:
        last_date = conv.get("lastMessageDate") or conv.get("last_message_date")
        if last_date and datetime.fromisoformat(last_date.replace("Z","")) > datetime.utcnow() - timedelta(hours=hours):
            recent.append(conv)
    return recent[:20]

def get_messages(conversation_id):
    url = f"https://services.leadconnectorhq.com/conversations/{conversation_id}/messages?limit=50"
    headers = {"Authorization": f"Bearer {GHL_V2_TOKEN}", "Version": "2021-04-15"}
    resp = requests.get(url, headers=headers)
    msgs = resp.json().get("messages", [])
    return "\n".join([f"{m.get('direction','')}: {m.get('body','')}" for m in msgs[-15:]])

def get_appointments(hours=3):
    start = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
    end = datetime.utcnow().isoformat()
    url = "https://rest.gohighlevel.com/v1/appointments/"
    headers = {"Authorization": f"Bearer {GHL_V1_KEY}"}
    params = {"locationId": LOCATION_ID, "startDate": start, "endDate": end}
    resp = requests.get(url, headers=headers, params=params)
    apps = resp.json().get("appointments", [])
    total = len(apps)
    cancelled = sum(1 for a in apps if a.get("status", "").lower() in ["cancelled", "canceled"])
    return total, cancelled

def analyze_with_grok(stats, sample_chats):
    prompt = f"""You are an expert GoHighLevel Conversational AI Analyst.

Stats (last 3 hours):
- Clients chatted: {stats['chats']}
- New bookings: {stats['bookings']}
- Cancelled: {stats['cancelled']}
- Conversion rate: {stats['conversion']}%

Sample real conversations:
{sample_chats}

Create a professional report:
1. Summary stats
2. Grade (A, B or C) with reasons
   • A = excellent conversion + smooth flow + almost no drop-offs
   • B = good but has clear issues
   • C = needs urgent fixes
3. Top 3-5 issues with exact examples from chats
4. Exact prompt/flow changes to reach Grade A
5. One good vs one bad chat example

Use markdown with headings and bullet points."""
    response = client.chat.completions.create(
        model="grok-beta",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=1500
    )
    return response.choices[0].message.content

def send_email(report):
    msg = MIMEMultipart()
    msg["From"] = GMAIL_EMAIL
    msg["To"] = REPORT_TO
    msg["Subject"] = f"GHL AI Bot Report - {datetime.now().strftime('%Y-%m-%d %H:%M')} (Grade in report)"
    msg.attach(MIMEText(report, "plain"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_EMAIL, GMAIL_PASS)
        server.sendmail(GMAIL_EMAIL, REPORT_TO, msg.as_string())

def main_job():
    print(f"[{datetime.now()}] Starting 3-hour analysis...")
    convs = get_recent_conversations(3)
    chats = len(convs)
    bookings, cancelled = get_appointments(3)
    conversion = round((bookings / chats * 100), 1) if chats > 0 else 0
    sample_text = ""
    for conv in convs[:8]:
        msgs = get_messages(conv["id"])
        sample_text += f"\n--- Conversation {conv['id']} ---\n{msgs}\n"
    stats = {"chats": chats, "bookings": bookings, "cancelled": cancelled, "conversion": conversion}
    report_body = analyze_with_grok(stats, sample_text)
    send_email(report_body)
    print(f"Report sent! Chats: {chats} | Bookings: {bookings}")

if __name__ == "__main__":
    main_job()
