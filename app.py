# app.py - WEBSITE ONLY (no bot)
import os
from flask import Flask, jsonify

app = Flask(__name__)
port = int(os.environ.get("PORT", 10000))

@app.route('/')
def home():
    return jsonify({
        "status": "online",
        "service": "SoT TDM Website",
        "message": "Website deployed successfully!",
        "next_step": "Add Discord bot functionality"
    })

@app.route('/health')
def health():
    return jsonify({"status": "healthy", "timestamp": "2024"})

@app.route('/api/test')
def test():
    return jsonify({"message": "API endpoint working!"})

if __name__ == '__main__':
    print(f"🌐 Starting website on port {port}...")
    app.run(host='0.0.0.0', port=port, debug=False)
