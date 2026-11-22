"""
ERIC SERVER - Anti-Ban Human Behavior Message Server
Memory-safe, lightweight, pattern-free.
"""
import os
import random
import string
import logging
from threading import Thread, Event
import requests
from flask import Flask, request, render_template, jsonify

# ==========================================
# CONFIG (memory guards)
# ==========================================
MAX_FILE_MB        = 2          # per file
MAX_TOKENS         = 500
MAX_MESSAGES       = 5000
MAX_ACTIVE_TASKS   = 10

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = (MAX_FILE_MB * 2) * 1024 * 1024  # 4MB total

# Active tasks (auto-cleaned on finish)
tasks = {}

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s'
)
log = logging.getLogger('eric')


# ==========================================
# HUMAN-LIKE DELAY
# ==========================================
def human_delay(min_s, max_s):
    """Strict random between min & max — no pattern."""
    return random.uniform(min_s, max_s)


USER_AGENTS = [
    'Mozilla/5.0 (Linux; Android 13; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Mobile Safari/537.36',
    'Mozilla/5.0 (Linux; Android 12; Pixel 6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Mobile Safari/537.36',
    'Mozilla/5.0 (Linux; Android 11; TECNO CE7j) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/101.0.4951.40 Mobile Safari/537.36',
    'Mozilla/5.0 (iPhone; CPU iPhone OS 16_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.3 Mobile/15E148 Safari/604.1',
    'Mozilla/5.0 (iPhone; CPU iPhone OS 17_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Mobile/15E148 Safari/604.1',
]
ACCEPT_LANGS = [
    'en-US,en;q=0.9',
    'en-GB,en;q=0.9',
    'en-US,en;q=0.8,es;q=0.7',
    'en-IN,en;q=0.9',
]


# ==========================================
# WORKER (memory-safe core)
# ==========================================
def send_messages(tid, tokens, thread_id, messages, min_s, max_s, hater_name):
    task = tasks.get(tid)
    if not task:
        return
    stop = task['stop_event']

    # Per-token session + fixed UA (consistent identity)
    sessions = {}
    ua_map = {}
    lang_map = {}
    for tok in tokens:
        sessions[tok] = requests.Session()
        ua_map[tok]   = random.choice(USER_AGENTS)
        lang_map[tok] = random.choice(ACCEPT_LANGS)

    url = f"https://graph.facebook.com/v18.0/t_{thread_id}"
    idx = list(range(len(messages)))  # reused, shuffled in place

    try:
        # Human warm-up (opens chat, thinks)
        if stop.wait(random.uniform(3, 10)):
            return

        while not stop.is_set():
            random.shuffle(idx)  # new order each cycle

            for i in idx:
                if stop.is_set():
                    break

                msg = messages[i]

                # Shuffle tokens per message (no rotation pattern)
                token_list = list(sessions.keys())
                random.shuffle(token_list)

                for tok in token_list:
                    if stop.is_set() or tok not in sessions:
                        continue

                    headers = {
                        'User-Agent':      ua_map[tok],
                        'Accept':          'application/json, text/plain, */*',
                        'Accept-Language': lang_map[tok],
                        'Accept-Encoding': 'gzip, deflate',
                        'Connection':      'keep-alive',
                        'Cache-Control':   'no-cache',
                        'Pragma':          'no-cache',
                    }

                    try:
                        r = sessions[tok].post(
                            url,
                            data={'access_token': tok,
                                  'message': f"{hater_name} {msg}".strip()},
                            headers=headers,
                            timeout=20,
                        )

                        if r.status_code == 200:
                            log.info(f"[{tid}] ✅ {tok[:10]}... | {msg[:40]}")
                        elif r.status_code in (401, 403):
                            log.warning(f"[{tid}] 🚫 token dead — removed")
                            dead = sessions.pop(tok, None)
                            if dead: dead.close()
                            continue
                        elif r.status_code == 429:
                            log.warning(f"[{tid}] ⏳ rate limit — 60~120s pause")
                            if stop.wait(random.uniform(60, 120)):
                                return
                            continue
                        else:
                            log.warning(f"[{tid}] ⚠ status {r.status_code}")

                    except requests.RequestException as e:
                        log.error(f"[{tid}] 🔌 {e}")

                    # 🎯 Random human delay between min & max
                    if stop.wait(human_delay(min_s, max_s)):
                        return

                if not sessions:
                    log.warning(f"[{tid}] all tokens dead — exiting")
                    return

    finally:
        # Always close sessions — no leaked sockets
        for s in sessions.values():
            try: s.close()
            except Exception: pass
        log.info(f"[{tid}] 🧹 worker cleaned up")


