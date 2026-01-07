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
                    payment_amount REAL,
                    payment_date DATE,
                    FOREIGN KEY(patient_id) REFERENCES patients(id)
                )''')

    # Settings Table
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
# 2. PDF GENERATOR
# ==========================================

def generate_pdf(patient_name, date_range_str, records):
    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    
    clinic_name = get_setting("clinic_name")
    address = get_setting("clinic_address")
    phone = get_setting("clinic_phone")
    hst_num = get_setting("hst_number")
    footer_text = get_setting("receipt_footer")

    # Header
    p.setFont("Helvetica-Bold", 20)
    p.drawString(50, height - 50, clinic_name)
    p.setFont("Helvetica", 10)
    p.drawString(50, height - 70, address)
    p.drawString(50, height - 85, f"Phone: {phone}")
    p.drawString(50, height - 100, f"HST #: {hst_num}")
    p.line(50, height - 110, width - 50, height - 110)

    # Info
    p.setFont("Helvetica-Bold", 14)
    p.drawString(50, height - 150, "STATEMENT OF ACCOUNT")
    p.setFont("Helvetica", 12)
    p.drawString(50, height - 175, f"Patient: {patient_name}")
    p.drawString(50, height - 195, f"Period: {date_range_str}")

    # Table
    y = height - 240
    p.setFont("Helvetica-Bold", 10)
    p.drawString(50, y, "Date")
    p.drawString(130, y, "Service")
    p.drawString(330, y, "Billed")
    p.drawString(400, y, "Paid")
    p.drawString(480, y, "Diff")
    p.line(50, y - 5, width - 50, y - 5)
    
    y -= 25
    p.setFont("Helvetica", 10)

    total_billed = 0.0
    total_paid = 0.0

    for item in records:
        if y < 100:
            p.showPage()
            y = height - 50
        
        billed = float(item['total'])
        paid = float(item['payment_amount'])
        
        p.drawString(50, y, str(item['treatment_date']))
        p.drawString(130, y, str(item['treatment_type']))
        p.drawString(330, y, f"${billed:.2f}")
        p.drawString(400, y, f"${paid:.2f}")
        
        diff = billed - paid
        if diff > 0.01: 
            p.setFillColor(colors.red)
        elif diff < -0.01:
            p.setFillColor(colors.green)
        
        p.drawString(480, y, f"${diff:.2f}")
        p.setFillColor(colors.black)
        
        total_billed += billed
        total_paid += paid
        y -= 20

    # Summary
    y -= 20
    p.line(50, y, width - 50, y)
    y -= 30
    
    net_position = total_billed - total_paid
    
    p.setFont("Helvetica-Bold", 12)
    p.drawString(250, y, "Total Billed:")
    p.drawString(400, y, f"${total_billed:.2f}")
    
    y -= 20
    p.drawString(250, y, "Total Paid:")
    p.drawString(400, y, f"${total_paid:.2f}")
    
    y -= 25
    p.setFont("Helvetica-Bold", 14)
    
    if net_position > 0.01:
        p.drawString(250, y, "BALANCE DUE:")
        p.setFillColor(colors.red)
        p.drawString(400, y, f"${net_position:.2f}")
    elif net_position < -0.01:
        p.drawString(250, y, "CREDIT REMAINING:")
        p.setFillColor(colors.orange)
        p.drawString(400, y, f"${abs(net_position):.2f}")
    else:
        p.drawString(250, y, "BALANCE:")
        p.setFillColor(colors.green)
        p.drawString(400, y, "$0.00")

    p.setFillColor(colors.black)
    p.setFont("Helvetica-Oblique", 10)
    p.drawCentredString(width / 2, 50, footer_text)

    p.showPage()
    p.save()
    buffer.seek(0)
    return buffer

# ==========================================
# 3. UI MAIN
# ==========================================

def main():
    st.set_page_config(page_title="Clinic Manager", page_icon="🏥", layout="wide")
    init_db()

    st.sidebar.title("Navigation")
    page = st.sidebar.radio("Go to:", ["New Treatment", "Patient Records", "Settings"])

    # ---------------------------------------------------------
    # PAGE: NEW TREATMENT
    # ---------------------------------------------------------
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
                    st.markdown(f"#### :red[Balance Remaining: ${bal:.2f}]")
                elif bal < -0.01:
                    st.markdown(f"#### :orange[Overpayment (Credit): ${abs(bal):.2f}]")
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
                    st.success(f"Saved! Payment recorded: ${payment_amount:.2f}")
                else:
                    st.error("Select a patient first.")

    # ---------------------------------------------------------
    # PAGE: PATIENT RECORDS (WITH EDITING & DELETING)
    # ---------------------------------------------------------
    elif page == "Patient Records":
        st.header("📂 Patient Financials")

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

        # 2. CALCULATE STANDING (ALL TIME)
        all_time_df = pd.read_sql("SELECT * FROM treatments WHERE patient_id = ?", conn, params=(pat_id,))
        all_time_df['total'] = all_time_df['total'].fillna(0.0)
        all_time_df['payment_amount'] = all_time_df['payment_amount'].fillna(0.0)
        
        if not all_time_df.empty:
            total_billed = all_time_df['total'].sum()
            total_paid = all_time_df['payment_amount'].sum()
            net_position = total_billed - total_paid

            st.divider()
            st.subheader(f"Financial Status: {pat_name}")
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Total Billed", f"${total_billed:.2f}")
            c2.metric("Total Paid", f"${total_paid:.2f}")
            
            if net_position > 0.01:
                c3.metric("Current Balance", f"${net_position:.2f}", delta="-OWING", delta_color="inverse")
            elif net_position < -0.01:
                c3.metric("Current Credit", f"${abs(net_position):.2f}", delta="CREDIT", delta_color="normal")
            else:
                c3.metric("Status", "Paid in Full", delta="OK")

        # 3. INTERACTIVE DATA EDITOR (EDIT & DELETE ROWS)
        st.divider()
        st.subheader("📋 Edit / Delete Records")
        st.info("💡 Edit cells below. To delete a row: Select it and press 'Delete'. Click 'Save Changes' to commit.")

        query_all = "SELECT id, treatment_date, treatment_type, total, payment_amount, payment_date FROM treatments WHERE patient_id = ? ORDER BY treatment_date DESC"
        editor_df = pd.read_sql(query_all, conn, params=(pat_id,))
        
        edited_df = st.data_editor(
            editor_df, 
            num_rows="dynamic", 
            key="data_editor",
            disabled=["id"],
            hide_index=True
        )
        
        if st.button("💾 Save Changes (Edits & Deletes)"):
            try:
                original_ids = set(editor_df['id'].tolist())
                new_ids = set(edited_df['id'].tolist())
                deleted_ids = original_ids - new_ids
                
                # Delete rows
                for del_id in deleted_ids:
                    conn.execute("DELETE FROM treatments WHERE id = ?", (del_id,))
                
                # Update rows
                for index, row in edited_df.iterrows():
                    if pd.notna(row['id']):
                        conn.execute('''
                            UPDATE treatments 
                            SET treatment_date=?, treatment_type=?, total=?, payment_amount=?, payment_date=?
                            WHERE id=?
                        ''', (
                            row['treatment_date'], 
                            row['treatment_type'], 
                            row['total'], 
                            row['payment_amount'], 
                            row['payment_date'],
                            row['id']
                        ))
                
                conn.commit()
                st.success("Changes saved successfully!")
                st.rerun()
                
            except Exception as e:
                st.error(f"Error saving changes: {e}")
        
        conn.close()

        # 4. GENERATE STATEMENT
        st.divider()
        st.subheader("🖨️ Generate Receipt / Statement")
        
        col_check, col_d1, col_d2 = st.columns([1, 2, 2])
        with col_check:
            st.write("") 
            use_all_time = st.checkbox("Select All Time?", value=False)
        with col_d1:
            today = datetime.now().date()
            start_date = st.date_input("Start Date", today - timedelta(days=365), disabled=use_all_time)
        with col_d2:
            end_date = st.date_input("End Date", today, disabled=use_all_time)

        if st.button("Generate Statement PDF"):
            conn = get_db_connection()
            if use_all_time:
                 query = 'SELECT * FROM treatments WHERE patient_id = ? ORDER BY treatment_date DESC'
                 params = (pat_id,)
            else:
                 query = 'SELECT * FROM treatments WHERE patient_id = ? AND treatment_date BETWEEN ? AND ? ORDER BY treatment_date DESC'
                 params = (pat_id, start_date, end_date)
                 
            range_df = pd.read_sql(query, conn, params=params)
            conn.close()

            if not range_df.empty:
                records = range_df.to_dict('records')
                date_str = "ALL TIME" if use_all_time else f"{start_date} to {end_date}"
                pdf_data = generate_pdf(pat_name, date_str, records)
                st.download_button(label="⬇️ Download PDF", data=pdf_data, file_name=f"Statement_{pat_name}.pdf", mime="application/pdf")
            else:
                st.error("No records found in that date range.")
                
        # 5. DANGER ZONE - DELETE PATIENT
        st.divider()
        with st.expander("🚨 Danger Zone: Delete Patient Profile"):
            st.error(f"Warning: You are about to delete **{pat_name}** and ALL their history. This cannot be undone.")
            if st.button("❌ Permanently Delete Patient"):
                conn = get_db_connection()
                # 1. Delete all history first
                conn.execute("DELETE FROM treatments WHERE patient_id = ?", (pat_id,))
                # 2. Delete the patient profile
                conn.execute("DELETE FROM patients WHERE id = ?", (pat_id,))
                conn.commit()
                conn.close()
                st.success(f"Patient {pat_name} has been deleted.")
                st.rerun()

    # ---------------------------------------------------------
    # PAGE: SETTINGS & DATA MANAGEMENT
    # ---------------------------------------------------------
    elif page == "Settings":
        st.header("⚙️ Settings")
        
        with st.expander("🧾 Receipt Customization", expanded=True):
            with st.form("settings"):
                c_name = st.text_input("Clinic Name", value=get_setting("clinic_name"))
                c_addr = st.text_input("Clinic Address", value=get_setting("clinic_address"))
                c_phone = st.text_input("Phone", value=get_setting("clinic_phone"))
                c_hst = st.text_input("HST #", value=get_setting("hst_number"))
                c_foot = st.text_input("Footer", value=get_setting("receipt_footer"))
                if st.form_submit_button("Save Details"):
                    update_setting("clinic_name", c_name)
                    update_setting("clinic_address", c_addr)
                    update_setting("clinic_phone", c_phone)
                    update_setting("hst_number", c_hst)
                    update_setting("receipt_footer", c_foot)
                    st.success("Updated!")

        st.divider()
        st.subheader("💾 Data Management (Backup & Restore)")
        
        tab_backup, tab_restore = st.tabs(["⬇️ Backup (Download)", "⬆️ Restore (Upload)"])
        
        # --- BACKUP ---
        with tab_backup:
            st.write("Download your data periodically to keep it safe.")
            
            conn = get_db_connection()
            df_pat_bk = pd.read_sql("SELECT * FROM patients", conn)
            df_treat_bk = pd.read_sql("SELECT * FROM treatments", conn)
            conn.close()
            
            b1, b2 = st.columns(2)
            with b1:
                st.download_button(
                    "Download Patients (CSV)", 
                    data=df_pat_bk.to_csv(index=False).encode('utf-8'),
                    file_name="backup_patients.csv",
                    mime="text/csv"
                )
            with b2:
                st.download_button(
                    "Download Treatments (CSV)", 
                    data=df_treat_bk.to_csv(index=False).encode('utf-8'),
                    file_name="backup_treatments.csv",
                    mime="text/csv"
                )
        
        # --- RESTORE ---
        with tab_restore:
            st.warning("⚠️ Uploading files will MERGE data into the database. Use this if your data was wiped.")
            
            up_pat = st.file_uploader("Upload Patients CSV", type=['csv'])
            up_treat = st.file_uploader("Upload Treatments CSV", type=['csv'])
            
            if st.button("Start Restore Process"):
                if up_pat and up_treat:
                    try:
                        conn = get_db_connection()
                        new_pats = pd.read_csv(up_pat)
                        new_treats = pd.read_csv(up_treat)
                        
                        new_pats.to_sql('patients', conn, if_exists='append', index=False)
                        st.success(f"✅ Restored {len(new_pats)} patients.")
                        
                        new_treats.to_sql('treatments', conn, if_exists='append', index=False)
                        st.success(f"✅ Restored {len(new_treats)} treatment records.")
                        
                        conn.close()
                        st.balloons()
                        
                    except sqlite3.IntegrityError:
                        st.error("Error: Some of this data already exists in the system.")
                    except Exception as e:
                        st.error(f"An error occurred: {e}")
                else:
                    st.error("Please upload BOTH files to restore.")

if __name__ == "__main__":
    main()
