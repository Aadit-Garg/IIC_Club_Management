// ===== Modal Handling =====
function openModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.add('active');
        document.body.style.overflow = 'hidden';
    }
}

function closeModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.remove('active');
        document.body.style.overflow = '';
    }
}

// Close modal on overlay click
document.addEventListener('click', function(e) {
    if (e.target.classList.contains('modal-overlay')) {
        e.target.classList.remove('active');
        document.body.style.overflow = '';
    }
});

// Close modal on Escape
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
        document.querySelectorAll('.modal-overlay.active').forEach(function(modal) {
            modal.classList.remove('active');
            document.body.style.overflow = '';
        });
    }
});

// ===== Discussion Polling & Mentions =====
let chatPollInterval = null;
let lastMsgId = 0;

function startChatPolling(channelId) {
    if (chatPollInterval) clearInterval(chatPollInterval);
    
    chatPollInterval = setInterval(() => {
        fetch(`/api/messages/${channelId}?after=${lastMsgId}`)
            .then(res => res.json())
            .then(messages => {
                if (messages.length > 0) {
                    const chatMessages = document.getElementById('chatMessages');
                    if (!chatMessages) return;
                    
                    // Remove loading spinner if present
                    const spinner = chatMessages.querySelector('.spinner')?.parentElement;
                    if (spinner) spinner.remove();
                    
                    messages.forEach(msg => {
                        if (msg.id > lastMsgId) {
                            lastMsgId = msg.id;
                            const msgHtml = typeof renderMsg === 'function' ? renderMsg(msg) : '';
                            if (msgHtml) {
                                chatMessages.insertAdjacentHTML('beforeend', msgHtml);
                            }
                        }
                    });
                    
                    chatMessages.scrollTop = chatMessages.scrollHeight;
                }
            })
            .catch(err => console.error('Polling error:', err));
    }, 3000);
}

// ===== Flash messages auto-dismiss =====
document.addEventListener('DOMContentLoaded', function() {
    const flashes = document.querySelectorAll('.flash-msg');
    flashes.forEach(function(flash, index) {
        setTimeout(function() {
            flash.style.animation = 'slideInRight 0.3s ease reverse forwards';
            setTimeout(function() { flash.remove(); }, 300);
        }, 4000 + index * 500);
    });

    // Auto-scroll discussion to bottom
    const chatMessages = document.querySelector('.chat-messages');
    if (chatMessages) {
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }
});

// ===== Sidebar Mobile Toggle =====
function toggleSidebar() {
    const sidebar = document.querySelector('.sidebar');
    sidebar.classList.toggle('open');
}

// ===== Confirm Delete =====
function confirmDelete(formId, itemName) {
    if (confirm('Are you sure you want to delete ' + itemName + '?')) {
        document.getElementById(formId).submit();
    }
}
