import os
import json
import sqlite3
import streamlit as st
from google import genai
from google.genai import types

# ==========================================
# 🚨 إعداد الصفحة
# ==========================================
st.set_page_config(page_title="SkyLine Portal", layout="wide", initial_sidebar_state="expanded")

# ==========================================
# 🎨 الواجهة واللغة (RTL Ultimate Fix)
# ==========================================
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Tajawal:wght@400;500;700&display=swap');
    
    * {
        font-family: 'Tajawal', sans-serif !important;
    }
    
    .stApp, .stChatInputContainer {
        direction: rtl !important;
    }
    
    p, div, span, h1, h2, h3, h4, h5, h6, label {
        text-align: right !important;
    }

    .material-symbols-rounded, 
    [data-testid="stIconMaterial"], 
    svg {
        direction: ltr !important;
        unicode-bidi: isolate !important; 
    }

    [data-testid="stSidebar"] {
        background-color: #0F172A !important; 
        border-left: 1px solid #1E293B;
        direction: rtl !important;
    }
    
    [data-testid="stSidebar"] * {
        color: #F8FAFC !important; 
    }

    table {
        width: 100%;
        border-collapse: collapse;
        margin: 25px 0;
        font-size: 0.95em;
        background-color: #ffffff;
        color: #1e293b;
        border-radius: 8px;
        overflow: hidden;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1); 
    }
    table thead tr {
        background-color: #1E293B;
        color: #ffffff;
    }
    table th, table td {
        padding: 15px;
        border-bottom: 1px solid #E2E8F0;
    }
    table tbody tr:hover {
        background-color: #F1F5F9; 
    }

    #MainMenu {visibility: hidden;}
    header {visibility: hidden;}
    footer {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

# ==========================================
# 1. إعداد قاعدة البيانات
# ==========================================
def setup_database():
    conn = sqlite3.connect('flights.db')
    cursor = conn.cursor() 
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS flights (
            flight_id TEXT PRIMARY KEY,
            origin TEXT,
            destination TEXT,
            departure_time TEXT,
            price REAL,
            available_seats INTEGER
        )
    ''')
    cursor.execute('INSERT OR IGNORE INTO flights VALUES (?, ?, ?, ?, ?, ?)',
                   ('FL001', 'Cairo', 'Dubai', '2026-04-10 10:00', 500.00, 10))
    cursor.execute('INSERT OR IGNORE INTO flights VALUES (?, ?, ?, ?, ?, ?)',
                   ('FL002', 'Cairo', 'Dubai', '2026-04-10 14:00', 550.00, 5))
    cursor.execute('INSERT OR IGNORE INTO flights VALUES (?, ?, ?, ?, ?, ?)',
                   ('FL003', 'Riyadh', 'Jeddah', '2026-04-12 09:00', 200.00, 20))
    conn.commit()
    conn.close()

setup_database()

# ==========================================
# 2. أدوات الـ Agent
# ==========================================
def get_available_flights(origin: str, destination: str) -> str:
    conn = sqlite3.connect('flights.db')
    cursor = conn.cursor()
    cursor.execute('SELECT flight_id, departure_time, price, available_seats FROM flights WHERE origin = ? AND destination = ? AND available_seats > 0', (origin, destination))
    flights = cursor.fetchall()
    conn.close()
    if not flights:
        return json.dumps({"status": "no_flights_found", "message": f"لا توجد رحلات متاحة من {origin} إلى {destination}."})
    results = [{"flight_id": f[0], "departure_time": f[1], "price": f[2], "available_seats": f[3]} for f in flights]
    return json.dumps({"status": "success", "flights": results})

def book_flight(flight_id: str) -> str:
    conn = sqlite3.connect('flights.db')
    cursor = conn.cursor()
    cursor.execute('SELECT available_seats FROM flights WHERE flight_id = ?', (flight_id,))
    result = cursor.fetchone()
    if not result:
        conn.close()
        return json.dumps({"status": "error", "message": "رقم الرحلة غير صحيح."})
    if result[0] <= 0:
        conn.close()
        return json.dumps({"status": "error", "message": "هذه الرحلة ممتلئة بالكامل."})
    cursor.execute('UPDATE flights SET available_seats = available_seats - 1 WHERE flight_id = ?', (flight_id,))
    conn.commit()
    conn.close()
    return json.dumps({"status": "success", "message": f"تم تأكيد حجز الرحلة {flight_id}."})

def cancel_flight(flight_id: str) -> str:
    conn = sqlite3.connect('flights.db')
    cursor = conn.cursor()
    cursor.execute('SELECT flight_id FROM flights WHERE flight_id = ?', (flight_id,))
    if not cursor.fetchone():
        conn.close()
        return json.dumps({"status": "error", "message": "رقم الرحلة غير صحيح، يرجى المراجعة."})
    cursor.execute('UPDATE flights SET available_seats = available_seats + 1 WHERE flight_id = ?', (flight_id,))
    conn.commit()
    conn.close()
    return json.dumps({"status": "success", "message": f"تم إلغاء حجز الرحلة {flight_id} واسترداد المقعد."})

# ======================
# 3. إعداد الـ Agent 
# ======================
if "ai_client" not in st.session_state:
    os.environ["GEMINI_API_KEY"] = "AIzaSyD7mD7-QYin5fc0go0-eCvgHPLbA0c7V_k"
    st.session_state.ai_client = genai.Client()

if "chat_session" not in st.session_state:
    tools = [get_available_flights, book_flight, cancel_flight]
    system_instruction = """
    أنت نظام حجز آلي متقدم لشركة طيران (SkyLine).
    1. ترجم أسماء المدن للإنجليزية قبل البحث في قاعدة البيانات.
    2. تحدث بأسلوب رسمي، مهني، وموجز. لا تستخدم لغة عامية أو مبالغات.
    3. عند عرض الرحلات، يجب أن تكون حصراً في جدول Markdown بالمواصفات التالية: (رقم الرحلة | وقت الإقلاع | السعر | المقاعد المتاحة).
    4. اسأل المستخدم بنهاية الرد عن الإجراء التالي (حجز/إلغاء/بحث جديد).
    """
    
    st.session_state.chat_session = st.session_state.ai_client.chats.create(
        model='gemini-2.5-flash',
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            tools=tools,
        )
    )

chat = st.session_state.chat_session

# ==========================================
# 4. بناء القائمة الجانبية (Sidebar)
# ==========================================
with st.sidebar:
    st.markdown("<h2 style='text-align: center; color: #38BDF8 !important; margin-bottom: 0;'>✈️ SkyLine Portal</h2>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: #94A3B8 !important; font-size: 0.9em;'>نظام إدارة حجوزات الطيران</p>", unsafe_allow_html=True)
    st.divider()

    st.markdown("### 📊 لوحة النظام")
    st.markdown("<div style='margin-bottom: 10px;'>🟢 خوادم الحجز: <b>متصل</b></div>", unsafe_allow_html=True)
    st.markdown("<div style='margin-bottom: 10px;'>🟢 قاعدة البيانات: <b>محدثة</b></div>", unsafe_allow_html=True)
    st.divider()

    st.markdown("### 📌 الإجراءات المتاحة")
    st.markdown("""
    <div style="background-color: #1E293B; padding: 12px; border-radius: 8px; margin-bottom: 10px; border-right: 3px solid #38BDF8;">
        <b style="color: #F8FAFC; font-size: 1.05em;">🔍 بحث عن رحلة</b><br>
        <span style="color: #94A3B8; font-size: 0.85em;">اذكر مدينة المغادرة والوصول بوضوح.<br><i>مثال: ابحث عن رحلات من القاهرة لدبي.</i></span>
    </div>
    <div style="background-color: #1E293B; padding: 12px; border-radius: 8px; margin-bottom: 10px; border-right: 3px solid #10B981;">
        <b style="color: #F8FAFC; font-size: 1.05em;">🎫 إصدار تذكرة (حجز)</b><br>
        <span style="color: #94A3B8; font-size: 0.85em;">استخدم رقم الرحلة لإتمام الحجز.<br><i>مثال: قم بحجز الرحلة FL001.</i></span>
    </div>
    <div style="background-color: #1E293B; padding: 12px; border-radius: 8px; margin-bottom: 10px; border-right: 3px solid #EF4444;">
        <b style="color: #F8FAFC; font-size: 1.05em;">❌ استرداد تذكرة (إلغاء)</b><br>
        <span style="color: #94A3B8; font-size: 0.85em;">استخدم رقم الرحلة لإلغاء الحجز.<br><i>مثال: إلغاء الحجز للرحلة FL001.</i></span>
    </div>
    """, unsafe_allow_html=True)
    
    st.divider()
    st.markdown("<p style='text-align: center; font-size: 0.75em; color: #64748B !important;'>© 2026 SkyLine Technologies</p>", unsafe_allow_html=True)

# ==========================================
# 5. المنطقة الرئيسية (Main Chat)
# ==========================================
st.markdown("<h2>بوابة استعلامات الطيران</h2>", unsafe_allow_html=True)
st.markdown("<p style='color: #94A3B8;'>يرجى إدخال أوامر البحث أو الحجز في مربع النص أدناه.</p>", unsafe_allow_html=True)
st.divider()

if "messages" not in st.session_state:
    st.session_state.messages = []

for message in st.session_state.messages:
    avatar_icon = "👤" if message["role"] == "user" else "✈️"
    with st.chat_message(message["role"], avatar=avatar_icon):
        st.markdown(message["content"])

if prompt := st.chat_input("اكتب أمر البحث أو الحجز هنا..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar="👤"):
        st.markdown(prompt)

    with st.chat_message("assistant", avatar="✈️"):
        with st.spinner("جاري الاتصال بقاعدة البيانات..."):
            try:
                response = chat.send_message(prompt)
                st.markdown(response.text)
                st.session_state.messages.append({"role": "assistant", "content": response.text})
            except Exception as e:
                error_msg = f"خطأ في الاتصال بالخادم: {e}"
                st.error(error_msg)
                st.session_state.messages.append({"role": "assistant", "content": error_msg})