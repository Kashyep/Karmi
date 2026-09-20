"""A dependency-free, accessible responsive web shell.

This module is intentionally a small adapter boundary.  It can be mounted by
the eventual API application, while remaining useful in offline tests and
local design review without making network calls or inventing usage values.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from html import escape
from typing import Final


class TaskState(StrEnum):
    """Customer-visible states shared by the chat and task views."""

    QUEUED = "queued"
    WORKING = "working"
    NEEDS_INPUT = "needs-input"
    COMPLETED = "completed"
    FAILED = "failed"
    LIMIT_REACHED = "limit-reached"
    DEFERRED = "deferred"


PLAN_LABELS: Final[tuple[str, ...]] = ("Ananta", "Yanta", "Trika", "Part")
_STATE_COPY: Final[dict[TaskState, str]] = {
    TaskState.QUEUED: "Queued",
    TaskState.WORKING: "Working",
    TaskState.NEEDS_INPUT: "Needs your input",
    TaskState.COMPLETED: "Completed",
    TaskState.FAILED: "Could not complete",
    TaskState.LIMIT_REACHED: "Allowance reached",
    TaskState.DEFERRED: "Deferred",
}


@dataclass(frozen=True, slots=True)
class WebTask:
    """A safe, already-authorized task summary for display."""

    state: TaskState
    title: str = "Your assistant"
    detail: str = ""

    def markup(self) -> str:
        state_label = _STATE_COPY[self.state]
        detail = f'<p class="task-detail">{escape(self.detail)}</p>' if self.detail else ""
        return (
            f'<article class="task-card state-{escape(self.state.value)}" '
            f'aria-label="Task status: {escape(state_label)}">'
            f'<div class="task-card-heading"><h3>{escape(self.title)}</h3>'
            f'<span class="status status-{escape(self.state.value)}" role="status">'
            f'{escape(state_label)}</span></div>{detail}</article>'
        )


def _plan_cards() -> str:
    cards = []
    for label in PLAN_LABELS:
        cards.append(
            f'<article class="plan-card"><h3>{label}</h3>'
            '<p class="muted">Plan details are provided by your account.</p>'
            '<p class="value-unavailable">Usage and price unavailable until the server responds.</p>'
            '<button class="button button-secondary" type="button" disabled>'
            'View plan details</button></article>'
        )
    return "".join(cards)


def render_shell(*, tasks: tuple[WebTask, ...] = ()) -> str:
    """Return the complete offline shell document.

    Values that require authenticated API data are rendered as unavailable;
    callers should replace them only with server-provided values.
    """

    rendered_tasks = "".join(task.markup() for task in tasks) or (
        '<p class="empty-state">No tasks yet. Your completed work will appear here.</p>'
    )
    return f'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="theme-color" content="#254EDB">
  <meta name="description" content="Daily assistant: your work, tasks, and plan status.">
  <title>Daily assistant</title>
  <link rel="manifest" href="/manifest.webmanifest">
  <style>{_STYLES}</style>
</head>
<body>
  <a class="skip-link" href="#main-content">Skip to main content</a>
  <div class="app-shell">
    <header class="topbar">
      <a class="brand" href="#chat" aria-label="Daily assistant home">Daily assistant</a>
      <button class="button button-secondary menu-toggle" type="button" aria-expanded="false"
              aria-controls="primary-nav">Menu</button>
      <nav id="primary-nav" class="primary-nav" aria-label="Primary navigation">
        <a href="#chat">Chat</a><a href="#tasks">Saved work</a>
        <a href="#usage">Usage &amp; plan</a><a href="#settings">Settings</a>
      </nav>
    </header>
    <main id="main-content" tabindex="-1">
      <section id="chat" class="hero" aria-labelledby="chat-heading">
        <p class="eyebrow">Your workspace</p>
        <h1 id="chat-heading">What would you like to work on?</h1>
        <p class="lede">Ask for a draft, a summary, or help organizing your next step.</p>
        <form class="composer" aria-label="Start a task">
          <label for="request">Your request</label>
          <textarea id="request" name="request" rows="3" maxlength="100000"
                    placeholder="Write a request…"></textarea>
          <div class="composer-actions"><span class="muted">The server keeps your account and limits authoritative.</span>
            <button class="button button-primary" type="submit">Start task</button>
          </div>
        </form>
      </section>
      <section id="tasks" class="section" aria-labelledby="tasks-heading">
        <div class="section-heading"><div><p class="eyebrow">Activity</p><h2 id="tasks-heading">Your tasks</h2></div>
          <span class="muted" aria-live="polite">Status updates appear here</span></div>
        <div id="task-list" class="task-list" aria-live="polite">{rendered_tasks}</div>
      </section>
      <section id="usage" class="section" aria-labelledby="usage-heading">
        <div class="section-heading"><div><p class="eyebrow">Account</p><h2 id="usage-heading">Usage &amp; plan</h2></div></div>
        <div class="usage-card"><div><h3>Current plan</h3><p id="plan-value" class="value-unavailable">Unavailable until signed in.</p></div>
          <div><h3>Capacity</h3><p id="capacity-value" class="value-unavailable">No balance shown without server data.</p></div>
          <div><h3>Reset</h3><p id="reset-value" class="value-unavailable">Reset time unavailable.</p></div></div>
        <div class="plan-grid" aria-label="Available plans">{_plan_cards()}</div>
      </section>
      <section id="settings" class="section settings" aria-labelledby="settings-heading">
        <p class="eyebrow">Privacy</p><h2 id="settings-heading">Settings &amp; memory</h2>
        <p>Saved preferences are controlled from your account. No private transcript is stored offline by this shell.</p>
        <button class="button button-secondary" type="button">Manage saved preferences</button>
      </section>
    </main>
    <footer class="footer"><span>Daily assistant</span><span id="server-status">Server status: connecting</span></footer>
  </div>
  <script>{_SCRIPT}</script>
</body>
</html>'''


_STYLES = r'''
:root{font-family:system-ui,-apple-system,"Segoe UI",sans-serif;color:#18212F;background:#F7F8FA;line-height:1.55;font-size:16px}
*{box-sizing:border-box}body{margin:0;background:#F7F8FA}.app-shell{min-height:100vh}.topbar{display:flex;align-items:center;gap:24px;min-height:64px;padding:8px max(16px,calc((100vw - 1200px)/2));background:#fff;border-bottom:1px solid #D7DDE5}.brand{color:#18212F;font-weight:750;text-decoration:none;white-space:nowrap}.primary-nav{display:flex;gap:20px;margin-left:auto}.primary-nav a{color:#4B5563;text-decoration:none;padding:10px 2px}.primary-nav a:hover,.primary-nav a:focus-visible{color:#254EDB}.menu-toggle{display:none;margin-left:auto}.skip-link{position:absolute;left:12px;top:-100px;background:#fff;color:#18212F;padding:10px 14px;z-index:2}.skip-link:focus{top:12px}main{max-width:1200px;margin:auto}.hero{padding:64px 16px 48px;max-width:760px}.eyebrow{color:#254EDB;font-size:.82rem;font-weight:700;letter-spacing:.08em;text-transform:uppercase;margin:0 0 8px}.hero h1{font-size:clamp(2rem,4vw,3rem);line-height:1.15;margin:0 0 12px;max-width:18ch}.lede{font-size:1.15rem;color:#4B5563;margin:0 0 28px}.composer,.usage-card,.plan-card,.task-card{background:#fff;border:1px solid #D7DDE5;border-radius:14px}.composer{padding:20px;max-width:720px}.composer label{font-weight:650;display:block;margin-bottom:8px}.composer textarea{display:block;width:100%;min-height:110px;resize:vertical;border:1px solid #9CA7B6;border-radius:10px;padding:12px;font:inherit;color:inherit}.composer-actions{display:flex;align-items:center;gap:16px;justify-content:space-between;margin-top:12px}.button{min-height:44px;border:1px solid transparent;border-radius:10px;padding:9px 16px;font:inherit;font-weight:650;cursor:pointer}.button:disabled{cursor:not-allowed;opacity:.6}.button-primary{background:#254EDB;color:white}.button-secondary{background:#fff;color:#18212F;border-color:#9CA7B6}.section{padding:40px 16px}.section-heading{display:flex;align-items:end;justify-content:space-between;gap:16px;margin-bottom:18px}.section h2{font-size:1.6rem;margin:0}.task-list{display:grid;gap:12px}.task-card{padding:16px}.task-card-heading{display:flex;align-items:center;justify-content:space-between;gap:12px}.task-card h3,.plan-card h3,.usage-card h3{margin:0;font-size:1rem}.task-detail{margin:8px 0 0;color:#4B5563}.status{font-size:.85rem;font-weight:700;padding:4px 8px;border-radius:999px;background:#EEF2FF}.status-completed{color:#146B43;background:#E9F7EF}.status-failed,.status-limit-reached{color:#B42332;background:#FFF0F1}.status-needs-input,.status-deferred{color:#805000;background:#FFF7E6}.usage-card{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;padding:20px;margin-bottom:18px}.usage-card p{margin:4px 0 0}.plan-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}.plan-card{padding:18px;min-height:180px}.plan-card .button{margin-top:14px}.value-unavailable{color:#4B5563}.muted{color:#4B5563;font-size:.9rem}.empty-state{color:#4B5563;margin:0;padding:20px;background:#fff;border:1px dashed #9CA7B6;border-radius:14px}.settings{padding-bottom:64px}.settings p:not(.eyebrow){max-width:65ch;color:#4B5563}.footer{display:flex;justify-content:space-between;gap:16px;padding:24px max(16px,calc((100vw - 1200px)/2));color:#4B5563;border-top:1px solid #D7DDE5;font-size:.9rem}a:focus-visible,button:focus-visible,textarea:focus-visible{outline:3px solid #254EDB;outline-offset:3px}@media(max-width:760px){.menu-toggle{display:block}.primary-nav{display:none;position:absolute;left:0;right:0;top:64px;padding:12px 16px;background:#fff;border-bottom:1px solid #D7DDE5;flex-direction:column;gap:4px}.primary-nav.is-open{display:flex}.hero{padding-top:40px}.composer-actions,.section-heading{align-items:stretch;flex-direction:column}.usage-card,.plan-grid{grid-template-columns:1fr}.footer{flex-direction:column}}@media(prefers-reduced-motion:reduce){*,*:before,*:after{scroll-behavior:auto!important;transition:none!important}}
'''

_SCRIPT = r'''(() => {
  const toggle = document.querySelector('.menu-toggle');
  const nav = document.querySelector('.primary-nav');
  if (toggle && nav) toggle.addEventListener('click', () => {
    const open = nav.classList.toggle('is-open');
    toggle.setAttribute('aria-expanded', String(open));
  });
  const form = document.querySelector('.composer');
  const request = document.querySelector('#request');
  const taskList = document.querySelector('#task-list');
  const serverStatus = document.querySelector('#server-status');
  let token = null;

  const taskCard = (state, label, detail) => {
    const article = document.createElement('article');
    article.className = `task-card state-${state}`;
    article.setAttribute('aria-label', `Task status: ${label}`);
    const heading = document.createElement('div'); heading.className = 'task-card-heading';
    const title = document.createElement('h3'); title.textContent = 'Your assistant';
    const status = document.createElement('span'); status.className = `status status-${state}`;
    status.setAttribute('role', 'status'); status.textContent = label;
    const text = document.createElement('p'); text.className = 'task-detail'; text.textContent = detail;
    heading.append(title, status); article.append(heading, text);
    taskList.replaceChildren(article);
  };

  const connect = async () => {
    try {
      const response = await fetch('/dev/token', {method: 'POST'});
      if (!response.ok) throw new Error('Sign-in is required');
      token = (await response.json()).token;
      serverStatus.textContent = 'Server status: connected to synthetic local account';
      const usage = await fetch('/v1/usage', {headers: {Authorization: `Bearer ${token}`}});
      if (usage.ok) {
        const value = await usage.json();
        document.querySelector('#plan-value').textContent = `${value.plan_label} · synthetic development policy`;
        document.querySelector('#capacity-value').textContent = `${value.everyday_used} of ${value.everyday_limit} tasks used`;
        document.querySelector('#reset-value').textContent = new Date(value.reset_at).toLocaleString();
      }
    } catch (error) {
      serverStatus.textContent = `Server status: ${error.message}`;
    }
  };

  if (form) form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const text = request.value.trim();
    if (!text || !token) return;
    taskCard('working', 'Working', 'Preparing a bounded local response…');
    try {
      const response = await fetch('/v1/messages', {
        method: 'POST', headers: {'Content-Type': 'application/json', Authorization: `Bearer ${token}`},
        body: JSON.stringify({text, idempotency_key: crypto.randomUUID()}),
      });
      const value = await response.json();
      if (!response.ok) throw new Error(value.detail?.message || 'Could not complete');
      taskCard(value.status === 'completed' ? 'completed' : 'deferred', value.status === 'completed' ? 'Completed' : 'Deferred', value.response);
    } catch (error) {
      taskCard('failed', 'Could not complete', error.message);
    }
  });
  connect();
})();'''
