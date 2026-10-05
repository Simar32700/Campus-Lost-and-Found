/**
 * Campus Lost and Found - API Client
 * Manages JWT tokens, authenticated HTTP requests, and backend endpoints.
 */

const API_BASE = '/api';

const api = {
  getToken() {
    return localStorage.getItem('clf_token');
  },

  setToken(token) {
    if (token) {
      localStorage.setItem('clf_token', token);
    } else {
      localStorage.removeItem('clf_token');
    }
  },

  getUser() {
    try {
      const user = localStorage.getItem('clf_user');
      return user ? JSON.parse(user) : null;
    } catch {
      return null;
    }
  },

  setUser(user) {
    if (user) {
      localStorage.setItem('clf_user', JSON.stringify(user));
    } else {
      localStorage.removeItem('clf_user');
    }
  },

  clearAuth() {
    localStorage.removeItem('clf_token');
    localStorage.removeItem('clf_user');
  },

  async request(endpoint, options = {}) {
    const headers = options.headers || {};
    const token = this.getToken();

    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    if (!(options.body instanceof FormData) && !headers['Content-Type']) {
      headers['Content-Type'] = 'application/json';
    }

    const config = {
      ...options,
      headers
    };

    try {
      const response = await fetch(`${API_BASE}${endpoint}`, config);
      const data = await response.json().catch(() => ({}));

      if (!response.ok) {
        if (response.status === 401) {
          this.clearAuth();
          window.dispatchEvent(new CustomEvent('auth:expired'));
        }
        throw new Error(data.detail || 'An unexpected error occurred');
      }

      return data;
    } catch (err) {
      console.error(`API Error [${endpoint}]:`, err);
      throw err;
    }
  },

  // Authentication endpoints
  auth: {
    async login(email, password) {
      const res = await api.request('/auth/login', {
        method: 'POST',
        body: JSON.stringify({ email, password })
      });
      api.setToken(res.access_token);
      api.setUser(res.user);
      return res;
    },

    async register(userData) {
      const res = await api.request('/auth/register', {
        method: 'POST',
        body: JSON.stringify(userData)
      });
      api.setToken(res.access_token);
      api.setUser(res.user);
      return res;
    },

    async getMe() {
      const user = await api.request('/auth/me');
      api.setUser(user);
      return user;
    }
  },

  // Item management endpoints
  items: {
    async listLost(params = {}) {
      const query = new URLSearchParams();
      if (params.search) query.append('search', params.search);
      if (params.category) query.append('category', params.category);
      if (params.location) query.append('location', params.location);
      if (params.status_filter) query.append('status_filter', params.status_filter);
      
      const qStr = query.toString() ? `?${query.toString()}` : '';
      return api.request(`/items/lost${qStr}`);
    },

    async reportLost(formData) {
      return api.request('/items/lost', {
        method: 'POST',
        body: formData
      });
    },

    async reportFound(formData) {
      return api.request('/items/found', {
        method: 'POST',
        body: formData
      });
    },

    async getMyPosts() {
      return api.request('/items/my-posts');
    },

    async getMyStats() {
      return api.request('/items/my-stats');
    },

    async getItem(id) {
      return api.request(`/items/${id}`);
    },

    async deleteItem(id) {
      return api.request(`/items/${id}`, {
        method: 'DELETE'
      });
    }
  },

  // Admin endpoints
  admin: {
    async getMatches(status = 'PENDING') {
      return api.request(`/admin/matches?status_filter=${encodeURIComponent(status)}`);
    },

    async approveMatch(matchId) {
      return api.request(`/admin/matches/${matchId}/approve`, {
        method: 'POST'
      });
    },

    async rejectMatch(matchId) {
      return api.request(`/admin/matches/${matchId}/reject`, {
        method: 'POST'
      });
    },

    async getStats() {
      return api.request('/admin/stats');
    }
  },

  // Chat & Handover endpoints
  chat: {
    async getRooms() {
      return api.request('/chat/rooms');
    },

    async getMessages(roomId) {
      return api.request(`/chat/rooms/${roomId}/messages`);
    },

    async sendMessage(roomId, content) {
      return api.request(`/chat/rooms/${roomId}/messages`, {
        method: 'POST',
        body: JSON.stringify({ content })
      });
    },

    async sendMedia(roomId, formData) {
      return api.request(`/chat/rooms/${roomId}/messages/media`, {
        method: 'POST',
        body: formData
      });
    },

    async dismissChat(roomId) {
      return api.request(`/chat/rooms/${roomId}/dismiss`, {
        method: 'POST'
      });
    },

    async reopenChat(roomId) {
      return api.request(`/chat/rooms/${roomId}/reopen`, {
        method: 'POST'
      });
    },

    async resolveHandover(roomId) {
      return api.request(`/chat/rooms/${roomId}/resolve`, {
        method: 'POST'
      });
    },

    async unresolveHandover(roomId) {
      return api.request(`/chat/rooms/${roomId}/unresolve`, {
        method: 'POST'
      });
    }
  }
};
