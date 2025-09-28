// Global state
let selectedFile = null;
let isProcessing = false;
let messageCount = 0;

// Utility functions
function getTimestamp() {
    return new Date().toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
}

function autoResize() {
    const textarea = document.getElementById('textInput');
    textarea.style.height = 'auto';
    textarea.style.height = Math.min(textarea.scrollHeight, 160) + 'px';
}

function handleEnterKey(event) {
    if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        submitMessage();
    }
}

function setPrompt(prompt) {
    document.getElementById('textInput').value = prompt;
    document.getElementById('textInput').focus();
    autoResize();
}

function clearChat() {
    document.getElementById('chatArea').innerHTML = `
        <div class="welcome-screen">
            <h3>📄 Intelligent Legal Document Analysis</h3>
            <p>Upload or paste legal documents to get AI-powered structured summaries. Our advanced system automatically detects document types (court cases, contracts, property deeds, tax documents, employment agreements, IP documents, criminal cases, and regulatory policies) and provides specialized analysis with proper legal formatting.</p>
            
            <div class="example-prompts">
                <div class="example-prompt" onclick="setPrompt('Summarize focusing on payment terms and financial obligations')">💰 Payment Focus</div>
                <div class="example-prompt" onclick="setPrompt('Summarize highlighting key dates and deadlines')">📅 Dates & Deadlines</div>
                <div class="example-prompt" onclick="setPrompt('Summarize emphasizing parties and their roles')">👥 Parties & Roles</div>
                <div class="example-prompt" onclick="setPrompt('Summarize with focus on legal risks and compliance')">⚠️ Risk Analysis</div>
            </div>
        </div>
    `;
    messageCount = 0;
    removeFile();
    document.getElementById('textInput').value = '';
    autoResize();
}

function triggerFileUpload() {
    document.getElementById('fileInput').click();
}

function removeFile() {
    selectedFile = null;
    document.getElementById('fileInput').value = '';
    document.getElementById('filePreview').classList.remove('show');
}

function handleFileSelection(event) {
    if (event.target.files.length > 0) {
        const file = event.target.files[0];
        const allowedExtensions = ['.pdf', '.docx', '.txt'];
        const fileExtension = '.' + file.name.split('.').pop().toLowerCase();
        
        if (!allowedExtensions.includes(fileExtension)) {
            alert('Please select a PDF, DOCX, or TXT file.');
            return;
        }
        
        if (file.size > 20 * 1024 * 1024) {
            alert('File size exceeds 20MB limit.');
            return;
        }
        
        selectedFile = file;
        document.getElementById('fileName').textContent = file.name;
        document.getElementById('fileSize').textContent = '(' + formatBytes(file.size) + ')';
        document.getElementById('filePreview').classList.add('show');
    }
}

