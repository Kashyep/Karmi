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


PLAN_LABELS: Final[tuple[str, ...]] = ("Ananta", "Yanta", "Trika", "Parth")
_STATE_COPY: Final[dict[TaskState, str]] = {
    TaskState.QUEUED: "Queued behind earlier work",
    TaskState.WORKING: "Actively running on the server",
    TaskState.NEEDS_INPUT: "Waiting for your answer",
    TaskState.COMPLETED: "Finished and verified",
    TaskState.FAILED: "Could not be finished safely",
    TaskState.LIMIT_REACHED: "Account daily limit reached",
    TaskState.DEFERRED: "Deferred to a later budget period",
}

_ARMORY_TIERS: Final[tuple[dict[str, str | int], ...]] = (
    {
        "id": 1,
        "key": "ananta",
        "label": "Ananta",
        "desc": "The Foundation: organic growth, approachability, and foundational balance.",
    },
    {
        "id": 2,
        "key": "yanta",
        "label": "Yanta",
        "desc": "The Control: precision, engineered focus, and structured capability.",
    },
    {
        "id": 3,
        "key": "trika",
        "label": "Trika",
        "desc": "The Trinity: high-velocity output, dynamism, and premium energy.",
    },
    {
        "id": 4,
        "key": "parth",
        "label": "Parth",
        "desc": "The Apex: exclusive luxury, ultimate focus, and minimalist achievement.",
    },
)


