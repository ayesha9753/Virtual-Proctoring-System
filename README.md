# 🎓 Virtual Proctoring System

An AI-powered Virtual Proctoring System developed using **Streamlit**, **YOLOv8**, and **OpenCV**. This application simulates a secure online examination environment, providing real-time monitoring, student tracking, and incident reporting — all through a user-friendly web interface.

---

## 📌 Features

### 👨‍🎓 Student Mode
- Secure login with credentials
- Attempt quiz with timer
- Submit quiz answers
- View results after submission

### 🛡️ Administrator Mode
- Admin login with secure credentials
- Real-time proctoring dashboard
- Monitor session incidents with YOLO-based face & object detection
- View screenshots of suspicious activity
- Generate reports
- Manage quiz questions

---

## 🧠 Technologies Used

| Category            | Tools / Libraries                                |
|---------------------|--------------------------------------------------|
| Frontend            | Streamlit, HTML/CSS (built-in via Streamlit)    |
| AI / CV Models      | YOLOv8 (Ultralytics), OpenCV, NumPy, PIL         |
| Backend Logic       | Python, Pandas, JSON, Datetime                   |
| Admin Dashboard     | Streamlit Components, Custom Session Analytics   |
| Data Storage        | Local CSV / JSON files for questions & results   |

---

## 🔐 Modules Overview

### `student/`
- Handles quiz display, submission, and result generation

### `admin/`
- Contains tools to track student activity
- Displays incidents using YOLO object detection
- Allows question management and session summaries

### `model/`
- Pre-trained YOLOv8 model for detecting face/no-face scenarios

---

## 🖥️ How to Run


# 1. Clone the repository
git clone https://github.com/ayesha9753/virtual-proctoring-system.git
cd virtual-proctoring-system

# 2. Create a virtual environment (optional but recommended)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 3. Install requirements
pip install -r requirements.txt

# 4. Launch the Streamlit app
streamlit run app.py

📸 How It Works
The system uses your webcam and a YOLOv8 model to detect:

Face presence

Multiple persons

Mobile phones or unusual activities

Incidents are captured as screenshots and logged

Admin can view detailed session analytics

Folder Structure
perl
Copy
Edit
virtual-proctoring-system/
│
├── student/                 # Student mode logic
├── admin/                   # Admin dashboard and monitoring
├── model/                   # YOLOv8 pretrained weights
├── screenshots/             # Saved alerts and screenshots
├── requirements.txt
├── README.md
└── app.py            

📬 Contact
Ayesha Imran
📧 Email: ayeshaimran9797@gmail.com
🔗 LinkedIn: linkedin.com/in/ayesha-imran-3a5265369
💻 GitHub: github.com/ayesha9753

✅ Future Enhancements
Replace local storage with a secure database (MongoDB or Firebase)

Add JWT-based authentication

Live video streaming for advanced proctoring

Integration with Learning Management Systems (LMS)

⚠️ Disclaimer
This project is developed for educational and research purposes only. Not intended for production use without further security and performance tuning.
