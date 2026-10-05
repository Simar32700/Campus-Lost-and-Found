# Campus Lost and Found - Prototype Requirements Specification

This document categorizes the functional and non-functional requirements for the **Campus Lost and Found Platform** prototype into **Must-Have (Core MVP)** and **Good-to-Have (Secondary/Future Phases)**, based on the project Software Requirements Specification (SRS) and architecture.

---

## 1. Must-Have Requirements (Core Prototype / MVP)

These features represent the minimum viable product required to demonstrate the complete end-to-end user journey and satisfy all core test cases.

### 1.1 User Management & Access Control
- **College Email Authentication:** User sign-up and login with college email verification pattern (`@<college>.edu` validation).
- **Role-Based Authorization:**
  - **Regular User (Student / Staff):** Can post items, view the public catalog, track personal posts, and chat when matched.
  - **Administrator:** Can inspect all reports, review AI-suggested matches, approve/reject matches, and monitor item status.

### 1.2 Item Reporting
- **Report Lost Item:**
  - Form fields: Item Name/Title, Category (Electronics, ID Cards, Books, Accessories, etc.), Description, Last Seen Location, Date, and optional Image Upload.
  - Public visibility across campus.
- **Report Found Item:**
  - Same structured input fields and optional image upload.
  - **Admin-only / Hidden visibility** by default to prevent fraudulent claims by unauthorized claimants.

### 1.3 Feeds & Dashboards
- **Public Lost Items Feed:** Browse active lost items with basic search and filter by category and location.
- **"My Posts" Dashboard:** Personal dashboard listing all items reported by the user, showing lifecycle status (`Open`, `Matched`, `Closed`) with edit/delete options.

### 1.4 Matching Engine (Core Prototype Logic)
- **Automated Match Scoring:**
  - Algorithmic scoring comparing Category, Title/Description keyword similarity, and Location proximity.
  - Computes a percentage match confidence score (target: $\ge 80\%$ similarity threshold).
  - Flags high-confidence matches as "Pending Admin Review".

### 1.5 Admin Verification & Workflow
- **Admin Review Queue:** Dedicated view displaying suggested matches side-by-side (Lost Item vs. Found Item) with score and details.
- **Decision Controls:** Action buttons to **Approve Match** or **Reject Match**.
- **State Transition:** Approving a match updates both items to `Matched` and unlocks communication between the respective parties.

### 1.6 In-App Communication
- **Auto-Generated Chat:** A dedicated private chat room opened between the owner and finder once the match is approved by an admin.
- **Message Exchange:** Basic text messaging to coordinate return/handover details.

---

## 2. Good-to-Have Requirements (Secondary & Future Enhancements)

Features that enhance user experience, scalability, and security, but can be deferred until post-prototype releases.

### 2.1 Advanced AI & Multimodal Intelligence
- **Image Embeddings (CLIP / Vision Models):** Visual feature comparison between uploaded photos (color, shape, brand logo matching).
- **Natural Language Embeddings (BERT / Sentence Transformers):** Deep semantic search and description similarity matching.
- **Automated Tagging:** Auto-extracting category and color from uploaded images.

### 2.2 Real-Time Infrastructure (Socket.IO Enhancements)
- **Live WebSocket Messaging:** Instant message delivery with typing indicators, presence status (online/offline), and read receipts.
- **Push & In-App Toast Notifications:** Real-time popups and badge counters for incoming messages and match approvals.

### 2.3 Handover & Physical Resolution Tracking
- **Handover Verification:** Formal security desk or admin-signed handover logging.
- **Resolution Code / OTP:** A one-time verification PIN exchanged between owner and finder upon physical handover to mark the item as `Closed`.

### 2.4 Institutional Single Sign-On (SSO)
- Institutional Google Workspace / Microsoft Entra ID OAuth 2.0 integration.
- Student ID card barcode / QR scanner integration.

### 2.5 Analytics & Reporting (Phase 3)
- Administrative analytics dashboard (recovery rate, average turnaround time, loss hot-spots across campus).
- Exportable audit reports (PDF / CSV) for campus security and administrative compliance.

### 2.6 Production Hardening & Accessibility
- Full WCAG 2.0 AA accessibility compliance.
- Automated daily backups, database rate-limiting, and DDoS protection.

---

## 3. Prototype Scope Summary Table

| Feature Module | Prototype (Must-Have) | Production / Future (Good-to-Have) |
| :--- | :--- | :--- |
| **Authentication** | Email/Password with college domain check | Full University SSO (OAuth / SAML) |
| **Found Items** | Stored hidden, visible only to Admin/Matcher | Automated fraud detection filters |
| **Matching Engine** | Rule-based & text-similarity scoring ($\ge 80\%$) | Deep multimodal AI (CLIP + BERT embeddings) |
| **Admin Flow** | Review suggestions, Approve/Reject matches | Audit logs, dispute resolution panels |
| **Chat & Alerts** | Basic item-linked chat & notification list | Socket.IO live push notifications & sound alerts |
| **Resolution** | User-marked `Closed` or status toggle | Secure OTP-based physical handover logging |
| **Analytics** | Basic item count counters | Full administrative reporting & campus heatmaps |
