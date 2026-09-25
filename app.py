
import os
import re
import json
from functools import wraps
from pathlib import Path
from uuid import UUID, uuid4

from dotenv import load_dotenv
from flask import (
    Flask,
    flash,
    redirect,
    render_template,
    request,
    jsonify,
    send_file,
    session,
    url_for,
)
from flask_session import Session
from supabase import create_client
from werkzeug.utils import secure_filename

from models.keyword_extractor import extract_keywords
from models.mindmap_generator import generate_mindmap
from models.mindmap_visualizer import build_mindmap_data
from models.lecture_qa import answer_question
from models.quiz_generator import generate_quiz
from models.quiz_generator import generate_targeted_quiz
from models.revision_engine import build_revision_recommendations
from models.speech_to_text import convert_audio_to_text


# =========================================================
# CONFIGURATION
# =========================================================

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent

UPLOAD_FOLDER = BASE_DIR / "uploads"
TRANSCRIPT_FOLDER = BASE_DIR / "transcripts"
KEYWORD_FOLDER = BASE_DIR / "keywords"

ALLOWED_EXTENSIONS = {"mp3", "wav"}

VALID_ROLES = {"Student", "Lecturer", "Admin"}

EMAIL_PATTERN = re.compile(
    r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
)


app = Flask(__name__)

app.config.update(
    SECRET_KEY=os.getenv("FLASK_SECRET_KEY", ""),
    MAX_CONTENT_LENGTH=100 * 1024 * 1024,

    SESSION_TYPE="filesystem",
    SESSION_FILE_DIR=str(
        BASE_DIR / "instance" / "flask_session"
    ),
    SESSION_PERMANENT=False,

    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=False,
)


for folder in [
    UPLOAD_FOLDER,
    TRANSCRIPT_FOLDER,
    KEYWORD_FOLDER,
]:
    folder.mkdir(
        parents=True,
        exist_ok=True
    )


(BASE_DIR / "instance" / "flask_session").mkdir(
    parents=True,
    exist_ok=True
)

Session(app)


# =========================================================
# SUPABASE
# =========================================================

def get_supabase():

    url = os.getenv("SUPABASE_URL")

    key = (
        os.getenv("SUPABASE_PUBLISHABLE_KEY")
        or os.getenv("SUPABASE_ANON_KEY")
    )

    if not url or not key:
        raise RuntimeError(
            "Supabase configuration is missing."
        )

    return create_client(
        url,
        key
    )

def get_authenticated_supabase():

    access_token = session.get("access_token")
    refresh_token = session.get("refresh_token")

    if not access_token or not refresh_token:
        return None

    try:
        client = get_supabase()

        client.auth.set_session(
            access_token,
            refresh_token
        )

        return client

    except Exception:

        app.logger.exception(
            "Could not restore Supabase session."
        )

        return None

def is_valid_uuid(value):
    try:
        UUID(str(value))
        return True
    except (TypeError, ValueError):
        return False


def get_owned_lecture(client, user_id, lecture_id):
    """Fetch a lecture only when it belongs to the authenticated user."""
    if not is_valid_uuid(lecture_id):
        return None
    result = (
        client.table("lectures").select("*")
        .eq("id", lecture_id).eq("user_id", user_id).single().execute()
    )
    return result.data

    try:

        client = get_supabase()

        client.auth.set_session(
            access_token,
            refresh_token
        )

        return client

    except Exception:

        app.logger.exception(
            "Could not restore Supabase session."
        )

        return None


# =========================================================
# CURRENT USER PROFILE
# =========================================================

def get_current_profile():

    user_id = session.get(
        "user_id"
    )

    if not user_id:
        return None

    client = get_authenticated_supabase()

    if not client:
        return None

    try:

        result = (
            client
            .table("profiles")
            .select(
                "id,name,email,role,created_at"
            )
            .eq(
                "id",
                user_id
            )
            .single()
            .execute()
        )

        profile = result.data

        if not profile:
            return None

        role = str(
            profile.get("role", "")
        ).strip()

        if role not in VALID_ROLES:
            return None

        profile["role"] = role

        return profile

    except Exception:

        app.logger.exception(
            "Could not retrieve user profile."
        )

        return None


# =========================================================
# ROLE GUARD
# =========================================================

