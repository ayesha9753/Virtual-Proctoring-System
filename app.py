import os
import cv2
import time
import json
import logging
import numpy as np
import pandas as pd
from PIL import Image
import streamlit as st
from ultralytics import YOLO
from datetime import datetime

# Configure logging
logging.basicConfig(
    filename='proctoring_log.txt',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Create directories for storing data
os.makedirs('incident_reports', exist_ok=True)
os.makedirs('suspicious_screenshots', exist_ok=True)
os.makedirs('session_data', exist_ok=True)
os.makedirs('quiz_questions', exist_ok=True)

# Initialize session state for student data, exam status, quiz, and alerts
if 'student_data' not in st.session_state:
    st.session_state.student_data = {'name': '', 'roll_number': '', 'department': ''}
if 'exam_started' not in st.session_state:
    st.session_state.exam_started = False
if 'last_face_center' not in st.session_state:
    st.session_state.last_face_center = None
if 'cap' not in st.session_state:
    st.session_state.cap = None
if 'last_alert' not in st.session_state:
    st.session_state.last_alert = None
if 'quiz_answers' not in st.session_state:
    st.session_state.quiz_answers = {}
if 'model' not in st.session_state:
    st.session_state.model = None
if 'alert_message' not in st.session_state:
    st.session_state.alert_message = None
if 'alert_display_until' not in st.session_state:
    st.session_state.alert_display_until = 0
if 'incident_counter' not in st.session_state:
    st.session_state.incident_counter = 0
if 'session_id' not in st.session_state:
    st.session_state.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
if 'mode' not in st.session_state:
    st.session_state.mode = "select"  # "select", "student" or "invigilator"
if 'live_feeds' not in st.session_state:
    st.session_state.live_feeds = {}
if 'recent_alerts' not in st.session_state:
    st.session_state.recent_alerts = []
if 'quiz_completed' not in st.session_state:
    st.session_state.quiz_completed = False
if 'quiz_score' not in st.session_state:
    st.session_state.quiz_score = None
if 'admin_authenticated' not in st.session_state:
    st.session_state.admin_authenticated = False
if 'current_students' not in st.session_state:
    st.session_state.current_students = []

# Admin credentials (in production, store these securely)
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin123"

# Sample quiz questions
QUIZ_QUESTIONS = [
    {
        "question": "What is the capital of France?",
        "options": ["A. Berlin", "B. Paris", "C. Madrid", "D. Rome"],
        "correct": "B"
    },
    {
        "question": "Which planet is known as the Red Planet?",
        "options": ["A. Jupiter", "B. Mars", "C. Venus", "D. Mercury"],
        "correct": "B"
    },
    {
        "question": "What is 2 + 2?",
        "options": ["A. 3", "B. 4", "C. 5", "D. 6"],
        "correct": "B"
    }
]

def log_event(message, level="INFO"):
    """Enhanced logging with incident tracking and screenshots"""
    student = st.session_state.student_data
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_msg = f"Student: {student['name']} (Roll: {student['roll_number']}), Dept: {student['department']} - {message}"
    
    if level == "WARNING":
        logging.warning(log_msg)
        st.session_state.incident_counter += 1
        
        # Create incident report
        incident_data = {
            "timestamp": timestamp,
            "session_id": st.session_state.session_id,
            "student_name": student['name'],
            "roll_number": student['roll_number'],
            "department": student['department'],
            "incident_type": message,
            "incident_id": st.session_state.incident_counter,
            "severity": "HIGH" if "Multiple faces" in message else "MEDIUM"
        }
        
        # Save incident report
        incident_file = f"incident_reports/incident_{st.session_state.session_id}_{st.session_state.incident_counter}.json"
        with open(incident_file, 'w') as f:
            json.dump(incident_data, f, indent=2)
        
        # Take screenshot if camera is available
        if st.session_state.cap is not None:
            ret, frame = st.session_state.cap.read()
            if ret:
                screenshot_file = f"suspicious_screenshots/screenshot_{st.session_state.session_id}_{st.session_state.incident_counter}.jpg"
                cv2.imwrite(screenshot_file, frame)
                incident_data["screenshot"] = screenshot_file
        
        # Add to recent alerts for invigilator dashboard
        alert_info = {
            "timestamp": timestamp,
            "student": f"{student['name']} ({student['roll_number']})",
            "message": message,
            "severity": incident_data["severity"]
        }
        st.session_state.recent_alerts.insert(0, alert_info)
        # Keep only last 10 alerts
        if len(st.session_state.recent_alerts) > 10:
            st.session_state.recent_alerts = st.session_state.recent_alerts[:10]
        
        # Set the appropriate alert message based on the event
        if "Multiple faces detected" in message:
            st.session_state.alert_message = "Multiple faces detected. Your exam may be canceled."
        elif "Student moved" in message:
            direction = message.split()[-1]
            st.session_state.alert_message = f"Movement detected ({direction}). Please stay centered."
        elif "No face detected" in message:
            st.session_state.alert_message = "No face detected. Please remain in view."
        
        # Set the display duration (5 seconds from now)
        st.session_state.alert_display_until = time.time() + 5
    else:
        logging.info(log_msg)
    
    st.session_state.last_alert = log_msg

def save_session_data():
    """Save session summary data"""
    try:
        quiz_score = None
        if st.session_state.quiz_completed and st.session_state.quiz_score:
            score, total = st.session_state.quiz_score
            quiz_score = {
                "score": score,
                "total": total,
                "percentage": (score / total) * 100 if total > 0 else 0,
                "status": "PASS" if (score / total) * 100 >= 70 else "FAIL"
            }
        
        session_summary = {
            "session_id": st.session_state.session_id,
            "student_data": st.session_state.student_data,
            "start_time": st.session_state.get('exam_start_time', 'Unknown'),
            "end_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "total_incidents": st.session_state.incident_counter,
            "quiz_answers": st.session_state.quiz_answers,
            "quiz_completed": st.session_state.quiz_completed,
            "quiz_score": quiz_score
        }
        
        # Ensure session_data directory exists
        os.makedirs('session_data', exist_ok=True)
        
        session_file = f"session_data/session_{st.session_state.session_id}.json"
        with open(session_file, 'w') as f:
            json.dump(session_summary, f, indent=2)
        
        # Debug info
        st.success(f"✅ Session data saved to: {session_file}")
        logging.info(f"Session data saved successfully to {session_file}")
        
    except Exception as e:
        st.error(f"❌ Error saving session data: {str(e)}")
        logging.error(f"Error saving session data: {str(e)}")

def show_session_data_info():
    """Display current session data information for debugging"""
    # st.subheader("🔍 Session Data Debug")
    
    # # Check directory status
    # st.write("**📁 Directory Status:**")
    # directories = ['incident_reports', 'suspicious_screenshots', 'session_data', 'quiz_questions']
    # col1, col2 = st.columns(2)
    # with col1:
    #     for i, directory in enumerate(directories[:2]):
    #         if os.path.exists(directory):
    #             st.success(f"✅ {directory}")
    #         else:
    #             st.error(f"❌ {directory}")
    # with col2:
    #     for i, directory in enumerate(directories[2:]):
    #         if os.path.exists(directory):
    #             st.success(f"✅ {directory}")
    #         else:
    #             st.error(f"❌ {directory}")
    
    # # Show current session state values
    # st.write("**Current Session State:**")
    # st.json({
    #     "session_id": st.session_state.session_id,
    #     "student_data": st.session_state.student_data,
    #     "exam_started": st.session_state.exam_started,
    #     "exam_start_time": st.session_state.get('exam_start_time', 'Not set'),
    #     "incident_counter": st.session_state.incident_counter,
    #     "quiz_completed": st.session_state.quiz_completed,
    #     "quiz_answers_count": len(st.session_state.quiz_answers),
    #     "quiz_score": st.session_state.quiz_score
    # })
    
    # # Check if session file exists and show its contents
    # session_file = f"session_data/session_{st.session_state.session_id}.json"
    # if os.path.exists(session_file):
    #     st.success(f"✅ Session file exists: {session_file}")
    #     try:
    #         with open(session_file, 'r') as f:
    #             file_contents = json.load(f)
    #         st.write("**File Contents:**")
    #         st.json(file_contents)
    #     except Exception as e:
    #         st.error(f"Error reading file: {e}")
    # else:
    #     st.warning(f"⚠️ Session file not found: {session_file}")
    #     # Try to list what files are in the session_data directory
    #     if os.path.exists('session_data'):
    #         files = os.listdir('session_data')
    #         st.write(f"Files in session_data directory: {files}")
    #     else:
    #         st.error("session_data directory doesn't exist!")

def enrollment_screen():
    st.title("📚 Student Enrollment")
    st.subheader("Enter your details to begin the proctored exam")
    
    with st.form("enrollment_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            name = st.text_input("👤 Student Name", value=st.session_state.student_data['name'], placeholder="Enter your full name")
            department = st.text_input("🏢 Department", value=st.session_state.student_data['department'], placeholder="e.g., Computer Science")
        
        with col2:
            roll_number = st.text_input("🎓 Roll Number", value=st.session_state.student_data['roll_number'], placeholder="Enter your roll number")
            st.write("")  # Spacer
        
        # Terms and conditions
        agree_terms = st.checkbox("I agree to the exam terms and conditions and understand that this session will be monitored")
        
        submitted = st.form_submit_button("🚀 Start Proctored Exam", type="primary", use_container_width=True)
        
        if submitted:
            if name and roll_number and department and agree_terms:
                st.session_state.student_data['name'] = name
                st.session_state.student_data['roll_number'] = roll_number
                st.session_state.student_data['department'] = department
                st.session_state.exam_started = True
                st.session_state.exam_start_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                # Add to active students list
                student_info = {
                    "name": name,
                    "roll_number": roll_number,
                    "department": department,
                    "session_id": st.session_state.session_id,
                    "start_time": st.session_state.exam_start_time
                }
                st.session_state.current_students.append(student_info)
                
                # Save initial session data when exam starts
                save_session_data()
                
                log_event("Exam session started", "INFO")
                st.success("✅ Registration successful! Starting your exam...")
                time.sleep(1)
                st.rerun()
            elif not agree_terms:
                st.error("❌ Please agree to the terms and conditions to proceed")
            else:
                st.error("❌ Please fill all required fields")
    
    # Instructions
    with st.expander("📋 Exam Instructions"):
        st.write("""
        **Important Guidelines:**
        - Ensure you are in a well-lit room
        - Keep your face visible to the camera at all times
        - Do not look away from the screen frequently
        - Ensure no other person is visible in the camera
        - Do not use any unauthorized materials
        - Complete all questions before submitting
        - Any suspicious activity will be recorded and flagged
        """)
    
    # Technical requirements
    with st.expander("💻 Technical Requirements"):
        st.write("""
        **System Requirements:**
        - Working webcam and microphone
        - Stable internet connection
        - Updated web browser
        - Camera permissions enabled
        - Adequate lighting in the room
        """)

def display_quiz():
    """Display quiz with dynamic questions and better flow (bugfixed)"""
    quiz_questions = load_quiz_questions()
    
    if not quiz_questions:
        st.warning("No quiz questions available. Please contact the administrator.")
        return
    
    st.subheader("📋 Quiz Questions")
    
    if st.session_state.quiz_completed:
        # Show results if quiz is completed
        score, total = st.session_state.quiz_score
        percentage = (score / total) * 100 if total > 0 else 0
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Score", f"{score}/{total}")
        with col2:
            st.metric("Percentage", f"{percentage:.1f}%")
        with col3:
            if percentage >= 70:
                st.metric("Result", "✅ PASS")
            else:
                st.metric("Result", "❌ FAIL")
        
        # Show detailed results
        with st.expander("View Detailed Results"):
            for idx, q in enumerate(quiz_questions):
                user_answer = st.session_state.quiz_answers.get(f"question_{idx}", "Not Answered")
                correct_answer = q["correct"]
                is_correct = user_answer == correct_answer
                
                st.write(f"**Question {idx + 1}:** {q['question']}")
                for option in q['options']:
                    option_letter = option.split('. ')[0]
                    if option_letter == user_answer:
                        if is_correct:
                            st.write(f"✅ {option} (Your answer - Correct)")
                        else:
                            st.write(f"❌ {option} (Your answer - Incorrect)")
                    elif option_letter == correct_answer:
                        st.write(f"✅ {option} (Correct answer)")
                    else:
                        st.write(f"⚪ {option}")
                st.write("---")
        
        return
    
    # Progress bar
    total_questions = len(quiz_questions)
    # Only count answers that are valid (A/B/C/D)
    answered_questions = len([
        k for k, v in st.session_state.quiz_answers.items()
        if k.startswith('question_') and v in ['A', 'B', 'C', 'D']
    ])
    progress = answered_questions / total_questions if total_questions > 0 else 0
    
    st.progress(progress)
    st.write(f"Progress: {answered_questions}/{total_questions} questions answered")
    
    # Display questions
    for idx, q in enumerate(quiz_questions):
        with st.container():
            st.write(f"**Question {idx + 1} of {total_questions}:**")
            st.write(q['question'])
            
            # Check if question is already answered
            current_answer = st.session_state.quiz_answers.get(f"question_{idx}")
            default_index = None
            if current_answer in ['A', 'B', 'C', 'D']:
                try:
                    default_index = ord(current_answer) - ord('A')
                except:
                    default_index = None
            # Only pass index if valid, else let Streamlit use default
            radio_kwargs = {
                "label": "Select your answer:",
                "options": q["options"],
                "key": f"question_{idx}"
            }
            if default_index is not None and 0 <= default_index < len(q["options"]):
                radio_kwargs["index"] = default_index
            selected_option = st.radio(**radio_kwargs)
            
            if selected_option:
                st.session_state.quiz_answers[f"question_{idx}"] = selected_option.split(". ")[0]
            
            st.write("---")
    
    # Quiz submission section
    if answered_questions == total_questions:
        st.success("🎯 All questions answered! You can now submit your quiz.")
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🚀 Submit Quiz", type="primary", use_container_width=True):
                score, total = evaluate_quiz()
                st.session_state.quiz_completed = True
                st.session_state.quiz_score = (score, total)
                log_event(f"Quiz submitted. Score: {score}/{total}", "INFO")
                # Save session data after quiz submission
                save_session_data()
                st.rerun()
        
        with col2:
            if st.button("🔄 Review Answers", type="secondary", use_container_width=True):
                st.info("Review your answers above before submitting.")
    elif answered_questions > 0:
        st.info(f"📝 Please answer {total_questions - answered_questions} more question(s) to submit the quiz.")
    else:
        st.info("📝 Please answer all questions to submit the quiz.")

def evaluate_quiz():
    """Evaluate quiz with dynamic questions"""
    quiz_questions = load_quiz_questions()
    score = 0
    total = len(quiz_questions)
    
    for idx, q in enumerate(quiz_questions):
        user_answer = st.session_state.quiz_answers.get(f"question_{idx}", None)
        if user_answer == q["correct"]:
            score += 1
    
    return score, total

def exam_screen():
    st.title("Exam in Progress")
    st.write(f"Student: {st.session_state.student_data['name']} (Roll: {st.session_state.student_data['roll_number']}), Dept: {st.session_state.student_data['department']}")
    
    # Debug sidebar - Show current session state
    # with st.sidebar:
    #     st.subheader("📊 Session Debug Info")
    #     st.write(f"**Session ID:** {st.session_state.session_id}")
    #     st.write(f"**Incidents:** {st.session_state.incident_counter}")
    #     st.write(f"**Quiz Completed:** {st.session_state.quiz_completed}")
    #     st.write(f"**Quiz Answers:** {len(st.session_state.quiz_answers)} answers")
        
    #     # Show session data file status
    #     session_file = f"session_data/session_{st.session_state.session_id}.json"
    #     if os.path.exists(session_file):
    #         st.success("✅ Session file exists")
    #         file_size = os.path.getsize(session_file)
    #         st.write(f"File size: {file_size} bytes")
    #     else:
    #         st.warning("⚠️ Session file not found")
        
    #     # Manual save button
    #     if st.button("💾 Save Session Data Now"):
    #         save_session_data()
    #         st.rerun()
    
    # Initialize camera if not already done
    if st.session_state.cap is None:
        st.session_state.cap = cv2.VideoCapture(0)
        if not st.session_state.cap.isOpened():
            log_event("Failed to open camera. Check permissions or connection.", "WARNING")
            st.error("Camera failed to open. Please check permissions or connection.")
            st.session_state.exam_started = False
            st.rerun()
            return
    
    # Load YOLOv8 face detection model
    if st.session_state.model is None:
        try:
            st.session_state.model = YOLO("yolov8n-face.pt")
        except Exception as e:
            log_event(f"Failed to load YOLOv8 face detection model: {str(e)}", "WARNING")
            st.error("Failed to load face detection model. Ensure 'yolov8n-face.pt' is available.")
            st.session_state.exam_started = False
            st.session_state.cap.release()
            st.session_state.cap = None
            st.rerun()
            return
    
    alert_active = False
    
    # Layout: Quiz on the main screen, camera feed on bottom-right
    col1, col2 = st.columns([3, 1])
    
    with col1:
        # Display quiz
        display_quiz()
    
    with col2:
        st.write("")
        video_placeholder = st.empty()
    
    # Alert message placeholder (above the quiz and camera)
    alert_placeholder = st.empty()
    
    while st.session_state.exam_started:
        ret, frame = st.session_state.cap.read()
        if not ret:
            log_event("Failed to capture video frame", "WARNING")
            st.error("Failed to capture video frame.")
            break
            
        # Perform face detection with YOLOv8
        results = st.session_state.model(frame, conf=0.25, imgsz=640)
        faces = results[0].boxes.xyxy.cpu().numpy()
        
        current_face_count = len(faces)
        
        # Track face movement
        if len(faces) > 0:
            x1, y1, x2, y2 = faces[0]  # Use first detected face
            face_center = (x1 + x2) // 2
            frame_width = frame.shape[1]
            threshold = frame_width * 0.2
            
            if st.session_state.last_face_center is not None:
                center_diff = face_center - st.session_state.last_face_center
                if abs(center_diff) > threshold:
                    direction = "left" if center_diff < 0 else "right"
                    if not alert_active and st.session_state.last_alert != f"Student: {st.session_state.student_data['name']} (Roll: {st.session_state.student_data['roll_number']}), Dept: {st.session_state.student_data['department']} - Alert: Student moved {direction}":
                        log_event(f"Alert: Student moved {direction}", "WARNING")
                        # alert active = True
            
            st.session_state.last_face_center = face_center
        else:
            st.session_state.last_face_center = None
        
        # Multiple faces or no face check
        if current_face_count > 1:
            if not alert_active and st.session_state.last_alert != f"Student: {st.session_state.student_data['name']} (Roll: {st.session_state.student_data['roll_number']}), Dept: {st.session_state.student_data['department']} - Alert: Multiple faces detected ({current_face_count})":
                log_event(f"Alert: Multiple faces detected ({current_face_count})", "WARNING")
                alert_active = True
        elif current_face_count == 0:
            current_time = time.time()
            if 'last_face_time' not in st.session_state or current_time - st.session_state.get('last_face_time', 0) > 3:
                if not alert_active and st.session_state.last_alert != f"Student: {st.session_state.student_data['name']} (Roll: {st.session_state.student_data['roll_number']}), Dept: {st.session_state.student_data['department']} - Alert: No face detected for extended period":
                    log_event("Alert: No face detected for extended period", "WARNING")
                    alert_active = True
        else:
            if alert_active and st.session_state.last_alert != f"Student: {st.session_state.student_data['name']} (Roll: {st.session_state.student_data['roll_number']}), Dept: {st.session_state.student_data['department']} - Normal: Single face detected":
                log_event("Normal: Single face detected", "INFO")
                alert_active = False
            st.session_state.last_face_time = time.time()
        
        # Draw rectangles around faces
        for (x1, y1, x2, y2) in faces:
            cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), (0, 255, 0), 2)
        
        # Convert frame for Streamlit
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(frame_rgb)
        img = img.resize((500, 500), Image.Resampling.LANCZOS)
        
        # Update video feed in bottom-right
        video_placeholder.image(img, channels="RGB")
        
        # Display alert message for 5 seconds if active
        current_time = time.time()
        if st.session_state.alert_message and current_time < st.session_state.alert_display_until:
            alert_placeholder.markdown(f"**Warning:** {st.session_state.alert_message}", unsafe_allow_html=True)
        else:
            alert_placeholder.empty()
            st.session_state.alert_message = None
            st.session_state.alert_display_until = 0
        
        # Auto-save session data every 30 seconds
        if not hasattr(st.session_state, 'last_save_time'):
            st.session_state.last_save_time = current_time
        
        if current_time - st.session_state.last_save_time > 30:  # 30 seconds
            save_session_data()
            st.session_state.last_save_time = current_time
        
        time.sleep(0.03)
    
    # Cleanup on exam end
    if st.session_state.cap is not None:
        st.session_state.cap.release()
        st.session_state.cap = None
        st.session_state.last_face_center = None
        st.session_state.last_alert = None
        # Don't clear quiz answers and completion status
        st.session_state.model = None
        st.session_state.alert_message = None
        st.session_state.alert_display_until = 0

    # Show current session data status
    st.subheader("📄 Current Session Data")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Session ID", st.session_state.session_id)
    with col2:
        st.metric("Incidents", st.session_state.incident_counter)
    with col3:
        st.metric("Quiz Progress", f"{len(st.session_state.quiz_answers)}/3")
    with col4:
        session_file = f"session_data/session_{st.session_state.session_id}.json"
        if os.path.exists(session_file):
            st.metric("Data Status", "✅ Saved")
        else:
            st.metric("Data Status", "❌ Not Saved")

    if st.button("End Exam"):
        save_session_data()
        log_event("Exam session ended", "INFO")
        st.session_state.exam_started = False
        st.rerun()
    
    # Add option to restart quiz if completed
    if st.session_state.quiz_completed:
        st.sidebar.markdown("---")
        st.sidebar.subheader("Quiz Options")
        if st.sidebar.button("🔄 Restart Quiz"):
            st.session_state.quiz_completed = False
            st.session_state.quiz_score = None
            st.session_state.quiz_answers = {}
            log_event("Quiz restarted", "INFO")
            st.rerun()

