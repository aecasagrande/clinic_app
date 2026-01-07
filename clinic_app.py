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
    
    # Treatments Table
    c.execute('''CREATE TABLE IF NOT EXISTS treatments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    patient_id INTEGER,
                    treatment_type TEXT,
                    treatment_date DATE,
                    subtotal REAL,
                    tax REAL,
                    total REAL,
                    is_paid BOOLEAN,
                    payment_date DATE,
                    FOREIGN KEY(patient_id) REFERENCES patients(id)
                )''')

    # Settings Table (Key-Value pair for clinic details)
    c.execute('''CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )''')
    
    # Initialize default settings if they don't exist
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

def generate_pdf(patient_name, service_date, service_desc, subtotal, tax, total, is_paid, payment_date):
    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    
    # Fetch Settings
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

    # --- Receipt Details ---
    p.setFont("Helvetica-Bold", 14)
    p.drawString(50, height - 150, "OFFICIAL RECEIPT")
    
    p.setFont("Helvetica", 12)
    p.drawString(50, height - 180, f"Patient Name: {patient_name}")
    p.drawString(50, height - 200, f"Date of Service: {service_date}")
    
    # --- Payment Status ---
    status_text = "PAID IN FULL" if is_paid else "BALANCE DUE"
    status_color = colors.green if is_paid else colors.red
    
    p.setFillColor(status_color)
    p.setFont("Helvetica-Bold", 14)
    p.drawString(400, height - 160, status_text)
    if is_paid and payment_date:
         p.setFont("Helvetica", 10)
         p.drawString(400, height - 175, f"Paid on: {payment_date}")
    p.setFillColor(colors.black)

    # --- Table Header ---
    y_start = height - 250
    p.setFont("Helvetica-Bold", 11)
    p.drawString(50, y_start, "Description")
    p.drawString(400, y_start, "Amount")
    p.line(50, y_start - 5, width - 50, y_start - 5)

    # --- Table Content ---
    p.setFont("Helvetica", 11)
    p.drawString(50, y_start - 25, service_desc)
    p.drawString(400, y_start - 25, f"${subtotal:.2f}")

    p.drawString(300, y_start - 55, "HST (13%):")
    p.drawString(400, y_start - 55, f"${tax:.2f}")

    p.line(300, y_start - 65, width - 50, y_start - 65)
    
    p.setFont("Helvetica-Bold", 12)
    p.drawString(300, y_start - 85, "TOTAL:")
    p.drawString(400, y_start - 85, f"${total:.2f}")

    # --- Footer ---
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
    page = st.sidebar.radio("Go to:", ["New Treatment", "Patient Records", "Receipt Settings"])

    # ==========================
    # PAGE: NEW TREATMENT
    # ==========================
    if page == "New Treatment":
        st.header("📝 New Treatment Entry")

        # 1. Patient Selection
        conn = get_db_connection()
        patients = pd.read_sql("SELECT * FROM patients", conn)
        conn.close()

        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Patient Details")
            patient_mode = st.radio("Select Mode:", ["Existing Patient", "New Patient"], horizontal=True)

            selected_patient_id = None
            
            if patient_mode == "Existing Patient":
                if not patients.empty:
                    # Create a search label that combines Name and ID
                    patients['display'] = patients['full_name'] + " (ID: " + patients['unique_id'] + ")"
                    selected_patient = st.selectbox("Search Patient (Name or ID)", patients['display'])
                    # Extract the database ID
                    selected_patient_id = patients.loc[patients['display'] == selected_patient, 'id'].values[0]
                else:
                    st.warning("No patients found. Please add a new patient.")
            
            else: # New Patient
                new_name = st.text_input("Full Name")
                new_id = st.text_input("Patient ID (Unique)")
                if st.button("Add Patient"):
                    if new_name and new_id:
                        try:
                            conn = get_db_connection()
                            conn.execute("INSERT INTO patients (full_name, unique_id) VALUES (?, ?)", (new_name, new_id))
                            conn.commit()
                            conn.close()
                            st.success("Patient Added!")
                            st.rerun()
                        except sqlite3.IntegrityError:
                            st.error("Patient ID must be unique.")
                    else:
                        st.error("Please fill in both Name and ID.")

        # 2. Treatment Details
        with col2:
            st.subheader("Treatment & Payment")
            
            # Dropdown for treatments
            treatment_options = {
                "Magnetic Field Therapy": 25.00,
                "Helium Neon Laser": 25.00
            }
            
            selected_treatment = st.selectbox("Treatment Type", list(treatment_options.keys()))
            treatment_date = st.date_input("Date of Treatment", datetime.now())

            # Financials
            cost = treatment_options[selected_treatment]
            hst = cost * 0.13
            total = cost + hst

            # Display Financials clearly
            st.markdown(f"""
            **Subtotal:** ${cost:.2f}  
            **HST (13%):** ${hst:.2f}  
            **Total:** :green[**${total:.2f}**]
            """)

            st.divider()

            # Payment Status
            is_paid = st.checkbox("Payment Received?", value=True)
            payment_date = None
            if is_paid:
                payment_date = st.date_input("Date of Payment", datetime.now())

            if st.button("💾 Save Treatment Record", type="primary"):
                if selected_patient_id:
                    conn = get_db_connection()
                    conn.execute('''INSERT INTO treatments 
                                    (patient_id, treatment_type, treatment_date, subtotal, tax, total, is_paid, payment_date) 
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)''', 
                                    (selected_patient_id, selected_treatment, treatment_date, cost, hst, total, is_paid, payment_date))
                    conn.commit()
                    conn.close()
                    st.success("Record saved successfully!")
                else:
                    st.error("Please select a valid patient.")

    # ==========================
    # PAGE: PATIENT RECORDS
    # ==========================
    elif page == "Patient Records":
        st.header("📂 History & Receipts")

        conn = get_db_connection()
        
        # Load data with a join to get patient names
        query = '''
        SELECT 
            t.id as trans_id,
            p.full_name,
            p.unique_id,
            t.treatment_type,
            t.treatment_date,
            t.total,
            t.is_paid,
            t.payment_date,
            t.subtotal,
            t.tax
        FROM treatments t
        JOIN patients p ON t.patient_id = p.id
        ORDER BY t.treatment_date DESC
        '''
        df = pd.read_sql(query, conn)
        conn.close()

        # Search Filter
        search_query = st.text_input("🔍 Search by Name or Patient ID")
        
        if search_query:
            df = df[df['full_name'].str.contains(search_query, case=False) | df['unique_id'].str.contains(search_query, case=False)]

        st.dataframe(
            df[['full_name', 'unique_id', 'treatment_type', 'treatment_date', 'total', 'is_paid', 'payment_date']],
            use_container_width=True
        )

        st.divider()
        st.subheader("Generate Receipt")
        
        # Select a transaction to generate receipt for
        if not df.empty:
            receipt_options = df.apply(lambda x: f"Trans ID {x['trans_id']} - {x['full_name']} - {x['treatment_date']}", axis=1)
            selected_option = st.selectbox("Select Transaction to Print", receipt_options)
            
            if selected_option:
                trans_id = int(selected_option.split(" ")[2])
                record = df[df['trans_id'] == trans_id].iloc[0]

                if st.button("Generate Receipt PDF"):
                    pdf_data = generate_pdf(
                        patient_name=record['full_name'],
                        service_date=record['treatment_date'],
                        service_desc=record['treatment_type'],
                        subtotal=record['subtotal'],
                        tax=record['tax'],
                        total=record['total'],
                        is_paid=record['is_paid'],
                        payment_date=record['payment_date']
                    )
                    
                    st.download_button(
                        label="⬇️ Download Receipt",
                        data=pdf_data,
                        file_name=f"Receipt_{record['full_name']}_{record['treatment_date']}.pdf",
                        mime="application/pdf"
                    )

    # ==========================
    # PAGE: SETTINGS
    # ==========================
    elif page == "Receipt Settings":
        st.header("⚙️ App & Receipt Settings")
        st.write("Update the details that appear on the generated PDF receipts.")

        with st.form("settings_form"):
            c_name = st.text_input("Clinic Name", value=get_setting("clinic_name"))
            c_addr = st.text_input("Clinic Address", value=get_setting("clinic_address"))
            c_phone = st.text_input("Phone Number", value=get_setting("clinic_phone"))
            c_hst = st.text_input("HST Number", value=get_setting("hst_number"))
            c_footer = st.text_input("Footer Message", value=get_setting("receipt_footer"))

            submitted = st.form_submit_button("Save Settings")
            if submitted:
                update_setting("clinic_name", c_name)
                update_setting("clinic_address", c_addr)
                update_setting("clinic_phone", c_phone)
                update_setting("hst_number", c_hst)
                update_setting("receipt_footer", c_footer)
                st.success("Settings updated!")

        st.divider()
        st.subheader("Receipt Preview")
        if st.button("Generate Preview Receipt"):
            # Dummy data for preview
            pdf_data = generate_pdf(
                patient_name="John Doe",
                service_date="2023-01-01",
                service_desc="Magnetic Field Therapy (PREVIEW)",
                subtotal=25.00,
                tax=3.25,
                total=28.25,
                is_paid=True,
                payment_date="2023-01-01"
            )
            st.download_button("⬇️ Download Preview PDF", data=pdf_data, file_name="preview_receipt.pdf", mime="application/pdf")

if __name__ == "__main__":
    main()