def role_required(*allowed_roles):

    def decorator(function):

        @wraps(function)
        def wrapper(*args, **kwargs):

            profile = get_current_profile()

            # No valid login
            if profile is None:

                session.clear()

                return redirect(
                    url_for("login_page")
                )


            current_role = profile["role"]


            # Role is NOT allowed
            if current_role not in allowed_roles:

                # ADMIN ALWAYS GOES TO ADMIN PAGE
                if current_role == "Admin":

                    return redirect(
                        url_for("admin_dashboard")
                    )

                # Student/Lecturer
                return redirect(
                    url_for("dashboard")
                )


            return function(
                profile,
                *args,
                **kwargs
            )

        return wrapper

    return decorator


# =========================================================
# HOME
# =========================================================

@app.route("/")
def home():

    profile = get_current_profile()

    if profile:

        if profile["role"] == "Admin":

            return redirect(
                url_for("admin_dashboard")
            )

        return redirect(
            url_for("dashboard")
        )

    return render_template(
        "home.html"
    )


# =========================================================
# LOGIN PAGE
# =========================================================

@app.route(
    "/login",
    methods=["GET"]
)
def login_page():

    profile = get_current_profile()

    if profile:

        if profile["role"] == "Admin":

            return redirect(
                url_for("admin_dashboard")
            )

        return redirect(
            url_for("dashboard")
        )

    return render_template(
        "login.html"
    )


# =========================================================
# LOGIN
# =========================================================

@app.route(
    "/login",
    methods=["POST"]
)
def check_login():

    email = (
        request.form
        .get("email", "")
        .strip()
        .lower()
    )

    password = request.form.get(
        "password",
        ""
    )


    if not email or not password:

        flash(
            "Please enter email and password.",
            "error"
        )

        return redirect(
            url_for("login_page")
        )


    try:

        client = get_supabase()

        response = client.auth.sign_in_with_password(
            {
                "email": email,
                "password": password,
            }
        )


        if (
            not response.user
            or not response.session
        ):

            raise ValueError(
                "Invalid Supabase session."
            )


        # Start fresh session
        session.clear()


        session["user_id"] = (
            response.user.id
        )

        session["access_token"] = (
            response.session.access_token
        )

        session["refresh_token"] = (
            response.session.refresh_token
        )


        # IMPORTANT:
        # Get actual role from database
        profile = get_current_profile()


        if not profile:

            session.clear()

            flash(
                "Your account profile was not found.",
                "error"
            )

            return redirect(
                url_for("login_page")
            )


        role = profile["role"]


        # =================================================
        # ADMIN
        # =================================================

        if role == "Admin":

            return redirect(
                url_for("admin_dashboard")
            )


        # =================================================
        # STUDENT / LECTURER
        # =================================================

        if role in {
            "Student",
            "Lecturer"
        }:

            return redirect(
                url_for("dashboard")
            )


        session.clear()

        flash(
            "Invalid account role.",
            "error"
        )

        return redirect(
            url_for("login_page")
        )


    except Exception:

        app.logger.exception(
            "LOGIN ERROR"
        )

        session.clear()

        flash(
            "Invalid email or password.",
            "error"
        )

        return redirect(
            url_for("login_page")
        )


# =========================================================
# REGISTER
# =========================================================

@app.route(
    "/register",
    methods=["GET"]
)
def register_page():

    return render_template(
        "register.html"
    )


@app.route(
    "/register",
    methods=["POST"]
)
def register():

    name = (
        request.form
        .get("name", "")
        .strip()
    )

    email = (
        request.form
        .get("email", "")
        .strip()
        .lower()
    )

    password = request.form.get(
        "password",
        ""
    )

    confirm_password = request.form.get(
        "confirm_password",
        ""
    )

    role = request.form.get(
        "role",
        ""
    )


    if not name or not EMAIL_PATTERN.fullmatch(email):

        flash(
            "Enter a valid name and email.",
            "error"
        )

        return redirect(
            url_for("register_page")
        )


    if len(password) < 8:

        flash(
            "Password must contain at least 8 characters.",
            "error"
        )

        return redirect(
            url_for("register_page")
        )


    if password != confirm_password:

        flash(
            "Passwords do not match.",
            "error"
        )

        return redirect(
            url_for("register_page")
        )


    # NEVER allow Admin through public registration
    if role not in {
        "Student",
        "Lecturer"
    }:

        flash(
            "Only Student or Lecturer accounts can register.",
            "error"
        )

        return redirect(
            url_for("register_page")
        )


    try:

        get_supabase().auth.sign_up(
            {
                "email": email,
                "password": password,
                "options": {
                    "data": {
                        "name": name,
                        "role": role,
                    }
                },
            }
        )

        flash(
            "Registration successful. Check your email and then log in.",
            "info"
        )

        return redirect(
            url_for("login_page")
        )


    except Exception:

        app.logger.exception(
            "Registration failed."
        )

        flash(
            "Could not create the account.",
            "error"
        )

        return redirect(
            url_for("register_page")
        )