def mode_selection_screen():
    """Screen for students to start exam"""
    st.title("📚 Exam Proctoring System")
    st.subheader("Student Portal")
    
    # Debug section - Show session data info
    with st.expander("🔧 Debug: Session Data Information"):
        show_session_data_info()
    
    # Student mode button
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.info("Click below to start your proctored exam session")
        if st.button("🎓 Start Student Exam", type="primary", use_container_width=True):
            st.session_state.mode = "student"
            st.rerun()
    
    with col2:
        st.write("")  # Spacer
    
    # Admin access (hidden/discrete)
    st.markdown("---")
    with st.expander("🔐 Administrator Access"):
        st.warning("This section is for authorized personnel only")
        admin_username = st.text_input("Username", key="admin_user")
        admin_password = st.text_input("Password", type="password", key="admin_pass")
        
        if st.button("Admin Login"):
            if admin_username == ADMIN_USERNAME and admin_password == ADMIN_PASSWORD:
                st.session_state.admin_authenticated = True
                st.session_state.mode = "invigilator"
                st.success("✅ Admin authentication successful!")
                st.rerun()
            else:
                st.error("❌ Invalid credentials")

def load_incident_reports():
    """Load all incident reports from files"""
    incidents = []
    if os.path.exists('incident_reports'):
        for filename in os.listdir('incident_reports'):
            if filename.endswith('.json'):
                filepath = os.path.join('incident_reports', filename)
                try:
                    with open(filepath, 'r') as f:
                        incident = json.load(f)
                        incidents.append(incident)
                except Exception as e:
                    st.error(f"Error loading {filename}: {e}")
    return sorted(incidents, key=lambda x: x['timestamp'], reverse=True)

