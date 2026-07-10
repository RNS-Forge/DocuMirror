document.addEventListener('DOMContentLoaded', () => {
    const uploadArea = document.getElementById('upload-area');
    const fileInput = document.getElementById('file-input');
    const startBtn = document.getElementById('start-btn');
    const logStream = document.getElementById('log-stream');
    
    // Tab switching
    const tabBtns = document.querySelectorAll('.tab-btn');
    const tabContents = document.querySelectorAll('.tab-content');
    
    tabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            tabBtns.forEach(b => b.classList.remove('active'));
            tabContents.forEach(c => c.classList.remove('active'));
            
            btn.classList.add('active');
            const targetId = `tab-${btn.dataset.tab}`;
            document.getElementById(targetId).classList.add('active');
        });
    });

    // File Upload handling
    uploadArea.addEventListener('click', () => fileInput.click());
    
    uploadArea.addEventListener('dragover', (e) => {
        e.preventDefault();
        uploadArea.style.borderColor = 'var(--accent-blue)';
    });

    uploadArea.addEventListener('dragleave', () => {
        uploadArea.style.borderColor = 'var(--border)';
    });

    uploadArea.addEventListener('drop', (e) => {
        e.preventDefault();
        uploadArea.style.borderColor = 'var(--border)';
        if(e.dataTransfer.files.length) {
            handleFile(e.dataTransfer.files[0]);
        }
    });

    fileInput.addEventListener('change', (e) => {
        if(e.target.files.length) {
            handleFile(e.target.files[0]);
        }
    });

    let currentFile = null;

    function handleFile(file) {
        currentFile = file;
        uploadArea.querySelector('p').textContent = file.name;
        startBtn.disabled = false;
        addLog(`File loaded: ${file.name}`, 'info');
    }

    function addLog(message, type='system') {
        const div = document.createElement('div');
        div.className = `log-entry ${type}`;
        div.textContent = `[${new Date().toLocaleTimeString()}] ${message}`;
        logStream.appendChild(div);
        logStream.scrollTop = logStream.scrollHeight;
    }

    // Pipeline Animation Mock
    const nodes = [
        'node-classifier',
        'node-generator',
        'node-verifier',
        'node-json',
        'node-output'
    ];

    startBtn.addEventListener('click', () => {
        startBtn.disabled = true;
        logStream.innerHTML = ''; // Clear logs
        addLog('Pipeline started...', 'info');
        
        // Reset nodes
        nodes.forEach(id => {
            document.getElementById(id).className = 'node';
        });
        
        simulatePipeline();
    });

    async function simulatePipeline() {
        const delay = ms => new Promise(r => setTimeout(r, ms));
        
        // 1. Classifier
        const nClass = document.getElementById('node-classifier');
        nClass.classList.add('active');
        addLog('Classifier Agent: analyzing image layout...', 'system');
        await delay(1500);
        addLog('Classifier Agent: Document is Commercial Invoice (Confidence 0.98)', 'success');
        nClass.classList.replace('active', 'done');
        
        // 2. Generator
        const nGen = document.getElementById('node-generator');
        nGen.classList.add('active');
        addLog('CI Agent: Querying RAG/ci/embeddings...', 'info');
        await delay(1000);
        addLog('CI Agent: Retrieved 3 matching templates (similarity 0.91, 0.87, 0.85)', 'system');
        await delay(1500);
        addLog('CI Agent: Generated draft HTML based on template #1', 'success');
        nGen.classList.replace('active', 'done');
        
        // 3. Verifier (Iterative)
        const nVer = document.getElementById('node-verifier');
        const vCount = document.getElementById('verifier-counter');
        nVer.classList.add('active');
        
        for (let i = 1; i <= 3; i++) {
            vCount.textContent = `Iteration ${i}/3`;
            addLog(`Verifier Agent: Rendering draft and comparing to source (Pass ${i})...`, 'system');
            await delay(1500);
            
            if (i < 3) {
                addLog(`Verifier Agent: colspan mismatch in item table row 4. Sending to CI Agent...`, 'warning');
                await delay(1000);
                addLog(`CI Agent: Correcting HTML structure...`, 'info');
                await delay(1000);
            } else {
                addLog(`Verifier Agent: 0 mismatches found. Output verified.`, 'success');
            }
        }
        nVer.classList.replace('active', 'done');

        // 4. JSON Agent
        const nJson = document.getElementById('node-json');
        nJson.classList.add('active');
        addLog('JSON Agent: Mapping fields to docs.* and item.* schema...', 'info');
        await delay(1000);
        addLog('JSON Agent: Output mapped and validated against schema.', 'success');
        nJson.classList.replace('active', 'done');
        
        // 5. Output
        const nOut = document.getElementById('node-output');
        nOut.classList.add('active');
        await delay(500);
        addLog('Orchestrator: Pipeline complete. Results ready.', 'success');
        nOut.classList.replace('active', 'done');
        
        // Populate output mock data
        populateMockOutput();
        startBtn.disabled = false;
    }
    
    function populateMockOutput() {
        // Hide empty states
        document.querySelectorAll('.empty-state').forEach(el => el.style.display = 'none');
        
        // HTML Code
        const htmlMock = `<!-- Generated Commercial Invoice -->\n<table>\n  <tr data-repeat="item">\n    <td data-field="item.style_number">101A</td>\n    <td data-field="item.amount">$450.00</td>\n  </tr>\n</table>`;
        document.getElementById('html-code').textContent = htmlMock;
        
        // JSON Code
        const jsonMock = `{\n  "docs": {\n    "invoice_number": "INV-2024-001"\n  },\n  "item": [\n    {\n      "style_number": "101A",\n      "amount": "$450.00"\n    }\n  ]\n}`;
        document.getElementById('json-code').textContent = jsonMock;
        
        // Switch to HTML tab to show it's done
        document.querySelector('[data-tab="html"]').click();
    }
    
    // Chatbot interactions
    const chatInput = document.getElementById('chat-input');
    const sendBtn = document.getElementById('send-chat-btn');
    const chatHistory = document.getElementById('chat-history');
    
    sendBtn.addEventListener('click', handleChat);
    chatInput.addEventListener('keypress', (e) => {
        if(e.key === 'Enter') handleChat();
    });
    
    function handleChat() {
        const text = chatInput.value.trim();
        if(!text) return;
        
        // Add user msg
        const uDiv = document.createElement('div');
        uDiv.className = 'chat-message user';
        uDiv.textContent = text;
        chatHistory.appendChild(uDiv);
        
        chatInput.value = '';
        chatHistory.scrollTop = chatHistory.scrollHeight;
        
        // Mock agent reply
        setTimeout(() => {
            const aDiv = document.createElement('div');
            aDiv.className = 'chat-message agent';
            aDiv.textContent = 'I have queried the RAG store. The "colspan" was adjusted because the underlying HTML template for this buyer variant merged the last two columns for the subtotal row.';
            chatHistory.appendChild(aDiv);
            chatHistory.scrollTop = chatHistory.scrollHeight;
        }, 1000);
    }
});