# =========================================================
# LOGOUT
# =========================================================

@app.route("/logout")
def logout():

    client = get_authenticated_supabase()

    if client:

        try:
            client.auth.sign_out()
        except Exception:
            pass

    session.clear()

    return redirect(
        url_for("login_page")
    )


# =========================================================
# STUDENT / LECTURER DASHBOARD
# =========================================================

@app.route("/dashboard")
@role_required(
    "Student",
    "Lecturer"
)
def dashboard(profile):

    return render_template(
        "dashboard.html",
        profile=profile
    )


@app.route("/performance")
@role_required("Student")
def performance(profile):
    stats = {"lectures_processed": 0, "quizzes_attempted": 0, "average_score": 0, "questions_answered": 0}
    attempts = []
    topic_accuracy = []
    revision_recommendations = []
    try:
        client = get_authenticated_supabase()
        lectures = (client.table("lectures").select("id,title,subject,transcript,keywords")
                .eq("user_id", profile["id"]).execute())
        lecture_rows = lectures.data or []
        stats["lectures_processed"] = len(lecture_rows)
        result = (client.table("quiz_attempts")
                  .select("id,lecture_id,score,total_questions,correct_answers,percentage,answers,created_at,lectures(title,subject)")
                  .eq("user_id", profile["id"]).order("created_at", desc=True).execute())
        attempts = result.data or []
        if attempts:
            stats["quizzes_attempted"] = len(attempts)
            stats["average_score"] = round(sum(float(item.get("percentage") or 0) for item in attempts) / len(attempts))
            stats["questions_answered"] = sum(int(item.get("total_questions") or 0) for item in attempts)

            # Concept accuracy is derived only from submitted answers containing quiz metadata.
            topic_totals = {}
            for attempt in attempts:
                for answer in attempt.get("answers") or []:
                    concept = answer.get("concept")
                    if concept:
                        record = topic_totals.setdefault(concept, [0, 0])
                        record[0] += 1
                        record[1] += int(bool(answer.get("is_correct")))
            topic_accuracy = [{"concept": key, "percentage": round(value[1] * 100 / value[0])}
                              for key, value in topic_totals.items()]
        revision_recommendations = build_revision_recommendations(attempts, lecture_rows)
    except Exception:
        app.logger.exception("Could not load performance data.")
        flash("Performance data is unavailable until the quiz schema has been installed.", "error")
    return render_template("performance.html", profile=profile, stats=stats, attempts=attempts[:10],
                           topic_accuracy=topic_accuracy, revision_recommendations=revision_recommendations)
@app.route("/history")
@role_required("Student", "Lecturer")
def lecture_history(profile):
    lectures = []

    try:
        client = get_authenticated_supabase()

        result = (
            client.table("lectures")
            .select(
                "id,title,subject,audio_filename,processing_status,created_at"
            )
            .eq("user_id", profile["id"])
            .order("created_at", desc=True)
            .execute()
        )

        lectures = result.data or []

    except Exception:
        app.logger.exception("Could not load lecture history.")
        flash("Could not load lecture history.", "error")

    return render_template(
        "history.html",
        profile=profile,
        lectures=lectures
    )
@app.route("/lecture/<lecture_id>")
@role_required("Student", "Lecturer")
def view_lecture(profile, lecture_id):
    try:
        client = get_authenticated_supabase()
        lecture = get_owned_lecture(client, profile["id"], lecture_id)

        if not lecture:
            flash("Lecture not found.", "error")
            return redirect(url_for("lecture_history"))

        mindmap_keywords = list(lecture.get("keywords") or [])
        selected_concept = request.args.get("concept", "").strip()
        if selected_concept and not any(str(item).casefold() == selected_concept.casefold() for item in mindmap_keywords):
            mindmap_keywords.append(selected_concept)
        return render_template(
            "lecture_view.html",
            profile=profile,
            lecture=lecture,
            mindmap_data=build_mindmap_data(lecture.get("title"), lecture.get("transcript"), mindmap_keywords),
            selected_concept=selected_concept,
        )

    except Exception:
        app.logger.exception("Could not load lecture.")
        flash("Could not load the lecture.", "error")
        return redirect(url_for("lecture_history"))


