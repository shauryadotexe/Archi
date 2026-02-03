from flask import Flask, request, jsonify, render_template, session, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from functools import wraps
from werkzeug.utils import secure_filename
import os

app = Flask(__name__)

# --- Configuration ---
app.config['SECRET_KEY'] = 'dev_secret_key_123' 
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///postfolify.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# File Upload Configuration
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'py', 'ino', 'pdf', 'txt'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Ensure the upload directory exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)

# --- Helpers ---

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({"message": "Please login first"}), 401
        return f(*args, **kwargs)
    return decorated_function

# --- Database Models ---

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
    
    # New Columns for File Storage
    screenshot_path = db.Column(db.String(200)) # Path to image
    project_file_path = db.Column(db.String(200)) # Path to .py/.ino file
    
    is_public = db.Column(db.Boolean, default=True) 
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

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
    new_user = User(
        email=data['email'], 
        password=hashed_pw,
        name=data.get('name', 'New Engineer'),
        profession=data.get('profession', 'Specialist'),
        bio=data.get('bio', '')
    )
    db.session.add(new_user)
    db.session.commit()
    session['user_id'] = new_user.id
    return jsonify({"message": "User created successfully"}), 201

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
    
    # Ensure the description is retrieved from the form data
    description = request.form.get('description')
    
    if not description:
        return jsonify({"message": "Description is required to save a post."}), 400

    screenshot = request.files.get('screenshot')
    project_file = request.files.get('project_file')

    s_path = None
    p_path = None

    # Handle Screenshot Upload
    if screenshot and allowed_file(screenshot.filename):
        s_filename = secure_filename(f"user_{user.id}_img_{screenshot.filename}")
        screenshot.save(os.path.join(app.config['UPLOAD_FOLDER'], s_filename))
        s_path = s_filename

    # Handle Project File Upload (.py, .ino)
    if project_file and allowed_file(project_file.filename):
        p_filename = secure_filename(f"user_{user.id}_code_{project_file.filename}")
        project_file.save(os.path.join(app.config['UPLOAD_FOLDER'], p_filename))
        p_path = p_filename

    # Construct the contextual generated post
    generated_post = (
        f"🚀 Engineering Milestone: {description}\n\n"
        f"As a {user.profession}, I focus on builds like this. Check out the logic below! #Innovation"
    )
    
    try:
        new_post = Post(
            description=description, 
            generated_text=generated_post, 
            screenshot_path=s_path,
            project_file_path=p_path,
            user_id=user.id
        )
        db.session.add(new_post)
        db.session.commit() # The data is officially saved to postfolify.db
        
        return jsonify({
            "post": generated_post, 
            "image": s_path, 
            "file": p_path,
            "message": "Success"
        }), 200
    except Exception as e:
        db.session.rollback() # Undo database changes if an error occurs
        print(f"Database Error: {e}")
        return jsonify({"message": "Database write failed."}), 500

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
    app.run(debug=True)