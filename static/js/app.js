/**
 * Campus Lost and Found - Frontend Application Controller
 * Handles SPA navigation, real-time rendering, interactive workflows, and polling.
 */

const App = {
  currentView: 'feed',
  currentUser: null,
  activeChatRoomId: null,
  chatPollInterval: null,
  adminPollInterval: null,

  init() {
    this.initTheme();
    this.bindEvents();
    this.restoreSession();
    this.loadStats();
    this.navigateTo('feed');
  },

  // --------------------------------------------------------------------------
  // Theme & Session Management
  // --------------------------------------------------------------------------
  initTheme() {
    const savedTheme = localStorage.getItem('clf_theme') || 'dark';
    document.documentElement.setAttribute('data-theme', savedTheme);
    this.updateThemeIcon(savedTheme);
  },

  toggleTheme() {
    const current = document.documentElement.getAttribute('data-theme') || 'dark';
    const next = current === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    localStorage.setItem('clf_theme', next);
    this.updateThemeIcon(next);
  },

  updateThemeIcon(theme) {
    const btn = document.getElementById('theme-toggle-btn');
    if (btn) {
      btn.innerHTML = theme === 'dark' ? '☀️' : '🌙';
    }
  },

  async restoreSession() {
    const token = api.getToken();
    if (token) {
      try {
        this.currentUser = await api.auth.getMe();
      } catch {
        this.currentUser = null;
        api.clearAuth();
      }
    } else {
      // Default to Alex Chen for instant frictionless demonstration if no user
      this.currentUser = null;
    }
    this.renderNavUser();
  },

  renderNavUser() {
    const container = document.getElementById('nav-user-area');
    const adminLink = document.getElementById('nav-admin-link');

    if (!container) return;

    if (this.currentUser) {
      const isAdm = this.currentUser.role === 'ADMIN';
      const initials = this.currentUser.full_name
        .split(' ')
        .map(n => n[0])
        .join('')
        .toUpperCase()
        .slice(0, 2);

      container.innerHTML = `
        <div class="user-profile-pill">
          <div class="user-avatar">${initials}</div>
          <div>
            <div style="font-weight: 600; line-height: 1.1;">${this.currentUser.full_name}</div>
            <span class="role-tag ${isAdm ? 'admin' : 'user'}">${this.currentUser.role}</span>
          </div>
          <button class="btn btn-sm btn-secondary" onclick="App.logout()" style="margin-left: 0.35rem; padding: 0.25rem 0.55rem; font-size: 0.75rem;">Logout</button>
        </div>
      `;

      if (adminLink) {
        adminLink.style.display = isAdm ? 'flex' : 'none';
      }
    } else {
      container.innerHTML = `
        <button class="btn btn-secondary btn-sm" onclick="App.openAuthModal('login')">Sign In</button>
        <button class="btn btn-primary btn-sm" onclick="App.openAuthModal('register')">Register</button>
      `;
      if (adminLink) {
        adminLink.style.display = 'none';
      }
    }
  },

  async quickLogin(email, password) {
    try {
      this.showToast(`Signing in as ${email}...`, 'info');
      await api.auth.login(email, password);
      this.currentUser = api.getUser();
      this.renderNavUser();
      this.showToast(`Welcome, ${this.currentUser.full_name}!`, 'success');
      this.loadStats();

      // If admin, navigate to admin queue; else feed or my posts
      if (this.currentUser.role === 'ADMIN') {
        this.navigateTo('admin-queue');
      } else {
        this.navigateTo(this.currentView);
      }
    } catch (err) {
      this.showToast(err.message, 'error');
    }
  },

  logout() {
    api.clearAuth();
    this.currentUser = null;
    this.renderNavUser();
    this.showToast('You have been signed out.', 'info');
    this.navigateTo('feed');
  },

  // --------------------------------------------------------------------------
  // Navigation & View Switching
  // --------------------------------------------------------------------------
  navigateTo(viewId) {
    this.currentView = viewId;

    // Check permissions
    if (viewId === 'admin-queue' && (!this.currentUser || this.currentUser.role !== 'ADMIN')) {
      this.showToast('Administrator access required for the Review Queue.', 'error');
      this.openAuthModal('login');
      return;
    }

    if ((viewId === 'my-posts' || viewId === 'chat') && !this.currentUser) {
      this.showToast('Please sign in with your college credentials first.', 'info');
      this.openAuthModal('login');
      return;
    }

    // Update active nav links
    document.querySelectorAll('.nav-link').forEach(link => {
      link.classList.toggle('active', link.dataset.view === viewId);
    });

    // Update views
    document.querySelectorAll('.view-section').forEach(sec => {
      sec.classList.remove('active');
    });

    const target = document.getElementById(`view-${viewId}`);
    if (target) {
      target.classList.add('active');
    }

    window.scrollTo({ top: 0, behavior: 'smooth' });

    // View-specific loader
    if (viewId === 'feed') this.loadLostFeed();
    if (viewId === 'my-posts') this.loadMyPosts();
    if (viewId === 'admin-queue') this.loadAdminMatches();
    if (viewId === 'chat') this.loadChatRooms();

    // Chat polling management
    if (viewId !== 'chat') {
      if (this.chatPollInterval) clearInterval(this.chatPollInterval);
    }
  },

  async loadStats() {
    try {
      if (this.currentUser && this.currentUser.role === 'ADMIN') {
        const stats = await api.admin.getStats();
        const lostEl = document.getElementById('stat-lost-count');
        const foundEl = document.getElementById('stat-found-count');
        const resolvedEl = document.getElementById('stat-resolved-count');
        const badge = document.getElementById('admin-badge-count');

        if (lostEl) lostEl.innerText = stats.total_lost;
        if (foundEl) foundEl.innerText = stats.total_found;
        if (resolvedEl) resolvedEl.innerText = stats.resolved_items;
        if (badge) {
          badge.innerText = stats.pending_matches;
          badge.style.display = stats.pending_matches > 0 ? 'inline-block' : 'none';
        }
      }
    } catch {
      // Ignore background stat error
    }
  },

  // --------------------------------------------------------------------------
  // Public Lost Items Feed
  // --------------------------------------------------------------------------
  async loadLostFeed() {
    const grid = document.getElementById('feed-items-grid');
    if (!grid) return;

    grid.innerHTML = `<div style="grid-column: 1/-1; text-align: center; padding: 3rem; color: var(--text-muted);">
      <div style="font-size: 1.5rem; margin-bottom: 0.5rem;">🔍</div>
      Searching campus lost reports...
    </div>`;

    const search = document.getElementById('feed-search-input')?.value || '';
    const category = document.querySelector('.cat-pill.active')?.dataset.category || '';
    const location = document.getElementById('feed-location-filter')?.value || '';

    try {
      const res = await api.items.listLost({ search, category, location });
      if (res.items.length === 0) {
        grid.innerHTML = `
          <div style="grid-column: 1/-1; text-align: center; padding: 4rem 1rem; color: var(--text-muted);">
            <div style="font-size: 2.5rem; margin-bottom: 1rem;">📦</div>
            <h3>No Lost Items Found</h3>
            <p style="margin-top: 0.5rem;">Try adjusting your search terms or category filter.</p>
          </div>
        `;
        return;
      }

      grid.innerHTML = res.items.map(item => this.renderItemCard(item)).join('');
    } catch (err) {
      grid.innerHTML = `<div style="grid-column: 1/-1; color: var(--danger); text-align: center; padding: 2rem;">Error loading items: ${err.message}</div>`;
    }
  },

  renderItemCard(item) {
    const defaultImg = 'https://images.unsplash.com/photo-1584438784894-089d6a62b8fa?auto=format&fit=crop&w=600&q=80';
    const imgUrl = item.image_url || defaultImg;
    const isOwner = this.currentUser && this.currentUser.id === item.reporter_id;
    const isAdm = this.currentUser && this.currentUser.role === 'ADMIN';

    return `
      <div class="item-card" id="card-${item.id}">
        <div class="item-img-wrap">
          <img src="${imgUrl}" alt="${item.title}" class="item-img" onerror="this.src='${defaultImg}'" />
          <span class="item-type-badge ${item.type.toLowerCase()}">${item.type}</span>
          <span class="item-status-badge status-${item.status.toLowerCase()}">${item.status}</span>
        </div>
        <div class="item-body">
          <div class="item-meta-top">
            <span class="item-category">${item.category}</span>
            <span>📅 ${item.item_date}</span>
          </div>
          <h3 class="item-title">${item.title}</h3>
          <p class="item-desc">${item.description}</p>
          <div class="item-location">
            <span>📍</span>
            <span>${item.location}</span>
          </div>
          <div class="item-footer">
            <span class="reporter-label">Reported by ${item.reporter_name || 'Student'}</span>
            <button class="btn btn-secondary btn-sm" onclick="App.openItemModal('${item.id}')">Details</button>
          </div>
        </div>
      </div>
    `;
  },

  // --------------------------------------------------------------------------
  // Item Reporting (Lost & Found)
  // --------------------------------------------------------------------------
  async handleReportLost(e) {
    e.preventDefault();
    if (!this.currentUser) {
      this.showToast('Please sign in to report a lost item.', 'info');
      this.openAuthModal('login');
      return;
    }

    const form = e.target;
    const formData = new FormData(form);
    const btn = form.querySelector('button[type="submit"]');
    const originalText = btn.innerHTML;

    try {
      btn.innerHTML = 'Submitting & Scanning Matches...';
      btn.disabled = true;

      const res = await api.items.reportLost(formData);
      form.reset();
      document.getElementById('lost-img-preview-box').style.display = 'none';

      if (res.matches_found > 0) {
        this.showToast(`🎉 Lost report created! Algorithm detected ${res.matches_found} candidate match(es) queued for admin approval!`, 'success');
      } else {
        this.showToast('Lost report published to campus feed!', 'success');
      }

      this.navigateTo('my-posts');
    } catch (err) {
      this.showToast(err.message, 'error');
    } finally {
      btn.innerHTML = originalText;
      btn.disabled = false;
    }
  },

  async handleReportFound(e) {
    e.preventDefault();
    if (!this.currentUser) {
      this.showToast('Please sign in to report a found item.', 'info');
      this.openAuthModal('login');
      return;
    }

    const form = e.target;
    const formData = new FormData(form);
    const btn = form.querySelector('button[type="submit"]');
    const originalText = btn.innerHTML;

    try {
      btn.innerHTML = 'Cataloging Securely...';
      btn.disabled = true;

      const res = await api.items.reportFound(formData);
      form.reset();
      document.getElementById('found-img-preview-box').style.display = 'none';

      this.showToast(res.message, 'success');
      if (res.matches_found > 0) {
        this.showToast(`🔎 Match Engine triggered! Found ${res.matches_found} potential owner match(es) sent to Admin Review.`, 'info');
      }

      this.navigateTo('my-posts');
    } catch (err) {
      this.showToast(err.message, 'error');
    } finally {
      btn.innerHTML = originalText;
      btn.disabled = false;
    }
  },

  // --------------------------------------------------------------------------
  // "My Posts" Dashboard
  // --------------------------------------------------------------------------
  async loadMyPosts() {
    const container = document.getElementById('my-posts-list');
    if (!container) return;

    container.innerHTML = `<div style="text-align: center; padding: 2rem; color: var(--text-muted);">Loading your posts...</div>`;

    try {
      const res = await api.items.getMyPosts();
      if (res.items.length === 0) {
        container.innerHTML = `
          <div style="text-align: center; padding: 3rem; background: var(--bg-glass-card); border-radius: var(--radius-lg); border: 1px solid var(--border-glass);">
            <h3>No reports submitted yet</h3>
            <p style="color: var(--text-secondary); margin: 0.75rem 0 1.5rem;">Have you lost something or found an item on campus?</p>
            <div style="display: flex; gap: 1rem; justify-content: center;">
              <button class="btn btn-primary" onclick="App.navigateTo('report-lost')">Report Lost Item</button>
              <button class="btn btn-secondary" onclick="App.navigateTo('report-found')">Report Found Item</button>
            </div>
          </div>
        `;
        return;
      }

      container.innerHTML = res.items.map(item => {
        const isMatched = item.status === 'MATCHED' && item.chat_room_id;
        const defaultImg = 'https://images.unsplash.com/photo-1584438784894-089d6a62b8fa?auto=format&fit=crop&w=600&q=80';

        return `
          <div class="match-comparison-card" style="margin-bottom: 1.5rem;">
            <div class="match-card-header" style="background: var(--bg-glass-subtle);">
              <div style="display: flex; align-items: center; gap: 0.75rem;">
                <span class="item-type-badge ${item.type.toLowerCase()}" style="position: static;">${item.type}</span>
                <span class="item-status-badge status-${item.status.toLowerCase()}" style="position: static;">${item.status}</span>
                <span style="font-weight: 700; font-size: 1.1rem;">${item.title}</span>
              </div>
              <span style="font-size: 0.8rem; color: var(--text-muted);">Reported ${item.item_date}</span>
            </div>

            <div style="padding: 1.25rem; display: flex; gap: 1.5rem; flex-wrap: wrap;">
              <img src="${item.image_url || defaultImg}" style="width: 120px; height: 90px; object-fit: cover; border-radius: var(--radius-sm);" />
              <div style="flex: 1; min-width: 250px;">
                <div style="font-size: 0.85rem; color: var(--primary); font-weight: 600; margin-bottom: 0.25rem;">${item.category} • 📍 ${item.location}</div>
                <p style="font-size: 0.9rem; color: var(--text-secondary); margin-bottom: 0.75rem;">${item.description}</p>
                
                ${item.type === 'FOUND' ? `
                  <div style="font-size: 0.8rem; color: #34d399; background: rgba(16, 185, 129, 0.1); padding: 0.4rem 0.75rem; border-radius: var(--radius-sm); display: inline-block;">
                    🛡️ Protected Found Report: Hidden from public feed to prevent false claims.
                  </div>
                ` : ''}

                ${isMatched ? `
                  <div style="margin-top: 0.5rem; background: rgba(99, 102, 241, 0.15); border: 1px solid rgba(99, 102, 241, 0.3); padding: 0.75rem 1rem; border-radius: var(--radius-md); display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 0.75rem;">
                    <div>
                      <div style="font-weight: 700; color: #818cf8; font-size: 0.95rem;">🎉 Verified Match Approved by Admin!</div>
                      <div style="font-size: 0.8rem; color: var(--text-secondary);">Direct private coordination room is unlocked.</div>
                    </div>
                    <button class="btn btn-primary btn-sm" onclick="App.openChatRoom('${item.chat_room_id}')">Open Handover Chat</button>
                  </div>
                ` : ''}
              </div>
            </div>

            <div class="match-card-actions" style="justify-content: flex-end;">
              <button class="btn btn-danger-outline btn-sm" onclick="App.deleteItem('${item.id}')">Delete Report</button>
            </div>
          </div>
        `;
      }).join('');
    } catch (err) {
      container.innerHTML = `<div style="color: var(--danger); text-align: center;">Error: ${err.message}</div>`;
    }
  },

  async deleteItem(id) {
    if (!confirm('Are you sure you want to delete this report?')) return;
    try {
      await api.items.deleteItem(id);
      this.showToast('Item deleted successfully.', 'success');
      this.loadMyPosts();
      this.loadStats();
    } catch (err) {
      this.showToast(err.message, 'error');
    }
  },

  // --------------------------------------------------------------------------
  // Admin Verification & Review Queue
  // --------------------------------------------------------------------------
  async loadAdminMatches() {
    const list = document.getElementById('admin-matches-list');
    if (!list) return;

    const filter = document.getElementById('admin-filter-status')?.value || 'PENDING';
    list.innerHTML = `<div style="text-align: center; padding: 3rem; color: var(--text-muted);">Loading review queue...</div>`;

    try {
      const res = await api.admin.getMatches(filter);
      if (res.matches.length === 0) {
        list.innerHTML = `
          <div style="text-align: center; padding: 4rem; background: var(--bg-glass-card); border-radius: var(--radius-lg); border: 1px solid var(--border-glass);">
            <div style="font-size: 2.5rem; margin-bottom: 1rem;">✨</div>
            <h3>Queue Cleared</h3>
            <p style="color: var(--text-secondary); margin-top: 0.5rem;">No matches matching status "${filter}".</p>
          </div>
        `;
        return;
      }

      list.innerHTML = res.matches.map(m => this.renderAdminMatchCard(m)).join('');
    } catch (err) {
      list.innerHTML = `<div style="color: var(--danger); text-align: center;">Error loading matches: ${err.message}</div>`;
    }
  },

  renderAdminMatchCard(m) {
    const bd = m.breakdown || {};
    const defaultImg = 'https://images.unsplash.com/photo-1584438784894-089d6a62b8fa?auto=format&fit=crop&w=600&q=80';
    const isPending = m.match_status === 'PENDING';

    return `
      <div class="match-comparison-card" id="match-${m.match_id}">
        <div class="match-card-header">
          <div class="score-badge">
            <div class="score-ring">${m.score}%</div>
            <div>
              <div class="score-text">Match Confidence Score: ${m.score}%</div>
              <div style="font-size: 0.8rem; color: var(--text-muted);">Evaluated via Multi-factor Token Similarity Engine ($\ge 80\%$ Threshold)</div>
            </div>
          </div>
          <span class="item-status-badge status-${m.match_status.toLowerCase()}" style="position: static;">
            ${m.match_status}
          </span>
        </div>

        <div class="match-grid-compare">
          <!-- Lost Item Card -->
          <div class="side-box">
            <div class="side-header">
              <span class="item-type-badge lost" style="position: static;">Lost Item Report</span>
              <span style="font-size: 0.8rem; color: var(--text-muted);">${m.lost_date}</span>
            </div>
            <img src="${m.lost_image || defaultImg}" class="side-img" onerror="this.src='${defaultImg}'" />
            <h4 style="font-size: 1.1rem;">${m.lost_title}</h4>
            <div style="font-size: 0.85rem; color: var(--primary); font-weight: 600;">${m.lost_category} • 📍 ${m.lost_location}</div>
            <p style="font-size: 0.875rem; color: var(--text-secondary); line-height: 1.4;">${m.lost_description}</p>
            <div style="font-size: 0.8rem; color: var(--text-muted); margin-top: auto; padding-top: 0.5rem; border-top: 1px solid var(--border-glass);">
              Reported by: <strong>${m.lost_reporter_name}</strong> (${m.lost_reporter_email})
            </div>
          </div>

          <!-- Found Item Card (Confidential) -->
          <div class="side-box">
            <div class="side-header">
              <span class="item-type-badge found" style="position: static;">Found Item Report (Hidden)</span>
              <span style="font-size: 0.8rem; color: var(--text-muted);">${m.found_date}</span>
            </div>
            <img src="${m.found_image || defaultImg}" class="side-img" onerror="this.src='${defaultImg}'" />
            <h4 style="font-size: 1.1rem;">${m.found_title}</h4>
            <div style="font-size: 0.85rem; color: var(--primary); font-weight: 600;">${m.found_category} • 📍 ${m.found_location}</div>
            <p style="font-size: 0.875rem; color: var(--text-secondary); line-height: 1.4;">${m.found_description}</p>
            <div style="font-size: 0.8rem; color: var(--text-muted); margin-top: auto; padding-top: 0.5rem; border-top: 1px solid var(--border-glass);">
              Finder: <strong>${m.found_reporter_name}</strong> (${m.found_reporter_email})
            </div>
          </div>
        </div>

        <!-- Algorithmic Breakdown Ribbon -->
        <div class="breakdown-bar">
          <div class="breakdown-item">
            <div class="breakdown-val">${bd.category_score ?? '--'}%</div>
            <div style="font-size: 0.725rem; color: var(--text-muted);">Category Match (30%)</div>
          </div>
          <div class="breakdown-item">
            <div class="breakdown-val">${bd.title_score ?? '--'}%</div>
            <div style="font-size: 0.725rem; color: var(--text-muted);">Title Similarity (35%)</div>
          </div>
          <div class="breakdown-item">
            <div class="breakdown-val">${bd.description_score ?? '--'}%</div>
            <div style="font-size: 0.725rem; color: var(--text-muted);">Description Tokens (20%)</div>
          </div>
          <div class="breakdown-item">
            <div class="breakdown-val">${bd.location_score ?? '--'}%</div>
            <div style="font-size: 0.725rem; color: var(--text-muted);">Location Proximity (15%)</div>
          </div>
        </div>

        <!-- Decision Controls -->
        <div class="match-card-actions">
          ${isPending ? `
            <button class="btn btn-danger-outline" onclick="App.rejectMatch('${m.match_id}')">
              ✕ Reject Match
            </button>
            <button class="btn btn-success" onclick="App.approveMatch('${m.match_id}')">
              ✓ Approve Match & Unlock Chat
            </button>
          ` : `
            <div style="font-size: 0.85rem; color: var(--text-secondary);">
              Review complete (${m.match_status})
              ${m.chat_room_id ? `<button class="btn btn-secondary btn-sm" onclick="App.openChatRoom('${m.chat_room_id}')" style="margin-left: 0.75rem;">View Chat Room</button>` : ''}
            </div>
          `}
        </div>
      </div>
    `;
  },

  async approveMatch(matchId) {
    try {
      this.showToast('Approving match and creating private chat...', 'info');
      const res = await api.admin.approveMatch(matchId);
      this.showToast(res.message, 'success');
      this.loadAdminMatches();
      this.loadStats();
    } catch (err) {
      this.showToast(err.message, 'error');
    }
  },

  async rejectMatch(matchId) {
    if (!confirm('Are you sure you want to reject this match suggestion? Items will remain open for other candidates.')) return;
    try {
      const res = await api.admin.rejectMatch(matchId);
      this.showToast(res.message, 'info');
      this.loadAdminMatches();
      this.loadStats();
    } catch (err) {
      this.showToast(err.message, 'error');
    }
  },

  // --------------------------------------------------------------------------
  // In-App Chat Room & Handover Resolution
  // --------------------------------------------------------------------------
  async loadChatRooms() {
    const list = document.getElementById('chat-rooms-list');
    if (!list) return;

    list.innerHTML = `<div style="padding: 1.5rem; text-align: center; color: var(--text-muted);">Loading chats...</div>`;

    try {
      const res = await api.chat.getRooms();
      if (res.rooms.length === 0) {
        list.innerHTML = `
          <div style="padding: 2rem 1rem; text-align: center; color: var(--text-muted);">
            <div style="font-size: 1.8rem; margin-bottom: 0.5rem;">💬</div>
            <p style="font-size: 0.9rem;">No active chat rooms yet.</p>
            <p style="font-size: 0.75rem; margin-top: 0.35rem;">Chat rooms are automatically generated once an admin approves a match.</p>
          </div>
        `;
        this.renderEmptyChatMain();
        return;
      }

      list.innerHTML = res.rooms.map(r => `
        <div class="room-item ${r.room_id === this.activeChatRoomId ? 'active' : ''}" onclick="App.selectChatRoom('${r.room_id}')">
          <div class="room-title">${r.lost_item_title}</div>
          <div class="room-counterpart">With: ${r.counterpart_name} (${r.my_role})</div>
          <div class="room-snippet">${r.last_message || 'Room unlocked. Start coordination...'}</div>
        </div>
      `).join('');

      // Auto-select first room or active room
      if (!this.activeChatRoomId && res.rooms.length > 0) {
        this.selectChatRoom(res.rooms[0].room_id);
      } else if (this.activeChatRoomId) {
        this.selectChatRoom(this.activeChatRoomId);
      }
    } catch (err) {
      list.innerHTML = `<div style="color: var(--danger); padding: 1rem;">Error: ${err.message}</div>`;
    }
  },

  openChatRoom(roomId) {
    this.activeChatRoomId = roomId;
    this.navigateTo('chat');
  },

  async selectChatRoom(roomId) {
    this.activeChatRoomId = roomId;

    // Update active highlight
    document.querySelectorAll('.room-item').forEach(el => {
      el.classList.toggle('active', el.getAttribute('onclick')?.includes(roomId));
    });

    // Start live polling for active room
    if (this.chatPollInterval) clearInterval(this.chatPollInterval);
    await this.fetchAndRenderMessages(roomId);
    this.chatPollInterval = setInterval(() => {
      if (this.currentView === 'chat' && this.activeChatRoomId === roomId) {
        this.fetchAndRenderMessages(roomId, true);
      }
    }, 2500);
  },

  async fetchAndRenderMessages(roomId, isPolling = false) {
    try {
      const data = await api.chat.getMessages(roomId);
      const headerTitle = document.getElementById('chat-room-title');
      const headerSub = document.getElementById('chat-room-sub');
      const resolveBtn = document.getElementById('chat-resolve-btn');
      const stream = document.getElementById('chat-messages-stream');

      if (headerTitle) {
        headerTitle.innerText = `Return Coordination: ${data.meta.lost_title}`;
      }
      if (headerSub) {
        headerSub.innerText = `Owner: ${data.meta.lost_reporter_name} • Finder: ${data.meta.found_reporter_name}`;
      }
      if (resolveBtn) {
        if (data.is_resolved) {
          resolveBtn.innerHTML = '✅ Resolved & Closed';
          resolveBtn.disabled = true;
          resolveBtn.className = 'btn btn-secondary btn-sm';
        } else {
          resolveBtn.innerHTML = 'Mark Handover Complete (Close)';
          resolveBtn.disabled = false;
          resolveBtn.className = 'btn btn-success btn-sm';
          resolveBtn.onclick = () => App.resolveHandover(roomId);
        }
      }

      if (!stream) return;

      const shouldScroll = !isPolling || (stream.scrollHeight - stream.scrollTop - stream.clientHeight < 50);

      stream.innerHTML = data.messages.map(msg => {
        const isMine = this.currentUser && msg.sender_id === this.currentUser.id;
        const isSystem = msg.sender_role === 'ADMIN' && msg.content.includes('Match Approved');

        if (isSystem || msg.content.startsWith('✅ Handover resolved!')) {
          return `
            <div class="msg-bubble system">
              ${msg.content}
              <div class="msg-time">${new Date(msg.created_at).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}</div>
            </div>
          `;
        }

        return `
          <div class="msg-bubble ${isMine ? 'mine' : 'theirs'}">
            <div class="msg-sender">${isMine ? 'You' : msg.sender_name}</div>
            <div>${msg.content}</div>
            <div class="msg-time">${new Date(msg.created_at).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}</div>
          </div>
        `;
      }).join('');

      if (shouldScroll) {
        stream.scrollTop = stream.scrollHeight;
      }
    } catch (err) {
      console.error('Error fetching messages:', err);
    }
  },

  async handleSendMessage(e) {
    e.preventDefault();
    if (!this.activeChatRoomId) return;

    const input = document.getElementById('chat-input-text');
    const content = input.value.trim();
    if (!content) return;

    input.value = '';
    try {
      await api.chat.sendMessage(this.activeChatRoomId, content);
      await this.fetchAndRenderMessages(this.activeChatRoomId);
    } catch (err) {
      this.showToast(err.message, 'error');
    }
  },

  async resolveHandover(roomId) {
    if (!confirm('Mark this lost & found case as RESOLVED and CLOSED? Both items will be marked as recovered.')) return;
    try {
      const res = await api.chat.resolveHandover(roomId);
      this.showToast(res.message, 'success');
      await this.fetchAndRenderMessages(roomId);
      this.loadStats();
    } catch (err) {
      this.showToast(err.message, 'error');
    }
  },

  renderEmptyChatMain() {
    const stream = document.getElementById('chat-messages-stream');
    if (stream) {
      stream.innerHTML = `
        <div style="display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100%; color: var(--text-muted); text-align: center;">
          <div style="font-size: 3rem; margin-bottom: 1rem;">🔒</div>
          <h3>Private Handover Channels</h3>
          <p style="max-width: 360px; font-size: 0.9rem; margin-top: 0.5rem;">
            When an administrator approves a lost-to-found match, a secure private chat room unlocks between the owner and finder.
          </p>
        </div>
      `;
    }
  },

  // --------------------------------------------------------------------------
  // Modals & Details Views
  // --------------------------------------------------------------------------
  async openItemModal(itemId) {
    const modal = document.getElementById('item-detail-modal');
    const content = document.getElementById('item-modal-content');
    if (!modal || !content) return;

    content.innerHTML = `<div style="text-align: center; padding: 2rem;">Loading details...</div>`;
    modal.classList.add('active');

    try {
      const item = await api.items.getItem(itemId);
      const defaultImg = 'https://images.unsplash.com/photo-1584438784894-089d6a62b8fa?auto=format&fit=crop&w=600&q=80';

      content.innerHTML = `
        <img src="${item.image_url || defaultImg}" style="width: 100%; height: 220px; object-fit: cover; border-radius: var(--radius-md); margin-bottom: 1.25rem;" />
        <div style="display: flex; gap: 0.5rem; margin-bottom: 0.75rem;">
          <span class="item-type-badge ${item.type.toLowerCase()}" style="position: static;">${item.type}</span>
          <span class="item-status-badge status-${item.status.toLowerCase()}" style="position: static;">${item.status}</span>
        </div>
        <h2 style="font-size: 1.5rem; margin-bottom: 0.5rem;">${item.title}</h2>
        <div style="font-size: 0.9rem; color: var(--primary); font-weight: 600; margin-bottom: 1rem;">${item.category} • 📍 ${item.location} • 📅 ${item.item_date}</div>
        <p style="font-size: 0.95rem; color: var(--text-secondary); line-height: 1.6; margin-bottom: 1.5rem;">${item.description}</p>
        <div style="background: var(--bg-glass-subtle); padding: 1rem; border-radius: var(--radius-md); font-size: 0.85rem; color: var(--text-muted);">
          Reported by: <strong>${item.reporter_name}</strong> (${item.reporter_email})
        </div>
      `;
    } catch (err) {
      content.innerHTML = `<div style="color: var(--danger); text-align: center;">${err.message}</div>`;
    }
  },

  closeModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) modal.classList.remove('active');
  },

  openAuthModal(tab = 'login') {
    const modal = document.getElementById('auth-modal');
    if (!modal) return;

    modal.classList.add('active');
    this.switchAuthTab(tab);
  },

  switchAuthTab(tab) {
    const loginForm = document.getElementById('auth-login-form');
    const regForm = document.getElementById('auth-register-form');
    const tabLogin = document.getElementById('tab-btn-login');
    const tabReg = document.getElementById('tab-btn-register');

    if (tab === 'login') {
      loginForm.style.display = 'block';
      regForm.style.display = 'none';
      tabLogin.classList.add('btn-primary');
      tabLogin.classList.remove('btn-secondary');
      tabReg.classList.add('btn-secondary');
      tabReg.classList.remove('btn-primary');
    } else {
      loginForm.style.display = 'none';
      regForm.style.display = 'block';
      tabReg.classList.add('btn-primary');
      tabReg.classList.remove('btn-secondary');
      tabLogin.classList.add('btn-secondary');
      tabLogin.classList.remove('btn-primary');
    }
  },

  async handleLoginSubmit(e) {
    e.preventDefault();
    const form = e.target;
    const email = form.email.value.trim();
    const password = form.password.value;

    try {
      await api.auth.login(email, password);
      this.currentUser = api.getUser();
      this.renderNavUser();
      this.closeModal('auth-modal');
      this.showToast(`Welcome back, ${this.currentUser.full_name}!`, 'success');
      this.loadStats();
      if (this.currentUser.role === 'ADMIN') {
        this.navigateTo('admin-queue');
      } else {
        this.navigateTo(this.currentView);
      }
    } catch (err) {
      this.showToast(err.message, 'error');
    }
  },

  async handleRegisterSubmit(e) {
    e.preventDefault();
    const form = e.target;
    const email = form.email.value.trim();
    const password = form.password.value;
    const full_name = form.full_name.value.trim();
    const phone = form.phone.value.trim();

    try {
      await api.auth.register({ email, password, full_name, phone });
      this.currentUser = api.getUser();
      this.renderNavUser();
      this.closeModal('auth-modal');
      this.showToast(`Account created! Welcome, ${this.currentUser.full_name}.`, 'success');
      this.loadStats();
      this.navigateTo('feed');
    } catch (err) {
      this.showToast(err.message, 'error');
    }
  },

  // --------------------------------------------------------------------------
  // Toasts Feedback
  // --------------------------------------------------------------------------
  showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    
    let icon = 'ℹ️';
    if (type === 'success') icon = '✅';
    if (type === 'error') icon = '❌';

    toast.innerHTML = `<span>${icon}</span> <span>${message}</span>`;
    container.appendChild(toast);

    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateX(100%)';
      toast.style.transition = 'all 0.3s ease';
      setTimeout(() => toast.remove(), 300);
    }, 4500);
  },

  // --------------------------------------------------------------------------
  // Event Bindings
  // --------------------------------------------------------------------------
  bindEvents() {
    // Theme toggle
    document.getElementById('theme-toggle-btn')?.addEventListener('click', () => this.toggleTheme());

    // Category pills filter
    document.querySelectorAll('.cat-pill').forEach(pill => {
      pill.addEventListener('click', (e) => {
        document.querySelectorAll('.cat-pill').forEach(p => p.classList.remove('active'));
        e.target.classList.add('active');
        this.loadLostFeed();
      });
    });

    // Search input debounce
    let debounceTimer;
    document.getElementById('feed-search-input')?.addEventListener('input', () => {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(() => this.loadLostFeed(), 300);
    });

    // Location filter
    document.getElementById('feed-location-filter')?.addEventListener('change', () => this.loadLostFeed());

    // File preview bindings
    this.setupFilePreview('lost-image-input', 'lost-img-preview-box', 'lost-img-thumb');
    this.setupFilePreview('found-image-input', 'found-img-preview-box', 'found-img-thumb');

    // Forms
    document.getElementById('report-lost-form')?.addEventListener('submit', (e) => this.handleReportLost(e));
    document.getElementById('report-found-form')?.addEventListener('submit', (e) => this.handleReportFound(e));
    document.getElementById('auth-login-form')?.addEventListener('submit', (e) => this.handleLoginSubmit(e));
    document.getElementById('auth-register-form')?.addEventListener('submit', (e) => this.handleRegisterSubmit(e));
    document.getElementById('chat-form')?.addEventListener('submit', (e) => this.handleSendMessage(e));

    // Admin filter
    document.getElementById('admin-filter-status')?.addEventListener('change', () => this.loadAdminMatches());

    // Auth expired listener
    window.addEventListener('auth:expired', () => {
      this.currentUser = null;
      this.renderNavUser();
      this.showToast('Session expired. Please sign in again.', 'info');
    });
  },

  setupFilePreview(inputId, boxId, thumbId) {
    const input = document.getElementById(inputId);
    const box = document.getElementById(boxId);
    const thumb = document.getElementById(thumbId);

    if (!input || !box || !thumb) return;

    input.addEventListener('change', () => {
      const file = input.files[0];
      if (file) {
        const reader = new FileReader();
        reader.onload = (e) => {
          thumb.src = e.target.result;
          box.style.display = 'flex';
        };
        reader.readAsDataURL(file);
      }
    });
  }
};

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', () => {
  App.init();
});
