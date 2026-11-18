/* Complaint inbox and admin conversation review. User content is rendered as text. */
(() => {
  const el = (tag, text, cls) => {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (cls) node.className = cls;
    return node;
  };
  const label = value => String(value || '').replaceAll('_', ' ');
  const itemIllustration = complaint => {
    const title = `${complaint.lost_title || ''} ${complaint.found_title || ''}`;
    const kind = /\b(laptop|macbook|notebook|chromebook)\b/i.test(title) ? 'laptop'
      : /\b(mobile|phone|smartphone|iphone|android|samsung|pixel|oneplus)\b/i.test(title) ? 'mobile' : null;
    if (!kind) return null;
    const image = el('img', undefined, 'complaint-item-image');
    image.src = `/static/images/${kind}.jpg`;
    image.alt = kind === 'mobile' ? 'Mobile phone photo' : 'Laptop photo';
    image.width = 640; image.height = 320;
    return image;
  };
  const button = (text, action, cls = 'btn btn-secondary btn-sm') => {
    const node = el('button', text, cls); node.type = 'button'; node.onclick = action; return node;
  };
  Object.assign(App, {
    complaintFilter: 'ALL',
    async loadComplaints() {
      document.getElementById('complaints-back-admin').style.display = this.currentUser?.role === 'ADMIN' ? '' : 'none';
      if (!this.currentUser) return;
      const list = document.getElementById('complaint-list');
      const request = this.complaintListRequest = (this.complaintListRequest || 0) + 1;
      list.textContent = 'Loading complaints...';
      document.getElementById('complaint-review').replaceChildren(el('h3', 'Select a complaint'), el('p', 'Choose an entry to view its details and review history.'));
      try {
        const result = await api.request('/complaints');
        if (request !== this.complaintListRequest || !this.currentUser) return;
        this.complaints = result.complaints;
        this.complaintCounts = result.counts;
        const admin = this.currentUser.role === 'ADMIN';
        document.getElementById('complaints-title').textContent = admin ? 'Complaint Review Inbox' : 'My Complaints';
        document.getElementById('complaints-intro').textContent = admin
          ? 'Investigate dismissed chats, review user reports, and record a decision.'
          : 'Track automatic dismissal reports and complaints you submitted to the campus admin.';
        this.renderComplaints();
      } catch (err) { list.textContent = err.message; }
    },
    renderComplaints() {
      const counts = document.getElementById('complaint-counts'); counts.replaceChildren();
      for (const [status, count] of Object.entries(this.complaintCounts)) {
        const b = button(`${status === 'ALL' ? 'All complaints' : label(status)} (${count})`, () => {
          this.complaintFilter = status; this.renderComplaints();
        }, `btn ${this.complaintFilter === status ? 'btn-primary' : 'btn-secondary'}`);
        b.setAttribute('aria-pressed', String(this.complaintFilter === status)); counts.append(b);
      }
      const list = document.getElementById('complaint-list'); list.replaceChildren();
      const rows = this.complaints.filter(c => this.complaintFilter === 'ALL' || c.status === this.complaintFilter);
      if (!rows.length) list.append(el('div', 'No complaints in this section.', 'complaint-empty'));
      rows.forEach(c => {
        const card = el('article', undefined, 'complaint-card');
        const image = itemIllustration(c);
        if (image) card.append(image);
        card.append(el('span', label(c.status), `complaint-status complaint-${c.status.toLowerCase()}`),
          el('h3', c.lost_title), el('p', `${c.reporter_name} reported ${c.reported_user_name || 'a conversation'}`),
          el('p', c.source === 'AUTOMATIC' ? 'Automatic report ? Chat dismissed' : label(c.category), 'complaint-help'),
          el('p', new Date(c.updated_at).toLocaleString(), 'complaint-help'),
          button('View complaint', () => this.selectComplaint(c)));
        list.append(card);
      });
    },
    async selectComplaint(c) {
      const panel = document.getElementById('complaint-review');
      this.selectedComplaintId = c.id;
      panel.replaceChildren(el('span', 'CASE DETAILS', 'complaint-eyebrow'), el('h3', c.lost_title),
        el('p', `Reporter: ${c.reporter_name}`), el('p', `Reported user: ${c.reported_user_name || 'Conversation review'}`),
        el('p', `Status: ${label(c.status)} ? Chat: ${label(c.room_status)}`),
        el('h4', label(c.category)), el('p', c.details || 'Automatically escalated because the conversation was dismissed.', 'complaint-text'),
        el('h4', 'Latest admin review'), el('p', c.admin_notes || 'Awaiting admin review.', 'complaint-text'));
      const image = itemIllustration(c);
      if (image) panel.prepend(image);
      if (this.currentUser.role !== 'ADMIN') {
        panel.append(button('Add or update complaint details', () => this.openComplaintForm(c.room_id, c)));
        return;
      }
      const form = el('form', undefined, 'complaint-review-form');
      const statusLabel = el('label', 'Review status'); statusLabel.htmlFor = 'complaint-review-status';
      const select = el('select', undefined, 'select-input'); select.id = 'complaint-review-status';
      ['PENDING', 'IN_REVIEW', 'RESOLVED', 'REJECTED'].forEach(status => { const option = el('option', label(status)); option.value = status; select.append(option); }); select.value = c.status;
      const notesLabel = el('label', 'Review note (visible to the reporter)'); notesLabel.htmlFor = 'complaint-review-notes';
      const notes = el('textarea', undefined, 'form-input'); notes.id = 'complaint-review-notes'; notes.rows = 4; notes.maxLength = 3000; notes.required = true; notes.value = c.admin_notes;
      const save = el('button', 'Save review', 'btn btn-primary'); save.type = 'submit';
      form.append(statusLabel, select, notesLabel, notes, save);
      form.onsubmit = async event => {
        event.preventDefault(); save.disabled = true;
        try {
          await api.request(`/complaints/${encodeURIComponent(c.id)}`, {method:'PATCH', body:JSON.stringify({status:select.value, admin_notes:notes.value})});
          this.showToast('Complaint review saved.', 'success'); await this.loadComplaints();
        } catch (err) { this.showToast(err.message, 'error'); } finally { save.disabled = false; }
      };
      panel.append(form, el('h4', 'Conversation evidence'));
      const transcript = el('div', 'Loading conversation...', 'complaint-transcript'); panel.append(transcript);
      try {
        const data = await api.request(`/complaints/${encodeURIComponent(c.id)}/conversation`);
        if (this.selectedComplaintId !== c.id) return;
        transcript.replaceChildren();
        if (!data.messages.length) transcript.append(el('p', 'No messages in this conversation.'));
        data.messages.forEach(m => {
          const message = el('article', undefined, 'complaint-message');
          message.append(el('strong', m.sender_name), el('small', new Date(m.created_at).toLocaleString()), el('p', m.content, 'complaint-text'));
          if (m.attachment_url && /^\/uploads\/[a-zA-Z0-9_.-]+$/.test(m.attachment_url)) {
            const attachment = el('a', m.attachment_name || 'View attachment'); attachment.href = m.attachment_url; attachment.target = '_blank'; attachment.rel = 'noopener'; message.append(attachment);
          }
          transcript.append(message);
        });
      } catch (err) { transcript.textContent = err.message; }
    },
    openComplaintForm(roomId = this.complaintRoomId, complaint = null) {
      if (!roomId || !this.currentUser || this.currentUser.role === 'ADMIN') return;
      this.reportingRoomId = roomId;
      document.getElementById('complaint-category').value = complaint?.source === 'USER' ? complaint.category : 'OTHER';
      document.getElementById('complaint-details').value = complaint?.details || '';
      document.getElementById('complaint-modal').classList.add('active');
      document.getElementById('complaint-category').focus();
    },
    async submitComplaint(event) {
      event.preventDefault();
      const submit = document.getElementById('complaint-submit'); submit.disabled = true;
      try {
        const result = await api.request('/complaints', {method:'POST', body:JSON.stringify({room_id:this.reportingRoomId, category:document.getElementById('complaint-category').value, details:document.getElementById('complaint-details').value.trim()})});
        this.closeModal('complaint-modal'); this.showToast(result.message, 'success'); this.navigateTo('complaints');
      } catch (err) { this.showToast(err.message, 'error'); } finally { submit.disabled = false; }
    }
  });
})();