def _worker(tid, *args):
    """Wraps send_messages, guarantees task removal from memory."""
    try:
        send_messages(tid, *args)
    except Exception as e:
        log.exception(f"[{tid}] fatal: {e}")
    finally:
        tasks.pop(tid, None)  # 🔑 KEY memory-leak fix
        log.info(f"[{tid}] ♻️  removed from task table")


# ==========================================
# FILE SAFETY
# ==========================================
def _read_lines(file, max_lines):
    raw = file.read(MAX_FILE_MB * 1024 * 1024 + 1)
    if len(raw) > MAX_FILE_MB * 1024 * 1024:
        raise ValueError(f"File > {MAX_FILE_MB}MB rejected")
    lines = raw.decode('utf-8', errors='ignore').splitlines()
    if len(lines) > max_lines:
        raise ValueError(f"Too many lines (max {max_lines})")
    return [l.strip() for l in lines if l.strip()]


# ==========================================
# ROUTES
# ==========================================
@app.route('/')
def index():
    return render_template('index.html')


@app.route('/start', methods=['POST'])
def start_task():
    try:
        if len(tasks) >= MAX_ACTIVE_TASKS:
            return jsonify({'success': False,
                            'message': f'Server busy: max {MAX_ACTIVE_TASKS} active tasks'})

        token_type = request.form.get('token_type', 'single')
        thread_id  = request.form.get('thread_id', '').strip()
        min_speed  = float(request.form.get('min_speed', 30))
        max_speed  = float(request.form.get('max_speed', 120))
        hater_name = request.form.get('hater_name', '').strip()

        if not thread_id:
            return jsonify({'success': False, 'message': 'Thread ID required'})
        if min_speed < 1:
            return jsonify({'success': False, 'message': 'Min speed must be ≥ 1s'})
        if max_speed <= min_speed:
            return jsonify({'success': False, 'message': 'Max must be > Min'})

        # Tokens
        if token_type == 'single':
            tok = request.form.get('single_token', '').strip()
            if not tok:
                return jsonify({'success': False, 'message': 'Token required'})
            tokens = [tok]
        else:
            f = request.files.get('token_file')
            if not f:
                return jsonify({'success': False, 'message': 'Token file required'})
            tokens = _read_lines(f, MAX_TOKENS)

        # Messages
        mf = request.files.get('msg_file')
        if not mf:
            return jsonify({'success': False, 'message': 'Messages file required'})
        messages = _read_lines(mf, MAX_MESSAGES)

        if not tokens:
            return jsonify({'success': False, 'message': 'No valid tokens'})
        if not messages:
            return jsonify({'success': False, 'message': 'No valid messages'})

        tid = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        ev  = Event()
        tasks[tid] = {'stop_event': ev}

        t = Thread(
            target=_worker,
            args=(tid, tokens, thread_id, messages, min_speed, max_speed, hater_name),
            daemon=True,
            name=f"eric-{tid}",
        )
        tasks[tid]['thread'] = t
        t.start()

        log.info(f"[{tid}] 🚀 started | tokens={len(tokens)} msgs={len(messages)} "
                 f"speed={min_speed}-{max_speed}s")
        return jsonify({'success': True, 'task_id': tid})

    except ValueError as ve:
        return jsonify({'success': False, 'message': str(ve)})
    except Exception as e:
        log.exception("start_task error")
        return jsonify({'success': False, 'message': str(e)})


@app.route('/stop', methods=['POST'])
def stop_task():
    tid = (request.get_json() or {}).get('task_id', '')
    t = tasks.get(tid)
    if t:
        t['stop_event'].set()
        return jsonify({'success': True, 'message': f'Task {tid} stopping...'})
    return jsonify({'success': False, 'message': 'Invalid or already finished task'})


@app.route('/status')
def status():
    return jsonify({'active_count': len(tasks), 'tasks': list(tasks.keys())})


@app.errorhandler(413)
def too_large(_):
    return jsonify({'success': False, 'message': 'Upload too large (max 4MB total)'}), 413


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
