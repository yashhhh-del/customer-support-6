import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import uuid
import time
import os
import json
import sqlite3
from typing import List, Dict, Optional, Tuple
import re
from io import BytesIO
import base64

# For PDF/DOCX/Excel processing
try:
    import PyPDF2
    from docx import Document
    import openpyxl
    from openpyxl import load_workbook
except ImportError:
    st.warning("Please install: pip install PyPDF2 python-docx openpyxl")

# For email functionality
try:
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    from email.mime.base import MIMEBase
    from email import encoders
    import imaplib
    import email
except ImportError:
    st.warning("Email libraries not available")

# For WhatsApp integration
try:
    import webbrowser
    import urllib.parse
except ImportError:
    st.warning("WhatsApp libraries not available")

# For vector database and embeddings
try:
    from langchain.text_splitter import RecursiveCharacterTextSplitter
    from langchain_community.vectorstores import FAISS
    from langchain_openai import OpenAIEmbeddings, ChatOpenAI
    from langchain.chains import RetrievalQA
    from langchain.docstore.document import Document as LangchainDocument
    from langchain.prompts import PromptTemplate
except ImportError:
    st.warning("Please install: pip install langchain langchain-openai langchain-community faiss-cpu")

# For language detection and translation
try:
    from langdetect import detect, LangDetectException
    from deep_translator import GoogleTranslator
except ImportError:
    st.warning("Please install: pip install langdetect deep-translator")

# For web scraping
try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    st.warning("Please install: pip install requests beautifulsoup4")

# For OCR
try:
    import pytesseract
    from PIL import Image
except ImportError:
    st.warning("Please install: pip install pytesseract Pillow")

# For semantic similarity (confidence scoring)
try:
    from sklearn.metrics.pairwise import cosine_similarity
    import numpy as np
except ImportError:
    st.warning("Please install: pip install scikit-learn numpy")

# Page configuration
st.set_page_config(
    page_title="AI Support Agent",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1f77b4;
        text-align: center;
        margin-bottom: 2rem;
    }
    .chat-message {
        padding: 1rem;
        border-radius: 0.5rem;
        margin-bottom: 1rem;
    }
    .user-message {
        background-color: #e3f2fd;
        margin-left: 2rem;
    }
    .bot-message {
        background-color: #f5f5f5;
        margin-right: 2rem;
    }
    .ticket-card {
        padding: 1rem;
        border: 1px solid #ddd;
        border-radius: 0.5rem;
        margin-bottom: 0.5rem;
    }
    .confidence-high {
        color: #2ecc71;
        font-weight: bold;
    }
    .confidence-medium {
        color: #f39c12;
        font-weight: bold;
    }
    .confidence-low {
        color: #e74c3c;
        font-weight: bold;
    }
    .whatsapp-button {
        background-color: #25D366;
        color: white;
        padding: 10px 20px;
        border-radius: 5px;
        text-decoration: none;
        display: inline-block;
        margin: 5px;
    }
</style>
""", unsafe_allow_html=True)

# Database setup
def init_database():
    """Initialize SQLite database for persistence"""
    conn = sqlite3.connect('support_agent.db', check_same_thread=False)
    c = conn.cursor()
    
    # Chat history table
    c.execute('''CREATE TABLE IF NOT EXISTS chat_history
                 (id TEXT PRIMARY KEY, role TEXT, message TEXT, timestamp TEXT, 
                  confidence REAL, response_time REAL, language TEXT, category TEXT)''')
    
    # Tickets table
    c.execute('''CREATE TABLE IF NOT EXISTS tickets
                 (id TEXT PRIMARY KEY, query TEXT, language TEXT, category TEXT, 
                  status TEXT, priority TEXT, assigned_to TEXT, timestamp TEXT, 
                  resolved_at TEXT, resolution_time REAL)''')
    
    # Feedback table
    c.execute('''CREATE TABLE IF NOT EXISTS feedback
                 (chat_id TEXT, feedback TEXT, timestamp TEXT)''')
    
    # Analytics table
    c.execute('''CREATE TABLE IF NOT EXISTS analytics
                 (date TEXT, total_queries INTEGER, answered INTEGER, escalated INTEGER,
                  avg_response_time REAL, avg_confidence REAL)''')
    
    conn.commit()
    return conn

# Initialize database
if 'db_conn' not in st.session_state:
    st.session_state.db_conn = init_database()

# Initialize session state
if 'chat_history' not in st.session_state:
    st.session_state.chat_history = []
if 'tickets' not in st.session_state:
    st.session_state.tickets = []
if 'analytics' not in st.session_state:
    st.session_state.analytics = {
        'total_queries': 0,
        'answered': 0,
        'escalated': 0,
        'languages': {'English': 0, 'Hindi': 0, 'Marathi': 0, 'Other': 0},
        'categories': {'Billing': 0, 'Technical': 0, 'General': 0}
    }
if 'vector_store' not in st.session_state:
    st.session_state.vector_store = None
if 'knowledge_base_text' not in st.session_state:
    st.session_state.knowledge_base_text = ""
if 'feedback' not in st.session_state:
    st.session_state.feedback = {}
if 'embeddings_model' not in st.session_state:
    st.session_state.embeddings_model = None
if 'channel_stats' not in st.session_state:
    st.session_state.channel_stats = {
        'Website': 0,
        'WhatsApp': 0,
        'Email': 0,
        'Manual': 0
    }
if 'email_queue' not in st.session_state:
    st.session_state.email_queue = []
if 'whatsapp_messages' not in st.session_state:
    st.session_state.whatsapp_messages = []
if 'gmail_config' not in st.session_state:
    st.session_state.gmail_config = {
        'email': 'Callistoitsolutions1@gmail.com',
        'smtp_server': 'smtp.gmail.com',
        'smtp_port': 587,
        'imap_server': 'imap.gmail.com'
    }
if 'whatsapp_config' not in st.session_state:
    st.session_state.whatsapp_config = {
        'phone_number': '+917057205423',
        'wa_link': 'https://wa.me/917057205423'
    }

# Helper Functions
def extract_text_from_pdf(file) -> str:
    """Extract text from PDF file"""
    try:
        pdf_reader = PyPDF2.PdfReader(file)
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text() + "\n"
        return text
    except Exception as e:
        st.error(f"Error reading PDF: {str(e)}")
        return ""

def extract_text_from_docx(file) -> str:
    """Extract text from DOCX file"""
    try:
        doc = Document(file)
        text = "\n".join([paragraph.text for paragraph in doc.paragraphs])
        return text
    except Exception as e:
        st.error(f"Error reading DOCX: {str(e)}")
        return ""

def extract_text_from_excel(file) -> str:
    """Extract text from Excel file (XLSX/XLS)"""
    try:
        wb = load_workbook(file, read_only=True, data_only=True)
        text = ""
        
        for sheet_name in wb.sheetnames:
            sheet = wb[sheet_name]
            text += f"\n[Sheet: {sheet_name}]\n"
            
            for row in sheet.iter_rows(values_only=True):
                row_data = [str(cell) for cell in row if cell is not None]
                if row_data:
                    text += " | ".join(row_data) + "\n"
        
        wb.close()
        return text
    except Exception as e:
        st.error(f"Error reading Excel file: {str(e)}")
        return ""

def extract_text_from_image(image_file) -> str:
    """Extract text from image using OCR"""
    try:
        image = Image.open(image_file)
        text = pytesseract.image_to_string(image)
        return text
    except Exception as e:
        st.error(f"Error performing OCR: {str(e)}")
        return ""

def scrape_url(url: str) -> str:
    """Scrape text content from URL"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        for script in soup(["script", "style"]):
            script.decompose()
        
        text = soup.get_text()
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = '\n'.join(chunk for chunk in chunks if chunk)
        
        return text
    except Exception as e:
        st.error(f"Error scraping URL {url}: {str(e)}")
        return ""