@app.route("/lecture/<lecture_id>/ask", methods=["POST"])
@role_required("Student")
def ask_lecture(profile, lecture_id):
    question = request.form.get("question", "").strip()
    if not question or len(question) > 500:
        return jsonify({"error": "Enter a question of up to 500 characters."}), 400
    try:
        lecture = get_owned_lecture(get_authenticated_supabase(), profile["id"], lecture_id)
        if not lecture:
            return jsonify({"error": "Lecture not found."}), 404
        response = answer_question(lecture.get("transcript"), question)
        return jsonify(response)
    except Exception:
        app.logger.exception("Lecture Q&A failed.")
        return jsonify({"error": "Could not search this lecture right now."}), 500


@app.route("/lecture/<lecture_id>/quiz")
@role_required("Student")
def take_quiz(profile, lecture_id):
    try:
        client = get_authenticated_supabase()
        lecture = get_owned_lecture(client, profile["id"], lecture_id)
        if not lecture:
            flash("Lecture not found.", "error")
            return redirect(url_for("lecture_history"))
        existing = (client.table("quizzes").select("id,title,questions")
                    .eq("lecture_id", lecture_id).order("created_at", desc=True).limit(1).execute()).data or []
        if existing and (existing[0].get("questions") or [{}])[0].get("generation_version") == 4:
            quiz = existing[0]
        else:
            questions = generate_quiz(lecture.get("transcript"), lecture.get("keywords") or [])
            saved = client.table("quizzes").insert({"lecture_id": lecture_id, "title": lecture.get("title"), "questions": questions}).execute()
            quiz = saved.data[0]
        return render_template("quiz.html", profile=profile, lecture=lecture, quiz=quiz)
    except ValueError as error:
        flash(str(error), "error")
    except Exception:
        app.logger.exception("Quiz generation failed.")
        flash("Could not prepare a lecture quiz. Confirm the quiz database schema is installed.", "error")
    return redirect(url_for("view_lecture", lecture_id=lecture_id))


@app.route("/lecture/<lecture_id>/practice")
@role_required("Student")
def practice_concept(profile, lecture_id):
    concept = request.args.get("concept", "").strip()
    if not concept or len(concept) > 200:
        flash("Choose a revision concept first.", "error")
        return redirect(url_for("performance"))
    try:
        client = get_authenticated_supabase()
        lecture = get_owned_lecture(client, profile["id"], lecture_id)
        if not lecture:
            flash("Lecture not found.", "error")
            return redirect(url_for("performance"))

        graph = build_mindmap_data(lecture.get("title"), lecture.get("transcript"), lecture.get("keywords") or [])
        node = next((item for item in graph.get("nodes", [])[1:]
                     if str(item.get("label", "")).casefold() == concept.casefold()), None)
        if not node:
            flash("That revision concept is not available for this lecture.", "error")
            return redirect(url_for("performance"))

        previous_quizzes = (client.table("quizzes").select("questions")
                            .eq("lecture_id", lecture_id).execute()).data or []
        previous_questions = [question for quiz in previous_quizzes
                              for question in (quiz.get("questions") or [])
                              if str(question.get("concept", "")).casefold() == concept.casefold()]
        questions = generate_targeted_quiz(
            lecture.get("transcript"), node.get("label"), lecture.get("keywords") or [],
            previous_questions=previous_questions,
        )
        saved = client.table("quizzes").insert({
            "lecture_id": lecture_id,
            "title": f"{lecture.get('title') or 'Lecture'} - Practice: {node.get('label')}",
            "questions": questions,
        }).execute()
        return render_template("quiz.html", profile=profile, lecture=lecture, quiz=saved.data[0])
    except ValueError as error:
        flash(str(error), "error")
    except Exception:
        app.logger.exception("Targeted practice generation failed.")
        flash("Could not prepare targeted practice.", "error")
    return redirect(url_for("performance"))


