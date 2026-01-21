// User info cache (in-memory and localStorage)
const userInfoCache = {};

// Load cache from localStorage on page load
function loadCacheFromStorage() {
    try {
        const stored = localStorage.getItem('userInfoCache');
        if (stored) {
            Object.assign(userInfoCache, JSON.parse(stored));
        }
    } catch (e) {
        console.error('Error loading cache from localStorage:', e);
    }
}

// Save cache to localStorage
function saveCacheToStorage() {
    try {
        localStorage.setItem('userInfoCache', JSON.stringify(userInfoCache));
    } catch (e) {
        console.error('Error saving cache to localStorage:', e);
    }
}

// Fetch user info from Cachet API with CORS proxy
async function fetchUserInfo(userId) {
    // Check in-memory cache first
    if (userInfoCache[userId]) {
        return userInfoCache[userId];
    }
    
    try {
        const corsProxy = 'https://corsproxy.io/?';
        const apiUrl = `https://cachet.dunkirk.sh/users/${userId}`;
        const response = await fetch(corsProxy + encodeURIComponent(apiUrl));
        
        if (response.ok) {
            const data = await response.json();
            // Store in cache
            userInfoCache[userId] = data;
            saveCacheToStorage();
            return data;
        }
    } catch (error) {
        console.error(`Error fetching user info for ${userId}:`, error);
    }
    
    return null;
}

// Create avatar HTML
function createAvatar(userInfo) {
    if (userInfo?.imageUrl) {
        return `<img src="${userInfo.imageUrl}" alt="${userInfo.displayName}" class="event-avatar" onerror="this.style.display='none'" style="border-radius: 50%; width: 32px; height: 32px;">`;
    } else if (userInfo?.displayName) {
        const initial = userInfo.displayName.charAt(0).toUpperCase();
        return `<div class="event-avatar" style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); display: flex; align-items: center; justify-content: center; color: white; font-weight: bold;">${initial}</div>`;
    } else {
        const initial = (userInfo?.id || 'U').charAt(0).toUpperCase();
        return `<div class="event-avatar" style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); display: flex; align-items: center; justify-content: center; color: white; font-weight: bold;">${initial}</div>`;
    }
}

// Parse and format mentions in text
async function formatMentions(text) {
    // Find all mentions like <@U0A9HJT5JB1>
    const mentionRegex = /<@(U[A-Z0-9]+)>/g;
    let formattedText = text;
    const mentions = text.match(mentionRegex) || [];
    
    for (const mention of mentions) {
        const userId = mention.match(/<@(U[A-Z0-9]+)>/)[1];
        const userInfo = await fetchUserInfo(userId);
        const displayName = userInfo?.displayName || userId;
        
        const mentionHtml = `<span class="mention" data-user-id="${userId}" data-user-name="${displayName}">@${displayName}</span>`;
        formattedText = formattedText.replace(mention, mentionHtml);
    }
    
    return formattedText;
}

// Create and show user tooltip
async function showUserTooltip(mentionEl) {
    const userId = mentionEl.dataset.userId;
    const userInfo = await fetchUserInfo(userId);
    
    if (!userInfo) {
        return;
    }
    
    // Remove existing tooltip
    const existingTooltip = document.querySelector('.user-tooltip');
    if (existingTooltip) {
        existingTooltip.remove();
    }
    
    const avatarHtml = userInfo.imageUrl 
        ? `<img src="${userInfo.imageUrl}" alt="${userInfo.displayName}" onerror="this.style.display='none'">`
        : `<div style="font-size: 1.2rem;">${userInfo.displayName.charAt(0).toUpperCase()}</div>`;
    
    const tooltipHtml = `
        <div class="user-tooltip show">
            <div class="tooltip-header">
                <div class="tooltip-avatar">
                    ${avatarHtml}
                </div>
                <div class="tooltip-info">
                    <h4>${userInfo.displayName}</h4>
                    ${userInfo.pronouns ? `<p>${userInfo.pronouns}</p>` : ''}
                    <p style="color: #999; font-size: 0.8rem;">${userId}</p>
                </div>
            </div>
        </div>
    `;
    
    document.body.appendChild(new DOMParser().parseFromString(tooltipHtml, 'text/html').body.firstChild);
    const tooltip = document.querySelector('.user-tooltip');
    
    // Position tooltip relative to mention element
    const rect = mentionEl.getBoundingClientRect();
    let top = rect.top - tooltip.offsetHeight - 10;
    let left = rect.left + rect.width / 2 - tooltip.offsetWidth / 2;
    
    // Keep tooltip within viewport
    if (top < 10) {
        top = rect.bottom + 10;
    }
    if (left < 10) {
        left = 10;
    }
    if (left + tooltip.offsetWidth > window.innerWidth - 10) {
        left = window.innerWidth - tooltip.offsetWidth - 10;
    }
    
    tooltip.style.top = top + 'px';
    tooltip.style.left = left + 'px';
}