def detect_language(text: str) -> str:
    """Detect language of text"""
    try:
        lang_code = detect(text)
        lang_map = {
            'en': 'English',
            'hi': 'Hindi',
            'mr': 'Marathi'
        }
        return lang_map.get(lang_code, 'Other')
    except:
        return 'English'

def translate_text(text: str, target_lang: str) -> str:
    """Translate text to target language"""
    try:
        if target_lang == 'English':
            return text
        
        lang_code_map = {
            'Hindi': 'hi',
            'Marathi': 'mr'
        }
        
        target_code = lang_code_map.get(target_lang, 'en')
        translator = GoogleTranslator(source='auto', target=target_code)
        translated = translator.translate(text)
        return translated
    except Exception as e:
        st.warning(f"Translation failed: {str(e)}")
        return text

def categorize_query(query: str) -> str:
    """Keyword-based categorization with AI enhancement"""
    query_lower = query.lower()
    
    billing_keywords = ['payment', 'invoice', 'bill', 'charge', 'refund', 'price', 'cost', 
                       'subscription', 'card', 'billing', 'money', 'paid']
    technical_keywords = ['error', 'bug', 'issue', 'problem', 'not working', 'broken', 
                         'crash', 'slow', 'loading', 'login', 'access', 'technical']
    
    billing_score = sum(1 for keyword in billing_keywords if keyword in query_lower)
    technical_score = sum(1 for keyword in technical_keywords if keyword in query_lower)
    
    if billing_score > technical_score and billing_score > 0:
        return 'Billing'
    elif technical_score > 0:
        return 'Technical'
    else:
        return 'General'

def assign_priority(confidence: float, category: str) -> str:
    """Assign priority based on confidence and category"""
    if confidence < 0.4 or category == 'Billing':
        return 'High'
    elif confidence < 0.6 or category == 'Technical':
        return 'Medium'
    else:
        return 'Low'

def create_vector_store(text: str, openai_api_key: str):
    """Create FAISS vector store from text with caching"""
    try:
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            length_function=len
        )
        chunks = text_splitter.split_text(text)
        
        documents = [LangchainDocument(page_content=chunk) for chunk in chunks]
        
        embeddings = OpenAIEmbeddings(openai_api_key=openai_api_key)
        st.session_state.embeddings_model = embeddings
        vector_store = FAISS.from_documents(documents, embeddings)
        
        return vector_store
    except Exception as e:
        st.error(f"Error creating vector store: {str(e)}")
        return None

def calculate_semantic_confidence(query: str, retrieved_docs: List, answer: str, embeddings) -> float:
    """Calculate confidence score using semantic similarity"""
    try:
        query_embedding = embeddings.embed_query(query)
        answer_embedding = embeddings.embed_query(answer)
        
        query_answer_sim = cosine_similarity(
            [query_embedding], 
            [answer_embedding]
        )[0][0]
        
        if retrieved_docs:
            doc_embeddings = [embeddings.embed_query(doc.page_content) for doc in retrieved_docs]
            doc_similarities = cosine_similarity([query_embedding], doc_embeddings)[0]
            avg_doc_sim = np.mean(doc_similarities)
        else:
            avg_doc_sim = 0.0
        
        confidence = (0.4 * query_answer_sim + 0.6 * avg_doc_sim)
        
        if len(answer.split()) < 10:
            confidence *= 0.7
        
        return float(min(max(confidence, 0.0), 1.0))
    except Exception as e:
        st.warning(f"Confidence calculation error: {str(e)}")
        return 0.7 if len(retrieved_docs) > 0 and len(answer) > 50 else 0.4