function formatBytes(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

function addMessage(content, isUser, attachedFileName = '') {
    if (messageCount === 0) {
        document.getElementById('chatArea').innerHTML = '';
    }
    
    messageCount++;
    const messageElement = document.createElement('div');
    messageElement.className = `message ${isUser ? 'user' : 'bot'}`;
    
    let fileAttachment = '';
    if (attachedFileName) {
        fileAttachment = `<div class="file-attachment">📄 ${attachedFileName}</div>`;
    }
    
    messageElement.innerHTML = `
        <div class="avatar">${isUser ? '👤' : '🤖'}</div>
        <div class="message-content">
            ${fileAttachment}
            ${content}
            ${!isUser ? '<button class="copy-button" onclick="copyContent(this)">📋</button>' : ''}
            <div class="timestamp">${getTimestamp()}</div>
        </div>
    `;
    
    document.getElementById('chatArea').appendChild(messageElement);
    document.getElementById('chatArea').scrollTop = document.getElementById('chatArea').scrollHeight;
    
    return messageElement;
}

function showTypingIndicator() {
    const typingElement = document.createElement('div');
    typingElement.className = 'message bot';
    typingElement.id = 'typingIndicator';
    
    typingElement.innerHTML = `
        <div class="avatar">🤖</div>
        <div class="typing-indicator">
            <span>Analyzing legal document with AI...</span>
            <div class="typing-dots">
                <span></span>
                <span></span>
                <span></span>
            </div>
        </div>
    `;
    
    document.getElementById('chatArea').appendChild(typingElement);
    document.getElementById('chatArea').scrollTop = document.getElementById('chatArea').scrollHeight;
    
    return typingElement;
}

function hideTypingIndicator() {
    const indicator = document.getElementById('typingIndicator');
    if (indicator) {
        indicator.remove();
    }
}

function copyContent(button) {
    const messageContent = button.parentElement;
    const tempElement = document.createElement('div');
    tempElement.innerHTML = messageContent.innerHTML;
    
    const copyBtn = tempElement.querySelector('.copy-button');
    const timestamp = tempElement.querySelector('.timestamp');
    if (copyBtn) copyBtn.remove();
    if (timestamp) timestamp.remove();
    
    const textContent = tempElement.textContent.trim();
    
    navigator.clipboard.writeText(textContent).then(function() {
        const originalText = button.textContent;
        button.textContent = '✅';
        setTimeout(function() {
            button.textContent = originalText;
        }, 1500);
    }).catch(function() {
        alert('Please manually copy the text');
    });
}

async function submitMessage() {
    if (isProcessing) return;
    
    const userMessage = document.getElementById('textInput').value.trim();
    const wordLimit = parseInt(document.getElementById('wordCount').value) || 500;
    
    if (!userMessage && !selectedFile) {
        alert('Please enter document text or attach a file for AI analysis.');
        return;
    }
    
    isProcessing = true;
    document.getElementById('sendButton').disabled = true;
    
    const displayMessage = userMessage || 'Please analyze this legal document using AI.';
    addMessage(displayMessage, true, selectedFile ? selectedFile.name : '');
    
    document.getElementById('textInput').value = '';
    autoResize();
    
    showTypingIndicator();
    
    try {
        const formData = new FormData();
        
        if (selectedFile) {
            formData.append('file', selectedFile);
        }
        
        if (userMessage) {
            formData.append('main_content', userMessage);
        }
        
        formData.append('max_length', wordLimit);
        
        const response = await fetch('/summarize', {
            method: 'POST',
            body: formData
        });
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        hideTypingIndicator();
        
        const contentType = response.headers.get('content-type');
        
        if (contentType && contentType.includes('text/event-stream')) {
            const botMessage = addMessage('', false);
            const contentArea = botMessage.querySelector('.message-content');
            const copyBtn = contentArea.querySelector('.copy-button');
            const timestamp = contentArea.querySelector('.timestamp');
            
            await processStreamingResponse(response, contentArea, copyBtn, timestamp);
        } else {
            const result = await response.json();
            if (result.success) {
                addMessage(result.summary, false);
            } else {
                addMessage(`❌ Error: ${result.error}`, false);
            }
        }
        
    } catch (error) {
        console.error('Error in submitMessage:', error);
        hideTypingIndicator();
        addMessage(`❌ Error: ${error.message}`, false);
    } finally {
        isProcessing = false;
        document.getElementById('sendButton').disabled = false;
        removeFile();
    }
}

async function processStreamingResponse(response, contentArea, copyBtn, timestamp) {
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let accumulator = '';
    
    try {
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            
            const chunk = decoder.decode(value, { stream: true });
            const lines = chunk.split('\n');
            
            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    try {
                        const data = JSON.parse(line.slice(6));
                        
                        if (data.error) {
                            contentArea.innerHTML = `❌ ${data.error}${copyBtn.outerHTML}${timestamp.outerHTML}`;
                            return;
                        }
                        
                        if (data.done) {
                            return;
                        }
                        
                        if (data.content) {
                            accumulator += data.content;
                            const tempDiv = document.createElement('div');
                            tempDiv.innerHTML = accumulator + copyBtn.outerHTML + timestamp.outerHTML;
                            contentArea.innerHTML = tempDiv.innerHTML;
                            
                            document.getElementById('chatArea').scrollTop = document.getElementById('chatArea').scrollHeight;
                        }
                    } catch (e) {
                        console.log('Ignoring malformed JSON line:', line);
                    }
                }
            }
        }
    } catch (error) {
        console.error('Streaming error:', error);
        contentArea.innerHTML = `❌ Streaming error: ${error.message}${copyBtn.outerHTML}${timestamp.outerHTML}`;
    }
}

// Setup drag and drop functionality
document.addEventListener('DOMContentLoaded', function() {
    const inputArea = document.querySelector('.input-area');
    
    inputArea.addEventListener('dragover', function(e) {
        e.preventDefault();
        inputArea.style.borderColor = '#3498db';
        inputArea.style.backgroundColor = '#f0f8ff';
    });
    
    inputArea.addEventListener('dragleave', function(e) {
        if (!inputArea.contains(e.relatedTarget)) {
            inputArea.style.borderColor = '#e1e8ed';
            inputArea.style.backgroundColor = '#f8f9fa';
        }
    });
    
    inputArea.addEventListener('drop', function(e) {
        e.preventDefault();
        inputArea.style.borderColor = '#e1e8ed';
        inputArea.style.backgroundColor = '#f8f9fa';
        
        const files = e.dataTransfer.files;
        if (files.length > 0) {
            const file = files[0];
            document.getElementById('fileInput').files = files;
            handleFileSelection({target: {files: [file]}});
        }
    });
    
    console.log('Legal Document Summarizer with Advanced AI loaded successfully!');
});