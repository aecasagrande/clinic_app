import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib import colors

# ==========================================
# 1. DATABASE MANAGEMENT
# ==========================================

DB_FILE = "clinic.db"

def init_db():
    """Initialize the SQLite database with necessary tables."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # Patients Table
    c.execute('''CREATE TABLE IF NOT EXISTS patients (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    full_name TEXT NOT NULL,
                    unique_id TEXT UNIQUE
                )''')
    
    # Treatments Table (Updated with payment_amount)
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

    # Settings Table
    c.execute('''CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )''')
    
    # Initialize default settings
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
# 2. PDF RECEIPT GENERATION
# ==========================================

def generate_pdf(patient_name, service_date, service_desc, subtotal, tax, total, paid_amount, payment_date):
    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    
    # Fetch Settings
    clinic_name = get_setting("clinic_name")
    address = get_setting("clinic_address")
    phone = get_setting("clinic_phone")
    hst_num = get_setting("hst_number")
    footer_text = get_setting("receipt_footer")

    # Calculations
    balance_due = total - paid_amount

    # --- Header ---
    p.setFont("Helvetica-Bold", 20)
    p.drawString(50, height - 50, clinic_name)
    
    p.setFont("Helvetica", 10)
    p.drawString(50, height - 70, address)
    p.drawString(50, height - 85, f"Phone: {phone}")
    p.drawString(50, height - 100, f"HST #: {hst_num}")
    
    p.line(50, height - 110, width - 50, height - 110)

    # --- Receipt Details ---
    p.setFont("Helvetica-Bold", 14)
    p.drawString(50, height - 150, "OFFICIAL RECEIPT")
    
    p.setFont("Helvetica", 12)
    p.drawString(50, height - 180, f"Patient Name: {patient_name}")
    p.drawString(50, height - 200, f"Date of Service: {service_date}")
    
    # --- Payment Status Badge ---
    is_fully_paid = balance_due <= 0.01 # Small tolerance for float math
    status_text = "PAID IN FULL" if is_fully_paid else "BALANCE DUE"
    status_color = colors.green if is_fully_paid else colors.red
    
    p.setFillColor(status_color)
    p.setFont("Helvetica-Bold", 14)
    p.drawString(400, height - 160, status_text)
    
    p.setFillColor(colors.black)
    p.setFont("Helvetica", 10)
    if payment_date and paid_amount > 0:
         p.drawString(400, height - 175, f"Payment Date: {payment_date}")

    # --- Financial Table ---
    y_start = height - 250
    p.setFont("Helvetica-Bold", 11)
    p.drawString(50, y_start, "Description")
    p.drawString(400, y_start, "Amount")
    p.line(50, y_start - 5, width - 50, y_start - 5)

    # Line Items
    p.setFont("Helvetica", 11)
    p.drawString(50, y_start - 25, service_desc)
    p.drawString(400, y_start - 25, f"${subtotal:.2f}")

    p.drawString(300, y_start - 45, "HST (13%):")
    p.drawString(400, y_start - 45, f"${tax:.2f}")

    p.line(300, y_start - 55, width - 50, y_start - 55)
    
    # Totals
    p.setFont("Helvetica-Bold", 12)
    p.drawString(300, y_start - 75, "TOTAL:")
    p.drawString(400, y_start - 75, f"${total:.2f}")
    
    p.setFont("Helvetica", 11)
    p.drawString(300, y_start - 95, "Amount Paid:")
    p.drawString(400, y_start - 95, f"${paid_amount:.2f}")
    
    p.setFont("Helvetica-Bold", 12)
    if not is_fully_paid:
        p.setFillColor(colors.red)
    p.drawString(300, y_start - 115, "Balance Due:")
    p.drawString(400, y_start - 115, f"${balance_due:.2f}")

    # --- Footer ---
    p.setFillColor(colors.black)
    p.setFont("Helvetica-Oblique", 10)
    p.drawCentredString(width / 2, 50, footer_text)

    p.showPage()
    p.save()
    
    buffer.seek(0)
    return buffer

# ==========================================
# 3. STREAMLIT UI
# ==========================================

def main():
    st.set_page_config(page_title="Clinic Manager", page_icon="🏥", layout="wide")
    init_db()

    # --- Sidebar Navigation ---
    st.sidebar.title("Navigation")
    page = st.sidebar.radio("Go to:", ["New Treatment", "Patient History & Receipts", "Settings"])

    # ==========================
    # PAGE: NEW TREATMENT
    # ==========================
    if page == "New Treatment":
        st.header("📝 New Treatment Entry")

        col1, col2 = st.columns(2)

        # --- 1. Select / Create Patient ---
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
                    st.info("No patients found. Please register a new one.")

            with tab_new:
                new_name = st.text_input("Full Name")
                new_id = st.text_input("Patient ID (Unique)")
                if st.button("Register Patient"):
                    if new_name and new_id:
                        try:
                            conn = get_db_connection()
                            conn.execute("INSERT INTO patients (full_name, unique_id) VALUES (?, ?)", (new_name, new_id))
                            conn.commit()
                            conn.close()
                            st.success(f"Registered {new_name}!")
                            st.rerun()
                        except sqlite3.IntegrityError:
                            st.error("Patient ID already exists.")
                    else:
                        st.error("Enter both Name and ID.")

        # --- 2. Treatment & Payment Details ---
        with col2:
            st.subheader("2. Treatment & Payment")
            
            treatment_type = st.selectbox("Service Type", ["Magnetic Field Therapy", "Helium Neon Laser"])
            treatment_date = st.date_input("Date of Service", datetime.now())

            # Cost Calculation
            cost = 25.00
            hst = cost * 0.13
            total = cost + hst

            st.markdown(f"**Total Due:** :green[**${total:.2f}**]")
            
            st.divider()
            
            # Payment Input
            st.write(" **Payment Details**")
            payment_date_input = st.date_input("Payment Date", datetime.now())
            payment_amount_input = st.number_input("Amount Paid ($)", min_value=0.0, max_value=1000.0, step=0.01, value=total)

            if st.button("💾 Save Record", type="primary"):
                if selected_patient_id:
                    conn = get_db_connection()
                    conn.execute('''INSERT INTO treatments 
                                    (patient_id, treatment_type, treatment_date, subtotal, tax, total, payment_amount, payment_date) 
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)''', 
                                    (selected_patient_id, treatment_type, treatment_date, cost, hst, total, payment_amount_input, payment_date_input))
                    conn.commit()
                    conn.close()
                    st.success("Treatment and payment recorded!")
                else:
                    st.error("Please select a patient first.")

    # ==========================
    # PAGE: PATIENT HISTORY
    # ==========================
    elif page == "Patient History & Receipts":
        st.header("📂 Patient History")

        conn = get_db_connection()
        patients_df = pd.read_sql("SELECT * FROM patients", conn)
        
        if patients_df.empty:
            st.warning("No patients in database.")
            conn.close()
            return

        # 1. Select Patient (Top Level)
        patients_df['display'] = patients_df['full_name'] + " (ID: " + patients_df['unique_id'] + ")"
        selected_patient_str = st.selectbox("Select Patient to View History:", patients_df['display'])
        
        # Get Patient ID
        current_patient_id = patients_df.loc[patients_df['display'] == selected_patient_str, 'id'].values[0]
        current_patient_name = patients_df.loc[patients_df['display'] == selected_patient_str, 'full_name'].values[0]

        # 2. Fetch History for THIS patient
        history_query = '''
            SELECT 
                id, treatment_date, treatment_type, total, payment_amount, payment_date, subtotal, tax
            FROM treatments 
            WHERE patient_id = ?
            ORDER BY treatment_date DESC
        '''
        history_df = pd.read_sql(history_query, conn, params=(current_patient_id,))
        conn.close()

        if not history_df.empty:
            # Calculate Balance for display
            history_df['balance'] = history_df['total'] - history_df['payment_amount']
            
            # Display intuitive table
            st.subheader(f"History for {current_patient_name}")
            
            # Rename columns for cleaner UI
            display_df = history_df[['treatment_date', 'treatment_type', 'total', 'payment_amount', 'balance', 'payment_date']].copy()
            display_df.columns = ['Date', 'Service', 'Total ($)', 'Paid ($)', 'Balance ($)', 'Paid On']
            
            # Highlight unpaid rows
            def highlight_unpaid(row):
                if row['Balance ($)'] > 0.01:
                    return ['background-color: #ffcccc'] * len(row)
                return [''] * len(row)

            st.dataframe(display_df.style.apply(highlight_unpaid, axis=1), use_container_width=True)

            st.divider()
            
            # 3. Receipt Generation Section
            st.subheader("🖨️ Generate Receipt")
            col_r1, col_r2 = st.columns([3, 1])
            
            with col_r1:
                # Create a readable list of visits for the dropdown
                visit_options = history_df.apply(
                    lambda x: f"{x['treatment_date']} - {x['treatment_type']} (Paid: ${x['payment_amount']:.2f})", axis=1
                )
                selected_visit_str = st.selectbox("Select Visit to Print:", visit_options)
            
            with col_r2:
                st.write("") # Spacer
                st.write("") # Spacer
                if st.button("Generate PDF"):
                    # Find the specific row data based on selection index
                    # (This assumes the dropdown order matches the dataframe order, which it does)
                    selected_index = visit_options[visit_options == selected_visit_str].index[0]
                    record = history_df.loc[selected_index]

                    pdf_data = generate_pdf(
                        patient_name=current_patient_name,
                        service_date=record['treatment_date'],
                        service_desc=record['treatment_type'],
                        subtotal=record['subtotal'],
                        tax=record['tax'],
                        total=record['total'],
                        paid_amount=record['payment_amount'],
                        payment_date=record['payment_date']
                    )
                    
                    st.download_button(
                        label="⬇️ Download Receipt",
                        data=pdf_data,
                        file_name=f"Receipt_{current_patient_name}_{record['treatment_date']}.pdf",
                        mime="application/pdf"
                    )

        else:
            st.info("No treatment history found for this patient.")

    # ==========================
    # PAGE: SETTINGS
    # ==========================
    elif page == "Settings":
        st.header("⚙️ Receipt Settings")
        
        with st.form("settings_form"):
            st.write("Customize your receipt header and footer.")
            c_name = st.text_input("Clinic Name", value=get_setting("clinic_name"))
            c_addr = st.text_input("Clinic Address", value=get_setting("clinic_address"))
            c_phone = st.text_input("Phone Number", value=get_setting("clinic_phone"))
            c_hst = st.text_input("HST Number", value=get_setting("hst_number"))
            c_footer = st.text_input("Footer Message", value=get_setting("receipt_footer"))

            if st.form_submit_button("Save Settings"):
                update_setting("clinic_name", c_name)
                update_setting("clinic_address", c_addr)
                update_setting("clinic_phone", c_phone)
                update_setting("hst_number", c_hst)
                update_setting("receipt_footer", c_footer)
                st.success("Settings updated!")

if __name__ == "__main__":
    main()
