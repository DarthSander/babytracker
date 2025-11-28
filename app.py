from flask import Flask, jsonify, request
from flask_cors import CORS
import json
import os
from datetime import datetime

app = Flask(__name__)
CORS(app)

DATA_FILE = 'baby_data.json'
USERS_FILE = 'users.json'

# Initialize data files if they don't exist
def init_files():
    if not os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'w') as f:
            json.dump([], f)
    
    if not os.path.exists(USERS_FILE):
        # Default users
        users = {
            'sander': 'password',
            'partner': 'password'
        }
        with open(USERS_FILE, 'w') as f:
            json.dump(users, f)

init_files()

# Login endpoint
@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    
    with open(USERS_FILE, 'r') as f:
        users = json.load(f)
    
    if username in users and users[username] == password:
        return jsonify({'success': True, 'username': username})
    else:
        return jsonify({'success': False, 'message': 'Ongeldige inloggegevens'}), 401

# Get all entries
@app.route('/api/entries', methods=['GET'])
def get_entries():
    with open(DATA_FILE, 'r') as f:
        entries = json.load(f)
    return jsonify(entries)

# Add new entry
@app.route('/api/entries', methods=['POST'])
def add_entry():
    entry = request.json
    
    with open(DATA_FILE, 'r') as f:
        entries = json.load(f)
    
    # Add timestamp if not present
    if 'timestamp' not in entry:
        entry['timestamp'] = datetime.now().isoformat()
    
    entries.insert(0, entry)
    
    with open(DATA_FILE, 'w') as f:
        json.dump(entries, f, indent=2)
    
    return jsonify({'success': True, 'entry': entry})

# Delete entry
@app.route('/api/entries/<int:entry_id>', methods=['DELETE'])
def delete_entry(entry_id):
    with open(DATA_FILE, 'r') as f:
        entries = json.load(f)
    
    entries = [e for e in entries if e.get('id') != entry_id]
    
    with open(DATA_FILE, 'w') as f:
        json.dump(entries, f, indent=2)
    
    return jsonify({'success': True})

# Serve frontend
@app.route('/')
def index():
    try:
        with open('index.html', 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        return f"""
        <html>
        <body>
            <h1>Error: index.html not found</h1>
            <p>Current directory: {os.getcwd()}</p>
            <p>Files in directory:</p>
            <pre>{chr(10).join(os.listdir('.'))}</pre>
        </body>
        </html>
        """, 404

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)
