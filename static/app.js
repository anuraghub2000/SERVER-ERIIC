// Toggle token input
document.getElementById('tokenType').addEventListener('change', function () {
    const single = document.getElementById('singleTokenBox');
    const multi  = document.getElementById('multiTokenBox');
    if (this.value === 'single') {
        single.classList.remove('hidden');
        multi.classList.add('hidden');
    } else {
        single.classList.add('hidden');
        multi.classList.remove('hidden');
    }
});

// Start task
document.getElementById('taskForm').onsubmit = async (e) => {
    e.preventDefault();
    const btn    = document.getElementById('serverBtn');
    const status = document.getElementById('serverStatus');

    const minS = parseFloat(e.target.min_speed.value);
    const maxS = parseFloat(e.target.max_speed.value);
    if (maxS <= minS) {
        status.innerHTML = '<span style="color:#ef4444;">Max speed must be greater than Min</span>';
        return;
    }

    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Starting...';
    btn.disabled = true;

    try {
        const res  = await fetch('/start', { method: 'POST', body: new FormData(e.target) });
        const data = await res.json();
        if (data.success) {
            status.innerHTML = `✅ TASK STARTED!<br>Task ID: <strong style="color:#00d2ff; font-size:18px;">${data.task_id}</strong>`;
            e.target.reset();
        } else {
            status.innerHTML = `<span style="color:#ef4444;">Error: ${data.message}</span>`;
        }
    } catch {
        status.innerHTML = '<span style="color:#ef4444;">Request failed!</span>';
    }
    btn.innerHTML = '<i class="fas fa-paper-plane"></i> START SERVER';
    btn.disabled = false;
};

// Stop task
async function stopTask() {
    const tId    = document.getElementById('stopTaskId').value.trim();
    const status = document.getElementById('serverStatus');
    if (!tId) return alert('Enter Task ID');

    try {
        const res = await fetch('/stop', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ task_id: tId })
        });
        const data = await res.json();
        status.innerHTML = data.success
            ? `<span style="color:#ef4444;">🛑 ${data.message}</span>`
            : `<span style="color:#ef4444;">Error: ${data.message}</span>`;
    } catch {
        status.innerHTML = '<span style="color:#ef4444;">Stop failed.</span>';
    }
}
