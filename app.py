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
            'sander': 'Seef88',
            'eva': 'Seef88'
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

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
