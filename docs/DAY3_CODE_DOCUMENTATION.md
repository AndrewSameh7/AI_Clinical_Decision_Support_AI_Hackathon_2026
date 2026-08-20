# Day 3 → Day 4 Code Documentation

## 1. Scope

Day 3 preserves the Day-2 retrieval foundation and adds the generation, identity, persistence, UI and security layers required for the third day.

## 2. `src/web.py`

This is the application boundary.

### Authentication
- `POST /api/auth/register`: creates an account with a `scrypt` password hash.
- `POST /api/auth/login`: verifies credentials and creates a protected session.
- `POST /api/auth/logout`: invalidates the session and deletes the cookie.
- `GET /api/auth/me`: returns the current authenticated user.
- `/api/auth/google` and `/api/auth/google/callback`: optional Google OAuth flow with state validation.

### User isolation
Every history query includes `WHERE user_id=?` using the authenticated server-side session identity. The browser cannot choose another owner.

### History
- `GET /api/history`
- `POST /api/history`
- `GET /api/history/{conversation_id}`
- `DELETE /api/history`

SQLite stores users, conversations and messages.

### Retrieval
`POST /api/retrieve` keeps the Day-2 retrieval implementation but forces the Day-3 visible pipeline to Top-1 evidence.

Only a server-issued `retrieval_id` is accepted by `/api/answer`.

### Generation
`POST /api/answer` checks session ownership, retrieval expiry and question equality, applies the Top-1 evidence gate, calls the grounded generator and stores the validated result in the user's conversation.

## 3. `src/llm.py`

This file defines the Day-3 generation contract.

The system prompt:
- restricts the model to the supplied evidence,
- treats retrieved content as untrusted,
- blocks outside medical knowledge,
- requires structured JSON,
- requires explicit refusal when evidence is insufficient,
- defines `safety_refusal` for unsafe/personalized requests.

The server rewrites/validates citations against the actual retrieved document metadata instead of trusting the model to invent source details.

## 4. `src/config.py`

Contains the Day-2 retrieval configurations and Day-3 controls. `TOP1_MIN_SIMILARITY` is the configurable gate for refusing weak evidence.

## 5. `web/index.html`

Contains:
- authentication screen,
- login/register controls,
- Google sign-in control,
- authenticated sidebar,
- chat history,
- message composer,
- microphone control,
- Day-2 visual layout.

## 6. `web/app.js`

Implements:
- authentication state,
- server-side history loading,
- conversation switching,
- message rendering,
- Top-1 answer flow,
- source rendering,
- logout,
- voice transcription,
- loading/status states,
- UI animations through CSS classes.

Voice transcription feeds the same question field and therefore the same backend pipeline as typed questions.

## 7. `web/styles.css`

Preserves the Day-2 visual language and adds:
- auth-card design,
- welcome/user identity,
- source cards,
- recording state,
- message animations,
- reduced-motion accessibility.

## 8. Persistence model

```text
users
  |
  +--- conversations
          |
          +--- messages
```

Every conversation references exactly one authenticated user. This is the critical isolation boundary for the Day-3 history requirement.

## 9. Security model

1. Passwords are never stored in plaintext.
2. Sessions are HttpOnly and SameSite.
3. Session state is invalidated on logout.
4. Authorization is performed server-side.
5. OAuth uses a server-generated state value.
6. Retrieval context is server-side and short-lived.
7. Browser-submitted evidence is never treated as authoritative.
8. Existing Day-2 request limits and security headers remain.
9. Retrieved PDF content is untrusted for prompt-injection purposes.
10. Internal retrieval metadata is not exposed in the normal user interface.

## 10. Day-3 test scenario

- Create User A.
- Create a conversation.
- Logout.
- Login/create User B.
- Verify no User A history is shown.
- Login User A again.
- Verify the original conversation is restored.
- Test text and voice input.
- Test a grounded answer.
- Test insufficient evidence and verify refusal.


### Day 3 usage limits
- Per-user chat storage quota: 2 MB by default (`USER_STORAGE_LIMIT_BYTES=2097152`).
- Day-4 change: daily question quota was removed. Users may ask questions without a daily count limit.
- The quota is enforced server-side before retrieval, not only in the browser.
- Day-4 change: the daily quota UI was removed.


## Day 4 Addendum
- Pre-generation input risk classification.
- Retrieval confidence threshold.
- Post-generation claim support validation.
- Partial-answer policy for multi-part questions.
- 2 MB hard storage maximum per user.
- No daily question limit.
- 35-case internal evaluation dataset.
