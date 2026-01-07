import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib import colors

# ==========================================
# 1. DATABASE MANAGEMENT
# ==========================================

DB_FILE = "clinic_v3.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS patients (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    full_name TEXT NOT NULL,
                    unique_id TEXT UNIQUE
                )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS treatments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    patient_id INTEGER,
                    treatment_type TEXT,
                    treatment_date DATE,
                    subtotal REAL,
                    tax REAL,
                    total REAL,
                    payment_amount REAL,
                    payment_date DATE,
                    FOREIGN KEY(patient_id) REFERENCES patients(id)
                )''')

    c.execute('''CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )''')
    
    defaults = {
        "clinic_name": "My Health Clinic",
        "clinic_address": "123 Wellness Blvd, City, ON",
        "clinic_phone": "(555) 123-4567",
        "hst_number": "123456789 RT0001",
        "receipt_footer": "Thank you for your business!"
    }
    
    for key, val in defaults.items():
        c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, val))

    conn.commit()
    conn.close()

def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def get_setting(key):
    conn = get_db_connection()
    val = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    conn.close()
    return val['value'] if val else ""

def update_setting(key, value):
    conn = get_db_connection()
    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()

# ==========================================
# 2. PDF GENERATOR (MULTI-ITEM SUPPORT)
# ==========================================

def generate_pdf(patient_name, date_range_str, records):
    """
    records: A list of dictionaries/rows containing treatment details
    """
    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    
    # Settings
    clinic_name = get_setting("clinic_name")
    address = get_setting("clinic_address")
    phone = get_setting("clinic_phone")
    hst_num = get_setting("hst_number")
    footer_text = get_setting("receipt_footer")

    # --- Header ---
    p.setFont("Helvetica-Bold", 20)
    p.drawString(50, height - 50, clinic_name)
    p.setFont("Helvetica", 10)
    p.drawString(50, height - 70, address)
    p.drawString(50, height - 85, f"Phone: {phone}")
    p.drawString(50, height - 100, f"HST #: {hst_num}")
    p.line(50, height - 110, width - 50, height - 110)

    # --- Info ---
    p.setFont("Helvetica-Bold", 14)
    p.drawString(50, height - 150, "STATEMENT / RECEIPT")
    p.setFont("Helvetica", 12)
    p.drawString(50, height - 175, f"Patient: {patient_name}")
    p.drawString(50, height - 195, f"Period: {date_range_str}")

    # --- Table Headers ---
    y = height - 240
    p.setFont("Helvetica-Bold", 10)
    p.drawString(50, y, "Date")
    p.drawString(130, y, "Description")
    p.drawString(350, y, "Cost")
    p.drawString(420, y, "Paid")
    p.drawString(490, y, "Balance")
    p.line(50, y - 5, width - 50, y - 5)
    
    y -= 25
    p.setFont("Helvetica", 10)

    # --- Loop Items ---
    total_cost = 0
    total_paid = 0

    for item in records:
        # Check for page overflow
        if y < 100:
            p.showPage()
            y = height - 50
        
        # Calculate item balance
        item_bal = item['total'] - item['payment_amount']
        
        p.drawString(50, y, str(item['treatment_date']))
        p.drawString(130, y, str(item['treatment_type']))
        p.drawString(350, y, f"{item['total']:.2f}")
        p.drawString(420, y, f"{item['payment_amount']:.2f}")
        
        # Color code item balance
        if item_bal > 0.01:
            p.setFillColor(colors.red)
        elif item_bal < -0.01:
            p.setFillColor(colors.green) # Or yellow logic, but standard ledger usually green/black
        p.drawString(490, y, f"{item_bal:.2f}")
        p.setFillColor(colors.black)
        
        total_cost += item['total']
        total_paid += item['payment_amount']
        y -= 20

    # --- Summary Box ---
    y -= 20
    p.line(50, y, width - 50, y)
    y -= 30
    
    grand_balance = total_cost - total_paid
    
    p.setFont("Helvetica-Bold", 12)
    p.drawString(300, y, "Total Billed:")
    p.drawString(450, y, f"${total_cost:.2f}")
    
    y -= 20
    p.drawString(300, y, "Total Paid:")
    p.drawString(450, y, f"${total_paid:.2f}")
    
    y -= 25
    p.setFont("Helvetica-Bold", 14)
    p.drawString(300, y, "BALANCE DUE:")
    
    if grand_balance > 0.01:
        p.setFillColor(colors.red)
    elif grand_balance < -0.01:
        p.setFillColor(colors.orange) # Credit
    else:
        p.setFillColor(colors.green)
        
    p.drawString(450, y, f"${grand_balance:.2f}")

    # --- Footer ---
    p.setFillColor(colors.black)
    p.setFont("Helvetica-Oblique", 10)
    p.drawCentredString(width / 2, 50, footer_text)

    p.showPage()
    p.save()
    buffer.seek(0)
    return buffer

# ==========================================
# 3. UI
# ==========================================

def main():
    st.set_page_config(page_title="Clinic Manager", page_icon="🏥", layout="wide")
    init_db()

    st.sidebar.title("Navigation")
    page = st.sidebar.radio("Go to:", ["New Treatment", "Patient Records", "Settings"])

    # --- NEW TREATMENT PAGE ---
    if page == "New Treatment":
        st.header("📝 New Treatment Entry")
        col1, col2 = st.columns(2)

        with col1:
            st.subheader("1. Patient")
            conn = get_db_connection()
            patients_df = pd.read_sql("SELECT * FROM patients", conn)
            conn.close()

            tab_exist, tab_new = st.tabs(["Existing Patient", "Register New"])
            selected_patient_id = None
            
            with tab_exist:
                if not patients_df.empty:
                    patients_df['display'] = patients_df['full_name'] + " (ID: " + patients_df['unique_id'] + ")"
                    selected_patient_str = st.selectbox("Search Patient", patients_df['display'])
                    selected_patient_id = patients_df.loc[patients_df['display'] == selected_patient_str, 'id'].values[0]
                else:
                    st.info("No patients found.")

            with tab_new:
                new_name = st.text_input("Full Name")
                new_id = st.text_input("Patient ID (Unique)")
                if st.button("Register Patient"):
                    try:
                        conn = get_db_connection()
                        conn.execute("INSERT INTO patients (full_name, unique_id) VALUES (?, ?)", (new_name, new_id))
                        conn.commit()
                        conn.close()
                        st.success(f"Registered {new_name}!")
                        st.rerun()
                    except sqlite3.IntegrityError:
                        st.error("Patient ID already exists.")

        with col2:
            st.subheader("2. Treatment Details")
            treatment_type = st.selectbox("Service Type", ["Magnetic Field Therapy", "Helium Neon Laser"])
            treatment_date = st.date_input("Date of Service", datetime.now())

            cost = 25.00
            hst = cost * 0.13
            total = cost + hst

            st.markdown(f"**Total Cost:** :green[**${total:.2f}**]")
            st.divider()
            
            st.write(" **Payment Status**")
            is_paid = st.checkbox("Payment Received?", value=True)
            
            payment_amount = 0.0
            payment_date = None

            if is_paid:
                payment_date = st.date_input("Payment Date", datetime.now())
                payment_amount = st.number_input("Amount Paid ($)", min_value=0.0, value=total, step=0.01)
                
                bal = total - payment_amount
                if bal > 0.01:
                    st.markdown(f"#### :red[Balance Due: ${bal:.2f}]")
                elif bal < -0.01:
                    st.markdown(f"#### :orange[Overpayment: ${abs(bal):.2f}]")
                else:
                    st.markdown(f"#### :green[Paid in Full]")
            else:
                st.markdown(f"#### :red[Balance Due: ${total:.2f}]")

            if st.button("💾 Save Record", type="primary"):
                if selected_patient_id:
                    conn = get_db_connection()
                    conn.execute('''INSERT INTO treatments 
                                    (patient_id, treatment_type, treatment_date, subtotal, tax, total, payment_amount, payment_date) 
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)''', 
                                    (selected_patient_id, treatment_type, treatment_date, cost, hst, total, payment_amount, payment_date))
                    conn.commit()
                    conn.close()
                    st.success("Saved!")
                else:
                    st.error("Select a patient first.")

    # --- PATIENT RECORDS PAGE ---
    elif page == "Patient Records":
        st.header("📂 Patient Records & Statements")

        conn = get_db_connection()
        patients_df = pd.read_sql("SELECT * FROM patients", conn)
        
        if patients_df.empty:
            st.warning("No patients found.")
            conn.close()
            return

        # 1. SELECT PATIENT
        patients_df['display'] = patients_df['full_name'] + " (ID: " + patients_df['unique_id'] + ")"
        selected_patient_str = st.selectbox("Select Patient:", patients_df['display'])
        
        pat_id = patients_df.loc[patients_df['display'] == selected_patient_str, 'id'].values[0]
        pat_name = patients_df.loc[patients_df['display'] == selected_patient_str, 'full_name'].values[0]

        # 2. CALCULATE STANDING (CREDIT/OWING)
        # We query ALL time for this patient to get their standing
        all_time_df = pd.read_sql("SELECT * FROM treatments WHERE patient_id = ?", conn, params=(pat_id,))
        
        if not all_time_df.empty:
            total_billed = all_time_df['total'].sum()
            total_paid = all_time_df['payment_amount'].sum()
            standing = total_billed - total_paid

            st.divider()
            st.subheader(f"Status: {pat_name}")

            # LOGIC:
            # If standing > 0: They owe money (RED, Negative)
            # If standing == 0: Paid (GREEN)
            # If standing < 0: They have credit (YELLOW, Positive)
            
            col_status, col_detail = st.columns([2, 1])
            
            with col_status:
                if standing > 0.01:
                    # They owe money
                    st.error(f"⚠️ OWING: -${standing:.2f}")
                elif standing < -0.01:
                    # Overpaid
                    credit = abs(standing)
                    st.warning(f"📒 CREDIT: +${credit:.2f}")
                else:
                    st.success("✅ PAID IN FULL: $0.00")

        # 3. GENERATE STATEMENT (DATE RANGE)
        st.divider()
        st.subheader("🖨️ Generate Receipt / Statement")
        
        col_d1, col_d2 = st.columns(2)
        with col_d1:
            # Date Range Selector
            today = datetime.now().date()
            start_date = st.date_input("Start Date", today - timedelta(days=30))
        with col_d2:
            end_date = st.date_input("End Date", today)

        # Filter Data by Range
        query = '''
            SELECT * FROM treatments 
            WHERE patient_id = ? 
            AND treatment_date BETWEEN ? AND ?
            ORDER BY treatment_date DESC
        '''
        range_df = pd.read_sql(query, conn, params=(pat_id, start_date, end_date))
        conn.close()

        if not range_df.empty:
            st.write(f"Found **{len(range_df)}** treatments in this period.")
            st.dataframe(range_df[['treatment_date', 'treatment_type', 'total', 'payment_amount']], use_container_width=True)
            
            if st.button("Generate Statement PDF"):
                # Convert DF to list of dicts for the PDF generator
                records = range_df.to_dict('records')
                date_str = f"{start_date} to {end_date}"
                
                pdf_data = generate_pdf(pat_name, date_str, records)
                
                st.download_button(
                    label="⬇️ Download PDF",
                    data=pdf_data,
                    file_name=f"Statement_{pat_name}_{start_date}.pdf",
                    mime="application/pdf"
                )
        else:
            st.info("No treatments found in the selected date range.")

    # --- SETTINGS PAGE ---
    elif page == "Settings":
        st.header("⚙️ Settings")
        with st.form("settings"):
            c_name = st.text_input("Clinic Name", value=get_setting("clinic_name"))
            c_addr = st.text_input("Clinic Address", value=get_setting("clinic_address"))
            c_phone = st.text_input("Phone", value=get_setting("clinic_phone"))
            c_hst = st.text_input("HST #", value=get_setting("hst_number"))
            c_foot = st.text_input("Footer", value=get_setting("receipt_footer"))
            
            if st.form_submit_button("Save"):
                update_setting("clinic_name", c_name)
                update_setting("clinic_address", c_addr)
                update_setting("clinic_phone", c_phone)
                update_setting("hst_number", c_hst)
                update_setting("receipt_footer", c_foot)
                st.success("Updated!")

if __name__ == "__main__":
    main()
