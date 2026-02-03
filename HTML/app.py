from flask import Flask, request, jsonify, render_template, session
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from functools import wraps
from werkzeug.utils import secure_filename
import os
import requests  

app = Flask(__name__)

# --- Config ---
app.config['SECRET_KEY'] = 'dev_secret_key_123' 
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///postfolify.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)

# --- Models (Same as before) ---
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(60), nullable=False)
    name = db.Column(db.String(100))
    profession = db.Column(db.String(100))
    bio = db.Column(db.Text)
    posts = db.relationship('Post', backref='author', lazy=True)

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.Text, nullable=False)
    generated_text = db.Column(db.Text, nullable=False)
    screenshot_path = db.Column(db.String(200))
    project_file_path = db.Column(db.String(200))
    is_public = db.Column(db.Boolean, default=True) 
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

# --- Helpers ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({"message": "Please login first"}), 401
        return f(*args, **kwargs)
    return decorated_function

# --- Routes ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/signup', methods=['POST'])
def signup():
    data = request.json
    if User.query.filter_by(email=data['email']).first():
        return jsonify({"message": "User already exists"}), 400
    hashed_pw = bcrypt.generate_password_hash(data['password']).decode('utf-8')
    new_user = User(email=data['email'], password=hashed_pw, name=data.get('name'), profession=data.get('profession'), bio=data.get('bio'))
    db.session.add(new_user)
    db.session.commit()
    session['user_id'] = new_user.id
    return jsonify({"message": "User created"}), 201

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    user = User.query.filter_by(email=data['email']).first()
    if user and bcrypt.check_password_hash(user.password, data['password']):
        session['user_id'] = user.id
        return jsonify({"name": user.name, "profession": user.profession, "bio": user.bio}), 200
    return jsonify({"message": "Invalid credentials"}), 401

@app.route('/api/generate', methods=['POST'])
@login_required
def generate():
    user = User.query.get(session['user_id'])
    description = request.form.get('description')
    
    if not description:
        return jsonify({"message": "Description required"}), 400

    screenshot = request.files.get('screenshot')
    project_file = request.files.get('project_file')
    
    s_path = None
    p_path = None

    # 1. Save files locally first
    files_to_send = {} 
    
    if screenshot:
        s_filename = secure_filename(f"user_{user.id}_{screenshot.filename}")
        full_path = os.path.join(app.config['UPLOAD_FOLDER'], s_filename)
        screenshot.save(full_path)
        s_path = s_filename
        
        # Open the file again to send to FastAPI
        # 'media_file' must match the parameter name in FastAPI
        files_to_send['media_file'] = open(full_path, 'rb')

    if project_file:
        p_filename = secure_filename(f"user_{user.id}_{project_file.filename}")
        project_file.save(os.path.join(app.config['UPLOAD_FOLDER'], p_filename))
        p_path = p_filename

    # 2. Prepare Data for FastAPI
    payload = {
        "raw_text": description,
        "user_persona": f"{user.name}, {user.profession}. Bio: {user.bio}",
        "tone": "Professional",     # You can add a dropdown in frontend later
        "platform": "LinkedIn"
    }

    # 3. Call The Brain (FastAPI Microservice)
    try:
        # Note: We send 'data' for text fields and 'files' for the image
        ai_response = requests.post("http://127.0.0.1:8000/forge", data=payload, files=files_to_send)
        ai_data = ai_response.json()
        
        if ai_data.get("success"):
            generated_text = ai_data["output"]
        else:
            generated_text = "AI generation failed."
            
    except Exception as e:
        print(f"Microservice connection failed: {e}")
        generated_text = "Error connecting to AI Brain."
    
    # Close the file if we opened it
    if 'media_file' in files_to_send:
        files_to_send['media_file'].close()

    # 4. Save to Database
    new_post = Post(
        description=description, 
        generated_text=generated_text, 
        screenshot_path=s_path,
        project_file_path=p_path,
        user_id=user.id
    )
    db.session.add(new_post)
    db.session.commit()

    return jsonify({
        "post": generated_text, 
        "image": s_path, 
        "file": p_path
    }), 200

@app.route('/api/feed', methods=['GET'])
def get_feed():
    posts = Post.query.filter_by(is_public=True).all()
    return jsonify([{
        "author": p.author.name,
        "profession": p.author.profession,
        "content": p.generated_text,
        "image": p.screenshot_path,
        "file": p.project_file_path
    } for p in posts])

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, port=5000)