// Hide tooltip
function hideUserTooltip(mentionEl) {
    const tooltip = document.querySelector('.user-tooltip');
    if (tooltip && !tooltip.dataset.pinned) {
        tooltip.classList.remove('show');
        setTimeout(() => tooltip.remove(), 200);
    }
}

// Close all pinned tooltips
function closeAllTooltips() {
    const tooltips = document.querySelectorAll('.user-tooltip[data-pinned]');
    tooltips.forEach(tooltip => {
        tooltip.classList.remove('show');
        setTimeout(() => tooltip.remove(), 200);
    });
}

// Setup tooltip close handler
function setupTooltipCloseHandler(tooltip) {
    document.addEventListener('click', function closeHandler(e) {
        if (!tooltip.contains(e.target)) {
            tooltip.classList.remove('show');
            setTimeout(() => tooltip.remove(), 200);
            document.removeEventListener('click', closeHandler);
        }
    });
}

function attachMentionListeners() {
    document.querySelectorAll('.mention').forEach(mentionEl => {
        if (!mentionEl.dataset.listenerAttached) {
            mentionEl.dataset.listenerAttached = 'true';
            mentionEl.addEventListener('mouseenter', () => showUserTooltip(mentionEl));
            mentionEl.addEventListener('mouseleave', () => hideUserTooltip(mentionEl));
            mentionEl.addEventListener('click', async (e) => {
                e.stopPropagation();
                closeAllTooltips();
                const userId = mentionEl.dataset.userId;
                const userInfo = await fetchUserInfo(userId);
                
                if (!userInfo) return;
                
                const avatarHtml = userInfo.imageUrl 
                    ? `<img src="${userInfo.imageUrl}" alt="${userInfo.displayName}" onerror="this.style.display='none'">`
                    : `<div style="font-size: 1.2rem;">${userInfo.displayName.charAt(0).toUpperCase()}</div>`;
                
                const tooltipHtml = `
                    <div class="user-tooltip show" data-pinned="true">
                        <div class="tooltip-header">
                            <div class="tooltip-avatar">
                                ${avatarHtml}
                            </div>
                            <div class="tooltip-info">
                                <h4>${userInfo.displayName}</h4>
                                ${userInfo.pronouns ? `<p>${userInfo.pronouns}</p>` : ''}
                                <p style="color: #999; font-size: 0.8rem;">${userId}</p>
                            </div>
                        </div>
                    </div>
                `;
                
                document.body.appendChild(new DOMParser().parseFromString(tooltipHtml, 'text/html').body.firstChild);
                const tooltip = document.querySelector('.user-tooltip[data-pinned]');
                
                // Position tooltip relative to mention element
                const rect = mentionEl.getBoundingClientRect();
                let top = rect.top - tooltip.offsetHeight - 10;
                let left = rect.left + rect.width / 2 - tooltip.offsetWidth / 2;
                
                // Keep tooltip within viewport
                if (top < 10) {
                    top = rect.bottom + 10;
                }
                if (left < 10) {
                    left = 10;
                }
                if (left + tooltip.offsetWidth > window.innerWidth - 10) {
                    left = window.innerWidth - tooltip.offsetWidth - 10;
                }
                
                tooltip.style.top = top + 'px';
                tooltip.style.left = left + 'px';
                
                setupTooltipCloseHandler(tooltip);
            });
        }
    });
}