def get_ai_response(query: str, vector_store, openai_api_key: str, target_language: str = 'English') -> Tuple[str, float, List]:
    """Get AI response using RAG with multilingual support"""
    try:
        english_query = query
        if target_language != 'English':
            try:
                translator = GoogleTranslator(source='auto', target='en')
                english_query = translator.translate(query)
            except:
                pass
        
        llm = ChatOpenAI(
            model_name="gpt-3.5-turbo",
            temperature=0.3,
            openai_api_key=openai_api_key
        )
        
        prompt_template = """You are a helpful customer support assistant. 
        Use the following context to answer the question. If you cannot find the answer in the context, 
        say so politely and suggest contacting support.
        
        Context: {context}
        
        Question: {question}
        
        Provide a helpful, accurate answer:"""
        
        PROMPT = PromptTemplate(
            template=prompt_template,
            input_variables=["context", "question"]
        )
        
        qa_chain = RetrievalQA.from_chain_type(
            llm=llm,
            chain_type="stuff",
            retriever=vector_store.as_retriever(search_kwargs={"k": 4}),
            return_source_documents=True,
            chain_type_kwargs={"prompt": PROMPT}
        )
        
        result = qa_chain({"query": english_query})
        
        answer = result['result']
        source_docs = result['source_documents']
        
        confidence = calculate_semantic_confidence(
            english_query, 
            source_docs, 
            answer, 
            st.session_state.embeddings_model
        )
        
        if target_language != 'English':
            answer = translate_text(answer, target_language)
        
        return answer, confidence, source_docs
    except Exception as e:
        st.error(f"Error getting AI response: {str(e)}")
        error_msg = "I apologize, but I encountered an error processing your query."
        if target_language != 'English':
            error_msg = translate_text(error_msg, target_language)
        return error_msg, 0.3, []

def create_ticket(query: str, language: str, category: str, confidence: float, channel: str = 'Website'):
    """Create escalation ticket with priority and assignment"""
    priority = assign_priority(confidence, category)
    
    agents = ['Agent A', 'Agent B', 'Agent C']
    assigned_to = agents[len(st.session_state.tickets) % len(agents)]
    
    ticket = {
        'id': str(uuid.uuid4())[:8],
        'query': query,
        'language': language,
        'category': category,
        'status': 'Open',
        'priority': priority,
        'assigned_to': assigned_to,
        'channel': channel,
        'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'resolved_at': None,
        'resolution_time': None
    }
    
    st.session_state.tickets.append(ticket)
    st.session_state.analytics['escalated'] += 1
    
    conn = st.session_state.db_conn
    c = conn.cursor()
    c.execute('''INSERT INTO tickets VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
              (ticket['id'], ticket['query'], ticket['language'], ticket['category'],
               ticket['status'], ticket['priority'], ticket['assigned_to'], 
               ticket['timestamp'], ticket['resolved_at'], ticket['resolution_time']))
    conn.commit()
    
    return ticket['id']

def save_chat_to_db(chat_entry: Dict):
    """Save chat entry to database"""
    conn = st.session_state.db_conn
    c = conn.cursor()
    
    chat_id = str(uuid.uuid4())
    c.execute('''INSERT INTO chat_history VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
              (chat_id, chat_entry['role'], chat_entry['message'], 
               chat_entry['timestamp'].strftime("%Y-%m-%d %H:%M:%S"),
               chat_entry.get('confidence', None),
               chat_entry.get('response_time', None),
               chat_entry.get('language', None),
               chat_entry.get('category', None)))
    conn.commit()
    return chat_id

def update_daily_analytics():
    """Update daily analytics in database"""
    try:
        conn = st.session_state.db_conn
        c = conn.cursor()
        
        today = datetime.now().strftime("%Y-%m-%d")
        analytics = st.session_state.analytics
        
        bot_messages = [msg for msg in st.session_state.chat_history if msg.get('role') == 'bot']
        avg_response_time = sum(msg.get('response_time', 0) for msg in bot_messages) / len(bot_messages) if bot_messages else 0
        avg_confidence = sum(msg.get('confidence', 0) for msg in bot_messages) / len(bot_messages) if bot_messages else 0
        
        c.execute('''INSERT OR REPLACE INTO analytics VALUES (?, ?, ?, ?, ?, ?)''',
                  (today, analytics.get('total_queries', 0), analytics.get('answered', 0), 
                   analytics.get('escalated', 0), avg_response_time, avg_confidence))
        conn.commit()
    except Exception as e:
        st.error(f"Error updating analytics: {str(e)}")

def send_gmail(to_email: str, subject: str, message: str, app_password: str) -> bool:
    """Send email via Gmail SMTP"""
    try:
        config = st.session_state.gmail_config
        
        msg = MIMEMultipart()
        msg['From'] = config['email']
        msg['To'] = to_email
        msg['Subject'] = subject
        
        msg.attach(MIMEText(message, 'plain'))
        
        server = smtplib.SMTP(config['smtp_server'], config['smtp_port'])
        server.starttls()
        server.login(config['email'], app_password)
        server.send_message(msg)
        server.quit()
        
        return True
    except Exception as e:
        st.error(f"Gmail sending failed: {str(e)}")
        return False

def check_gmail_inbox(app_password: str, max_emails: int = 10) -> List[Dict]:
    """Check Gmail inbox for new emails"""
    try:
        config = st.session_state.gmail_config
        
        mail = imaplib.IMAP4_SSL(config['imap_server'])
        mail.login(config['email'], app_password)
        mail.select('inbox')
        
        _, search_data = mail.search(None, 'UNSEEN')
        email_ids = search_data[0].split()[-max_emails:]
        
        emails = []
        for email_id in email_ids:
            _, data = mail.fetch(email_id, '(RFC822)')
            msg = email.message_from_bytes(data[0][1])
            
            subject = msg['subject']
            from_email = msg['from']
            
            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        body = part.get_payload(decode=True).decode()
                        break
            else:
                body = msg.get_payload(decode=True).decode()
            
            emails.append({
                'id': email_id.decode(),
                'from': from_email,
                'subject': subject,
                'body': body,
                'timestamp': datetime.now()
            })
        
        mail.close()
        mail.logout()
        
        return emails
    except Exception as e:
        st.error(f"Error checking Gmail: {str(e)}")
        return []

def create_whatsapp_link(phone_number: str, message: str) -> str:
    """Create WhatsApp direct message link"""
    encoded_message = urllib.parse.quote(message)
    phone_clean = phone_number.replace('+', '').replace('-', '').replace(' ', '')
    return f"https://wa.me/{phone_clean}?text={encoded_message}"