def invigilator_dashboard():
    """Invigilator monitoring dashboard with live alerts and incident history"""
    # Check authentication
    if not st.session_state.admin_authenticated:
        st.error("🚫 Access Denied: Admin authentication required")
        if st.button("← Back to Main"):
            st.session_state.mode = "select"
            st.rerun()
        return
    
    st.title("🔍 Invigilator Dashboard")
    st.caption("Administrator Panel - Authorized Personnel Only")
    
    # Sidebar navigation
    st.sidebar.title("Navigation")
    
    # Handle quick navigation
    if st.session_state.get('quick_nav'):
        dashboard_option = st.session_state['quick_nav']
        st.session_state['quick_nav'] = None  # Clear after use
    else:
        dashboard_option = st.sidebar.selectbox(
            "Select View",
            ["Live Monitoring", "Question Management", "Incident History", "Session Reports", "System Settings"]
        )
    
    if dashboard_option == "Live Monitoring":
        st.header("🔴 Live Monitoring")
        
        # --- Live Student List ---
        st.subheader("👥 Live Student List")
        session_files = []
        if os.path.exists('session_data'):
            session_files = [f for f in os.listdir('session_data') if f.endswith('.json')]
        student_sessions = []
        for filename in session_files:
            filepath = os.path.join('session_data', filename)
            try:
                with open(filepath, 'r') as f:
                    session = json.load(f)
                    student_sessions.append(session)
            except:
                continue
        # Sort by start time, most recent first
        student_sessions.sort(key=lambda x: x.get('start_time', ''), reverse=True)
        if student_sessions:
            for session in student_sessions:
                status = 'Active' if session.get('end_time', 'Unknown') == 'Unknown' else 'Completed'
                status_icon = "🟢" if status == "Active" else "⚪"
                col1, col2, col3, col4, col5 = st.columns([2,2,2,2,2])
                with col1:
                    st.write(f"{status_icon} **{session['student_data']['name']}**")
                    st.caption(f"Roll: {session['student_data']['roll_number']}")
                with col2:
                    st.write(f"**Department:** {session['student_data']['department']}")
                with col3:
                    st.write(f"**Status:** {status}")
                with col4:
                    st.write(f"**Incidents:** {session.get('total_incidents', 0)}")
                with col5:
                    if status == 'Active':
                        if st.button(f"Force End", key=f"force_end_{session['session_id']}"):
                            session['end_time'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            # Save update
                            with open(os.path.join('session_data', f"session_{session['session_id']}.json"), 'w') as f:
                                json.dump(session, f, indent=2)
                            st.success(f"Session forcibly ended for {session['student_data']['name']}")
                            st.rerun()
                # Send message to student (demo: just logs message)
                if status == 'Active':
                    msg = st.text_input(f"Message to {session['student_data']['name']}", key=f"msg_{session['session_id']}")
                    if st.button(f"Send Message", key=f"sendmsg_{session['session_id']}"):
                        log_event(f"Admin message to {session['student_data']['name']}: {msg}", "INFO")
                        st.success(f"Message sent to {session['student_data']['name']}")
            st.write("---")
        else:
            st.info("No student sessions found yet.")
        
        # Current active sessions
        st.subheader("📊 Active Sessions")
        
        # Get currently active students (this would be populated when students start exams)
        active_sessions = []
        if os.path.exists('session_data'):
            for filename in os.listdir('session_data'):
                if filename.endswith('.json'):
                    filepath = os.path.join('session_data', filename)
                    try:
                        with open(filepath, 'r') as f:
                            session = json.load(f)
                            # Consider a session active if it doesn't have an end_time or end_time is recent
                            if session.get('end_time') == 'Unknown' or not session.get('end_time'):
                                active_sessions.append(session)
                            else:
                                # Check if ended in last hour (consider as recently active)
                                try:
                                    end_time = datetime.strptime(session['end_time'], "%Y-%m-%d %H:%M:%S")
                                    current_time = datetime.now()
                                    if (current_time - end_time).total_seconds() < 3600:  # Last hour
                                        session['status'] = 'Recently Ended'
                                        active_sessions.append(session)
                                except:
                                    pass
                    except Exception as e:
                        continue
        
        if active_sessions:
            for session in active_sessions:
                status = session.get('status', 'Active')
                status_icon = "🟢" if status == "Active" else "🟡"
                
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.write(f"{status_icon} **{session['student_data']['name']}**")
                    st.caption(f"Roll: {session['student_data']['roll_number']}")
                with col2:
                    st.write(f"**Department:** {session['student_data']['department']}")
                with col3:
                    incidents = session.get('total_incidents', 0)
                    if incidents > 0:
                        st.write(f"🚨 **Incidents:** {incidents}")
                    else:
                        st.write("✅ **No Incidents**")
                with col4:
                    quiz_status = "Not Started"
                    if session.get('quiz_completed'):
                        quiz_status = "Completed"
                    elif session.get('quiz_answers'):
                        quiz_status = "In Progress"
                    st.write(f"**Quiz:** {quiz_status}")
                
                st.write("---")
        else:
            st.info("No active exam sessions")
        
        # Real-time alerts section
        st.subheader("⚠️ Recent Alerts")
        if st.session_state.recent_alerts:
            st.write(f"**Total Alerts Today:** {len(st.session_state.recent_alerts)}")
            
            for alert in st.session_state.recent_alerts[:10]:  # Show last 10 alerts
                severity_color = "🔴" if alert['severity'] == "HIGH" else "🟡"
                
                with st.container():
                    col1, col2 = st.columns([1, 4])
                    with col1:
                        st.write(severity_color)
                    with col2:
                        st.write(f"**{alert['timestamp']}**")
                        st.write(f"Student: {alert['student']}")
                        st.write(f"Alert: {alert['message']}")
                    st.write("---")
        else:
            st.info("No recent alerts - All students are following exam protocols")
        
        # Live statistics
        st.subheader("📈 Live Statistics")
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Active Sessions", len([s for s in active_sessions if s.get('status', 'Active') == 'Active']))
        with col2:
            total_alerts = len(st.session_state.recent_alerts)
            st.metric("Today's Alerts", total_alerts)
        with col3:
            high_severity = len([a for a in st.session_state.recent_alerts if a['severity'] == 'HIGH'])
            st.metric("High Priority", high_severity)
        with col4:
            # Calculate completion rate
            completed = len([s for s in active_sessions if s.get('quiz_completed')])
            total = len(active_sessions) if active_sessions else 1
            completion_rate = (completed / total) * 100
            st.metric("Completion Rate", f"{completion_rate:.1f}%")
        
        # Auto-refresh controls
        st.subheader("🔄 Refresh Controls")
        col1, col2 = st.columns(2)
        
        with col1:
            auto_refresh = st.checkbox("Auto-refresh (every 5 seconds)")
            if auto_refresh:
                time.sleep(5)
                st.rerun()
        
        with col2:
            if st.button("🔄 Manual Refresh", use_container_width=True):
                st.rerun()
        
        # Quick actions
        st.subheader("⚡ Quick Actions")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if st.button("📋 View All Incidents", use_container_width=True):
                st.session_state['quick_nav'] = "Incident History"
                st.rerun()
        
        with col2:
            if st.button("📊 Generate Report", use_container_width=True):
                st.session_state['quick_nav'] = "Session Reports"
                st.rerun()
        
        with col3:
            if st.button("📝 Manage Questions", use_container_width=True):
                st.session_state['quick_nav'] = "Question Management"
                st.rerun()
    
    elif dashboard_option == "Question Management":
        question_management_interface()
    
    elif dashboard_option == "Incident History":
        st.header("📋 Incident History")
        
        incidents = load_incident_reports()
        
        if incidents:
            # Filter options
            col1, col2, col3 = st.columns(3)
            with col1:
                severity_filter = st.selectbox("Filter by Severity", ["All", "HIGH", "MEDIUM"])
            with col2:
                date_filter = st.date_input("Filter by Date", value=None)
            with col3:
                student_filter = st.text_input("Filter by Student Name")
            
            # Apply filters
            filtered_incidents = incidents
            if severity_filter != "All":
                filtered_incidents = [i for i in filtered_incidents if i.get('severity') == severity_filter]
            if date_filter:
                date_str = date_filter.strftime("%Y-%m-%d")
                filtered_incidents = [i for i in filtered_incidents if i['timestamp'].startswith(date_str)]
            if student_filter:
                filtered_incidents = [i for i in filtered_incidents if student_filter.lower() in i['student_name'].lower()]
            
            # Display incidents
            for incident in filtered_incidents:
                with st.expander(f"🚨 {incident['timestamp']} - {incident['student_name']} ({incident['severity']})"):
                    col1, col2 = st.columns([2, 1])
                    with col1:
                        st.write(f"**Student:** {incident['student_name']} (Roll: {incident['roll_number']})")
                        st.write(f"**Department:** {incident['department']}")
                        st.write(f"**Incident:** {incident['incident_type']}")
                        st.write(f"**Session ID:** {incident['session_id']}")
                        st.write(f"**Severity:** {incident['severity']}")
                    
                    with col2:
                        # Display screenshot if available
                        screenshot_path = incident.get('screenshot')
                        if screenshot_path and os.path.exists(screenshot_path):
                            try:
                                screenshot = Image.open(screenshot_path)
                                st.image(screenshot, caption="Incident Screenshot", width=200)
                            except Exception as e:
                                st.error(f"Could not load screenshot: {e}")
        else:
            st.info("No incidents recorded yet")
    
    elif dashboard_option == "Session Reports":
        st.header("📊 Session Reports")
        
        # Load session data and incidents
        session_files = []
        if os.path.exists('session_data'):
            session_files = [f for f in os.listdir('session_data') if f.endswith('.json')]
        
        incidents = load_incident_reports()
        
        if session_files:
            # Enhanced summary statistics
            total_sessions = len(session_files)
            total_incidents = len(incidents)
            
            # Calculate additional metrics
            completed_quizzes = 0
            total_quiz_score = 0
            quiz_count = 0
            
            session_data_list = []
            for session_file in session_files:
                filepath = os.path.join('session_data', session_file)
                try:
                    with open(filepath, 'r') as f:
                        session_data = json.load(f)
                        # Only append if session_data is not None and is a dict
                        if session_data and isinstance(session_data, dict):
                            session_data_list.append(session_data)
                            
                            if session_data.get('quiz_completed'):
                                completed_quizzes += 1
                            
                            if session_data.get('quiz_score'):
                                quiz_count += 1
                                total_quiz_score += session_data['quiz_score']['percentage']
                except (json.JSONDecodeError, FileNotFoundError, KeyError) as e:
                    # Log the error but continue processing other files
                    st.warning(f"Error reading session file {session_file}: {str(e)}")
                    continue
                except Exception as e:
                    # Catch any other unexpected errors
                    st.warning(f"Unexpected error reading session file {session_file}: {str(e)}")
                    continue
            
            # Display metrics
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Total Sessions", total_sessions)
            with col2:
                st.metric("Total Incidents", total_incidents)
            with col3:
                st.metric("Completed Quizzes", completed_quizzes)
            with col4:
                avg_score = total_quiz_score / quiz_count if quiz_count > 0 else 0
                st.metric("Avg Quiz Score", f"{avg_score:.1f}%")
            
            # Additional statistics
            st.subheader("📈 Detailed Analytics")
            col1, col2, col3 = st.columns(3)
            
            with col1:
                avg_incidents = total_incidents / total_sessions if total_sessions > 0 else 0
                st.metric("Avg Incidents/Session", f"{avg_incidents:.1f}")
            
            with col2:
                # Safer null checking for pass rate calculation
                pass_sessions = [s for s in session_data_list if s and isinstance(s, dict) and s.get('quiz_score', {}) and s.get('quiz_score', {}).get('status') == 'PASS']
                pass_rate = len(pass_sessions) / quiz_count * 100 if quiz_count > 0 else 0
                st.metric("Pass Rate", f"{pass_rate:.1f}%")
            
            with col3:
                # Safer null checking for high risk sessions
                high_risk_sessions = len([s for s in session_data_list if s and isinstance(s, dict) and s.get('total_incidents', 0) >= 3])
                st.metric("High Risk Sessions", high_risk_sessions)
            
            # Filter and sort options
            st.subheader("🔍 Filter & Sort")
            col1, col2, col3 = st.columns(3)
            
            with col1:
                sort_by = st.selectbox("Sort by", ["Recent First", "Oldest First", "Most Incidents", "Best Score"])
            with col2:
                filter_status = st.selectbox("Filter by Status", ["All", "Completed", "Incomplete", "High Risk"])
            with col3:
                date_filter = st.date_input("Filter by Date", value=None)
            
            # Apply filters and sorting
            filtered_sessions = session_data_list.copy()
            
            if filter_status == "Completed":
                filtered_sessions = [s for s in filtered_sessions if s.get('quiz_completed')]
            elif filter_status == "Incomplete":
                filtered_sessions = [s for s in filtered_sessions if not s.get('quiz_completed')]
            elif filter_status == "High Risk":
                filtered_sessions = [s for s in filtered_sessions if s.get('total_incidents', 0) >= 3]
            
            if date_filter:
                date_str = date_filter.strftime("%Y-%m-%d")
                filtered_sessions = [s for s in filtered_sessions if s.get('start_time', '').startswith(date_str)]
            
            # Apply sorting
            if sort_by == "Recent First":
                filtered_sessions.sort(key=lambda x: x.get('start_time', ''), reverse=True)
            elif sort_by == "Oldest First":
                filtered_sessions.sort(key=lambda x: x.get('start_time', ''))
            elif sort_by == "Most Incidents":
                filtered_sessions.sort(key=lambda x: x.get('total_incidents', 0), reverse=True)
            elif sort_by == "Best Score":
                # Safer sorting with null checking
                filtered_sessions.sort(key=lambda x: (x.get('quiz_score', {}) or {}).get('percentage', 0) if x and isinstance(x, dict) else 0, reverse=True)
            
            # Display sessions
            st.subheader(f"📋 Session Details ({len(filtered_sessions)} sessions)")
            
            for session_data in filtered_sessions:
                # Skip if session_data is None or not a dict
                if not session_data or not isinstance(session_data, dict):
                    continue
                    
                # Determine session status and color
                incidents_count = session_data.get('total_incidents', 0)
                quiz_completed = session_data.get('quiz_completed', False)
                
                if incidents_count >= 3:
                    status_icon = "🔴"
                    status_text = "High Risk"
                elif incidents_count > 0:
                    status_icon = "🟡"
                    status_text = "Moderate Risk"
                else:
                    status_icon = "🟢"
                    status_text = "Clean Session"
                
                # Safely get student data
                student_data = session_data.get('student_data', {})
                student_name = student_data.get('name', 'Unknown') if isinstance(student_data, dict) else 'Unknown'
                student_roll = student_data.get('roll_number', 'Unknown') if isinstance(student_data, dict) else 'Unknown'
                student_dept = student_data.get('department', 'Unknown') if isinstance(student_data, dict) else 'Unknown'
                session_id = session_data.get('session_id', 'Unknown')
                
                with st.expander(f"{status_icon} {student_name} - {status_text} ({session_id})"):
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.write(f"**Student:** {student_name}")
                        st.write(f"**Roll Number:** {student_roll}")
                        st.write(f"**Department:** {student_dept}")
                        st.write(f"**Session ID:** {session_id}")
                    
                    with col2:
                        st.write(f"**Start Time:** {session_data.get('start_time', 'Unknown')}")
                        st.write(f"**End Time:** {session_data.get('end_time', 'Unknown')}")
                        st.write(f"**Total Incidents:** {incidents_count}")
                        st.write(f"**Status:** {status_text}")
                    
                    # Quiz performance section
                    quiz_score_data = session_data.get('quiz_score')
                    if quiz_score_data and isinstance(quiz_score_data, dict):
                        st.subheader("📝 Quiz Performance")
                        
                        col1, col2, col3, col4 = st.columns(4)
                        with col1:
                            score = quiz_score_data.get('score', 0)
                            total = quiz_score_data.get('total', 0)
                            st.metric("Score", f"{score}/{total}")
                        with col2:
                            percentage = quiz_score_data.get('percentage', 0)
                            st.metric("Percentage", f"{percentage:.1f}%")
                        with col3:
                            status = quiz_score_data.get('status', 'Unknown')
                            st.metric("Status", status)
                        with col4:
                            percentage = quiz_score_data.get('percentage', 0)
                            grade = "A" if percentage >= 90 else "B" if percentage >= 80 else "C" if percentage >= 70 else "F"
                            st.metric("Grade", grade)
                    
                    elif quiz_completed:
                        st.info("Quiz completed (Score details not available)")
                    else:
                        st.warning("Quiz not completed")
                    
                    # Show related incidents
                    session_incidents = [inc for inc in incidents if inc.get('session_id') == session_data['session_id']]
                    if session_incidents:
                        st.subheader("⚠️ Incidents")
                        for incident in session_incidents[:3]:  # Show first 3 incidents
                            severity_color = "🔴" if incident.get('severity') == "HIGH" else "🟡"
                            st.write(f"{severity_color} {incident['timestamp']}: {incident['incident_type']}")
                        
                        if len(session_incidents) > 3:
                            st.caption(f"... and {len(session_incidents) - 3} more incidents")
                    
                    # Quiz answers if available
                    if session_data.get('quiz_answers'):
                        st.subheader("📝 Quiz Answers")
                        with st.container():
                            for q, a in session_data['quiz_answers'].items():
                                st.write(f"**{q.replace('question_', 'Question ')}:** {a}")
            
            # Export functionality
            st.subheader("📤 Export Data")
            col1, col2 = st.columns(2)
            
            with col1:
                if st.button("Export Session Data"):
                    try:
                        # Filter out any None or invalid entries before creating DataFrame
                        valid_sessions = [s for s in session_data_list if s and isinstance(s, dict)]
                        if valid_sessions:
                            df = pd.DataFrame(valid_sessions)
                            csv = df.to_csv(index=False)
                            st.download_button(
                                label="Download Sessions CSV",
                                data=csv,
                                file_name=f"session_reports_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                                mime="text/csv"
                            )
                        else:
                            st.warning("No valid session data to export")
                    except Exception as e:
                        st.error(f"Error creating CSV: {e}")
            
            with col2:
                if st.button("Export Incident Data"):
                    if incidents:
                        try:
                            df = pd.DataFrame(incidents)
                            csv = df.to_csv(index=False)
                            st.download_button(
                                label="Download Incidents CSV",
                                data=csv,
                                file_name=f"incident_reports_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                                mime="text/csv"
                            )
                        except Exception as e:
                            st.error(f"Error creating CSV: {e}")
                    else:
                        st.info("No incidents to export")
        
        else:
            st.info("📭 No session reports available yet")
            st.write("Session reports will appear here once students start taking exams.")
            
            # Show sample data structure
            with st.expander("📖 What will be shown here?"):
                st.write("Once students start taking exams, you'll see:")
                st.write("- 📊 Session statistics and analytics")
                st.write("- 👥 Individual student performance")
                st.write("- 🎯 Quiz scores and completion rates")
                st.write("- ⚠️ Incident summaries")
                st.write("- 📈 Trends and patterns")
                st.write("- 📤 Export capabilities")
    
    elif dashboard_option == "System Settings":
        st.header("⚙️ System Settings")
        
        st.subheader("Detection Sensitivity")
        sensitivity = st.slider("Face Movement Threshold", 0.1, 0.5, 0.2, 0.05)
        st.write(f"Current threshold: {sensitivity}")
        
        st.subheader("Alert Settings")
        alert_duration = st.number_input("Alert Display Duration (seconds)", 1, 30, 5)
        
        st.subheader("Data Management")
        if st.button("Export All Incident Reports"):
            # This would export all incidents to a CSV file
            incidents = load_incident_reports()
            if incidents:
                # Convert to DataFrame for easy export
                try:
                    df = pd.DataFrame(incidents)
                    csv = df.to_csv(index=False)
                    st.download_button(
                        label="Download CSV",
                        data=csv,
                        file_name=f"incident_reports_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                        mime="text/csv"
                    )
                except Exception as e:
                    st.error(f"Error creating CSV: {e}")
            else:
                st.info("No incidents to export")
        
        if st.button("Clear Old Data"):
            st.warning("This will delete all incident reports and screenshots older than 30 days")
            # Implementation for clearing old data would go here
    
    # Back to mode selection and logout
    st.sidebar.markdown("---")
    st.sidebar.subheader("👤 Admin Controls")
    
    col1, col2 = st.sidebar.columns(2)
    with col1:
        if st.button("🏠 Main Menu"):
            st.session_state.mode = "select"
            st.rerun()
    
    with col2:
        if st.button("🚪 Logout"):
            st.session_state.admin_authenticated = False
            st.session_state.mode = "select"
            st.success("Logged out successfully!")
            st.rerun()

def load_quiz_questions():
    """Load quiz questions from file or return default questions"""
    questions_file = 'quiz_questions/current_quiz.json'
    if os.path.exists(questions_file):
        try:
            with open(questions_file, 'r') as f:
                questions = json.load(f)
                return questions
        except Exception as e:
            st.error(f"Error loading quiz questions: {e}")
    
    # Return default questions if file doesn't exist
    return QUIZ_QUESTIONS

def save_quiz_questions(questions):
    """Save quiz questions to file"""
    questions_file = 'quiz_questions/current_quiz.json'
    try:
        with open(questions_file, 'w') as f:
            json.dump(questions, f, indent=2)
        return True
    except Exception as e:
        st.error(f"Error saving quiz questions: {e}")
        return False

def question_management_interface():
    """Interface for managing quiz questions"""
    st.header("📝 Question Management")
    
    # Load current questions
    current_questions = load_quiz_questions()
    
    # Add new question section
    st.subheader("Add New Question")
    with st.form("add_question_form"):
        new_question = st.text_area("Question Text", placeholder="Enter your question here...")
        
        col1, col2 = st.columns(2)
        with col1:
            option_a = st.text_input("Option A", placeholder="First option")
            option_c = st.text_input("Option C", placeholder="Third option")
        with col2:
            option_b = st.text_input("Option B", placeholder="Second option")
            option_d = st.text_input("Option D", placeholder="Fourth option")
        
        correct_answer = st.selectbox("Correct Answer", ["A", "B", "C", "D"])
        
        if st.form_submit_button("Add Question"):
            if new_question and option_a and option_b and option_c and option_d:
                new_q = {
                    "question": new_question,
                    "options": [f"A. {option_a}", f"B. {option_b}", f"C. {option_c}", f"D. {option_d}"],
                    "correct": correct_answer
                }
                current_questions.append(new_q)
                if save_quiz_questions(current_questions):
                    st.success("Question added successfully!")
                    st.rerun()
            else:
                st.error("Please fill all fields")
    
    # Display and manage existing questions
    st.subheader("Current Questions")
    if current_questions:
        for idx, q in enumerate(current_questions):
            with st.expander(f"Question {idx + 1}: {q['question'][:50]}..."):
                col1, col2 = st.columns([3, 1])
                
                with col1:
                    st.write(f"**Question:** {q['question']}")
                    for option in q['options']:
                        is_correct = option.startswith(q['correct'])
                        if is_correct:
                            st.write(f"✅ {option}")
                        else:
                            st.write(f"❌ {option}")
                
                with col2:
                    if st.button("Delete", key=f"delete_{idx}"):
                        current_questions.pop(idx)
                        if save_quiz_questions(current_questions):
                            st.success("Question deleted!")
                            st.rerun()
                    
                    if st.button("Edit", key=f"edit_{idx}"):
                        st.session_state[f'editing_{idx}'] = True
                        st.rerun()
                
                # Edit form for this question
                if st.session_state.get(f'editing_{idx}', False):
                    with st.form(f"edit_form_{idx}"):
                        edited_question = st.text_area("Edit Question", value=q['question'])
                        
                        # Extract current options
                        current_options = [opt.split('. ', 1)[1] for opt in q['options']]
                        
                        col1_edit, col2_edit = st.columns(2)
                        with col1_edit:
                            edit_a = st.text_input("Option A", value=current_options[0])
                            edit_c = st.text_input("Option C", value=current_options[2])
                        with col2_edit:
                            edit_b = st.text_input("Option B", value=current_options[1])
                            edit_d = st.text_input("Option D", value=current_options[3])
                        
                        edit_correct = st.selectbox("Correct Answer", ["A", "B", "C", "D"], 
                                                  index=["A", "B", "C", "D"].index(q['correct']))
                        
                        col_save, col_cancel = st.columns(2)
                        with col_save:
                            if st.form_submit_button("Save Changes"):
                                current_questions[idx] = {
                                    "question": edited_question,
                                    "options": [f"A. {edit_a}", f"B. {edit_b}", f"C. {edit_c}", f"D. {edit_d}"],
                                    "correct": edit_correct
                                }
                                if save_quiz_questions(current_questions):
                                    st.session_state[f'editing_{idx}'] = False
                                    st.success("Question updated!")
                                    st.rerun()
                        
                        with col_cancel:
                            if st.form_submit_button("Cancel"):
                                st.session_state[f'editing_{idx}'] = False
                                st.rerun()
    else:
        st.info("No questions available. Add some questions to get started.")
    
    # Preview Quiz Section
    st.subheader("📋 Preview Current Quiz")
    if current_questions:
        if st.button("Preview Quiz"):
            st.session_state['preview_mode'] = True
        
        if st.session_state.get('preview_mode', False):
            st.markdown("**Preview Mode - Test your questions:**")
            with st.container():
                for idx, q in enumerate(current_questions):
                    st.write(f"**Question {idx + 1}:** {q['question']}")
                    for option in q['options']:
                        is_correct = option.startswith(q['correct'])
                        if is_correct:
                            st.write(f"✅ {option} (Correct Answer)")
                        else:
                            st.write(f"⚪ {option}")
                    st.write("---")
            
            if st.button("Close Preview"):
                st.session_state['preview_mode'] = False
                st.rerun()
    else:
        st.info("No questions to preview. Add some questions first.")
    
    # Bulk operations
    st.subheader("Bulk Operations")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("Reset to Default Questions"):
            if save_quiz_questions(QUIZ_QUESTIONS):
                st.success("Questions reset to default!")
                st.rerun()
    
    with col2:
        if st.button("Clear All Questions"):
            if save_quiz_questions([]):
                st.success("All questions cleared!")
                st.rerun()
    
    with col3:
        if current_questions:
            # Export questions as JSON
            questions_json = json.dumps(current_questions, indent=2)
            st.download_button(
                label="Export Questions",
                data=questions_json,
                file_name=f"quiz_questions_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                mime="application/json"
            )

# Main Streamlit app
st.set_page_config(
    page_title="Exam Proctoring System",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="auto"
)

# Add some custom CSS for better styling
st.markdown("""
<style>
    .main-header {
        text-align: center;
        color: #1f77b4;
        margin-bottom: 2rem;
    }
    .success-box {
        padding: 1rem;
        border-radius: 0.5rem;
        background-color: #d4edda;
        border: 1px solid #c3e6cb;
        color: #155724;
    }
    .warning-box {
        padding: 1rem;
        border-radius: 0.5rem;
        background-color: #fff3cd;
        border: 1px solid #ffeaa7;
        color: #856404;
    }
</style>
""", unsafe_allow_html=True)

if st.session_state.mode == "select":
    mode_selection_screen()
elif st.session_state.mode == "student":
    if not st.session_state.exam_started:
        enrollment_screen()
    else:
        exam_screen()
elif st.session_state.mode == "invigilator":
    invigilator_dashboard()