from flask import Flask, request, render_template, session, redirect, url_for,flash,jsonify
import os
from googleapiclient.discovery import build
import google.generativeai as genai
import urllib.parse
import requests
from collections import Counter
app = Flask(__name__)
app.secret_key = 'your-secret-key'  #for every session
import sqlite3
from groq import Groq
def get_db_connection():# establish database connection
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row  # Allow accessing columns by name instead of index
    return conn
def init_views_table():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS views (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        video_url TEXT NOT NULL,
        view_count INTEGER DEFAULT 0,
        UNIQUE(video_url)
    )
    ''')
    conn.commit()
    conn.close()
init_views_table()
@app.route('/increment_view', methods=['POST'])
def increment_view():
    data = request.get_json()
    video_url = data.get('video_url')
    if not video_url or not video_url.startswith('/static/uploads/'):
        return jsonify({'error': 'Invalid video_url'}), 400
    video_key = video_url.split('/')[-1]
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO views (video_url, view_count) VALUES (?, 0)", (video_key,))
    cursor.execute("UPDATE views SET view_count = view_count + 1 WHERE video_url = ?", (video_key,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})
@app.route('/get_views', methods=['GET'])
def get_views():
    video_url = request.args.get('video_url')
    if not video_url or not video_url.startswith('/static/uploads/'):
        return jsonify({'error': 'Invalid video_url'}), 400
    video_key = video_url.split('/')[-1]
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT view_count FROM views WHERE video_url = ?", (video_key,))
    row = cursor.fetchone()
    conn.close()
    count = row['view_count'] if row else 0
    return jsonify({'views': count})
def init_likes_table():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS likes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        video_url TEXT NOT NULL,
        username TEXT NOT NULL,
        UNIQUE(video_url, username)
    )
    ''')
    conn.commit()
    conn.close()
init_likes_table() #initialize likes table
@app.route('/add_like', methods=['POST'])
def add_like():
    if 'username' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.get_json()
    video_url = data.get('video_url')
    if not video_url:
        return jsonify({'error': 'Missing video_url'}), 400
    # Normalize video_url for local videos
    if not video_url.startswith('/static/uploads/'):
        return jsonify({'error': 'Likes only allowed for uploaded videos'}), 400
    video_key = video_url.split('/')[-1]
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT 1 FROM likes WHERE video_url = ? AND username = ?", (video_key, session['username']))
        if cursor.fetchone():
            return jsonify({'success': False, 'already_liked': True})
        cursor.execute("INSERT INTO likes (video_url, username) VALUES (?, ?)", (video_key, session['username']))
        conn.commit()
        return jsonify({'success': True})
    finally:
        conn.close()
@app.route('/get_likes', methods=['GET'])
def get_likes():
    video_url = request.args.get('video_url')
    if not video_url:
        return jsonify({'error': 'Missing video_url'}), 400
    # Normalize local videos
    if video_url.startswith('/static/uploads/'):
        video_key = video_url.split('/')[-1]
    else:
        video_key = video_url
# connect to the database and retrieve the like count for the video
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as like_count FROM likes WHERE video_url = ?", (video_key,))
    like_count = cursor.fetchone()['like_count']
    conn.close()
    return jsonify({'likes': like_count})