def open_whatsapp_chat(message: str = ""):
    """Open WhatsApp chat with pre-filled message"""
    config = st.session_state.whatsapp_config
    wa_link = create_whatsapp_link(config['phone_number'], message)
    return wa_link

def process_multi_channel_query(query: str, channel: str, openai_api_key: str, 
                                contact_info: dict = None) -> tuple:
    """Process query from any channel and route appropriately"""
    
    if not st.session_state.vector_store:
        return "Knowledge base not loaded. Please upload documents first.", 0.3, None
    
    language = detect_language(query)
    category = categorize_query(query)
    
    st.session_state.channel_stats[channel] = st.session_state.channel_stats.get(channel, 0) + 1
    
    answer, confidence, source_docs = get_ai_response(
        query, 
        st.session_state.vector_store, 
        openai_api_key,
        language
    )
    
    ticket_id = None
    if confidence < 0.6:
        ticket_id = create_ticket(query, language, category, confidence, channel)
        escalation_msg = f"\n\n⚠️ This query has been escalated. Ticket ID: {ticket_id}"
        if language != 'English':
            escalation_msg = translate_text(escalation_msg, language)
        answer += escalation_msg
    
    return answer, confidence, ticket_id

# Sidebar - Knowledge Management
st.sidebar.title("📚 Knowledge Base Management")

openai_api_key = st.sidebar.text_input("OpenAI API Key", type="password", help="Enter your OpenAI API key")

st.sidebar.markdown("---")

uploaded_files = st.sidebar.file_uploader(
    "Upload PDF/DOCX/Excel/Image files",
    type=['pdf', 'docx', 'xlsx', 'xls', 'png', 'jpg', 'jpeg'],
    accept_multiple_files=True
)

url_input = st.sidebar.text_area("Enter URLs (one per line)", height=100)

if st.sidebar.button("🔄 Process Knowledge Base", type="primary"):
    if not openai_api_key:
        st.sidebar.error("Please enter your OpenAI API key first!")
    else:
        with st.spinner("Processing knowledge base..."):
            all_text = ""
            
            if uploaded_files:
                progress_bar = st.sidebar.progress(0)
                for idx, file in enumerate(uploaded_files):
                    if file.name.endswith('.pdf'):
                        all_text += extract_text_from_pdf(file) + "\n\n"
                    elif file.name.endswith('.docx'):
                        all_text += extract_text_from_docx(file) + "\n\n"
                    elif file.name.endswith(('.xlsx', '.xls')):
                        excel_text = extract_text_from_excel(file)
                        if excel_text:
                            all_text += f"[Excel file: {file.name}]\n{excel_text}\n\n"
                    elif file.name.lower().endswith(('.png', '.jpg', '.jpeg')):
                        ocr_text = extract_text_from_image(file)
                        if ocr_text:
                            all_text += f"[OCR from {file.name}]\n{ocr_text}\n\n"
                    
                    progress_bar.progress((idx + 1) / len(uploaded_files))
                progress_bar.empty()
            
            if url_input.strip():
                urls = [url.strip() for url in url_input.split('\n') if url.strip()]
                progress_bar = st.sidebar.progress(0)
                for idx, url in enumerate(urls):
                    st.sidebar.info(f"Scraping: {url[:50]}...")
                    scraped_text = scrape_url(url)
                    if scraped_text:
                        all_text += f"[Content from {url}]\n{scraped_text}\n\n"
                    progress_bar.progress((idx + 1) / len(urls))
                progress_bar.empty()
            
            if all_text.strip():
                st.session_state.knowledge_base_text = all_text
                st.session_state.vector_store = create_vector_store(all_text, openai_api_key)
                
                if st.session_state.vector_store:
                    st.sidebar.success(f"✅ Processed {len(all_text)} characters successfully!")
                else:
                    st.sidebar.error("Failed to create vector store")
            else:
                st.sidebar.warning("No content to process. Please upload files or enter URLs.")

if st.session_state.vector_store:
    st.sidebar.success("✅ Knowledge Base Active")
    st.sidebar.metric("KB Size", f"{len(st.session_state.knowledge_base_text):,} chars")
    
    num_docs = st.session_state.vector_store.index.ntotal if st.session_state.vector_store else 0
    st.sidebar.metric("Indexed Documents", num_docs)
else:
    st.sidebar.info("ℹ️ No knowledge base loaded")

st.sidebar.markdown("---")
st.sidebar.caption("💡 Supports: PDF, DOCX, Excel (XLSX/XLS), Images (OCR), Web URLs")

# Main page
st.markdown('<div class="main-header">🤖 Multi-Channel Customer Support AI Agent</div>', unsafe_allow_html=True)