@dataclass(frozen=True, slots=True)
class WebTask:
    """A safe, already-authorized task summary for display."""

    state: TaskState
    title: str = "Assistant task"
    detail: str | None = None

    def markup(self) -> str:
        safe_title = escape(self.title)
        safe_detail = escape(self.detail or _STATE_COPY[self.state])
        label = self.state.value.replace("-", " ").capitalize()
        return (
            f'<article class="task-card state-{self.state.value}" '
            f'aria-label="Task status: {label}">'
            f'<div class="task-card-heading"><h3>{safe_title}</h3>'
            f'<span class="status status-{self.state.value}" role="status">{label}</span></div>'
            f'<p class="task-detail">{safe_detail}</p></article>'
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


def _armory_cards() -> str:
    cards = []
    for tier in _ARMORY_TIERS:
        tid = tier["id"]
        key = tier["key"]
        label = tier["label"]
        desc = tier["desc"]
        is_unlocked = tid == 1
        locked_class = "" if is_unlocked else " is-locked"
        active_badge = (
            '<span class="status status-active armory-status-badge">Active</span>'
            if is_unlocked
            else '<span class="status status-locked armory-status-badge">Locked</span>'
        )
        activate_btn = (
            '<button class="button button-primary armory-activate-btn" type="button" disabled>'
            "Active</button>"
            if is_unlocked
            else '<button class="button button-primary armory-activate-btn" type="button" '
            'aria-disabled="true" disabled>Activate</button>'
        )
        cards.append(
            f'<article class="armory-card tier-{key}{locked_class}" '
            f'data-tier-id="{tid}" data-tier-key="{key}">'
            '<div class="armory-card-visual" aria-hidden="true">'
            f'<img src="/static/icons/{key}-192.png" alt="" width="72" height="72" '
            'loading="lazy"></div>'
            '<div class="padlock-badge" aria-label="Locked"><span aria-hidden="true">🔒</span> '
            "Locked</div>"
            f'<div class="armory-card-heading"><h3>{label}</h3>{active_badge}</div>'
            f'<p class="muted">{desc}</p>'
            '<div class="armory-card-actions">'
            f"{activate_btn}"
            '<button class="button button-secondary armory-preview-btn" type="button"'
            f'{" hidden" if is_unlocked else ""}>'
            "Preview 10 s</button>"
            "</div></article>"
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
    return f"""<!doctype html>
<html lang="en" data-tier="ananta" data-theme="light">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="theme-color" content="#66C796">
  <meta name="description" content="Daily assistant: your work, tasks, and plan status.">
  <title>Daily assistant</title>
  <link rel="manifest" href="/manifest.webmanifest?tier=ananta">
  <link rel="stylesheet" href="/static/karmi-tokens.css">
  <script>{_HEAD_SCRIPT}</script>
  <style>{_STYLES}</style>
</head>
<body>
  <a class="skip-link" href="#main-content">Skip to main content</a>
  <div class="app-shell">
    <header class="topbar glass-panel">
      <a class="brand" href="#chat" aria-label="Daily assistant home">Daily assistant</a>
      <button class="button button-secondary menu-toggle" type="button" aria-expanded="false"
              aria-controls="primary-nav">Menu</button>
      <nav id="primary-nav" class="primary-nav" aria-label="Primary navigation">
        <a href="#chat">Chat</a><a href="#tasks">Saved work</a>
        <a href="#usage">Usage &amp; plan</a><a href="#armory">Armory</a><a href="#settings">Settings</a>
      </nav>
    </header>
    <main id="main-content" tabindex="-1">
      <section id="chat" class="hero" aria-labelledby="chat-heading">
        <p class="eyebrow">Your workspace</p>
        <h1 id="chat-heading">What would you like to work on?</h1>
        <p class="lede">Ask for a draft, a summary, or help organizing your next step.</p>
        <form class="composer glass-panel" aria-label="Start a task">
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
      <section id="armory" class="section" aria-labelledby="armory-heading">
        <div class="section-heading"><div><p class="eyebrow">The Armory</p><h2 id="armory-heading">Themes &amp; Progression</h2></div></div>
        <p class="armory-explainer muted">Customize your workspace theme. Installed PWAs retain their home screen icon until reinstalled due to platform constraints.</p>
        <div id="armory-preview-banner" class="armory-preview-banner glass-panel" style="display:none;" role="region" aria-label="Theme preview banner">
          <span id="armory-countdown" class="armory-countdown" aria-live="polite"></span>
          <button id="armory-end-preview" class="button button-secondary" type="button">End preview</button>
        </div>
        <div class="armory-grid" aria-label="Armory tier themes">{_armory_cards()}</div>
      </section>
      <section id="settings" class="section settings" aria-labelledby="settings-heading">
        <p class="eyebrow">Appearance &amp; Privacy</p><h2 id="settings-heading">Settings &amp; appearance</h2>
        <fieldset class="theme-mode-fieldset">
          <legend>Theme mode</legend>
          <div class="radio-group" role="radiogroup" aria-label="Theme mode">
            <label><input type="radio" name="theme-mode" value="system" checked> System</label>
            <label><input type="radio" name="theme-mode" value="light"> Light</label>
            <label><input type="radio" name="theme-mode" value="dark"> Dark</label>
          </div>
        </fieldset>
        <p>Saved preferences are controlled from your account. No private transcript is stored offline by this shell.</p>
        <button class="button button-secondary" type="button">Manage saved preferences</button>
      </section>
    </main>
    <footer class="footer"><span>Daily assistant</span><span id="server-status">Server status: connecting</span></footer>
  </div>
  <script>{_SCRIPT}</script>
</body>
</html>"""


_HEAD_SCRIPT = r"""(() => {
  try {
    const mode = localStorage.getItem('theme_mode') || 'system';
    const isDark = mode === 'dark' || (mode === 'system' && window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches);
    document.documentElement.setAttribute('data-theme', isDark ? 'dark' : 'light');
    const tier = localStorage.getItem('active_tier');
    if (['ananta', 'yanta', 'trika', 'parth'].includes(tier)) {
      document.documentElement.setAttribute('data-tier', tier);
    }
  } catch (_) {}
})();"""


_STYLES = r"""
:root{font-family:system-ui,-apple-system,"Segoe UI",sans-serif;color:var(--color-foreground);background:var(--color-background);line-height:1.55;font-size:16px}
*{box-sizing:border-box}
body{margin:0;background:var(--color-background);color:var(--color-foreground)}
.app-shell{min-height:100vh}
.topbar{display:flex;align-items:center;gap:24px;min-height:64px;padding:8px max(16px,calc((100vw - 1200px)/2));border-bottom:1px solid var(--color-glass-border)}
.brand{color:var(--color-foreground);font-weight:750;text-decoration:none;white-space:nowrap}
.primary-nav{display:flex;gap:20px;margin-left:auto}
.primary-nav a{color:var(--color-muted-foreground);text-decoration:none;padding:10px 2px}
.primary-nav a:hover,.primary-nav a:focus-visible{color:var(--color-primary-text)}
.menu-toggle{display:none;margin-left:auto}
.skip-link{position:absolute;left:12px;top:-100px;background:var(--color-card);color:var(--color-foreground);padding:10px 14px;z-index:2;border:1px solid var(--color-border)}
.skip-link:focus{top:12px}
main{max-width:1200px;margin:auto}
.hero{padding:64px 16px 48px;max-width:760px}
.eyebrow{color:var(--color-primary-text);font-size:.82rem;font-weight:700;letter-spacing:.08em;text-transform:uppercase;margin:0 0 8px}
.hero h1{font-size:clamp(2rem,4vw,3rem);line-height:1.15;margin:0 0 12px;max-width:18ch}
.lede{font-size:1.15rem;color:var(--color-muted-foreground);margin:0 0 28px}
.composer,.usage-card,.plan-card,.task-card,.armory-card{background:var(--color-card);border:1px solid var(--color-border-subtle);border-radius:14px}
.composer{padding:20px;max-width:720px}
.composer label{font-weight:650;display:block;margin-bottom:8px}
.composer textarea{display:block;width:100%;min-height:110px;resize:vertical;border:1px solid var(--color-border);border-radius:10px;padding:12px;font:inherit;color:var(--color-foreground);background:var(--color-card)}
.composer-actions{display:flex;align-items:center;gap:16px;justify-content:space-between;margin-top:12px}
.button{min-height:44px;border:1px solid transparent;border-radius:10px;padding:9px 16px;font:inherit;font-weight:650;cursor:pointer;display:inline-flex;align-items:center;justify-content:center;text-decoration:none}
.button:disabled,.button[aria-disabled="true"]{cursor:not-allowed;background:var(--color-muted);color:var(--color-muted-foreground);border-color:var(--color-border-subtle)}
[hidden]{display:none!important}
.button-primary{background:var(--color-primary);color:var(--color-primary-foreground)}
.button-secondary{background:var(--color-card);color:var(--color-foreground);border-color:var(--color-border)}
.section{padding:40px 16px}
.section-heading{display:flex;align-items:end;justify-content:space-between;gap:16px;margin-bottom:18px}
.section h2{font-size:1.6rem;margin:0}
.task-list{display:grid;gap:12px}
.task-card{padding:16px}
.task-card-heading,.armory-card-heading{display:flex;align-items:center;justify-content:space-between;gap:12px}
.task-card h3,.plan-card h3,.usage-card h3,.armory-card h3{margin:0;font-size:1rem}
.task-detail{margin:8px 0 0;color:var(--color-muted-foreground)}
.status{font-size:.85rem;font-weight:700;padding:4px 8px;border-radius:999px;background:var(--color-muted);color:var(--color-foreground)}
.status-completed{color:var(--color-success);background:var(--color-muted)}
.status-failed,.status-limit-reached{color:var(--color-destructive);background:var(--color-muted)}
.status-needs-input,.status-deferred{color:var(--color-warning);background:var(--color-muted)}
.status-active{color:var(--color-accent-foreground);background:var(--color-accent)}
.status-locked{color:var(--color-muted-foreground);background:var(--color-muted)}
.usage-card{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;padding:20px;margin-bottom:18px}
.usage-card p{margin:4px 0 0}
.plan-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}
.plan-card{padding:18px;min-height:180px}
.plan-card .button{margin-top:14px}
.value-unavailable{color:var(--color-muted-foreground)}
.muted{color:var(--color-muted-foreground);font-size:.9rem}
.empty-state{color:var(--color-muted-foreground);margin:0;padding:20px;background:var(--color-card);border:1px dashed var(--color-border);border-radius:14px}
.settings{padding-bottom:64px}
.settings p:not(.eyebrow){max-width:65ch;color:var(--color-muted-foreground)}
.theme-mode-fieldset{border:1px solid var(--color-border-subtle);border-radius:10px;padding:16px;margin:20px 0;max-width:480px}
.theme-mode-fieldset legend{font-weight:650;padding:0 6px;color:var(--color-foreground)}
.radio-group{display:flex;gap:20px;margin-top:8px}
.radio-group label{display:flex;align-items:center;gap:6px;cursor:pointer;color:var(--color-foreground)}
.footer{display:flex;justify-content:space-between;gap:16px;padding:24px max(16px,calc((100vw - 1200px)/2));color:var(--color-muted-foreground);border-top:1px solid var(--color-border-subtle);font-size:.9rem}
.glass-panel{background:var(--color-glass-base);backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px);border:1px solid var(--color-glass-border);box-shadow:inset 0 1px 0 var(--color-glass-highlight)}
.glass-panel:hover{border-color:var(--color-border)}
.glass-panel:active{border-color:var(--color-ring)}
@supports not (backdrop-filter:blur(16px)){.glass-panel{background:var(--color-glass-fallback);backdrop-filter:none;-webkit-backdrop-filter:none}}
@media (prefers-reduced-transparency:reduce){.glass-panel{background:var(--color-glass-fallback);backdrop-filter:none;-webkit-backdrop-filter:none}}
@media (forced-colors:active){.glass-panel{background:var(--color-glass-fallback);backdrop-filter:none;-webkit-backdrop-filter:none;border:1px solid CanvasText}}
.armory-preview-banner{padding:16px 20px;border-radius:12px;margin-bottom:24px;display:flex;align-items:center;justify-content:space-between;gap:16px}
.armory-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:16px}
.armory-card{padding:18px;display:flex;flex-direction:column;gap:12px;position:relative}
.armory-card-visual{height:90px;border-radius:8px;position:relative;overflow:hidden;display:flex;align-items:center;justify-content:center;border:1px solid var(--color-border-subtle);background:var(--color-muted)}
.armory-card-visual img{width:72px;height:72px;border-radius:16px;display:block}
.armory-card.is-locked .armory-card-visual{filter:blur(4px) grayscale(80%)}
.padlock-badge{display:none;position:absolute;top:8px;right:8px;background:var(--color-muted);color:var(--color-foreground);padding:4px 8px;border-radius:6px;font-size:.85rem;font-weight:700;align-items:center;gap:4px;border:1px solid var(--color-border)}
.armory-card.is-locked .padlock-badge{display:inline-flex}
.armory-card-actions{display:flex;flex-direction:column;gap:8px;margin-top:auto}
.armory-card-actions .button{width:100%}
a:focus-visible,button:focus-visible,input:focus-visible,textarea:focus-visible{outline:2px solid var(--color-ring);outline-offset:2px}
@media (prefers-contrast:more){a:focus-visible,button:focus-visible,input:focus-visible,textarea:focus-visible{outline-width:3px}}
@media(max-width:760px){.menu-toggle{display:block}.primary-nav{display:none;position:absolute;left:0;right:0;top:64px;padding:12px 16px;background:var(--color-card);border-bottom:1px solid var(--color-border-subtle);flex-direction:column;gap:4px}.primary-nav.is-open{display:flex}.hero{padding-top:40px}.composer-actions,.section-heading{align-items:stretch;flex-direction:column}.usage-card,.plan-grid,.armory-grid{grid-template-columns:1fr}.armory-preview-banner{flex-direction:column;align-items:stretch}.footer{flex-direction:column}}
@media(prefers-reduced-motion:reduce){*,*:before,*:after{scroll-behavior:auto!important;transition:none!important}}
"""


_SCRIPT = r"""(() => {
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

  const TIER_ACCENT_COLORS = {
    ananta: '#66C796',
    yanta: '#00D4FF',
    trika: '#FF5722',
    parth: '#D4AF37'
  };

  let armoryData = null;
  let previewTimer = null;
  let previewInterval = null;
  let previewGeneration = 0;
  let savedTierBeforePreview = null;

  // `persist` is false for previews: an install during a preview must still
  // get the account's real (unlocked) icon.
  const setEffectiveTier = (tierKey, persist = true) => {
    document.documentElement.setAttribute('data-tier', tierKey);
    if (!persist) return;
    const manifestLink = document.querySelector('link[rel="manifest"]');
    if (manifestLink) {
      manifestLink.href = `/manifest.webmanifest?tier=${encodeURIComponent(tierKey)}`;
    }
    const metaThemeColor = document.querySelector('meta[name="theme-color"]');
    if (metaThemeColor && TIER_ACCENT_COLORS[tierKey]) {
      metaThemeColor.content = TIER_ACCENT_COLORS[tierKey];
    }
  };

  const endPreview = () => {
    if (previewTimer) {
      clearTimeout(previewTimer);
      previewTimer = null;
    }
    if (previewInterval) {
      clearInterval(previewInterval);
      previewInterval = null;
    }
    previewGeneration++;
    if (savedTierBeforePreview) {
      setEffectiveTier(savedTierBeforePreview);
      savedTierBeforePreview = null;
    }
    const banner = document.querySelector('#armory-preview-banner');
    const countdown = document.querySelector('#armory-countdown');
    if (banner) banner.style.display = 'none';
    if (countdown) countdown.textContent = '';
  };

  const isLockedKey = (tierKey) => {
    const tier = armoryData && armoryData.tiers.find((t) => t.key === tierKey);
    return tier ? tier.id > armoryData.unlocked_tier : tierKey !== 'ananta';
  };

  const startPreview = (tierKey, tierLabel) => {
    // Only locked tiers are previewed; unlocked ones are activated.
    if (!isLockedKey(tierKey)) return;
    if (savedTierBeforePreview) {
      endPreview();
    }
    const currentGen = ++previewGeneration;
    savedTierBeforePreview = document.documentElement.getAttribute('data-tier') || 'ananta';
    setEffectiveTier(tierKey, false);

    const banner = document.querySelector('#armory-preview-banner');
    const countdown = document.querySelector('#armory-countdown');
    let remaining = 10;

    const updateBanner = (sec) => {
      if (countdown) {
        countdown.textContent = `Previewing ${tierLabel} theme: ${sec}s remaining`;
      }
      if (banner) {
        banner.style.display = 'flex';
      }
    };

    updateBanner(remaining);

    previewInterval = setInterval(() => {
      if (previewGeneration !== currentGen) return;
      remaining--;
      if (remaining > 0) {
        updateBanner(remaining);
      }
    }, 1000);

    previewTimer = setTimeout(() => {
      if (previewGeneration !== currentGen) return;
      endPreview();
    }, 10000);
  };

  const endPreviewBtn = document.querySelector('#armory-end-preview');
  if (endPreviewBtn) {
    endPreviewBtn.addEventListener('click', () => {
      endPreview();
    });
  }

  window.addEventListener('pagehide', () => {
    endPreview();
  });
  window.addEventListener('beforeunload', () => {
    endPreview();
  });

  const renderArmoryUI = () => {
    const cards = document.querySelectorAll('.armory-card');
    cards.forEach((card) => {
      const tierId = parseInt(card.getAttribute('data-tier-id'), 10);
      const isLocked = tierId > (armoryData ? armoryData.unlocked_tier : 1);
      const isActive = armoryData ? armoryData.active_theme === tierId : (tierId === 1);

      if (isLocked) {
        card.classList.add('is-locked');
      } else {
        card.classList.remove('is-locked');
      }

      const badge = card.querySelector('.armory-status-badge');
      if (badge) {
        if (isActive) {
          badge.className = 'status status-active armory-status-badge';
          badge.textContent = 'Active';
        } else if (isLocked) {
          badge.className = 'status status-locked armory-status-badge';
          badge.textContent = 'Locked';
        } else {
          badge.className = 'status armory-status-badge';
          badge.textContent = 'Unlocked';
        }
      }

      const previewBtn = card.querySelector('.armory-preview-btn');
      if (previewBtn) previewBtn.hidden = !isLocked;

      const activateBtn = card.querySelector('.armory-activate-btn');
      if (activateBtn) {
        if (isActive) {
          activateBtn.textContent = 'Active';
          activateBtn.disabled = true;
          activateBtn.removeAttribute('aria-disabled');
        } else if (isLocked) {
          activateBtn.textContent = 'Activate';
          activateBtn.disabled = true;
          activateBtn.setAttribute('aria-disabled', 'true');
        } else {
          activateBtn.textContent = 'Activate';
          activateBtn.disabled = false;
          activateBtn.removeAttribute('aria-disabled');
        }
      }
    });
  };

  let armoryGeneration = 0;

  const activateTheme = async (tierId, tierKey) => {
    endPreview();
    if (!token) return;
    const generation = ++armoryGeneration;
    try {
      const response = await fetch('/v1/armory/active-theme', {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ active_theme: tierId }),
      });

      if (response.status === 403) {
        await fetchArmory();
        return;
      }

      if (!response.ok) {
        throw new Error(`Failed to activate theme: ${response.status}`);
      }

      const data = await response.json();
      if (generation !== armoryGeneration) return; // a newer request won
      armoryData = data;
      localStorage.setItem('active_tier', tierKey);
      setEffectiveTier(tierKey);
      renderArmoryUI();
    } catch (error) {
      console.error(error);
    }
  };

  const wireArmoryEvents = () => {
    const cards = document.querySelectorAll('.armory-card');
    cards.forEach((card) => {
      const tierId = parseInt(card.getAttribute('data-tier-id'), 10);
      const tierKey = card.getAttribute('data-tier-key');
      const heading = card.querySelector('h3');
      const tierLabel = heading ? heading.textContent : tierKey;

      const previewBtn = card.querySelector('.armory-preview-btn');
      if (previewBtn) {
        previewBtn.addEventListener('click', () => {
          startPreview(tierKey, tierLabel);
        });
      }

      const activateBtn = card.querySelector('.armory-activate-btn');
      if (activateBtn) {
        activateBtn.addEventListener('click', () => {
          if (!activateBtn.disabled) {
            activateTheme(tierId, tierKey);
          }
        });
      }
    });
  };

  const fetchArmory = async () => {
    if (!token) return;
    const generation = ++armoryGeneration;
    try {
      const response = await fetch('/v1/armory', {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!response.ok) return;
      const data = await response.json();
      if (generation !== armoryGeneration) return; // a newer request won
      armoryData = data;
      const activeTierObj = armoryData.tiers.find((t) => t.id === armoryData.active_theme);
      if (activeTierObj) {
        localStorage.setItem('active_tier', activeTierObj.key);
        if (savedTierBeforePreview) {
          // Preview running: revert to the fresh server tier when it ends.
          savedTierBeforePreview = activeTierObj.key;
          if (!isLockedKey(document.documentElement.getAttribute('data-tier'))) endPreview();
        } else {
          setEffectiveTier(activeTierObj.key);
        }
      }
      renderArmoryUI();
    } catch (error) {
      console.error(error);
    }
  };

  const initThemeMode = () => {
    const radios = document.querySelectorAll('input[name="theme-mode"]');
    const storedMode = localStorage.getItem('theme_mode') || 'system';
    radios.forEach((r) => {
      r.checked = r.value === storedMode;
      r.addEventListener('change', () => {
        if (r.checked) {
          applyThemeMode(r.value);
        }
      });
    });

    const mql = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)');
    if (mql) {
      mql.addEventListener('change', (e) => {
        const mode = localStorage.getItem('theme_mode') || 'system';
        if (mode === 'system') {
          document.documentElement.setAttribute('data-theme', e.matches ? 'dark' : 'light');
        }
      });
    }
  };

  const applyThemeMode = (mode) => {
    localStorage.setItem('theme_mode', mode);
    let theme = 'light';
    if (mode === 'dark') {
      theme = 'dark';
    } else if (mode === 'light') {
      theme = 'light';
    } else {
      const isDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
      theme = isDark ? 'dark' : 'light';
    }
    document.documentElement.setAttribute('data-theme', theme);
  };

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
      await fetchArmory();
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

  initThemeMode();
  wireArmoryEvents();
  connect();
})();"""
