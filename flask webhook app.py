from flask import Flask, request, jsonify, render_template_string
from pymongo import MongoClient
from datetime import datetime
import os

app = Flask(__name__)

# MongoDB setup
MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017/")
client = MongoClient(MONGO_URI)
db = client["webhookdb"]
collection = db["events"]

# UI template
HTML = """
<!DOCTYPE html>
<html>
<head>
  <title>GitHub Activity Feed</title>
  <style>
    body { font-family: Arial, sans-serif; padding: 2rem; background: #f9f9f9; }
    .card { background: white; padding: 1rem; margin-bottom: 1rem; border-radius: 8px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1); }
  </style>
</head>
<body>
  <h1>GitHub Activity Feed</h1>
  <div id="feed"></div>

  <script>
    async function fetchEvents() {
      const res = await fetch('/events');
      const data = await res.json();
      const feed = document.getElementById('feed');
      feed.innerHTML = '';
      data.forEach(event => {
        const date = new Date(event.timestamp).toUTCString();
        let msg = '';
        if (event.action === 'PUSH') {
          msg = `${event.author} pushed to ${event.to_branch} on ${date}`;
        } else if (event.action === 'PULL_REQUEST') {
          msg = `${event.author} submitted a pull request from ${event.from_branch} to ${event.to_branch} on ${date}`;
        } else if (event.action === 'MERGE') {
          msg = `${event.author} merged branch ${event.from_branch} to ${event.to_branch} on ${date}`;
        }
        const card = `<div class="card">${msg}</div>`;
        feed.innerHTML += card;
      });
    }

    fetchEvents();
    setInterval(fetchEvents, 15000);
  </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML)

@app.route('/events', methods=['GET'])
def get_events():
    events = list(collection.find().sort("timestamp", -1).limit(10))
    for e in events:
        e["_id"] = str(e["_id"])
    return jsonify(events)

@app.route('/webhook', methods=['POST'])
def webhook():
    payload = request.json
    event_type = request.headers.get('X-GitHub-Event')

    if event_type == "push":
        author = payload.get("pusher", {}).get("name", "unknown")
        to_branch = payload.get("ref", "").split("/")[-1]
        timestamp = payload.get("head_commit", {}).get("timestamp", datetime.utcnow().isoformat())
        doc = {
            "author": author,
            "action": "PUSH",
            "from_branch": None,
            "to_branch": to_branch,
            "timestamp": timestamp
        }

    elif event_type == "pull_request":
        pr = payload.get("pull_request", {})
        author = pr.get("user", {}).get("login", "unknown")
        from_branch = pr.get("head", {}).get("ref", "")
        to_branch = pr.get("base", {}).get("ref", "")
        timestamp = pr.get("created_at", datetime.utcnow().isoformat())

        if payload.get("action") == "closed" and pr.get("merged"):
            action_type = "MERGE"
        elif payload.get("action") == "opened":
            action_type = "PULL_REQUEST"
        else:
            return jsonify({"status": "ignored"}), 200

        doc = {
            "author": author,
            "action": action_type,
            "from_branch": from_branch,
            "to_branch": to_branch,
            "timestamp": timestamp
        }
    else:
        return jsonify({"status": "unsupported event"}), 400

    collection.insert_one(doc)
    return jsonify({"status": "success"}), 200

if __name__ == "__main__":
    app.run(debug=True, port=5000)