# Quick Contact Banner
st.markdown(f"""
<div style='background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 20px; border-radius: 10px; margin-bottom: 20px;'>
    <h3 style='color: white; text-align: center; margin-bottom: 15px;'>📞 Contact Us Directly</h3>
    <div style='display: flex; justify-content: center; gap: 20px; flex-wrap: wrap;'>
        <div style='background: white; padding: 15px; border-radius: 8px; text-align: center; min-width: 250px;'>
            <h4 style='margin-top: 0;'>📧 Email Support</h4>
            <p style='color: #555; font-size: 14px; margin: 10px 0;'>{st.session_state.gmail_config['email']}</p>
        </div>
        <div style='background: white; padding: 15px; border-radius: 8px; text-align: center; min-width: 250px;'>
            <h4 style='margin-top: 0;'>💬 WhatsApp Support</h4>
            <p style='color: #555; font-size: 14px; margin: 10px 0;'>{st.session_state.whatsapp_config['phone_number']}</p>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

# Channel Overview
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("🌐 Website", st.session_state.channel_stats.get('Website', 0))
with col2:
    st.metric("💬 WhatsApp", st.session_state.channel_stats.get('WhatsApp', 0))
with col3:
    st.metric("📧 Email", st.session_state.channel_stats.get('Email', 0))
with col4:
    st.metric("👤 Manual", st.session_state.channel_stats.get('Manual', 0))

st.markdown("---")

# Tabs
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "💬 Website Chat", 
    "📱 WhatsApp Support", 
    "📧 Gmail Management",
    "🎫 Ticket Management", 
    "📊 Analytics Dashboard"
])

# Tab 1: Website Chat Agent
with tab1:
    st.header("Website Chat Interface")
    st.caption("🌐 Customers chat directly on your website")
    
    if not st.session_state.vector_store:
        st.info("ℹ️ Please upload and process knowledge base files in the sidebar first.")
    elif not openai_api_key:
        st.warning("⚠️ Please enter your OpenAI API key in the sidebar.")
    else:
        chat_container = st.container()
        
        with chat_container:
            for i, chat in enumerate(st.session_state.chat_history):
                if chat['role'] == 'user':
                    st.markdown(f'<div class="chat-message user-message">👤 **You:** {chat["message"]}</div>', unsafe_allow_html=True)
                else:
                    confidence = chat.get('confidence', 0)
                    if confidence >= 0.7:
                        conf_class = "confidence-high"
                        conf_emoji = "🟢"
                    elif confidence >= 0.5:
                        conf_class = "confidence-medium"
                        conf_emoji = "🟡"
                    else:
                        conf_class = "confidence-low"
                        conf_emoji = "🔴"
                    
                    response_time = chat.get('response_time', 0)
                    
                    st.markdown(
                        f'<div class="chat-message bot-message">'
                        f'🤖 **AI:** {chat["message"]}<br>'
                        f'<small>{conf_emoji} Confidence: <span class="{conf_class}">{confidence:.1%}</span> | '
                        f'⏱️ {response_time:.2f}s</small>'
                        f'</div>', 
                        unsafe_allow_html=True
                    )
                    
                    if i not in st.session_state.feedback:
                        col1, col2, col3 = st.columns([1, 1, 10])
                        with col1:
                            if st.button("👍", key=f"up_{i}"):
                                st.session_state.feedback[i] = 'positive'
                                st.rerun()
                        with col2:
                            if st.button("👎", key=f"down_{i}"):
                                st.session_state.feedback[i] = 'negative'
                                st.rerun()
                    else:
                        if st.session_state.feedback[i] == 'positive':
                            st.success("✓ Marked as helpful")
                        else:
                            st.error("✗ Marked as not helpful")
        
        with st.form(key="chat_form", clear_on_submit=True):
            col1, col2 = st.columns([4, 1])
            with col1:
                user_input = st.text_input("Ask your question:", placeholder="Type your question here...")
            with col2:
                submit_button = st.form_submit_button("Send 🚀", use_container_width=True)
        
        if submit_button and user_input:
            start_time = time.time()
            
            language = detect_language(user_input)
            category = categorize_query(user_input)
            
            st.session_state.analytics['total_queries'] += 1
            st.session_state.analytics['languages'][language] = st.session_state.analytics['languages'].get(language, 0) + 1
            st.session_state.analytics['categories'][category] += 1
            st.session_state.channel_stats['Website'] += 1
            
            user_chat = {
                'role': 'user',
                'message': user_input,
                'timestamp': datetime.now(),
                'language': language,
                'category': category
            }
            st.session_state.chat_history.append(user_chat)
            save_chat_to_db(user_chat)
            
            with st.spinner(f"Thinking... ({language} detected)"):
                answer, confidence, source_docs = get_ai_response(
                    user_input, 
                    st.session_state.vector_store, 
                    openai_api_key,
                    language
                )
            
            response_time = time.time() - start_time
            
            if confidence < 0.6:
                ticket_id = create_ticket(user_input, language, category, confidence, 'Website')
                escalation_msg = f"\n\n⚠️ **Note:** Your query has been escalated to our support team. Ticket ID: `{ticket_id}` | Priority: {assign_priority(confidence, category)}"
                if language != 'English':
                    escalation_msg = translate_text(escalation_msg, language)
                answer += escalation_msg
            else:
                st.session_state.analytics['answered'] += 1
            
            bot_chat = {
                'role': 'bot',
                'message': answer,
                'timestamp': datetime.now(),
                'confidence': confidence,
                'response_time': response_time,
                'language': language,
                'category': category
            }
            st.session_state.chat_history.append(bot_chat)
            save_chat_to_db(bot_chat)
            
            update_daily_analytics()
            
            st.rerun()

# Tab 2: WhatsApp Support
with tab2:
    st.header("📱 WhatsApp Support Integration")
    st.caption(f"Connected to: {st.session_state.whatsapp_config['phone_number']}")
    
    st.markdown("---")
    
    # Quick WhatsApp Link
    st.subheader("🚀 Quick Chat Link")
    st.info("💡 Click the button below to open WhatsApp chat with our support number")
    
    col1, col2 = st.columns([2, 1])
    with col1:
        quick_message = st.text_input(
            "Pre-fill message (optional)", 
            placeholder="Hello, I need help with..."
        )
    with col2:
        st.write("")
        st.write("")
        wa_link = open_whatsapp_chat(quick_message if quick_message else "Hello, I need support!")
        st.markdown(f'<a href="{wa_link}" target="_blank" class="whatsapp-button">💬 Open WhatsApp Chat</a>', 
                   unsafe_allow_html=True)
    
    st.markdown("---")
    
    # Process incoming WhatsApp message simulation
    st.subheader("📥 Process WhatsApp Queries (AI Auto-Response)")
    
    with st.form("whatsapp_form"):
        col1, col2 = st.columns([3, 1])
        with col1:
            wa_message = st.text_area("Customer WhatsApp Message", placeholder="Customer query here...", height=100)
        with col2:
            wa_phone = st.text_input("Customer Phone", placeholder="+91XXXXXXXXXX")
        
        process_wa = st.form_submit_button("🤖 Generate AI Response", type="primary")
    
    if process_wa and wa_message and openai_api_key and st.session_state.vector_store:
        with st.spinner("Processing WhatsApp message..."):
            answer, confidence, ticket_id = process_multi_channel_query(
                wa_message, 
                'WhatsApp', 
                openai_api_key
            )
            
            st.success("✅ AI Response Generated!")
            
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("**📨 Customer Message:**")
                st.info(wa_message)
            with col2:
                st.markdown("**🤖 AI Response:**")
                st.success(answer)
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Confidence", f"{confidence:.1%}")
            with col2:
                st.metric("Status", "Escalated" if ticket_id else "Resolved")
            with col3:
                if ticket_id:
                    st.metric("Ticket ID", ticket_id)
            
            # Create WhatsApp send link
            st.markdown("---")
            st.subheader("📤 Send Response via WhatsApp")
            
            if wa_phone:
                send_link = create_whatsapp_link(wa_phone, answer)
                st.markdown(f'<a href="{send_link}" target="_blank" class="whatsapp-button">💬 Send Response to Customer</a>', 
                           unsafe_allow_html=True)
            else:
                st.warning("Enter customer phone number to generate send link")
            
            st.session_state.whatsapp_messages.append({
                'message': wa_message,
                'response': answer,
                'confidence': confidence,
                'ticket_id': ticket_id,
                'phone': wa_phone,
                'timestamp': datetime.now()
            })
    
    # Recent WhatsApp interactions
    if st.session_state.whatsapp_messages:
        st.markdown("---")
        st.subheader("📋 Recent WhatsApp Interactions")
        
        for idx, msg in enumerate(reversed(st.session_state.whatsapp_messages[-10:])):
            with st.expander(f"💬 {msg['timestamp'].strftime('%Y-%m-%d %H:%M')} - Confidence: {msg['confidence']:.1%}"):
                st.write(f"**Phone:** {msg.get('phone', 'N/A')}")
                st.write(f"**Customer:** {msg['message']}")
                st.write(f"**AI Response:** {msg['response']}")
                if msg['ticket_id']:
                    st.warning(f"Escalated - Ticket: {msg['ticket_id']}")
                
                # Quick resend option
                if msg.get('phone'):
                    resend_link = create_whatsapp_link(msg['phone'], msg['response'])
                    st.markdown(f'<a href="{resend_link}" target="_blank">📤 Resend This Response</a>', 
                               unsafe_allow_html=True)

# Tab 3: Gmail Management
with tab3:
    st.header("📧 Gmail Auto-Response System")
    st.caption(f"Connected to: {st.session_state.gmail_config['email']}")
    
    # Gmail App Password Configuration
    with st.expander("⚙️ Gmail Configuration", expanded=False):
        st.info("""
        **How to setup:**
        1. Go to your Google Account settings
        2. Enable 2-Step Verification
        3. Generate an App Password for 'Mail'
        4. Enter the 16-character app password below
        """)
        gmail_app_password = st.text_input("Gmail App Password", type="password", key="gmail_pwd")
        
        if gmail_app_password:
            st.success("✅ Gmail credentials configured")
    
    st.markdown("---")
    
    # Check Inbox
    st.subheader("📬 Check Gmail Inbox")
    
    col1, col2 = st.columns([3, 1])
    with col1:
        max_emails = st.slider("Number of recent emails to check", 1, 20, 10)
    with col2:
        st.write("")
        st.write("")
        check_inbox = st.button("🔄 Check Inbox", type="primary")
    
    if check_inbox and gmail_app_password:
        with st.spinner("Checking Gmail inbox..."):
            new_emails = check_gmail_inbox(gmail_app_password, max_emails)
            
            if new_emails:
                st.success(f"✅ Found {len(new_emails)} unread email(s)")
                
                for email_data in new_emails:
                    with st.expander(f"📧 From: {email_data['from']} - {email_data['subject']}"):
                        st.write(f"**Subject:** {email_data['subject']}")
                        st.write(f"**From:** {email_data['from']}")
                        st.write(f"**Body:**\n{email_data['body'][:500]}...")
                        
                        if st.button(f"🤖 Generate AI Response", key=f"respond_{email_data['id']}"):
                            with st.spinner("Generating response..."):
                                answer, confidence, ticket_id = process_multi_channel_query(
                                    email_data['body'], 
                                    'Email', 
                                    openai_api_key
                                )
                                
                                st.success("Response generated!")
                                st.write(answer)
                                
                                # Add to queue
                                st.session_state.email_queue.append({
                                    'from': email_data['from'],
                                    'subject': email_data['subject'],
                                    'body': email_data['body'],
                                    'response': answer,
                                    'confidence': confidence,
                                    'ticket_id': ticket_id,
                                    'timestamp': datetime.now(),
                                    'sent': False
                                })
            else:
                st.info("No new unread emails found")
    
    st.markdown("---")
    
    # Manual Email Response
    st.subheader("✍️ Compose & Send Email Response")
    
    with st.form("email_form"):
        customer_email = st.text_input("Customer Email", placeholder="customer@example.com")
        email_subject = st.text_input("Email Subject", placeholder="Re: Your inquiry")
        email_body = st.text_area("Customer's Email Message", placeholder="Customer query...", height=150)
        
        process_email = st.form_submit_button("🤖 Generate AI Response", type="primary")
    
    if process_email and email_body and openai_api_key and st.session_state.vector_store:
        with st.spinner("Processing email..."):
            answer, confidence, ticket_id = process_multi_channel_query(
                email_body, 
                'Email', 
                openai_api_key
            )
            
            email_response = f"""Dear Customer,

Thank you for contacting us. Here's the response to your inquiry:

{answer}

Best regards,
AI Support Team
{st.session_state.gmail_config['email']}

---
This is an automated response. If you need further assistance, please reply to this email.
"""
            
            if ticket_id:
                email_response += f"\n\nYour ticket ID: {ticket_id}"
            
            st.success("✅ Email Response Generated!")
            
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("**📨 Customer Email:**")
                st.info(email_body)
            with col2:
                st.markdown("**🤖 AI Response:**")
                st.success(answer)
            
            st.markdown("**📧 Full Email Response:**")
            st.code(email_response, language="text")
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Confidence", f"{confidence:.1%}")
            with col2:
                st.metric("Status", "Escalated" if ticket_id else "Resolved")
            with col3:
                if ticket_id:
                    st.metric("Ticket ID", ticket_id)
            
            # Send email
            if gmail_app_password and customer_email:
                if st.button("📤 Send Email Now", type="primary", key="send_now"):
                    response_subject = f"Re: {email_subject}" if email_subject else "Response to your inquiry"
                    
                    if send_gmail(customer_email, response_subject, email_response, gmail_app_password):
                        st.success("✅ Email sent successfully!")
                        st.balloons()
            else:
                st.info("💡 Configure Gmail App Password above to enable email sending")
            
            st.session_state.email_queue.append({
                'from': customer_email,
                'subject': email_subject,
                'body': email_body,
                'response': answer,
                'confidence': confidence,
                'ticket_id': ticket_id,
                'timestamp': datetime.now(),
                'sent': False
            })
    
    # Email Queue
    if st.session_state.email_queue:
        st.markdown("---")
        st.subheader("📬 Email Queue")
        
        email_df = pd.DataFrame([
            {
                'Time': email['timestamp'].strftime('%Y-%m-%d %H:%M'),
                'From': email['from'],
                'Subject': email['subject'][:50] + '...' if len(email['subject']) > 50 else email['subject'],
                'Confidence': f"{email['confidence']:.1%}",
                'Status': 'Escalated' if email['ticket_id'] else 'Resolved',
                'Sent': '✅' if email.get('sent') else '⏳'
            }
            for email in reversed(st.session_state.email_queue[-20:])
        ])
        
        st.dataframe(email_df, use_container_width=True, hide_index=True)

# Tab 4: Ticket Management
with tab4:
    st.header("🎫 Escalated Tickets")
    
    if st.session_state.tickets:
        col1, col2, col3 = st.columns(3)
        with col1:
            status_filter = st.multiselect(
                "Filter by Status",
                options=['Open', 'In Progress', 'Closed'],
                default=['Open', 'In Progress']
            )
        with col2:
            priority_filter = st.multiselect(
                "Filter by Priority",
                options=['High', 'Medium', 'Low'],
                default=['High', 'Medium', 'Low']
            )
        with col3:
            category_filter = st.multiselect(
                "Filter by Category",
                options=['Billing', 'Technical', 'General'],
                default=['Billing', 'Technical', 'General']
            )
        
        df_tickets = pd.DataFrame(st.session_state.tickets)
        
        filtered_df = df_tickets[
            (df_tickets['status'].isin(status_filter)) &
            (df_tickets['priority'].isin(priority_filter)) &
            (df_tickets['category'].isin(category_filter))
        ]
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Tickets", len(df_tickets))
        with col2:
            st.metric("Open", len(df_tickets[df_tickets['status'] == 'Open']))
        with col3:
            st.metric("High Priority", len(df_tickets[df_tickets['priority'] == 'High']))
        with col4:
            avg_resolution = df_tickets[df_tickets['resolution_time'].notna()]['resolution_time'].mean()
            st.metric("Avg Resolution Time", f"{avg_resolution:.1f}h" if not pd.isna(avg_resolution) else "N/A")
        
        st.markdown("---")
        
        for idx, ticket in filtered_df.iterrows():
            priority_color = {'High': '🔴', 'Medium': '🟡', 'Low': '🟢'}
            
            with st.expander(f"{priority_color[ticket['priority']]} Ticket #{ticket['id']} - {ticket['status']} ({ticket['priority']} Priority)"):
                col1, col2 = st.columns(2)
                with col1:
                    st.write(f"**Query:** {ticket['query']}")
                    st.write(f"**Category:** {ticket['category']}")
                    st.write(f"**Language:** {ticket['language']}")
                    st.write(f"**Channel:** {ticket['channel']}")
                with col2:
                    st.write(f"**Assigned To:** {ticket['assigned_to']}")
                    st.write(f"**Created:** {ticket['timestamp']}")
                    if ticket['resolved_at']:
                        st.write(f"**Resolved:** {ticket['resolved_at']}")
                        st.write(f"**Resolution Time:** {ticket['resolution_time']:.1f}h")
                
                col1, col2, col3 = st.columns([2, 2, 1])
                with col1:
                    new_status = st.selectbox(
                        "Update Status",
                        options=['Open', 'In Progress', 'Closed'],
                        index=['Open', 'In Progress', 'Closed'].index(ticket['status']),
                        key=f"status_{ticket['id']}"
                    )
                with col2:
                    new_assignee = st.selectbox(
                        "Reassign To",
                        options=['Agent A', 'Agent B', 'Agent C'],
                        index=['Agent A', 'Agent B', 'Agent C'].index(ticket['assigned_to']),
                        key=f"assign_{ticket['id']}"
                    )
                with col3:
                    st.write("")
                    st.write("")
                    if st.button("Update", key=f"update_{ticket['id']}", type="primary"):
                        if new_status == 'Closed' and ticket['status'] != 'Closed':
                            created = datetime.strptime(ticket['timestamp'], "%Y-%m-%d %H:%M:%S")
                            resolution_time = (datetime.now() - created).total_seconds() / 3600
                            st.session_state.tickets[idx]['resolved_at'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            st.session_state.tickets[idx]['resolution_time'] = resolution_time
                        
                        st.session_state.tickets[idx]['status'] = new_status
                        st.session_state.tickets[idx]['assigned_to'] = new_assignee
                        st.success(f"Ticket #{ticket['id']} updated!")
                        st.rerun()
    else:
        st.info("No escalated tickets yet.")

# Tab 5: Analytics Dashboard
with tab5:
    st.header("📊 Analytics Dashboard")
    
    analytics = st.session_state.analytics
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Queries", analytics.get('total_queries', 0))
    with col2:
        st.metric("Answered", analytics.get('answered', 0))
    with col3:
        st.metric("Escalated", analytics.get('escalated', 0))
    with col4:
        total = analytics.get('total_queries', 0)
        answered = analytics.get('answered', 0)
        resolution_rate = (answered / total * 100) if total > 0 else 0
        st.metric("Resolution Rate", f"{resolution_rate:.1f}%")
    
    st.markdown("---")
    
    if st.session_state.chat_history:
        st.subheader("📈 Query Trends")
        
        chat_df = pd.DataFrame([
            {
                'timestamp': chat['timestamp'],
                'role': chat['role'],
                'confidence': chat.get('confidence', None),
                'response_time': chat.get('response_time', None)
            }
            for chat in st.session_state.chat_history
        ])
        
        chat_df['hour'] = pd.to_datetime(chat_df['timestamp']).dt.floor('H')
        hourly_queries = chat_df[chat_df['role'] == 'user'].groupby('hour').size().reset_index(name='queries')
        
        if len(hourly_queries) > 0:
            fig_timeline = px.line(
                hourly_queries,
                x='hour',
                y='queries',
                title="Queries Over Time",
                labels={'hour': 'Time', 'queries': 'Number of Queries'}
            )
            st.plotly_chart(fig_timeline, use_container_width=True)
    
    st.markdown("---")
    
    col1, col2 = st.columns(2)
    
    with col1:
        answered = analytics.get('answered', 0)
        escalated = analytics.get('escalated', 0)
        
        fig_queries = go.Figure(data=[
            go.Bar(
                x=['Answered', 'Escalated'],
                y=[answered, escalated],
                marker_color=['#2ecc71', '#e74c3c'],
                text=[answered, escalated],
                textposition='auto'
            )
        ])
        fig_queries.update_layout(
            title="Query Distribution",
            xaxis_title="Status",
            yaxis_title="Count",
            height=300
        )
        st.plotly_chart(fig_queries, use_container_width=True)
    
    with col2:
        channel_data = {k: v for k, v in st.session_state.channel_stats.items() if v > 0}
        if channel_data:
            fig_channel = px.pie(
                values=list(channel_data.values()),
                names=list(channel_data.keys()),
                title="Queries by Channel"
            )
            fig_channel.update_layout(height=300)
            st.plotly_chart(fig_channel, use_container_width=True)
        else:
            st.info("No channel data available yet")
    
    st.markdown("---")
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Category Breakdown")
        categories = analytics.get('categories', {'Billing': 0, 'Technical': 0, 'General': 0})
        category_df = pd.DataFrame({
            'Category': list(categories.keys()),
            'Count': list(categories.values())
        })
        
        fig_category = px.bar(
            category_df,
            x='Category',
            y='Count',
            color='Category',
            title="Queries by Category"
        )
        st.plotly_chart(fig_category, use_container_width=True)
    
    with col2:
        st.subheader("Performance Metrics")
        bot_messages = [msg for msg in st.session_state.chat_history if msg['role'] == 'bot']
        
        if bot_messages:
            avg_response_time = sum(msg.get('response_time', 0) for msg in bot_messages) / len(bot_messages)
            avg_confidence = sum(msg.get('confidence', 0) for msg in bot_messages) / len(bot_messages)
            
            perf_metrics = pd.DataFrame({
                'Metric': ['Avg Response Time (s)', 'Avg Confidence Score'],
                'Value': [avg_response_time, avg_confidence]
            })
            
            fig_perf = go.Figure(data=[
                go.Bar(
                    x=perf_metrics['Metric'],
                    y=perf_metrics['Value'],
                    marker_color=['#3498db', '#9b59b6'],
                    text=[f"{avg_response_time:.2f}s", f"{avg_confidence:.1%}"],
                    textposition='auto'
                )
            ])
            fig_perf.update_layout(
                title="Average Performance",
                height=300,
                yaxis_title="Value"
            )
            st.plotly_chart(fig_perf, use_container_width=True)
        else:
            st.info("No performance data available yet")

# Footer
st.markdown("---")
st.markdown(f"""
<div style='text-align: center; color: #666;'>
    <p><strong>Multi-Channel AI Customer Support Agent v3.1</strong></p>
    <p>Powered by OpenAI GPT-3.5, LangChain & FAISS</p>
    <p><small>📧 Email: {st.session_state.gmail_config['email']} | 💬 WhatsApp: {st.session_state.whatsapp_config['phone_number']}</small></p>
    <p><small>✅ Features: Website Chat | WhatsApp Integration | Gmail Auto-Response | PDF/DOCX/Excel/Image Processing | 
    Web Scraping | OCR | Multilingual (EN/HI/MR) | Ticket Management | Real-time Analytics</small></p>
</div>
""", unsafe_allow_html=True)

# Export data functionality
with st.sidebar:
    st.markdown("---")
    st.subheader("📥 Export Data")
    
    if st.button("Export Chat History (CSV)"):
        if st.session_state.chat_history:
            df = pd.DataFrame(st.session_state.chat_history)
            csv = df.to_csv(index=False)
            st.download_button(
                "Download CSV",
                csv,
                "chat_history.csv",
                "text/csv"
            )
    
    if st.button("Export Tickets (CSV)"):
        if st.session_state.tickets:
            df = pd.DataFrame(st.session_state.tickets)
            csv = df.to_csv(index=False)
            st.download_button(
                "Download CSV",
                csv,
                "tickets.csv",
                "text/csv"
            )
    
    if st.button("🗑️ Clear All Data"):
        if st.button("⚠️ Confirm Clear", type="primary"):
            st.session_state.chat_history = []
            st.session_state.tickets = []
            st.session_state.analytics = {
                'total_queries': 0,
                'answered': 0,
                'escalated': 0,
                'languages': {'English': 0, 'Hindi': 0, 'Marathi': 0, 'Other': 0},
                'categories': {'Billing': 0, 'Technical': 0, 'General': 0}
            }
            st.session_state.feedback = {}
            
            conn = st.session_state.db_conn
            c = conn.cursor()
            c.execute("DELETE FROM chat_history")
            c.execute("DELETE FROM tickets")
            c.execute("DELETE FROM feedback")
            c.execute("DELETE FROM analytics")
            conn.commit()
            
            st.success("All data cleared!")
            st.rerun()