@app.route("/quiz/<quiz_id>/submit", methods=["POST"])
@role_required("Student")
def submit_quiz(profile, quiz_id):
    if not is_valid_uuid(quiz_id):
        flash("Invalid quiz.", "error")
        return redirect(url_for("lecture_history"))
    try:
        client = get_authenticated_supabase()
        quiz_result = client.table("quizzes").select("*").eq("id", quiz_id).single().execute()
        quiz = quiz_result.data
        lecture = get_owned_lecture(client, profile["id"], quiz.get("lecture_id")) if quiz else None
        if not quiz or not lecture:
            flash("Quiz not found.", "error")
            return redirect(url_for("lecture_history"))
        questions = quiz.get("questions") or []
        if not questions:
            raise ValueError("This quiz has no valid questions.")
        answers, correct = [], 0
        for question in questions:
            selected = request.form.get(question.get("id"), "")
            if selected not in question.get("options", []):
                selected = "No answer"
            is_correct = selected == question.get("correct_answer")
            correct += int(is_correct)
            answers.append({"question_id": question.get("id"), "selected_answer": selected,
                            "correct_answer": question.get("correct_answer"), "is_correct": is_correct,
                            "concept": question.get("concept")})
        total = len(questions)
        percentage = round(correct * 100 / total) if total else 0
        attempt = client.table("quiz_attempts").insert({
            "quiz_id": quiz_id, "lecture_id": lecture["id"], "user_id": profile["id"],
            "score": correct, "total_questions": total, "correct_answers": correct,
            "percentage": percentage, "answers": answers,
        }).execute().data[0]
        return render_template("quiz_result.html", profile=profile, lecture=lecture, quiz=quiz,
                               attempt=attempt, answers=answers)
    except ValueError as error:
        flash(str(error), "error")
    except Exception:
        app.logger.exception("Quiz submission failed.")
        flash("Could not save your quiz attempt.", "error")
    return redirect(url_for("lecture_history"))

# =========================================================
# ADMIN DASHBOARD
# =========================================================

@app.route("/admin")
@role_required("Admin")
def admin_dashboard(profile):

    client = get_authenticated_supabase()

    users = []

    try:

        result = (
            client
            .table("profiles")
            .select(
                "id,name,email,role,created_at"
            )
            .order(
                "created_at",
                desc=True
            )
            .execute()
        )

        users = result.data or []

    except Exception:

        app.logger.exception(
            "Could not load admin users."
        )


    students = [
        user
        for user in users
        if user.get("role") == "Student"
    ]

    lecturers = [
        user
        for user in users
        if user.get("role") == "Lecturer"
    ]

    admins = [
        user
        for user in users
        if user.get("role") == "Admin"
    ]


    return render_template(
        "admin_dashboard.html",
        profile=profile,
        users=users,
        students=students,
        lecturers=lecturers,
        admins=admins
    )


# =========================================================
# ADMIN ROLE MANAGEMENT
# =========================================================

@app.route(
    "/admin/users/<user_id>/role",
    methods=["POST"]
)
@role_required("Admin")
def update_user_role(
    profile,
    user_id
):

    role = request.form.get(
        "role",
        ""
    )


    if user_id == profile["id"]:

        flash(
            "You cannot change your own role.",
            "error"
        )

        return redirect(
            url_for("admin_dashboard")
        )


    if role not in VALID_ROLES:

        flash(
            "Invalid role.",
            "error"
        )

        return redirect(
            url_for("admin_dashboard")
        )


    try:

        (
            get_authenticated_supabase()
            .table("profiles")
            .update(
                {
                    "role": role
                }
            )
            .eq(
                "id",
                user_id
            )
            .execute()
        )


        flash(
            "User role updated successfully.",
            "info"
        )

    except Exception:

        app.logger.exception(
            "Role update failed."
        )

        flash(
            "Could not update user role.",
            "error"
        )


    return redirect(
        url_for("admin_dashboard")
    )

ALLOWED_EXTENSIONS = {"mp3", "wav", "m4a", "ogg", "webm"}

def allowed_file(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
    )
# =========================================================
# AUDIO UPLOAD
#
# CRITICAL:
# ONLY Student + Lecturer can access this route.
# ADMIN IS NOT ALLOWED.
# =========================================================

