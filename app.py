import os
import uuid
import json
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename
from config import Config
from models import User, init_db

# Import evaluation functions from existing script
from human_vs_gold import (
    read_transcript,
    clean_text,
    calculate_detailed_metrics,
    get_alignment_details,
    format_detailed_report,
    generate_html_report
)

app = Flask(__name__)
app.config.from_object(Config)

# Ensure upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to access this page.'
login_manager.login_message_category = 'info'

@login_manager.user_loader
def load_user(user_id):
    return User.get_by_id(int(user_id))

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('upload'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('upload'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        if not username or not password:
            flash('Please enter both username and password.', 'error')
            return render_template('login.html')

        user = User.get_by_username(username)
        if user and user.check_password(password):
            login_user(user)
            next_page = request.args.get('next')
            flash(f'Welcome back, {username}!', 'success')
            return redirect(next_page or url_for('upload'))
        else:
            flash('Invalid username or password.', 'error')

    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
@login_required
def register():
    if not current_user.is_admin:
        flash('Only administrators can register new users.', 'error')
        return redirect(url_for('upload'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        is_admin = request.form.get('is_admin') == 'on'

        if not username or not password:
            flash('Please fill in all required fields.', 'error')
        elif password != confirm_password:
            flash('Passwords do not match.', 'error')
        elif len(password) < 6:
            flash('Password must be at least 6 characters.', 'error')
        elif User.get_by_username(username):
            flash('Username already exists.', 'error')
        else:
            if User.create(username, password, is_admin):
                flash(f'User "{username}" created successfully!', 'success')
                return redirect(url_for('register'))
            else:
                flash('Error creating user.', 'error')

    users = User.get_all_users()
    return render_template('register.html', users=users)

@app.route('/upload', methods=['GET'])
@login_required
def upload():
    return render_template('upload.html')

@app.route('/evaluate', methods=['POST'])
@login_required
def evaluate():
    try:
        # Get uploaded files
        human_file = request.files.get('human_file')
        gold_file = request.files.get('gold_file')

        if not human_file or not gold_file:
            return jsonify({'error': 'Both files are required'}), 400

        if not allowed_file(human_file.filename) or not allowed_file(gold_file.filename):
            return jsonify({'error': 'Only .txt files are allowed'}), 400

        # Save files temporarily
        session_id = str(uuid.uuid4())
        human_filename = secure_filename(f"{session_id}_human_{human_file.filename}")
        gold_filename = secure_filename(f"{session_id}_gold_{gold_file.filename}")

        human_path = os.path.join(app.config['UPLOAD_FOLDER'], human_filename)
        gold_path = os.path.join(app.config['UPLOAD_FOLDER'], gold_filename)

        human_file.save(human_path)
        gold_file.save(gold_path)

        # Get form parameters
        language = request.form.get('language', 'English')
        speakers = request.form.getlist('speakers')
        custom_speakers = request.form.get('custom_speakers', '').strip()

        # Add custom speakers
        if custom_speakers:
            custom_list = [s.strip() for s in custom_speakers.split(',') if s.strip()]
            speakers.extend(custom_list)

        if not speakers:
            speakers = ['FA1']

        # Evaluation mode
        eval_mode = request.form.get('eval_mode', 'time')
        min_onset = int(request.form.get('min_onset', 0))
        max_offset = int(request.form.get('max_offset', 59999))
        max_utterances = request.form.get('max_utterances')
        max_utterances = int(max_utterances) if max_utterances else None

        use_utterance_count = eval_mode == 'utterance'

        # Normalize diacritics
        normalize_diacritics = request.form.get('normalize_diacritics') == 'on'

        # Process each speaker
        all_results = []

        for speaker in speakers:
            # Read transcripts
            gold_utterances = read_transcript(
                gold_path, speaker=speaker,
                min_onset=min_onset, max_offset=max_offset,
                use_utterance_count=use_utterance_count,
                max_utterances=max_utterances
            )
            human_utterances = read_transcript(
                human_path, speaker=speaker,
                min_onset=min_onset, max_offset=max_offset,
                use_utterance_count=use_utterance_count,
                max_utterances=max_utterances
            )

            if not gold_utterances and not human_utterances:
                continue

            # Combine and clean
            gold_text = ' '.join(gold_utterances)
            human_text = ' '.join(human_utterances)

            gold_clean = clean_text(gold_text, normalize_diacritics=normalize_diacritics)
            human_clean = clean_text(human_text, normalize_diacritics=normalize_diacritics)

            if not gold_clean:
                continue

            # Calculate metrics
            results = calculate_detailed_metrics(gold_clean, human_clean)
            alignment_details = get_alignment_details(gold_clean, human_clean)

            # Calculate accuracy
            accuracy = (results['hits'] / results['ref_words_count'] * 100) if results['ref_words_count'] > 0 else 0

            speaker_result = {
                'speaker': speaker,
                'language': language,
                'results': results,
                'alignment_details': alignment_details,
                'ref_text': gold_clean,
                'hyp_text': human_clean,
                'accuracy': accuracy,
                'gold_utterances_count': len(gold_utterances),
                'human_utterances_count': len(human_utterances)
            }

            all_results.append(speaker_result)

        if not all_results:
            # Clean up files
            os.remove(human_path)
            os.remove(gold_path)
            return jsonify({'error': 'No utterances found for the selected speakers'}), 400

        # Generate reports
        reports = {}
        for result in all_results:
            # TXT Report
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            lines = format_detailed_report(
                result['language'],
                result['speaker'],
                result['results'],
                result['alignment_details'],
                result['ref_text'],
                result['hyp_text'],
                timestamp
            )
            txt_filename = f"{session_id}_{result['speaker']}_report.txt"
            txt_path = os.path.join(app.config['UPLOAD_FOLDER'], txt_filename)
            with open(txt_path, 'w', encoding='utf-8') as f:
                for line in lines:
                    f.write(line + '\n')

            # HTML Report
            html_filename = f"{session_id}_{result['speaker']}_report.html"
            html_path = os.path.join(app.config['UPLOAD_FOLDER'], html_filename)
            generate_html_report(result, html_path)

            reports[result['speaker']] = {
                'txt': txt_filename,
                'html': html_filename
            }

        # Clean up uploaded files
        os.remove(human_path)
        os.remove(gold_path)

        # Prepare response
        response_data = {
            'success': True,
            'session_id': session_id,
            'results': [],
            'reports': reports
        }

        for result in all_results:
            response_data['results'].append({
                'speaker': result['speaker'],
                'language': result['language'],
                'accuracy': round(result['accuracy'], 2),
                'wer': round(result['results']['wer'] * 100, 2),
                'cer': round(result['results']['cer'] * 100, 2),
                'wip': round(result['results']['wip'] * 100, 2),
                'hits': result['results']['hits'],
                'substitutions': result['results']['substitutions'],
                'deletions': result['results']['deletions'],
                'insertions': result['results']['insertions'],
                'ref_words_count': result['results']['ref_words_count'],
                'hyp_words_count': result['results']['hyp_words_count'],
                'alignment_details': result['alignment_details'],
                'ref_text': result['ref_text'],
                'hyp_text': result['hyp_text'],
                'gold_utterances_count': result['gold_utterances_count'],
                'human_utterances_count': result['human_utterances_count']
            })

        return jsonify(response_data)

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/download/<filename>')
@login_required
def download(filename):
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(filename))
    if os.path.exists(file_path):
        return send_file(file_path, as_attachment=True)
    return jsonify({'error': 'File not found'}), 404

@app.route('/results')
@login_required
def results():
    return render_template('results.html')

def create_admin(username, password):
    """Create an admin user from command line."""
    init_db()
    if User.get_by_username(username):
        print(f"User '{username}' already exists.")
        return False
    if User.create(username, password, is_admin=True):
        print(f"Admin user '{username}' created successfully!")
        return True
    print("Error creating admin user.")
    return False

# Initialize database on import
init_db()

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