async function renderMessagesFromData(eventsData, container) {
    const userInfoMap = {};
    
    if (eventsData.length === 0) return;
    
    // Fetch all user info in parallel (uses cache for already-fetched users)
    await Promise.all(eventsData.map(async (event) => {
        if (!userInfoMap[event.author]) {
            userInfoMap[event.author] = await fetchUserInfo(event.author);
        }
    }));
    
    // Also fetch mentions from event bodies
    const mentionUserIds = new Set();
    eventsData.forEach(event => {
        const bodyText = event.body || '';
        const mentionMatches = bodyText.match(/<@(U[A-Z0-9]+)>/g) || [];
        mentionMatches.forEach(mention => {
            const userId = mention.match(/<@(U[A-Z0-9]+)>/)[1];
            mentionUserIds.add(userId);
        });
    });
    
    await Promise.all(Array.from(mentionUserIds).map(userId => fetchUserInfo(userId)));
    
    let html = '';
    for (const event of eventsData) {
        const userInfo = userInfoMap[event.author];
        const displayName = userInfo?.displayName || event.author;
        const avatarHtml = createAvatar(userInfo || { id: event.author });
        
        const formattedBody = await formatMentions(event.body || '');
        
        html += `
            <div class="event">
                <div class="event-header">
                    ${avatarHtml}
                    <div>
                        <div class="event-author">${displayName}</div>
                        <div class="event-date" style="font-size: 0.75rem; color: #999;">${new Date(event.created_at).toLocaleString()}</div>
                    </div>
                </div>
                <div class="event-body" data-event-body="${event.id}">${formattedBody}</div>
            </div>
        `;
    }
    
    container.insertAdjacentHTML('beforeend', html);
}

async function renderMessages(events, container, startIndex = 0, endIndex = 20) {
    const userInfoMap = {};
    const eventsSlice = events.slice(startIndex, endIndex);
    
    if (eventsSlice.length === 0) return;
    
    // Fetch all user info in parallel (uses cache for already-fetched users)
    await Promise.all(eventsSlice.map(async (event) => {
        if (!userInfoMap[event.author]) {
            userInfoMap[event.author] = await fetchUserInfo(event.author);
        }
    }));
    
    // Also fetch mentions from event bodies
    const mentionUserIds = new Set();
    eventsSlice.forEach(event => {
        const bodyText = event.body || '';
        const mentionMatches = bodyText.match(/<@(U[A-Z0-9]+)>/g) || [];
        mentionMatches.forEach(mention => {
            const userId = mention.match(/<@(U[A-Z0-9]+)>/)[1];
            mentionUserIds.add(userId);
        });
    });
    
    await Promise.all(Array.from(mentionUserIds).map(userId => fetchUserInfo(userId)));
    
    let html = '';
    for (const event of eventsSlice) {
        const userInfo = userInfoMap[event.author];
        const displayName = userInfo?.displayName || event.author;
        const avatarHtml = createAvatar(userInfo || { id: event.author });
        
        const formattedBody = await formatMentions(event.body || '');
        
        html += `
            <div class="event">
                <div class="event-header">
                    ${avatarHtml}
                    <div>
                        <div class="event-author">${displayName}</div>
                        <div class="event-date" style="font-size: 0.75rem; color: #999;">${new Date(event.created_at).toLocaleString()}</div>
                    </div>
                </div>
                <div class="event-body" data-event-body="${event.id}">${formattedBody}</div>
            </div>
        `;
    }
    
    container.insertAdjacentHTML('beforeend', html);
}