@app.route(
    "/upload",
    methods=["POST"]
)
@role_required(
    "Student",
    "Lecturer"
)
def upload(profile):

    lecture_title = request.form.get("title", "").strip()
    subject = request.form.get("subject", "").strip()
    print("TITLE RECEIVED:", lecture_title)
    print("SUBJECT RECEIVED:", subject)
    if not lecture_title or not subject:
        flash("Please enter the lecture title and subject.", "error")
        return redirect(url_for("dashboard"))

    audio = request.files.get("audio")
    audio = request.files.get(
        "audio"
    )


    if not audio or not audio.filename:

        flash(
            "Please choose an MP3 or WAV file.",
            "error"
        )

        return redirect(
            url_for("dashboard")
        )


    if not allowed_file(
        audio.filename
    ):

        flash(
            "Only MP3 and WAV files are supported.",
            "error"
        )

        return redirect(
            url_for("dashboard")
        )


    filename = secure_filename(
        audio.filename
    )

    job_id = uuid4().hex[:10]

    upload_path = (
        UPLOAD_FOLDER
        / f"{job_id}_{filename}"
    )


    audio.save(
        upload_path
    )


    try:

        transcript = convert_audio_to_text(
            str(upload_path)
        ).strip()


        if not transcript:

            raise ValueError(
                "No speech detected in the audio."
            )


        keywords = extract_keywords(
            transcript
        )


        if not keywords:

            raise ValueError(
                "No meaningful keywords were found."
            )


        mindmap = generate_mindmap(
            keywords
        )


    except ValueError as error:

        flash(
            str(error),
            "error"
        )

        return redirect(
            url_for("dashboard")
        )


    except Exception:

        app.logger.exception(
            "Audio processing failed."
        )

        flash(
            "Unable to process the lecture.",
            "error"
        )

        return redirect(
            url_for("dashboard")
        )


    stem = Path(
        filename
    ).stem or "lecture"


    transcript_path = (
        TRANSCRIPT_FOLDER
        / f"{stem}_{job_id}_transcript.txt"
    )

    keyword_path = (
        KEYWORD_FOLDER
        / f"{stem}_{job_id}_keywords.txt"
    )


    transcript_path.write_text(
        transcript,
        encoding="utf-8"
    )

    keyword_path.write_text(
        "\n".join(keywords),
        encoding="utf-8"
    )


    session["transcript_file"] = (
    transcript_path.name
    )

    session["keyword_file"] = (
    keyword_path.name
    )

# =========================================================
# SAVE LECTURE TO SUPABASE
# =========================================================

    try:
        client = get_authenticated_supabase()

        if not client:
            raise RuntimeError(
            "Could not connect to authenticated Supabase session."
            )

       

        lecture_data = {
        "user_id": profile["id"],
        "title": lecture_title,
        "subject": subject,
        "audio_filename": filename,
        "transcript": transcript,
        "keywords": keywords,
        "mindmap": mindmap,
        "processing_status": "COMPLETED"
        }

        saved_lecture = client.table("lectures").insert(lecture_data).execute()
        lecture_id = (saved_lecture.data or [{}])[0].get("id")

    except Exception:
         app.logger.exception(
        "Could not save lecture to Supabase."
         )

         flash(
        "Lecture processed, but could not be saved to history.",
        "error"
        )

    return render_template(
        "result.html",
        transcript=transcript,
        keywords=keywords,
        mindmap=mindmap,
        lecture_id=locals().get("lecture_id")
    )
# =========================================================
# DOWNLOAD
# =========================================================

def download_document(
    folder,
    session_key,
    download_name
):

    filename = session.get(
        session_key
    )

    if not filename:

        flash(
            "Generate a lecture analysis first.",
            "info"
        )

        return redirect(
            url_for("dashboard")
        )


    path = (
        folder
        / Path(filename).name
    )


    if not path.is_file():

        flash(
            "File not found.",
            "error"
        )

        return redirect(
            url_for("dashboard")
        )


    return send_file(
        path,
        as_attachment=True,
        download_name=download_name,
        mimetype="text/plain"
    )


@app.route(
    "/download/transcript"
)
@role_required(
    "Student",
    "Lecturer"
)
def download_transcript(profile):

    return download_document(
        TRANSCRIPT_FOLDER,
        "transcript_file",
        "lecture_transcript.txt"
    )


@app.route(
    "/download/keywords"
)
@role_required(
    "Student",
    "Lecturer"
)
def download_keywords(profile):

    return download_document(
        KEYWORD_FOLDER,
        "keyword_file",
        "lecture_keywords.txt"
    )


# =========================================================
# FILE SIZE ERROR
# =========================================================

@app.errorhandler(413)
def file_too_large(error):

    flash(
        "File is too large. Maximum size is 100 MB.",
        "error"
    )

    return redirect(
        url_for("dashboard")
    )


# =========================================================
# START
# =========================================================

if __name__ == "__main__":

    app.run(
        host="127.0.0.1",
        port=5000,
        debug=True
    )
