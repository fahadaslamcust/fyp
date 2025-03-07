from flask import Flask, request, render_template, session, redirect, url_for,flash
import os
from googleapiclient.discovery import build
import google.generativeai as genai
import urllib.parse
import requests
from collections import Counter
app = Flask(__name__)
app.secret_key = 'your-secret-key'  # Change this in production
import sqlite3
# Function to establish database connection
def get_db_connection():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row  # Allow accessing columns by name
    return conn
# Function to initialize users table if not exists
def init_users_table():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Create users table if not exists
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        username TEXT PRIMARY KEY,
        password TEXT NOT NULL,
        role TEXT NOT NULL
    )
    ''')
    
    # Check if users exist, if not, insert default users
    cursor.execute("SELECT COUNT(*) as count FROM users")
    count = cursor.fetchone()['count']
    
    if count == 0:
        # Insert default users
        default_users = [
            ('uploader', 'upload123', 'uploader'),
            ('viewer', 'view123', 'viewer')
        ]
        cursor.executemany(
            "INSERT INTO users (username, password, role) VALUES (?, ?, ?)", 
            default_users
        )
    
    conn.commit()
    conn.close()
# Function to verify user credentials
def verify_user(username, password):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Fetch user by username and password
    cursor.execute(
        "SELECT username, role FROM users WHERE username = ? AND password = ?", 
        (username, password)
    )
    user = cursor.fetchone()
    
    conn.close()
    
    # Return user info if found, else None
    if user:
        return {
            'username': user['username'],
            'role': user['role']
        }
    return None
# Function to add a new user
def add_user(username, password, role):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute(
            "INSERT INTO users (username, password, role) VALUES (?, ?, ?)", 
            (username, password, role)
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        # Username already exists
        return False
    finally:
        conn.close()

# Function to update user password
def update_user_password(username, new_password):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET password = ? WHERE username = ?", 
        (new_password, username)
    )
    conn.commit()
    conn.close()
# Initialize users table when the module is imported
init_users_table()
# Configure APIs
GEMINI_API_KEY = 'AIzaSyAV-h_kIu5EE5YI1G_WE8X1bBpTpWqpfOo'
genai.configure(api_key=GEMINI_API_KEY)
UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
# Ensure upload directory exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
@app.route('/')
def index():
    return render_template('login.html')
# Function to add a new user to the database
def add_user_to_db(username, password, role):
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    try:
        # Check if user already exists
        cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
        if cursor.fetchone():
            return False  # User already exists
        # Insert new user
        cursor.execute(
            "INSERT INTO users (username, password, role) VALUES (?, ?, ?)", 
            (username, password, role)
        )
        conn.commit()
        return True
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        return False
    finally:
        conn.close()
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        role = request.form['role']  # Assuming you have a role selection in the form
        
        # Use the database-based user check instead of USERS dictionary
        if add_user_to_db(username, password, role):
            flash('Registration successful!')
            return redirect(url_for('login'))
        else:
            flash('Username already exists or registration failed.')
    
    return render_template('register.html')
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        # Use the new verify_user function
        user = verify_user(username, password)
        
        if user:
            # Set session variables
            session['username'] = user['username']
            session['role'] = user['role']
            
            # Redirect based on role
            if user['role'] == 'uploader':
                return redirect(url_for('upload'))
            elif user['role'] == 'viewer':
                return redirect(url_for('chat'))
        
        # If login fails
        flash('Invalid credentials')
        return redirect(url_for('login'))
    
    return render_template('login.html')
@app.route('/upload', methods=['GET', 'POST'])
def upload():
    if 'username' not in session or session['role'] != 'uploader':
        return redirect(url_for('index'))
    if request.method == 'POST':
        if 'video' not in request.files:
            flash('No file part')
            return redirect(request.url)
        file = request.files['video']
        if file.filename == '':
            flash('No selected file')
            return redirect(request.url)
        if file and file.filename.endswith(('.mp4', '.avi', '.mov')):
            filename = file.filename
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            flash('Video uploaded successfully')
            return redirect(url_for('manage_videos'))
    
    return render_template('upload.html')
@app.route('/manage', methods=['GET', 'POST'])
def manage_videos():
    if 'username' not in session or session['role'] != 'uploader':
        return redirect(url_for('index'))

    videos = [f for f in os.listdir(app.config['UPLOAD_FOLDER']) if f.endswith(('.mp4', '.avi', '.mov'))]
    playlists_file = 'uploads/playlists.txt'
    playlists = {}
    # Load playlists from file
    if os.path.exists(playlists_file):
        with open(playlists_file, 'r') as f:
            for line in f:
                parts = line.strip().split(':', 1)  # Split only once at the first colon
                name = parts[0]
                vids = parts[1].split(',') if len(parts) > 1 and parts[1] else [] # Handle empty playlists
                playlists[name] = vids
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'delete_video':
            video = request.form.get('video')
            video_path = os.path.join(app.config['UPLOAD_FOLDER'], video)
            if os.path.exists(video_path):
                os.remove(video_path)
                flash(f'Video {video} deleted')
        
        elif action == 'create_playlist':
            playlist_name = request.form.get('playlist_name')
            if playlist_name and playlist_name not in playlists:
                playlists[playlist_name] = []
                flash(f'Playlist {playlist_name} created')
        
        elif action == 'add_to_playlist':
            playlist_name = request.form.get('playlist')
            video = request.form.get('video')
            if playlist_name in playlists and video not in playlists[playlist_name]:
                playlists[playlist_name].append(video)
                flash(f'Video {video} added to {playlist_name}')
        
        elif action == 'remove_from_playlist':
            playlist_name = request.form.get('playlist')
            video = request.form.get('video')
            if playlist_name in playlists and video in playlists[playlist_name]:
                playlists[playlist_name].remove(video)
                flash(f'Video {video} removed from {playlist_name}')
        elif action == 'delete_playlist':
            playlist_name = request.form.get('playlist')
            if playlist_name in playlists:
                del playlists[playlist_name]
                flash(f'Playlist {playlist_name} deleted')
        # Save playlists to file
        with open(playlists_file, 'w') as f:
            for name, vids in playlists.items():
                f.write(f"{name}:{','.join(vids)}\n")

        return redirect(url_for('manage_videos'))

    return render_template('manage.html', videos=videos, playlists=playlists)
@app.route('/chat', methods=['GET', 'POST'])
def chat():
    if 'username' not in session or session['role'] != 'viewer':
        return redirect(url_for('index'))
    
    videos = []
    if request.method == 'POST':
        topic = request.form['topic']
        videos = search_videos(topic)
    
    return render_template('chat.html', videos=videos)
def search_videos(topic):
    # Define a list of stop words
    stop_words = set(['the', 'is', 'in', 'and', 'to', 'a', 'of', 'for', 'on', 'with', 'as', 'by', 'at', 'this', 'that', 'an', 'it', 'are', 'from', 'or', 'but', 'not', 'be', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'can', 'could', 'should', 'may', 'might', 'must'])
    # Filter the topic to exclude stop words
    keywords = [word for word in topic.lower().split() if word not in stop_words]
    uploaded_videos = []
    for filename in os.listdir(app.config['UPLOAD_FOLDER']):
        # Use more flexible matching strategies with filtered keywords
        if (any(keyword in filename.lower() for keyword in keywords)):
            uploaded_videos.append({
                'title': filename,
                'url': f"/static/uploads/{filename}",
                'description': f"video from faculty collection"
            })
    # If local videos exist, ALWAYS return them first
    if uploaded_videos:
        return uploaded_videos
    try:
        API_KEY = 'AIzaSyC8_Pgzha5aP0yXzjdAZqIt5eUilgquFN4'
        # Initialize YouTube API client
        youtube = build('youtube', 'v3', developerKey=API_KEY)
        search_response = youtube.search().list(
            q=topic,
            part='id,snippet',
            maxResults=5,
            type='video'
        ).execute()
        # Process results
        videos = []
        for item in search_response.get('items', []):
            video_info = {
                'title': item['snippet']['title'],
                'url': f'https://www.youtube.com/watch?v={item["id"]["videoId"]}',
                'description': item['snippet']['description']
            }
            videos.append(video_info)
        return videos
    except Exception as e:
        print(f"An error occurred: {str(e)}")
        return []
@app.route('/logout')
def logout():
    session.pop('username', None)
    session.pop('role', None)
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)