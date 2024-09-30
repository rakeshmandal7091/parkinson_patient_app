from fastapi import FastAPI, Depends, Request, Form, File, UploadFile
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from db import get_db
from models import Patient
import requests
from passlib.context import CryptContext
from fastapi.responses import RedirectResponse, HTMLResponse
from starlette.status import HTTP_303_SEE_OTHER
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from datetime import datetime
from models import FinalReport
from models import Notification
app = FastAPI()

# Mount the static directory
app.mount("/static", StaticFiles(directory="static"), name="static")

# Add session middleware
app.add_middleware(SessionMiddleware, secret_key="your_secret_key")

templates = Jinja2Templates(directory="templates")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Hash a password
def hash_password(password: str) -> str:
    return pwd_context.hash(password)

# Verify a password
def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

# Function to get user logged in status
def get_user_logged_in_status(request: Request) -> bool:
    return request.session.get('user_id') is not None

# Root Page (Homepage)
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    user_logged_in = get_user_logged_in_status(request)
    return templates.TemplateResponse("home.html", {"request": request, "user_logged_in": user_logged_in})

# Signup Page
@app.get("/signup", response_class=HTMLResponse)
def signup_page(request: Request):
    user_logged_in = get_user_logged_in_status(request)
    return templates.TemplateResponse("signup.html", {"request": request, "user_logged_in": user_logged_in})

@app.post("/signup")
def signup(
    request: Request, 
    username: str = Form(...), 
    password: str = Form(...), 
    email: str = Form(...), 
    db: Session = Depends(get_db)
):
    hashed_password = hash_password(password)
    patient = Patient(username=username, password=hashed_password, email=email)
    db.add(patient)
    db.commit()
    db.refresh(patient)
    return RedirectResponse(url="/login", status_code=HTTP_303_SEE_OTHER)

# Login Page
@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    flash_message = request.session.get('flash_message', None)
    request.session.pop('flash_message', None)  # Remove the message after displaying it
    user_logged_in = get_user_logged_in_status(request)
    return templates.TemplateResponse("login.html", {"request": request, "user_logged_in": user_logged_in, "flash_message": flash_message})

@app.post("/login")
def login(
    request: Request, 
    username: str = Form(...), 
    password: str = Form(...), 
    db: Session = Depends(get_db)
):
    patient = db.query(Patient).filter(Patient.username == username).first()
    if not patient or not verify_password(password, patient.password):
        request.session['flash_message'] = "Invalid username or password"
        return RedirectResponse(url="/login", status_code=HTTP_303_SEE_OTHER)
    
    # Create a session
    request.session['user_id'] = patient.id
    return RedirectResponse(url="/dashboard", status_code=HTTP_303_SEE_OTHER)

# Dashboard Page
@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    if not get_user_logged_in_status(request):
        return RedirectResponse(url="/login", status_code=HTTP_303_SEE_OTHER)

    try:
        # Fetch doctors from the doctor app running on port 5001
        response = requests.get("http://localhost:5001/doctors")
        doctors = response.json()
    except requests.RequestException:
        doctors = []

    patient_id = request.session.get('user_id')
    notifications = db.query(Notification).filter(Notification.patient_id == patient_id).all()

    user_logged_in = get_user_logged_in_status(request)
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "doctors": doctors,
        "user_logged_in": user_logged_in,
        "notifications": notifications
    })


# Send Report to Doctor Page
@app.get("/send-report", response_class=HTMLResponse)
def send_report_page(request: Request):
    doctor_id = request.query_params.get("doctor_id")
    user_logged_in = get_user_logged_in_status(request)
    return templates.TemplateResponse("send_report.html", {"request": request, "doctor_id": doctor_id, "user_logged_in": user_logged_in})

@app.post("/send-report")
async def send_report(
    request: Request,
    doctor_id: int = Form(...),
    report: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    # Read the file contents
    file_content = await report.read()
    patient_id = request.session.get('user_id')
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    patient_name = patient.username  # Updated to `username` since `name` might not be a field in `Patient`

    # Send the report to the doctor
    try:
        response = requests.post(
            "http://localhost:5001/receive-report",
            data={
                "doctor_id": doctor_id,
                "patient_name": patient_name,
                "date": datetime.now().isoformat()
            },
            files={"report": ("report", file_content, "application/octet-stream")}
        )
        response.raise_for_status()
    except requests.RequestException:
        return {"error": "Failed to send report"}

    return RedirectResponse(url="/dashboard", status_code=HTTP_303_SEE_OTHER)


# Profile Page
@app.get("/profile", response_class=HTMLResponse)
def profile(request: Request, db: Session = Depends(get_db)):
    if not get_user_logged_in_status(request):
        return RedirectResponse(url="/login", status_code=HTTP_303_SEE_OTHER)

    patient_id = request.session.get('user_id')
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    user_logged_in = get_user_logged_in_status(request)
    return templates.TemplateResponse("profile.html", {"request": request, "patient": patient, "user_logged_in": user_logged_in})

# Logout
@app.get("/logout")
def logout(request: Request):
    request.session.pop('user_id', None)
    return RedirectResponse(url="/login", status_code=HTTP_303_SEE_OTHER)

from fastapi import FastAPI, HTTPException

from pydantic import BaseModel
class ReportData(BaseModel):
    id: int
    report: str

@app.post("/receive_report")
async def receive_report(report_data: ReportData):
    # Here you would store the report and possibly create a notification
    # For example, adding to the Notification model
    # notification = Notification(
    #     doctor_id=<doctor_id>,
    #     patient_id=report_data.id,
    #     patient_name=<patient_name>,
    #     date=datetime.utcnow(),
    #     report=report_data.report
    # )
    # db.add(notification)
    # db.commit()
    return {"message": "Report received successfully"}