def init_users_table():#  initialize users table if not exists
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
     # Create login_streak table if not exists
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS login_streak (
        username TEXT PRIMARY KEY,
        last_login DATE,
        streak INTEGER DEFAULT 0
    )
    ''')
    # Check if users exist, if not, insert default users
    cursor.execute("SELECT COUNT(*) as count FROM users")# counting the total number of rows in the users table 
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
    conn.commit()# save all the changes you've made to the database
    conn.close()
def init_comments_table():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS comments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        video_url TEXT NOT NULL,
        username TEXT NOT NULL,
        comment TEXT NOT NULL,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    conn.commit()
    conn.close()
# Call initialization functions at startup
init_users_table()
init_comments_table()
def verify_user(username, password):# to verify user credentials
    conn = get_db_connection()
    cursor = conn.cursor()
    # Fetch user by username and password
    cursor.execute(
        "SELECT username, role FROM users WHERE username = ? AND password = ?", 
        (username, password)
    )
    user = cursor.fetchone() #if called first time, it will return the first row if called again, it will return the next row each time
    conn.close()
    # Return user info if found, else None 
    if user:
        return {
            'username': user['username'],
            'role': user['role']
        }
    return None
# Initialize users table when the module is imported
init_users_table()
# Configure APIs
GEMINI_API_KEY = 'AIzaSyAV-h_kIu5EE5YI1G_WE8X1bBpTpWqpfOo'
genai.configure(api_key=GEMINI_API_KEY)
UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER# stores the path to the upload folder in the Flask app's configuration dictionary
# Ensure upload directory exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
@app.route('/')#home page is login page by default
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
    finally: #code will always execute regardless of whether an exception occurred or not
        conn.close()
@app.route('/register', methods=['GET', 'POST'])#get is used to retrieve data from the server which is register.html
def register():
    err = None
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        role = request.form['role']  # Assuming a role selection in the form
        # Use the database-based user check instead of USERS dictionary
        if add_user_to_db(username, password, role):
            return redirect(url_for('login'))
        else:
            err='Username already exists or registration failed.'
    return render_template('register.html',message=err)
from datetime import datetime, timedelta
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
            #Learning streak
            conn = get_db_connection()
            cursor = conn.cursor()
            today = datetime.now().date()#current date
            cursor.execute("SELECT last_login, streak FROM login_streak WHERE username = ?", (username,))
            row = cursor.fetchone()
            if row:
                last_login = datetime.strptime(row['last_login'], "%Y-%m-%d").date()#retrieve last login date in YYYY-MM-DD format
                streak = row['streak']# retrieve the streak value
                if (today - last_login).days == 1:# if the last login was yesterday
                    streak += 1# increment the streak
                elif (today - last_login).days > 1:# if the last login was more than one day ago
                    streak = 1 # reset the streak
                cursor.execute("UPDATE login_streak SET last_login = ?, streak = ? WHERE username = ?", (today.strftime("%Y-%m-%d"), streak, username))# update the last login date and streak for the username
            else:# if the user is logging in for the first time
                streak = 1
                cursor.execute("INSERT INTO login_streak (username, last_login, streak) VALUES (?, ?, ?)", (username, today.strftime("%Y-%m-%d"), streak))
            conn.commit()
            conn.close()
            session['streak'] = streak #display the user's current login streak during their session.
            # Redirect based on role
            if user['role'] == 'uploader':
                return redirect(url_for('upload'))
            elif user['role'] == 'viewer':
                return redirect(url_for('chat'))
        # If login fails
        flash('Invalid credentials if you have not registered, please sign up')
        return redirect(url_for('login'))
    
    return render_template('login.html')
app.config['MAX_CONTENT_LENGTH'] = 1024 * 1024 * 1024 #in bytes the limit is set for upload
@app.route('/upload', methods=['GET', 'POST'])
def upload():
    if 'username' not in session or session['role'] != 'uploader': #  if user is not logged in and is not an uploader then redirect to the index route
        return redirect(url_for('index'))
    if request.method == 'POST':
        class_name = request.form['class_level']
        if 'video' not in request.files:# if no video file is uploaded
            flash('No file part')
            return redirect(request.url)# redirect to the same page
        file = request.files['video'] # get the video file from the request
        if file.filename == '':
            flash('No selected file')
            return redirect(request.url)
        if file and not file.filename.endswith('.mp4'):
            flash('Only .mp4 files are allowed')
            return redirect(request.url)
        if file and file.filename.endswith(('.mp4')):
            file.seek(0, os.SEEK_END)  # Move cursor to end of file
            file_size = file.tell()  # Get file size in bytes
            file.seek(0)  # Reset cursor position
            if file_size > app.config['MAX_CONTENT_LENGTH']:
                return redirect(request.url)# redirect to the same page
            filename = file.filename # get the filename
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename) # create the full path to save the file
            file.save(file_path)
            metadata_file = 'uploads/metadata.txt'
            os.makedirs('uploads', exist_ok=True)  # Ensure the folder exists
            with open(metadata_file, 'a') as f:
                f.write(f"{filename}:{session['username']}:{class_name}\n")
            flash('Video uploaded successfully by ' + session['username'])
            return redirect(url_for('manage_videos'))
    return render_template('upload.html')
@app.route('/manage', methods=['GET', 'POST'])
def manage_videos():
    metadata_file = 'uploads/metadata.txt'
    if 'username' not in session or session['role'] != 'uploader':
        return redirect(url_for('index'))
    current_uploader = session['username']
    # Load videos uploaded by the current user
    user_videos = []
    if os.path.exists(metadata_file):
        with open(metadata_file, 'r') as f:
            for line in f:
                parts = line.strip().split(':', 2)#remove whitespace and split the line into 3 parts
                if len(parts) == 3: #if the split operation results in 3 parts
                    video_name, uploader,grade = parts
                    if uploader == current_uploader: # check if the uploader is the current user
                        user_videos.append(video_name) # add the video name to the uploaded videos
    videos = [video for video in os.listdir(app.config['UPLOAD_FOLDER']) if video in user_videos] # filter the videos in the upload folder to only include those uploaded by the current user
    playlists_file = 'uploads/playlists.txt'
    playlists = {}
    # Load playlists from file
    if os.path.exists(playlists_file):
        with open(playlists_file, 'r') as f:
            for line in f:
                parts = line.strip().split(':', 2)
                if len(parts) == 3:
                    name, vids, uploader = parts
                    if uploader == current_uploader:
                        playlists[name] = vids.split(',') if vids else [] #split the videos in the playlist into a list of video names or an empty list if no videos are present
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'delete_video':
            video = request.form.get('video')
            video_path = os.path.join(app.config['UPLOAD_FOLDER'], video)# create the full path like upload_folder/video
            if os.path.exists(video_path):
                os.remove(video_path)
                flash(f'Video {video} deleted')
                if os.path.exists(metadata_file):
                        with open(metadata_file, 'r') as f:
                            lines = f.readlines() # read all lines from file into a list
                        # Write back all lines except the one containing the deleted video
                        with open(metadata_file, 'w') as f:
                            for line in lines:
                                if not line.startswith(f"{video}:"):
                                    f.write(line)
        elif action == 'create_playlist':
            playlist_name = request.form.get('playlist_name')
            if playlist_name and playlist_name not in playlists: # check if the playlist name is not empty and does not already exist
                playlists[playlist_name] = []
                flash(f'Playlist {playlist_name} created')
        elif action == 'add_to_playlist':
            playlist_name = request.form.get('playlist')
            video = request.form.get('video')
            video_grades = {}
            if os.path.exists(metadata_file):
                with open(metadata_file, 'r') as f:
                    for line in f:
                        parts = line.strip().split(':', 2)
                        if len(parts) == 3:
                            v_name, uploader, grade = parts
                            video_grades[v_name] = grade
            if playlist_name in playlists and video not in playlists[playlist_name]:
                # Check if playlist has videos already
                if playlists[playlist_name]:
                    first_video = playlists[playlist_name][0]
                    # Check grades
                    if video_grades.get(first_video) == video_grades.get(video):
                        playlists[playlist_name].append(video)
                        flash(f'Video {video} added to {playlist_name}')
                    else:
                        flash(f'Cannot add video of a different grade to playlist please add a video of the same grade', 'error')
                else:
                    playlists[playlist_name].append(video)# Playlist is empty, so we can add any video
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
                f.write(f"{name}:{','.join(vids)}:{current_uploader}\n")
        return redirect(url_for('manage_videos'))
    return render_template('manage.html', videos=videos, playlists=playlists)
@app.errorhandler(413)
def request_entity_too_large(error):
    flash("File size exceeds the 1GB limit")
    return redirect(url_for('upload'))
@app.route('/chat', methods=['GET', 'POST'])
def chat():
    if 'username' not in session or session['role'] != 'viewer':
        return redirect(url_for('index'))
    videos = []
    if request.method == 'POST':
        topic = request.form['topic']
        videos = search_videos(topic) #video list from search
    return render_template('chat.html', videos=videos)
@app.route('/get_dynamic_reply', methods=['POST'])
def get_dynamic_reply():
    data = request.get_json()
    topic = data.get("topic")
    class_level = data.get("cLevel")
    if not topic or not topic.strip():  # Validate topic
        return jsonify({
            "reply": "Please provide a valid topic.",
            "context": {
                "topic": topic,
                "classLevel": class_level
            }
        })
    # Directly use the LLM response
    full_response = stream_llm_response(topic)
    return jsonify({
        "reply": full_response,
        "context": {
            "topic": topic,
            "classLevel": class_level
        }
    })
def stream_llm_response(topic):
    client = Groq(api_key="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")
    completion = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": topic}],
        temperature=1,
        max_completion_tokens=1024,
        top_p=1,
        stream=True,
        stop=None, #let the model decide when to stop
    )
    full_response = ""
    for chunk in completion:
        part = chunk.choices[0].delta.content or "" # each chunk has response is a string or add empty string
        full_response += part # concatenate the chunks to form the full response
    return full_response
import markdown
@app.route('/quiz', methods=['POST'])
def quiz():
    metadataFile = 'uploads/metadata.txt'
    selected_video = request.form.get('video')
    grade = None
    # Extract grade for the selected video from metadata.txt
    if selected_video and os.path.exists(metadataFile):
        with open(metadataFile, 'r') as f:
            for line in f:
                parts = line.strip().split(':', 2)
                if len(parts) == 3:
                    video_name, uploader, video_grade = parts
                    if video_name == selected_video:
                        grade = video_grade
                        break

    quiz_type = request.form.get('type')
    no_of_questions = request.form.get('no')

    if not quiz_type or not no_of_questions:
        # First step: show quizzes.html to collect type and no
        return render_template('quizzes.html', result=None, grade=grade, playlist=selected_video)
    else:
        # Second step: generate quiz
        prompt = f"make a quiz of {no_of_questions} questions on this topic {selected_video} for class {grade} in {quiz_type} format.(donot make mcq for subjective format)" 
        norm_result = stream_llm_response(prompt)
        formatted_result = markdown.markdown(norm_result, extensions=['nl2br', 'sane_lists'])
        return render_template('quizzes.html', result=formatted_result, playlist=selected_video, grade=grade)     
def search_videos(topic, class_level=None, teacher_name=None):
    if not any(char.isalnum() for char in topic): # if the topic does not contain any alphanumeric characters
        return []  # Return empty list 
    # Define a list of stop words
    stop_words = set(['the', 'is', 'in', 'and', 'to', 'a', 'of', 'for', 'on', 'with', 'as', 'by', 'at', 'this', 'that', 'an', 'it', 'are', 'from', 'or', 'but', 'not', 'be', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'can', 'could', 'should', 'may', 'might', 'must'])
    # Filter the topic to exclude stop words
    keywords = [word for word in topic.lower().split() if word not in stop_words]
    uploaded_videos = []
    metadata_file = 'uploads/metadata.txt'
    metadata = {}
    if os.path.exists(metadata_file):
        with open(metadata_file, 'r') as f:
            for line in f:
                parts = line.strip().split(':', 2)
                if len(parts) == 3:
                    metadata[parts[0]] = {'uploader': parts[1], 'class': parts[2]} # video name= uploader, class 
    for filename in os.listdir(app.config['UPLOAD_FOLDER']):
        file_lower = filename.lower()
        # Check if topic keywords match the filename
        topic_match = any(keyword in file_lower for keyword in keywords)
        if not topic_match:
            continue # if the topic keywords are not in the filename then skip to the next video 
        file_metadata = metadata.get(filename, {'uploader': 'Unknown', 'class': None}) # get the metadata for the video
        # Extract class from metadata
        file_class = file_metadata['class']
        # Check class_level and teacher_name filters if provided
        class_match = (class_level is None) or (file_class and class_level.lower() in file_class.lower()) # check if the class level is not None and if it is in the file class
        if topic_match and class_match:# Check if all filters match then add the video to the uploaded_videos list
            uploaded_videos.append({
                'title': filename,
                'url': f"/static/uploads/{filename}",
                'description': f"Video from {file_metadata['uploader']} for class {file_class or 'unspecified'}"
            })
    if uploaded_videos:
        return uploaded_videos
    try:
        API_KEY = 'AIzaSyC8_Pgzha5aP0yXzjdAZqIt5eUilgquFN4'
        # Initialize YouTube API client
        youtube = build('youtube', 'v3', developerKey=API_KEY)
        # Search for videos
        search_response = youtube.search().list(
            q=topic,
            part='id,snippet',
            maxResults=3,
            type='video'
        ).execute()
        # Process results
        video_ids = [item["id"]["videoId"] for item in search_response.get("items", [])]
        if not video_ids: # if no video IDs are found then return an empty list
         return []
        # Fetch video statistics including view count and likes
        video_response = youtube.videos().list(
            part="statistics,snippet",
            id=",".join(video_ids)
        ).execute()
        videos = []
        for item in video_response.get("items", []): # iterate through the items in the video response and extract the relevant information
            video_info = {
                "title": item["snippet"]["title"],
                "url": f'https://www.youtube.com/watch?v={item["id"]}',
                "description": item["snippet"]["description"],
                "views": int(item["statistics"]["viewCount"]),
                "likes": int(item["statistics"].get("likeCount", 0)) # Default to 0 if likes are hidden
            }
            videos.append(video_info) # concatenate the relevant information to the videos list
        videos.sort(key=lambda x: (x["views"], x["likes"]), reverse=True)  # sort videos by most view count and likes
        return videos
    except Exception as e:
        print(f"An error occurred: {str(e)}")
        return []
@app.route('/search', methods=['POST'])
def search():
    data = request.get_json() # get the data in json from the request and pass to frontend 
    topic = data.get('topic', '')
    class_level = data.get('clevel', None)
    teacher_name = data.get('teacher', None)
    videos = search_videos_with_sentiment(topic, class_level, teacher_name)
    if not videos:
        videos = search_videos(topic, class_level, teacher_name)  # Fallback to basic search if no videos found with sentiment
        return jsonify({"videos": videos, "info": "No videos found with feedback. Showing basic search results."})
    response = {"videos": videos}
    return jsonify(response)
def ratioSort(video):
    conn = get_db_connection()
    cursor = conn.cursor()
    video_url = video['url'] # Get the full URL
    # Extract video_key for database lookup (assuming it's the filename for local videos)
    if video_url.startswith('/static/uploads/'):
        video_key = video_url.split('/')[-1]
    else:
        # This function is intended for local videos, but handle other cases defensively
        conn.close()
        video['comment_view_ratio'] = 0 # Or some default low value
        return

    # Get comment count
    cursor.execute("SELECT COUNT(*) as comment_count FROM comments WHERE video_url = ?", (video_key,))
    comment_count = cursor.fetchone()['comment_count']
    video['comment_count'] = comment_count

    # Get view count
    cursor.execute("SELECT view_count FROM views WHERE video_url = ?", (video_key,))
    row = cursor.fetchone()
    view_count = row['view_count'] if row else 0
    video['views'] = view_count

    conn.close()
    # Calculate comment-to-view ratio Add a small epsilon to view_count to avoid division by zero if views are 0 Or handle the zero case explicitly
    if view_count > 0:
        video['comment_view_ratio'] = comment_count / view_count
    else:
        # If no views, the ratio is effectively infinite or undefined. Assign a value based on comment count (more comments with 0 views is better)
        video['comment_view_ratio'] = comment_count # Assign comment count directly if views are 0
@app.route('/add_comment', methods=['POST'])
def add_comment():
    if 'username' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.get_json()
    video_url = data.get('video_url')
    comment = data.get('comment')
    if not video_url or not comment:
        return jsonify({'error': 'Missing fields'}), 400
    # Normalize video_url for YouTube videos
    if "youtube.com/watch?v=" in video_url:
        # Extract the video ID
        from urllib.parse import urlparse, parse_qs
        parsed_url = urlparse(video_url)
        video_id = parse_qs(parsed_url.query).get("v", [None])[0]
        video_key = video_id
    elif video_url.startswith('/static/uploads/'):
        video_key = video_url.split('/')[-1]
    else:
        video_key = video_url
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO comments (video_url, username, comment) VALUES (?, ?, ?)", 
                   (video_key, session['username'], comment))
    conn.commit()
    conn.close()
    return jsonify({'success': True})
# retrieve comments for a given video
@app.route('/get_comments', methods=['GET'])
def get_comments():
    video_url = request.args.get('video_url')
    if not video_url: # if the video URL is not provided
        return jsonify({'error': 'Missing video_url'}), 400
    # Normalize video_url for YouTube and local videos
    if "youtube.com/watch?v=" in video_url:
        from urllib.parse import urlparse, parse_qs
        parsed_url = urlparse(video_url)
        video_id = parse_qs(parsed_url.query).get("v", [None])[0]
        video_key = video_id
    elif video_url.startswith('/static/uploads/'):
        video_key = video_url.split('/')[-1]
    else:
        video_key = video_url
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT username, comment, timestamp FROM comments WHERE video_url = ? ORDER BY timestamp DESC", (video_key,)) # show the most recent comments first
    comments = cursor.fetchall()
    conn.close()
    comments_list = [{'username': row['username'], 'comment': row['comment'], 'timestamp': row['timestamp']} for row in comments] # convert the comments to a list
    return jsonify({'comments': comments_list})
import nltk #natural language toolkit
from nltk.sentiment import SentimentIntensityAnalyzer
# Download VADER lexicon if not already downloaded
nltk.download('vader_lexicon')
def analyze_sentiment(comment):
    sia = SentimentIntensityAnalyzer()
    sentiment = sia.polarity_scores(comment)
    return sentiment['compound']  # Returns a value between -1 (negative) and 1 (positive)
def get_video_sentiment(video_url):
    # Normalize video_url for YouTube videos
    if "youtube.com/watch?v=" in video_url:
        from urllib.parse import urlparse, parse_qs
        parsed_url = urlparse(video_url)
        video_id = parse_qs(parsed_url.query).get("v", [None])[0]
        video_key = video_id
    elif video_url.startswith('/static/uploads/'):
        video_key = video_url.split('/')[-1]
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT comment FROM comments WHERE video_url = ? ", (video_key,))
    comments = cursor.fetchall()
    conn.close()
    if not comments:
        return None
    scores = [analyze_sentiment(row['comment']) for row in comments]
    avg_sentiment = sum(scores) / len(scores)
    return avg_sentiment

# Modify search_videos_with_sentiment
def search_videos_with_sentiment(topic, class_level=None, teacher_name=None):
    videos = search_videos(topic, class_level, teacher_name)
    if not videos:
        return []

    youtube_videos = []
    local_videos = []

    for video in videos:
        if video['url'].startswith('https://www.youtube.com/watch?v='):
            youtube_videos.append(video)
        elif video['url'].startswith('/static/uploads/'):
            local_videos.append(video)
        # Other video types are ignored

    for video in youtube_videos:
        avg_sentiment = get_video_sentiment(video['url'])
        video['avg_sentiment'] = avg_sentiment if avg_sentiment is not None else 0
    # Sort YouTube videos by sentiment (descending)
    youtube_videos.sort(key=lambda x: x.get('avg_sentiment', -2), reverse=True)
    # Process local videos and calculate comment-to-view ratio
    for video in local_videos:
        ratioSort(video) # Adds 'comment_count', 'views', 'comment_view_ratio'
    # Sort local videos by comment-to-view ratio (descending)
    local_videos.sort(key=lambda x: x.get('comment_view_ratio', 0), reverse=True) # Use .get with a default for safety

    # Combine sorted YouTube videos and sorted local videos
    # YouTube videos come first, then local videos, both sorted within their groups
    ranked_videos = youtube_videos + local_videos

    return ranked_videos
@app.route('/video/<filename>')
def video_landing(filename):
    video_url = f"/static/uploads/{filename}"
    return render_template('video_landing.html', video_url=video_url, filename=filename)
@app.route('/logout')
def logout():
    session.pop('username', None)
    session.pop('role', None)
    return redirect(url_for('index'))
if __name__ == '__main__':
    app.debug = True  
    app.run()