async function showIssueDetail(issueId) {
    const modal = document.getElementById('issueModal');
    const title = document.getElementById('modalTitle');
    const body = document.getElementById('modalBody');
    
    modal.classList.add('active');
    title.textContent = 'Loading...';
    body.innerHTML = 'Loading issue details...';
    
    try {
        const response = await fetch(`/api/issues/${issueId}`);
        const issue = await response.json();
        
        title.textContent = issue.title;
        
        let html = `
            <div style="margin-bottom: 1rem;">
                <p style="color: #666; margin-bottom: 1rem; white-space: pre-wrap; word-wrap: break-word;">${issue.description || 'No description'}</p>
                <div style="display: flex; gap: 1rem; margin-bottom: 1rem; align-items: center;">
                    <div style="display: flex; align-items: center; gap: 0.5rem;">
                        <label style="font-weight: 600; color: #333;">Status:</label>
                        <select id="statusSelect" data-issue-id="${issue.id}" style="padding: 0.5rem; border: 1px solid #ddd; border-radius: 4px; background-color: #fff; cursor: pointer;">
                            <option value="unverified" ${issue.status === 'unverified' ? 'selected' : ''}>Unverified</option>
                            <option value="verified" ${issue.status === 'verified' ? 'selected' : ''}>Verified</option>
                            <option value="in_progress" ${issue.status === 'in_progress' ? 'selected' : ''}>In Progress</option>
                            <option value="resolved" ${issue.status === 'resolved' ? 'selected' : ''}>Resolved</option>
                        </select>
                    </div>
                    <div style="display: flex; align-items: center; gap: 0.5rem;">
                        <label style="font-weight: 600; color: #333;">Priority:</label>
                        <select id="prioritySelect" data-issue-id="${issue.id}" style="padding: 0.5rem; border: 1px solid #ddd; border-radius: 4px; background-color: #fff; cursor: pointer;">
                            <option value="low" ${issue.priority === 'low' ? 'selected' : ''}>Low</option>
                            <option value="medium" ${issue.priority === 'medium' ? 'selected' : ''}>Medium</option>
                            <option value="high" ${issue.priority === 'high' ? 'selected' : ''}>High</option>
                            <option value="critical" ${issue.priority === 'critical' ? 'selected' : ''}>Critical</option>
                        </select>
                    </div>
                </div>
                <p style="color: #999; font-size: 0.875rem;">Created: ${new Date(issue.created_at).toLocaleString()}</p>
            </div>
        `;
        
        if (issue.events && issue.events.length > 0) {
            html += '<h3 style="margin-top: 2rem; margin-bottom: 1rem;">Messages</h3>';
            html += '<div id="messagesContainer"></div>';
            
            if (issue.events.length > 20) {
                html += '<div id="loadMoreContainer" style="text-align: center; padding: 1rem;"><p style="color: #999; font-size: 0.875rem;">Loaded 20 of ' + issue.events.length + ' messages</p></div>';
            }
        } else {
            html += '<p style="color: #999; margin-top: 2rem;">No messages yet</p>';
        }
        
        body.innerHTML = html;
        
        // Attach hover and click listeners to mentions - will be done after message rendering
        
        // Add event listeners for status and priority dropdowns
        const statusSelect = document.getElementById('statusSelect');
        const prioritySelect = document.getElementById('prioritySelect');
        
        if (statusSelect) {
            statusSelect.addEventListener('change', async (e) => {
                const newStatus = e.target.value;
                const issueId = e.target.dataset.issueId;
                
                try {
                    const response = await fetch(`/api/issues/${issueId}/status`, {
                        method: 'PATCH',
                        headers: {
                            'Content-Type': 'application/json'
                        },
                        body: JSON.stringify({ status: newStatus })
                    });
                    
                    if (!response.ok) {
                        alert('Failed to update status');
                        e.target.value = issue.status;
                    } else {
                        const result = await response.json();
                        console.log('Status updated successfully');
                    }
                } catch (error) {
                    console.error('Error updating status:', error);
                    alert('Error updating status');
                    e.target.value = issue.status;
                }
            });
        }
        
        if (prioritySelect) {
            prioritySelect.addEventListener('change', async (e) => {
                const newPriority = e.target.value;
                const issueId = e.target.dataset.issueId;
                
                try {
                    const response = await fetch(`/api/issues/${issueId}/priority`, {
                        method: 'PATCH',
                        headers: {
                            'Content-Type': 'application/json'
                        },
                        body: JSON.stringify({ priority: newPriority })
                    });
                    
                    if (!response.ok) {
                        alert('Failed to update priority');
                        e.target.value = issue.priority;
                    } else {
                        const result = await response.json();
                        console.log('Priority updated successfully');
                    }
                } catch (error) {
                    console.error('Error updating priority:', error);
                    alert('Error updating priority');
                    e.target.value = issue.priority;
                }
            });
        }
        
        // Lazy load messages
        if (issue.events && issue.events.length > 0) {
            const messagesContainer = document.getElementById('messagesContainer');
            
            if (messagesContainer) {
                try {
                    // Render first 20 messages
                    await renderMessages(issue.events, messagesContainer, 0, 20);
                    
                    // Attach listeners to newly rendered mentions
                    attachMentionListeners();
                    
                    // Add scroll listener for lazy loading
                    if (issue.total_events > 20) {
                        let currentIndex = 20;
                        let isLoading = false;
                        let lastScrollCheck = 0;
                        
                        const modalContent = document.querySelector('.modal-content');
                        if (modalContent) {
                            
                            const scrollHandler = async () => {
                                const now = Date.now();
                                // Throttle: only check every 500ms
                                if (now - lastScrollCheck < 500) return;
                                lastScrollCheck = now;
                                
                                if (isLoading) return;
                                
                                // Check if scrolled near bottom
                                const scrollTop = modalContent.scrollTop;
                                const scrollHeight = modalContent.scrollHeight;
                                const clientHeight = modalContent.clientHeight;
                                const distanceFromBottom = scrollHeight - (scrollTop + clientHeight);
                                
                                console.log('Scroll check:', { 
                                    scrollTop, 
                                    scrollHeight, 
                                    clientHeight, 
                                    distanceFromBottom,
                                    hasMoreToLoad: currentIndex < issue.events.length,
                                    currentIndex,
                                    totalEvents: issue.events.length
                                });
                                
                                // Trigger load when within 500px of bottom
                                if (distanceFromBottom < 500 && currentIndex < issue.total_events) {
                                    isLoading = true;

                                    
                                    try {
                                        // Fetch next 20 messages from API
                                        const response = await fetch(`/api/issues/${issue.id}/messages?offset=${currentIndex}&limit=20`);
                                        if (!response.ok) throw new Error(`HTTP ${response.status}`);
                                        
                                        const result = await response.json();
                                        
                                        // Render the fetched messages
                                        if (result.events && result.events.length > 0) {
                                            await renderMessagesFromData(result.events, messagesContainer);
                                            
                                            currentIndex = result.offset + result.returned;
                                            
                                            // Update counter
                                            const loadMoreContainer = document.getElementById('loadMoreContainer');
                                            if (loadMoreContainer) {
                                                if (currentIndex >= result.total_events) {
                                                    loadMoreContainer.remove();
                                                } else {
                                                    loadMoreContainer.innerHTML = '<p style="color: #999; font-size: 0.875rem;">Loaded ' + currentIndex + ' of ' + result.total_events + ' messages</p>';
                                                }
                                            }
                                            
                                            // Attach listeners to newly loaded mentions
                                            attachMentionListeners();
                                        }
                                    } catch (apiError) {
                                        console.error('Error fetching messages from API:', apiError);
                                    }
                                    
                                    isLoading = false;
                                }
                            };
                            
                            modalContent.addEventListener('scroll', scrollHandler);
                        }
                    }
                } catch (renderError) {
                    console.error('Error rendering initial messages:', renderError);
                }
            }
        }
    } catch (error) {
        console.error('Error loading issue:', error);
        body.innerHTML = '<p style="color: red;">Error loading issue details</p>';
    }
}

// Load cache on page load
loadCacheFromStorage();

function closeModal() {
    document.getElementById('issueModal').classList.remove('active');
}

// Close modal on background click
document.getElementById('issueModal').addEventListener('click', (e) => {
    if (e.target.id === 'issueModal') {
        closeModal();
    }
});

// Filter functionality
const statusFilter = document.getElementById('statusFilter');
const priorityFilter = document.getElementById('priorityFilter');

function filterIssues() {
    const status = statusFilter.value;
    const priority = priorityFilter.value;
    const cards = document.querySelectorAll('.issue-card');
    
    cards.forEach(card => {
        const statusBadge = card.querySelector('[class*="status-"]');
        const priorityBadge = card.querySelector('[class*="priority-"]');
        
        const matchesStatus = !status || statusBadge.className.includes(`status-${status}`);
        const matchesPriority = !priority || priorityBadge.className.includes(`priority-${priority}`);
        
        card.style.display = matchesStatus && matchesPriority ? 'block' : 'none';
    });
}

statusFilter.addEventListener('change', filterIssues);
priorityFilter.addEventListener('change', filterIssues);
