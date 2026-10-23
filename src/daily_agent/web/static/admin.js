/* Karmi operator admin dashboard. Vanilla JS, no dependencies.
 *
 * Security notes:
 * - The admin session token lives only in the closure variable `state.adminToken`.
 *   It is never written to web storage, cookies, or the URL.
 * - Server text is written with textContent only; nothing is parsed as markup.
 * - Pure helpers are exposed on window.KarmiAdmin for inspection and tests.
 */
(() => {
  'use strict';

  const TIERS = ['ananta', 'yanta', 'trika', 'parth'];
  const USER_STATUSES = ['active', 'suspended'];
  const API_BASE = '/v1/admin';
  const PAGE_SIZE = 25;
  const POLL_INTERVAL_MS = 5000;
  const MAX_TIMEOUT_MS = 2147483647;
  const DELETE_PHRASE = 'DELETE';
  const VIEWS = ['signin', 'unavailable', 'code', 'dashboard'];
  const TABS = ['users', 'monitor', 'audit'];

  class ApiError extends Error {
    constructor(status, message, body) {
      super(message);
      this.name = 'ApiError';
      this.status = status;
      this.body = body;
      this.retryAfter = null;
    }
  }

  // ---------------------------------------------------------------------------
  // Pure helpers
  // ---------------------------------------------------------------------------

  /** Clerk frontend API domain encoded in a pk_test_/pk_live_ publishable key, or null. */
  function clerkFrontendApi(publishableKey) {
    const match = /^pk_(?:test|live)_([A-Za-z0-9+/_-]+)$/.exec(String(publishableKey ?? '').trim());
    if (!match) return null;
    let encoded = match[1].replace(/-/g, '+').replace(/_/g, '/');
    while (encoded.length % 4 !== 0) encoded += '=';
    let decoded;
    try {
      decoded = atob(encoded);
    } catch (_) {
      return null;
    }
    if (!decoded.endsWith('$')) return null;
    const domain = decoded.slice(0, -1);
    return /^[a-z0-9-]+(\.[a-z0-9-]+)+$/i.test(domain) ? domain : null;
  }

  /** Clerk browser bundle URL for a publishable key, or null when the key is unusable. */
  function clerkScriptUrl(publishableKey) {
    const domain = clerkFrontendApi(publishableKey);
    return domain ? `https://${domain}/npm/@clerk/clerk-js@5/dist/clerk.browser.js` : null;
  }

  /** Query string (with leading '?') for cursor pagination; empty values are omitted. */
  function buildPageQuery({ limit, cursor } = {}) {
    const params = new URLSearchParams();
    if (limit) params.set('limit', String(limit));
    if (cursor) params.set('cursor', String(cursor));
    const text = params.toString();
    return text ? `?${text}` : '';
  }

  /** Query string for GET /users. Unknown tier/status values are dropped. */
  function buildUsersQuery(filters = {}) {
    const params = new URLSearchParams();
    const q = String(filters.q ?? '').trim();
    if (q) params.set('q', q);
    if (TIERS.includes(filters.tier)) params.set('tier', filters.tier);
    if (USER_STATUSES.includes(filters.status)) params.set('status', filters.status);
    const page = buildPageQuery({ limit: filters.limit, cursor: filters.cursor });
    const pageParams = new URLSearchParams(page.slice(1));
    for (const [key, value] of pageParams) params.set(key, value);
    const text = params.toString();
    return text ? `?${text}` : '';
  }

  function isMissing(value) {
    return value === null || value === undefined || value === '';
  }

  function formatUsd(value) {
    if (isMissing(value)) return 'Unavailable';
    const n = Number(value);
    if (!Number.isFinite(n)) return 'Unavailable';
    return `${n < 0 ? '-' : ''}$${Math.abs(n).toFixed(2)}`;
  }

  function formatCount(value) {
    if (isMissing(value)) return 'Unavailable';
    const n = Number(value);
    return Number.isFinite(n) ? n.toLocaleString() : 'Unavailable';
  }

  /** Error rate is reported as a fraction (0.02 = 2%). */
  function formatPercent(value) {
    if (isMissing(value)) return 'Unavailable';
    const n = Number(value);
    return Number.isFinite(n) ? `${(n * 100).toFixed(2)}%` : 'Unavailable';
  }

  function formatMs(value) {
    if (isMissing(value)) return 'Unavailable';
    const n = Number(value);
    return Number.isFinite(n) ? `${Math.round(n)} ms` : 'Unavailable';
  }

  function formatTimestamp(value) {
    if (isMissing(value)) return 'Unavailable';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return 'Unavailable';
    return date.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
  }

  /** Text for any server value; objects are shown as compact JSON. */
  function displayValue(value) {
    if (isMissing(value)) return 'Unavailable';
    if (typeof value === 'object') return JSON.stringify(value);
    return String(value);
  }

  /** Word + icon status for a provider. Icons are decorative; the label carries the meaning. */
  function providerStatus(status) {
    const s = String(status ?? '').toLowerCase();
    if (['ok', 'up', 'healthy', 'operational'].includes(s)) return { label: 'Healthy', icon: '✓', tone: 'ok' };
    if (['degraded', 'warning', 'slow', 'partial'].includes(s)) return { label: 'Degraded', icon: '▲', tone: 'warn' };
    if (['down', 'outage', 'error', 'failing', 'unhealthy'].includes(s)) return { label: 'Down', icon: '✕', tone: 'bad' };
    return { label: 'Unknown', icon: '?', tone: 'unknown' };
  }

  /** Unparseable expiry fails closed (treated as expired). */
  function isExpired(expiresAt, now = Date.now()) {
    const t = Date.parse(expiresAt);
    return Number.isNaN(t) ? true : t <= now;
  }

  /**
   * Validate the credits form. Exactly one of delta or budget must be given.
   * Returns { error } or { payload, summary }.
   */
  function validateCreditInput(deltaText, budgetText) {
    const delta = String(deltaText ?? '').trim();
    const budget = String(budgetText ?? '').trim();
    if (delta && budget) return { error: 'Enter either a credit change or a budget, not both.' };
    if (!delta && !budget) return { error: 'Enter a credit change or a budget.' };
    if (delta) {
      const n = Number(delta);
      if (!Number.isFinite(n) || n === 0) return { error: 'The credit change must be a non-zero number.' };
      return { payload: { delta_usd: n }, summary: `Change credits by ${formatUsd(n)}` };
    }
    const n = Number(budget);
    if (!Number.isFinite(n) || n < 0) return { error: 'The budget must be zero or more.' };
    return { payload: { budget_usd: n }, summary: `Set budget to ${formatUsd(n)}` };
  }

  const REASON_MIN_LENGTH = 3;

  function canSubmitReason(reason, typed, requireTyped) {
    if (String(reason ?? '').trim().length < REASON_MIN_LENGTH) return false;
    return !requireTyped || typed === DELETE_PHRASE;
  }

  /** Seconds to wait from a 423 body (`retry_after`) or Retry-After header; null if unknown. */
  function parseRetryAfter(body, header) {
    const fromBody = body && typeof body === 'object' ? Number(body.retry_after) : NaN;
    if (Number.isFinite(fromBody) && fromBody >= 0) return fromBody;
    if (!isMissing(header)) {
      const fromHeader = Number(header);
      if (Number.isFinite(fromHeader) && fromHeader >= 0) return fromHeader;
    }
    return null;
  }

  const root = typeof window !== 'undefined' ? window : globalThis;
  root.KarmiAdmin = Object.freeze({
    TIERS,
    USER_STATUSES,
    clerkFrontendApi,
    clerkScriptUrl,
    buildPageQuery,
    buildUsersQuery,
    formatUsd,
    formatCount,
    formatPercent,
    formatMs,
    formatTimestamp,
    displayValue,
    providerStatus,
    isExpired,
    validateCreditInput,
    canSubmitReason,
    parseRetryAfter,
  });

  if (typeof document === 'undefined') return;

  // ---------------------------------------------------------------------------
  // Closure state. The admin token is held here and nowhere else.
  // ---------------------------------------------------------------------------

  const state = {
    adminToken: null,
    expiresAt: null,
    expiryTimer: null,
    devCandidate: null,
    devJwt: null,
    signedInHandled: false,
    lockedOut: false,
    countdownTimer: null,
    activeTab: 'users',
    usersCursor: null,
    usersRequest: 0,
    selectedUserId: null,
    detailUser: null,
    detailRequest: 0,
    auditCursor: null,
    auditLoaded: false,
    auditRequest: 0,
    monitorTimer: null,
    monitorInFlight: false,
    pending: null,
  };

  const $ = (id) => document.getElementById(id);

  function el(tag, props, ...children) {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(props || {})) {
      if (value === undefined || value === null || value === false) continue;
      if (key === 'class') node.className = value;
      else if (key === 'text') node.textContent = String(value);
      else if (key.startsWith('on') && typeof value === 'function') node.addEventListener(key.slice(2), value);
      else node.setAttribute(key, value === true ? '' : String(value));
    }
    for (const child of children.flat()) {
      if (child === null || child === undefined || child === false) continue;
      node.append(child instanceof Node ? child : document.createTextNode(String(child)));
    }
    return node;
  }

  function setMessage(id, text, tone) {
    const node = $(id);
    node.textContent = text || '';
    node.className = tone ? `message message-${tone}` : 'message';
  }

  function tierLabel(tier) {
    return isMissing(tier) ? 'Unavailable' : String(tier).charAt(0).toUpperCase() + String(tier).slice(1);
  }

  function userLabel(user) {
    return displayValue(user.email || user.display_name || user.id);
  }

  function encodeId(id) {
    return encodeURIComponent(String(id));
  }

  function messageForStatus(status) {
    if (status === 401) return 'Your sign-in was not accepted. Try again.';
    if (status === 403) return 'Not available for this account.';
    if (status === 423) return 'Too many attempts.';
    return `Request failed with status ${status}.`;
  }

  async function readJson(res) {
    try {
      return await res.json();
    } catch (_) {
      return null;
    }
  }

  // ---------------------------------------------------------------------------
  // Views and session lifecycle
  // ---------------------------------------------------------------------------

  function showView(name) {
    for (const view of VIEWS) $(`view-${view}`).hidden = view !== name;
    $('logout-button').hidden = name !== 'dashboard';
    $(`${name}-heading`).focus();
  }

  function showCodeEntry() {
    showView('code');
    $('code-input').focus();
  }

  function clearSensitiveUi() {
    $('users-body').replaceChildren();
    $('audit-body').replaceChildren();
    $('users-more').hidden = true;
    $('audit-more').hidden = true;
    $('monitor-metrics').replaceChildren();
    $('provider-list').replaceChildren();
    $('monitor-updated').textContent = 'Not yet updated.';
    $('credit-delta').value = '';
    $('credit-budget').value = '';
    clearDetail();
    state.usersCursor = null;
    state.auditCursor = null;
    state.auditLoaded = false;
    state.usersRequest += 1;
    state.auditRequest += 1;
  }

  /** Drop the admin token and all admin-only UI, then return to code entry. */
  function endAdminSession(message) {
    state.adminToken = null;
    state.expiresAt = null;
    clearTimeout(state.expiryTimer);
    state.expiryTimer = null;
    stopMonitor();
    state.pending = null;
    const dialog = $('confirm-dialog');
    if (dialog.open) dialog.close();
    clearSensitiveUi();
    showCodeEntry();
    setMessage('code-message', message || '', message ? 'info' : '');
  }

  /** Clerk sign-in lost: clear admin state and return to sign-in. */
  function resetToSignIn(message) {
    state.devJwt = null;
    state.signedInHandled = false;
    endAdminSession('');
    showView('signin');
    setMessage('signin-message', message || '', message ? 'error' : '');
  }

  function scheduleExpiry() {
    clearTimeout(state.expiryTimer);
    const remaining = Date.parse(state.expiresAt) - Date.now();
    state.expiryTimer = setTimeout(() => {
      if (isExpired(state.expiresAt)) {
        endAdminSession('Your admin session expired. Enter the code again.');
      } else {
        scheduleExpiry();
      }
    }, Math.min(Math.max(remaining, 0), MAX_TIMEOUT_MS));
  }

  function startLockoutCountdown(seconds) {
    clearInterval(state.countdownTimer);
    const submit = $('code-submit');
    if (seconds === null) {
      state.lockedOut = false;
      submit.disabled = false;
      setMessage('code-message', 'Too many attempts. Wait a while, then try again.', 'error');
      return;
    }
    state.lockedOut = true;
    submit.disabled = true;
    let remaining = Math.max(1, Math.ceil(seconds));
    const tick = () => {
      if (remaining <= 0) {
        clearInterval(state.countdownTimer);
        state.lockedOut = false;
        submit.disabled = false;
        setMessage('code-message', 'You can try again now.', 'info');
        return;
      }
      setMessage('code-message', `Too many attempts. Try again in ${remaining} second${remaining === 1 ? '' : 's'}.`, 'error');
      remaining -= 1;
    };
    tick();
    state.countdownTimer = setInterval(tick, 1000);
  }

  function enterDashboard() {
    showView('dashboard');
    showTab('users');
    loadUsers(true).catch(() => {});
  }

  // ---------------------------------------------------------------------------
  // API access
  // ---------------------------------------------------------------------------

  async function currentJwt() {
    if (state.devJwt) return state.devJwt;
    const session = root.Clerk && root.Clerk.session;
    if (!session) throw new Error('signed out');
    const token = await session.getToken();
    if (!token) throw new Error('signed out');
    return token;
  }

  /**
   * Call the admin API. Sends the Clerk JWT on every call and the admin session
   * token once it is held. Any 401/403 while an admin session is held ends it.
   */
  async function api(method, path, options = {}) {
    const { body, raw = false } = options;
    if (state.adminToken && isExpired(state.expiresAt)) {
      endAdminSession('Your admin session expired. Enter the code again.');
      throw new ApiError(401, messageForStatus(401));
    }
    let jwt;
    try {
      jwt = await currentJwt();
    } catch (_) {
      resetToSignIn('Your sign-in ended. Sign in again to continue.');
      throw new ApiError(401, messageForStatus(401));
    }
    const headers = { Accept: 'application/json', Authorization: `Bearer ${jwt}` };
    if (state.adminToken) headers['X-Admin-Session'] = state.adminToken;
    const init = { method, headers, cache: 'no-store', credentials: 'omit', referrerPolicy: 'no-referrer' };
    if (body !== undefined) {
      headers['Content-Type'] = 'application/json';
      init.body = JSON.stringify(body);
    }
    let res;
    try {
      res = await fetch(API_BASE + path, init);
    } catch (_) {
      throw new ApiError(0, 'Network error. Check your connection and try again.');
    }
    if (!res.ok) {
      const payload = await readJson(res);
      const err = new ApiError(res.status, messageForStatus(res.status), payload);
      err.retryAfter = res.headers.get('Retry-After');
      if (state.adminToken && (res.status === 401 || res.status === 403)) {
        endAdminSession('Your admin session ended. Enter the code again.');
      }
      throw err;
    }
    return raw ? res : readJson(res);
  }

  // ---------------------------------------------------------------------------
  // Sign-in (Clerk, or local dev token when no publishable key is configured)
  // ---------------------------------------------------------------------------

  function startSignIn() {
    const key = $('admin-app').dataset.clerkPublishableKey || '';
    const url = clerkScriptUrl(key);
    if (!url) {
      setMessage('signin-message', 'Sign-in is not configured.', 'error');
      probeDevSignIn().catch(() => {});
      return;
    }
    setMessage('signin-message', 'Loading sign-in…', 'info');
    const script = document.createElement('script');
    script.src = url;
    script.async = true;
    script.dataset.clerkPublishableKey = key;
    script.onload = () => {
      initClerk().catch(() => setMessage('signin-message', 'Sign-in could not start. Reload the page to try again.', 'error'));
    };
    script.onerror = () => setMessage('signin-message', 'Sign-in could not load. Check your connection and reload the page.', 'error');
    document.head.append(script);
  }

  async function initClerk() {
    const clerk = root.Clerk;
    if (!clerk) throw new Error('Clerk unavailable');
    await clerk.load();
    clerk.addListener(({ session }) => {
      if (session && !state.signedInHandled) onSignedIn();
    });
    if (clerk.session) {
      onSignedIn();
    } else {
      setMessage('signin-message', '', '');
      clerk.mountSignIn($('clerk-mount'));
    }
  }

  /** Local development sign-in: offered only if POST /dev/token answers 200. */
  async function probeDevSignIn() {
    const res = await fetch('/dev/token?role=admin', {
      method: 'POST',
      headers: { Accept: 'application/json' },
      cache: 'no-store',
      credentials: 'omit',
    });
    if (!res.ok) return;
    const data = await readJson(res);
    if (data && typeof data.token === 'string') {
      state.devCandidate = data.token;
      $('dev-signin-button').hidden = false;
    }
  }

  function useDevSignIn() {
    state.devJwt = state.devCandidate;
    state.devCandidate = null;
    $('dev-signin-button').hidden = true;
    onSignedIn();
  }

  /** After Clerk sign-in: probe admin access, then show code entry or Not available. */
  async function onSignedIn() {
    if (state.signedInHandled) return;
    state.signedInHandled = true;
    setMessage('signin-message', 'Checking admin access…', 'info');
    try {
      await api('GET', '/session');
      setMessage('signin-message', '', '');
      showCodeEntry();
    } catch (err) {
      if (err.status === 403) {
        showView('unavailable');
      } else if (err.status === 401) {
        state.signedInHandled = false;
        setMessage('signin-message', 'Your sign-in could not be verified. Try signing in again.', 'error');
      } else {
        showCodeEntry();
      }
    }
  }

  async function submitCode(event) {
    event.preventDefault();
    const input = $('code-input');
    const code = input.value;
    if (!code.trim()) {
      setMessage('code-message', 'Enter the admin code.', 'error');
      input.focus();
      return;
    }
    $('code-submit').disabled = true;
    setMessage('code-message', 'Checking code…', 'info');
    try {
      const data = await api('POST', '/session', { body: { code } });
      if (!data || typeof data.admin_session_token !== 'string' || isExpired(data.expires_at)) {
        throw new ApiError(0, 'Unexpected response from the server.');
      }
      input.value = '';
      state.adminToken = data.admin_session_token;
      state.expiresAt = data.expires_at;
      scheduleExpiry();
      setMessage('code-message', '', '');
      enterDashboard();
    } catch (err) {
      if (err.status === 401) {
        setMessage('code-message', 'That code was not accepted.', 'error');
      } else if (err.status === 403) {
        showView('unavailable');
      } else if (err.status === 423) {
        const body = err.body;
        startLockoutCountdown(parseRetryAfter(body, err.retryAfter));
      } else {
        setMessage('code-message', err.message || 'Could not verify the code. Try again.', 'error');
      }
    } finally {
      if (!state.lockedOut) $('code-submit').disabled = false;
    }
  }

  async function logout() {
    $('logout-button').disabled = true;
    try {
      await api('DELETE', '/session', { raw: true });
    } catch (_) {
      // Local state is cleared regardless of the server response.
    } finally {
      $('logout-button').disabled = false;
      endAdminSession('You signed out of admin.');
    }
  }

  // ---------------------------------------------------------------------------
  // Tabs
  // ---------------------------------------------------------------------------

  function showTab(name) {
    state.activeTab = name;
    for (const tab of TABS) {
      const button = $(`tab-${tab}`);
      const selected = tab === name;
      button.setAttribute('aria-selected', String(selected));
      button.tabIndex = selected ? 0 : -1;
      $(`panel-${tab}`).hidden = !selected;
    }
    if (name === 'monitor') startMonitor();
    else stopMonitor();
    if (name === 'audit' && !state.auditLoaded) loadAudit(true).catch(() => {});
  }

  // ---------------------------------------------------------------------------
  // Monitor
  // ---------------------------------------------------------------------------

  function stopMonitor() {
    clearInterval(state.monitorTimer);
    state.monitorTimer = null;
  }

  function startMonitor() {
    stopMonitor();
    if (!state.adminToken || document.visibilityState === 'hidden') return;
    refreshMonitor().catch(() => {});
    state.monitorTimer = setInterval(() => {
      refreshMonitor().catch(() => {});
    }, POLL_INTERVAL_MS);
  }

  async function refreshMonitor() {
    if (state.monitorInFlight || !state.adminToken) return;
    state.monitorInFlight = true;
    try {
      renderMonitor(await api('GET', '/monitor'));
      setMessage('monitor-message', '', '');
    } catch (err) {
      setMessage('monitor-message', err.message, 'error');
    } finally {
      state.monitorInFlight = false;
    }
  }

  function renderMonitor(data) {
    const source = data && typeof data === 'object' ? data : {};
    $('monitor-updated').textContent = `Updated ${formatTimestamp(source.generated_at)}`;
    const metrics = [
      ['Active users', formatCount(source.active_users)],
      ['Active streams', formatCount(source.active_streams)],
      ['Requests per minute', formatCount(source.req_per_min)],
      ['Error rate', formatPercent(source.error_rate)],
      ['p95 latency', formatMs(source.p95_latency_ms)],
      ['Spend today', formatUsd(source.spend_today_usd)],
      ['Platform budget', formatUsd(source.platform_budget_usd)],
    ];
    const nodes = [];
    for (const [label, value] of metrics) {
      nodes.push(el('dt', { text: label }), el('dd', { text: value }));
    }
    $('monitor-metrics').replaceChildren(...nodes);

    const providers = Array.isArray(source.provider_health) ? source.provider_health : [];
    const items = providers.length === 0
      ? [el('li', { text: 'Unavailable: no provider health reported.' })]
      : providers.map((provider) => {
        const status = providerStatus(provider && provider.status);
        return el('li', { class: `provider provider-${status.tone}` },
          el('span', { class: 'provider-icon', 'aria-hidden': 'true', text: status.icon }),
          el('span', { class: 'provider-name', text: displayValue(provider && provider.provider) }),
          el('span', { class: 'provider-status', text: `${status.label} (${displayValue(provider && provider.status)})` }));
      });
    $('provider-list').replaceChildren(...items);
  }

  // ---------------------------------------------------------------------------
  // Users
  // ---------------------------------------------------------------------------

  async function loadUsers(reset) {
    if (!reset && !state.usersCursor) return;
    const requestId = ++state.usersRequest;
    if (reset) state.usersCursor = null;
    const query = buildUsersQuery({
      q: $('user-q').value,
      tier: $('user-tier').value,
      status: $('user-status').value,
      limit: PAGE_SIZE,
      cursor: reset ? undefined : state.usersCursor,
    });
    setMessage('users-message', 'Loading users…', 'info');
    $('users-more').disabled = true;
    try {
      const data = await api('GET', `/users${query}`);
      if (requestId !== state.usersRequest) return;
      const items = Array.isArray(data && data.items) ? data.items : [];
      const body = $('users-body');
      if (reset) body.replaceChildren();
      body.querySelectorAll('.empty-row').forEach((node) => node.remove());
      if (items.length === 0 && body.children.length === 0) {
        body.append(el('tr', { class: 'empty-row' }, el('td', { colspan: 6, text: 'No users match these filters.' })));
      }
      for (const user of items) body.append(userRow(user));
      state.usersCursor = (data && data.next_cursor) || null;
      $('users-more').hidden = !state.usersCursor;
      setMessage('users-message', '', '');
      highlightSelectedUser();
    } catch (err) {
      if (requestId === state.usersRequest) setMessage('users-message', err.message, 'error');
    } finally {
      if (requestId === state.usersRequest) $('users-more').disabled = false;
    }
  }

  function userRow(user) {
    const suspended = Boolean(user.disabled);
    return el('tr', {
      class: 'user-row',
      'data-user-id': user.id,
      onclick: (event) => {
        if (!event.target.closest('button')) selectUser(user.id).catch(() => {});
      },
    },
    el('td', { 'data-label': 'Email' },
      el('button', { class: 'link-button', type: 'button', onclick: () => selectUser(user.id).catch(() => {}),
        text: displayValue(user.email) })),
    el('td', { 'data-label': 'Name', text: displayValue(user.display_name) }),
    el('td', { 'data-label': 'Tier', text: tierLabel(user.tier) }),
    el('td', { 'data-label': 'Status' },
      el('span', { class: suspended ? 'status status-bad' : 'status status-ok' },
        el('span', { 'aria-hidden': 'true', text: suspended ? '✕' : '✓' }),
        ` ${suspended ? 'Suspended' : 'Active'}`)),
    el('td', { 'data-label': 'Last active', text: formatTimestamp(user.last_active_at) }),
    el('td', { 'data-label': 'Created', text: formatTimestamp(user.created_at) }));
  }

  function highlightSelectedUser() {
    for (const row of $('users-body').querySelectorAll('tr[data-user-id]')) {
      const selected = state.selectedUserId !== null && row.dataset.userId === String(state.selectedUserId);
      row.classList.toggle('is-selected', selected);
    }
  }

  function clearDetail() {
    state.selectedUserId = null;
    state.detailUser = null;
    state.detailRequest += 1;
    $('detail-body').hidden = true;
    $('detail-empty').hidden = false;
    $('detail-heading').textContent = 'User details';
    setMessage('detail-message', '', '');
    setMessage('credits-error', '', '');
    highlightSelectedUser();
  }

  async function selectUser(id) {
    state.selectedUserId = id;
    highlightSelectedUser();
    const requestId = ++state.detailRequest;
    $('detail-empty').hidden = true;
    $('detail-body').hidden = true;
    setMessage('detail-message', 'Loading user…', 'info');
    try {
      const user = await api('GET', `/users/${encodeId(id)}`);
      if (requestId !== state.detailRequest) return;
      renderDetail(user);
    } catch (err) {
      if (requestId === state.detailRequest) {
        $('detail-empty').hidden = false;
        setMessage('detail-message', err.message, 'error');
      }
    }
  }

  function dlPairs(pairs) {
    const nodes = [];
    for (const [label, value] of pairs) {
      nodes.push(el('dt', { text: label }), el('dd', { text: value }));
    }
    return nodes;
  }

  function renderDetail(user) {
    state.detailUser = user;
    state.selectedUserId = user.id;
    const usage = user.usage && typeof user.usage === 'object' ? user.usage : {};
    const suspended = Boolean(user.disabled);
    $('detail-heading').textContent = userLabel(user);
    $('detail-profile').replaceChildren(...dlPairs([
      ['Email', displayValue(user.email)],
      ['Name', displayValue(user.display_name)],
      ['Tier', tierLabel(user.tier)],
      ['Status', suspended ? 'Suspended' : 'Active'],
      ['Created', formatTimestamp(user.created_at)],
      ['Last active', formatTimestamp(user.last_active_at)],
    ]));
    $('detail-usage').replaceChildren(...dlPairs([
      ['Requests today', formatCount(usage.today_requests)],
      ['Spend this month', formatUsd(usage.month_spend_usd)],
      ['Credits remaining', formatUsd(usage.credits_remaining)],
      ['Active sessions', formatCount(usage.sessions)],
    ]));
    $('btn-status').textContent = suspended ? 'Unsuspend user' : 'Suspend user';
    $('detail-tier').value = TIERS.includes(user.tier) ? user.tier : TIERS[0];
    $('detail-empty').hidden = true;
    $('detail-body').hidden = false;
    setMessage('detail-message', '', '');
    highlightSelectedUser();
  }

  /** Refresh the open detail and the list after a change. Errors here do not fail the action. */
  async function refreshAfterChange(userId) {
    loadUsers(true).catch(() => {});
    if (String(state.selectedUserId) === String(userId)) await selectUser(userId);
  }

  /** Builds the confirm-dialog run function for a POST /users/{id}/{action} call. */
  function mutateUser(userId, action, fields, successText) {
    return async (reason) => {
      await api('POST', `/users/${encodeId(userId)}/${action}`, { body: { ...fields, reason } });
      await refreshAfterChange(userId);
      return successText;
    };
  }

  function requireDetailUser() {
    return state.detailUser;
  }

  /** Download the user's export. The reason is sent as ?reason= and recorded server-side. */
  async function exportUser(reason) {
    const user = requireDetailUser();
    if (!user) throw new Error('No user selected.');
    const query = `?${new URLSearchParams({ reason }).toString()}`;
    const res = await api('GET', `/users/${encodeId(user.id)}/export${query}`, { raw: true });
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    const safeId = String(user.id).replace(/[^A-Za-z0-9_-]/g, '_');
    link.href = url;
    link.download = `user-${safeId}-export.json`;
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    setMessage('detail-message', 'Export downloaded.', 'ok');
  }

  // ---------------------------------------------------------------------------
  // Confirm dialog: every mutation requires a non-empty reason
  // ---------------------------------------------------------------------------

  function updateConfirmState() {
    const pending = state.pending;
    const submit = $('confirm-submit');
    submit.disabled = !pending || pending.busy || pending.done
      || !canSubmitReason($('confirm-reason').value, $('confirm-typed').value, pending.requireTyped);
  }

  function openConfirm({ title, summary, requireTyped = false, run }) {
    state.pending = { run, requireTyped, busy: false, done: false };
    $('confirm-title').textContent = title;
    $('confirm-summary').textContent = summary;
    $('confirm-reason').value = '';
    $('confirm-typed').value = '';
    $('confirm-typed-wrap').hidden = !requireTyped;
    $('confirm-typed').required = requireTyped;
    setMessage('confirm-error', '', '');
    setMessage('confirm-result', '', '');
    $('confirm-cancel').textContent = 'Cancel';
    updateConfirmState();
    const dialog = $('confirm-dialog');
    if (!dialog.open) dialog.showModal();
    $('confirm-reason').focus();
  }

  async function submitConfirm(event) {
    event.preventDefault();
    const pending = state.pending;
    if (!pending || pending.busy || pending.done) return;
    const reason = $('confirm-reason').value.trim();
    if (!canSubmitReason(reason, $('confirm-typed').value, pending.requireTyped)) {
      updateConfirmState();
      return;
    }
    pending.busy = true;
    updateConfirmState();
    setMessage('confirm-error', '', '');
    setMessage('confirm-result', 'Working…', 'info');
    try {
      const text = await pending.run(reason);
      pending.done = true;
      setMessage('confirm-result', text, 'ok');
      $('confirm-cancel').textContent = 'Close';
    } catch (err) {
      setMessage('confirm-result', '', '');
      setMessage('confirm-error', err.message || 'The action failed. Try again.', 'error');
    } finally {
      pending.busy = false;
      updateConfirmState();
    }
  }

  // ---------------------------------------------------------------------------
  // Audit
  // ---------------------------------------------------------------------------

  async function loadAudit(reset) {
    if (!reset && !state.auditCursor) return;
    const requestId = ++state.auditRequest;
    if (reset) state.auditCursor = null;
    const query = buildPageQuery({ limit: PAGE_SIZE, cursor: reset ? undefined : state.auditCursor });
    setMessage('audit-message', 'Loading audit log…', 'info');
    $('audit-more').disabled = true;
    try {
      const data = await api('GET', `/audit${query}`);
      if (requestId !== state.auditRequest) return;
      const items = Array.isArray(data && data.items) ? data.items : [];
      const body = $('audit-body');
      if (reset) body.replaceChildren();
      if (items.length === 0 && body.children.length === 0) {
        body.append(el('tr', {}, el('td', { colspan: 6, text: 'No audit entries yet.' })));
      }
      for (const entry of items) {
        body.append(el('tr', {},
          el('td', { 'data-label': 'When', text: formatTimestamp(entry.at) }),
          el('td', { 'data-label': 'Admin', text: displayValue(entry.admin_user_id) }),
          el('td', { 'data-label': 'Action', text: displayValue(entry.action) }),
          el('td', { 'data-label': 'Target user', text: displayValue(entry.target_user_id) }),
          el('td', { 'data-label': 'Reason', text: displayValue(entry.reason) }),
          el('td', { 'data-label': 'Detail', text: displayValue(entry.detail) })));
      }
      state.auditCursor = (data && data.next_cursor) || null;
      state.auditLoaded = true;
      $('audit-more').hidden = !state.auditCursor;
      setMessage('audit-message', '', '');
    } catch (err) {
      if (requestId === state.auditRequest) setMessage('audit-message', err.message, 'error');
    } finally {
      if (requestId === state.auditRequest) $('audit-more').disabled = false;
    }
  }

  // ---------------------------------------------------------------------------
  // Wiring
  // ---------------------------------------------------------------------------

  function wireDetailActions() {
    $('btn-status').addEventListener('click', () => {
      const user = requireDetailUser();
      if (!user) return;
      const unsuspend = Boolean(user.disabled);
      openConfirm({
        title: unsuspend ? 'Unsuspend user' : 'Suspend user',
        summary: `${unsuspend ? 'Unsuspend' : 'Suspend'} ${userLabel(user)}.`,
        run: mutateUser(user.id, unsuspend ? 'unsuspend' : 'suspend', {}, unsuspend ? 'User unsuspended.' : 'User suspended.'),
      });
    });
    $('btn-revoke').addEventListener('click', () => {
      const user = requireDetailUser();
      if (!user) return;
      openConfirm({
        title: 'Revoke sessions',
        summary: `Sign out every active session for ${userLabel(user)}.`,
        run: mutateUser(user.id, 'revoke-sessions', {}, 'Sessions revoked.'),
      });
    });
    $('btn-tier').addEventListener('click', () => {
      const user = requireDetailUser();
      const tier = $('detail-tier').value;
      if (!user) return;
      if (!TIERS.includes(tier) || tier === user.tier) {
        setMessage('detail-message', 'Choose a different tier first.', 'error');
        return;
      }
      openConfirm({
        title: 'Change tier',
        summary: `Change ${userLabel(user)} from ${tierLabel(user.tier)} to ${tierLabel(tier)}.`,
        run: mutateUser(user.id, 'tier', { tier }, `Tier changed to ${tierLabel(tier)}.`),
      });
    });
    $('btn-credits').addEventListener('click', () => {
      const user = requireDetailUser();
      if (!user) return;
      const result = validateCreditInput($('credit-delta').value, $('credit-budget').value);
      if (result.error) {
        setMessage('credits-error', result.error, 'error');
        return;
      }
      setMessage('credits-error', '', '');
      openConfirm({
        title: 'Adjust credits',
        summary: `${result.summary} for ${userLabel(user)}.`,
        run: mutateUser(user.id, 'credits', result.payload, 'Credits updated.'),
      });
    });
    $('btn-delete').addEventListener('click', () => {
      const user = requireDetailUser();
      if (!user) return;
      openConfirm({
        title: 'Delete user',
        summary: `Permanently delete ${userLabel(user)}. This cannot be undone.`,
        requireTyped: true,
        run: async (reason) => {
          await api('DELETE', `/users/${encodeId(user.id)}`, { body: { reason, confirm: DELETE_PHRASE } });
          clearDetail();
          loadUsers(true).catch(() => {});
          return 'User deleted.';
        },
      });
    });
    $('btn-export').addEventListener('click', () => {
      const user = requireDetailUser();
      if (!user) return;
      openConfirm({
        title: 'Export user data',
        summary: `Download a JSON export of ${userLabel(user)}.`,
        run: async (reason) => {
          await exportUser(reason);
          return 'Export downloaded.';
        },
      });
    });
  }

  function wireTabs() {
    $('admin-tabs').addEventListener('click', (event) => {
      const button = event.target.closest('[role="tab"]');
      if (button) showTab(button.dataset.tab);
    });
    $('admin-tabs').addEventListener('keydown', (event) => {
      const buttons = TABS.map((tab) => $(`tab-${tab}`));
      const index = buttons.indexOf(document.activeElement);
      if (index < 0) return;
      let next = null;
      if (event.key === 'ArrowRight') next = (index + 1) % buttons.length;
      else if (event.key === 'ArrowLeft') next = (index - 1 + buttons.length) % buttons.length;
      else if (event.key === 'Home') next = 0;
      else if (event.key === 'End') next = buttons.length - 1;
      if (next === null) return;
      event.preventDefault();
      buttons[next].focus();
      showTab(TABS[next]);
    });
  }

  function wire() {
    $('code-form').addEventListener('submit', (event) => {
      submitCode(event).catch(() => {});
    });
    $('dev-signin-button').addEventListener('click', useDevSignIn);
    $('logout-button').addEventListener('click', () => {
      logout().catch(() => {});
    });
    $('user-search-form').addEventListener('submit', (event) => {
      event.preventDefault();
      loadUsers(true).catch(() => {});
    });
    $('users-more').addEventListener('click', () => {
      loadUsers(false).catch(() => {});
    });
    $('audit-more').addEventListener('click', () => {
      loadAudit(false).catch(() => {});
    });
    wireTabs();
    wireDetailActions();

    $('confirm-form').addEventListener('submit', (event) => {
      submitConfirm(event).catch(() => {});
    });
    $('confirm-reason').addEventListener('input', updateConfirmState);
    $('confirm-typed').addEventListener('input', updateConfirmState);
    $('confirm-cancel').addEventListener('click', () => $('confirm-dialog').close());
    $('confirm-dialog').addEventListener('close', () => {
      state.pending = null;
    });

    document.addEventListener('visibilitychange', () => {
      if (!state.adminToken) return;
      if (document.visibilityState === 'hidden') stopMonitor();
      else if (state.activeTab === 'monitor') startMonitor();
    });
  }

  function applyColorScheme() {
    const dark = root.matchMedia && root.matchMedia('(prefers-color-scheme: dark)');
    const apply = () => {
      document.documentElement.setAttribute('data-theme', dark && dark.matches ? 'dark' : 'light');
    };
    apply();
    if (dark && dark.addEventListener) dark.addEventListener('change', apply);
  }

  function init() {
    applyColorScheme();
    wire();
    showView('signin');
    startSignIn();
  }

  init();
})();
