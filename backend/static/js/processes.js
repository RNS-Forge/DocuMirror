document.addEventListener('DOMContentLoaded', () => {
    const refreshBtn = document.getElementById('refresh-btn');
    
    const cpuVal = document.getElementById('cpu-val');
    const cpuBar = document.getElementById('cpu-bar');
    const memVal = document.getElementById('mem-val');
    const memBar = document.getElementById('mem-bar');
    const appMemVal = document.getElementById('app-mem-val');
    
    const jobsList = document.getElementById('jobs-list');

    let fetchInterval;

    async function fetchProcesses() {
        try {
            const res = await fetch('/processes');
            if (!res.ok) throw new Error('Network response was not ok');
            const data = await res.json();
            
            updateStats(data.system_stats);
            updateJobs(data.active_jobs);
        } catch (error) {
            console.error('Failed to fetch processes:', error);
            if(jobsList.children.length === 1 && jobsList.children[0].classList.contains('empty-state')) {
                jobsList.innerHTML = '<div class="empty-state">Error loading processes. Is backend running?</div>';
            }
        }
    }

    function updateStats(stats) {
        if (stats.error) return;
        
        cpuVal.textContent = `${stats.cpu_percent.toFixed(1)}%`;
        cpuBar.style.width = `${stats.cpu_percent}%`;
        
        if (stats.cpu_percent > 80) cpuBar.style.backgroundColor = '#e74c3c';
        else if (stats.cpu_percent > 50) cpuBar.style.backgroundColor = '#f39c12';
        else cpuBar.style.backgroundColor = 'var(--accent-blue)';

        memVal.textContent = `${stats.memory_percent.toFixed(1)}%`;
        memBar.style.width = `${stats.memory_percent}%`;
        
        if (stats.memory_percent > 80) memBar.style.backgroundColor = '#e74c3c';
        else if (stats.memory_percent > 50) memBar.style.backgroundColor = '#f39c12';
        else memBar.style.backgroundColor = 'var(--accent-blue)';

        appMemVal.textContent = `${stats.app_memory_mb} MB`;
    }

    function updateJobs(jobs) {
        const jobIds = Object.keys(jobs);
        
        if (jobIds.length === 0) {
            jobsList.innerHTML = '<div class="empty-state">No active or recently completed jobs.</div>';
            return;
        }

        // Sort by start time descending
        jobIds.sort((a, b) => jobs[b].started_at - jobs[a].started_at);

        let html = '';
        jobIds.forEach(id => {
            const job = jobs[id];
            const startTime = new Date(job.started_at * 1000).toLocaleTimeString();
            let duration = '';
            
            if (job.status === 'completed' && job.completed_at) {
                const secs = Math.round(job.completed_at - job.started_at);
                duration = ` • Took ${secs}s`;
            }

            html += `
                <div class="job-card">
                    <div class="job-info">
                        <div class="job-file">File: ${job.filename}</div>
                        <div class="job-id">Job ID: ${id}</div>
                        <div class="job-time">Started at ${startTime}${duration}</div>
                    </div>
                    <div class="job-status ${job.status}">
                        ${job.status}
                    </div>
                </div>
            `;
        });

        jobsList.innerHTML = html;
    }

    refreshBtn.addEventListener('click', () => {
        refreshBtn.disabled = true;
        refreshBtn.textContent = 'Refreshing...';
        
        fetchProcesses().then(() => {
            setTimeout(() => {
                refreshBtn.disabled = false;
                refreshBtn.textContent = 'Refresh';
            }, 500);
        });
    });

    // Initial fetch
    fetchProcesses();
    
    // Auto refresh every 3 seconds
    fetchInterval = setInterval(fetchProcesses, 3000);
});
