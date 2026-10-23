"""Server-rendered shell for the operator admin dashboard at ``/admin``.

The page carries no secrets.  Its only configuration value is the Clerk
publishable key, which is public by design.  All data comes from the admin
API at runtime, authorised per request by the browser.
"""

from __future__ import annotations

from html import escape
from typing import Final

_TIERS: Final[tuple[str, ...]] = ("ananta", "yanta", "trika", "parth")


def _tier_options(include_blank: bool) -> str:
    options = ['<option value="">Any tier</option>'] if include_blank else []
    options.extend(f'<option value="{tier}">{tier.capitalize()}</option>' for tier in _TIERS)
    return "".join(options)


def render_admin_page(*, publishable_key: str | None) -> str:
    """Return the admin dashboard document.

    The publishable key is embedded only when configured; without it the page
    reports that sign-in is not configured instead of loading Clerk.
    """
    key_attr = (
        f' data-clerk-publishable-key="{escape(publishable_key, quote=True)}"'
        if publishable_key
        else ""
    )
    return f"""<!doctype html>
<html lang="en" data-tier="ananta" data-theme="light">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="robots" content="noindex">
  <meta name="description" content="Karmi operator administration.">
  <title>Karmi admin</title>
  <link rel="stylesheet" href="/static/karmi-tokens.css">
  <link rel="stylesheet" href="/static/admin.css">
  <script src="/static/admin.js" defer></script>
</head>
<body>
  <a class="skip-link" href="#main-content">Skip to main content</a>
  <div id="admin-app" class="admin-app"{key_attr}>
    <header class="admin-topbar">
      <p class="brand">Karmi <span class="brand-sub">Admin</span></p>
      <button id="logout-button" class="button button-secondary" type="button" hidden>Log out of admin</button>
    </header>
    <main id="main-content" class="admin-main" tabindex="-1">

      <section id="view-signin" class="card view" aria-labelledby="signin-heading">
        <h1 id="signin-heading" tabindex="-1">Admin sign-in</h1>
        <p class="muted">Sign in with your account to continue.</p>
        <div id="clerk-mount" class="clerk-mount"></div>
        <p id="signin-message" class="message" role="status"></p>
        <button id="dev-signin-button" class="button button-secondary" type="button" hidden>Continue with local dev sign-in</button>
      </section>

      <section id="view-unavailable" class="card view" aria-labelledby="unavailable-heading" hidden>
        <h1 id="unavailable-heading" tabindex="-1">Not available</h1>
        <p class="muted">This page is not available for your account.</p>
      </section>

      <section id="view-code" class="card view" aria-labelledby="code-heading" hidden>
        <h1 id="code-heading" tabindex="-1">Enter admin code</h1>
        <p class="muted">Enter the admin code to open the dashboard. The code is never stored in this browser.</p>
        <form id="code-form" class="stack" autocomplete="off">
          <label for="code-input">Admin code</label>
          <input id="code-input" class="input" name="admin-code" type="password" autocomplete="off"
                 autocapitalize="off" spellcheck="false" required>
          <button id="code-submit" class="button button-primary" type="submit">Continue</button>
        </form>
        <p id="code-message" class="message" role="status"></p>
      </section>

      <section id="view-dashboard" class="view" aria-labelledby="dashboard-heading" hidden>
        <h1 id="dashboard-heading" tabindex="-1">Admin dashboard</h1>
        <div id="admin-tabs" class="tabs" role="tablist" aria-label="Admin sections">
          <button id="tab-users" class="tab" type="button" role="tab" data-tab="users"
                  aria-controls="panel-users" aria-selected="true" tabindex="0">Users</button>
          <button id="tab-monitor" class="tab" type="button" role="tab" data-tab="monitor"
                  aria-controls="panel-monitor" aria-selected="false" tabindex="-1">Monitor</button>
          <button id="tab-audit" class="tab" type="button" role="tab" data-tab="audit"
                  aria-controls="panel-audit" aria-selected="false" tabindex="-1">Audit</button>
        </div>

        <section id="panel-users" class="panel" role="tabpanel" aria-labelledby="tab-users">
          <form id="user-search-form" class="toolbar" role="search">
            <div class="field">
              <label for="user-q">Search users</label>
              <input id="user-q" class="input" type="search" name="q" autocomplete="off"
                     placeholder="Email, name or ID">
            </div>
            <div class="field">
              <label for="user-tier">Tier</label>
              <select id="user-tier" class="input" name="tier">{_tier_options(include_blank=True)}</select>
            </div>
            <div class="field">
              <label for="user-status">Status</label>
              <select id="user-status" class="input" name="status">
                <option value="">Any status</option>
                <option value="active">Active</option>
                <option value="suspended">Suspended</option>
              </select>
            </div>
            <button class="button button-primary" type="submit">Search</button>
          </form>
          <p id="users-message" class="message" role="status"></p>
          <div class="split">
            <div class="list-column">
              <div class="table-wrap">
                <table class="data-table">
                  <caption class="sr-only">Users matching the current filters</caption>
                  <thead>
                    <tr>
                      <th scope="col">Email</th>
                      <th scope="col">Name</th>
                      <th scope="col">Tier</th>
                      <th scope="col">Status</th>
                      <th scope="col">Last active</th>
                      <th scope="col">Created</th>
                    </tr>
                  </thead>
                  <tbody id="users-body"></tbody>
                </table>
              </div>
              <button id="users-more" class="button button-secondary" type="button" hidden>Load more</button>
            </div>
            <section id="user-detail" class="card detail" aria-labelledby="detail-heading">
              <h2 id="detail-heading">User details</h2>
              <p id="detail-empty" class="muted">Choose a user to see usage and actions.</p>
              <div id="detail-body" hidden>
                <h3>Profile</h3>
                <dl id="detail-profile" class="kv"></dl>
                <h3>Usage</h3>
                <dl id="detail-usage" class="kv"></dl>
                <div class="action-group">
                  <h3>Account actions</h3>
                  <button id="btn-status" class="button button-secondary" type="button">Suspend user</button>
                  <button id="btn-revoke" class="button button-secondary" type="button">Revoke sessions</button>
                  <button id="btn-export" class="button button-secondary" type="button">Export data (JSON)</button>
                </div>
                <div class="action-group">
                  <h3>Tier</h3>
                  <div class="inline-field">
                    <label for="detail-tier">New tier</label>
                    <select id="detail-tier" class="input">{_tier_options(include_blank=False)}</select>
                    <button id="btn-tier" class="button button-secondary" type="button">Change tier</button>
                  </div>
                </div>
                <div class="action-group">
                  <h3>Credits</h3>
                  <div class="inline-field">
                    <label for="credit-delta">Credit change (USD)</label>
                    <input id="credit-delta" class="input" type="number" step="0.01" inputmode="decimal">
                  </div>
                  <div class="inline-field">
                    <label for="credit-budget">Set budget (USD)</label>
                    <input id="credit-budget" class="input" type="number" step="0.01" min="0" inputmode="decimal">
                  </div>
                  <p class="muted">Enter either a change or a budget, not both.</p>
                  <p id="credits-error" class="message" role="alert"></p>
                  <button id="btn-credits" class="button button-secondary" type="button">Apply credits</button>
                </div>
                <div class="action-group danger-zone">
                  <h3>Danger zone</h3>
                  <button id="btn-delete" class="button button-danger" type="button">Delete user</button>
                </div>
                <p id="detail-message" class="message" role="status"></p>
              </div>
            </section>
          </div>
        </section>

        <section id="panel-monitor" class="panel" role="tabpanel" aria-labelledby="tab-monitor" hidden>
          <div class="section-heading">
            <h2>Live monitor</h2>
            <p id="monitor-updated" class="muted" aria-live="polite">Not yet updated.</p>
          </div>
          <p class="muted">Refreshes every 5 seconds while this tab is visible.</p>
          <dl id="monitor-metrics" class="metrics"></dl>
          <h3>Provider health</h3>
          <ul id="provider-list" class="provider-list"></ul>
          <p id="monitor-message" class="message" role="status"></p>
        </section>

        <section id="panel-audit" class="panel" role="tabpanel" aria-labelledby="tab-audit" hidden>
          <h2>Audit log</h2>
          <p id="audit-message" class="message" role="status"></p>
          <div class="table-wrap">
            <table class="data-table">
              <caption class="sr-only">Administrator actions, newest first</caption>
              <thead>
                <tr>
                  <th scope="col">When</th>
                  <th scope="col">Admin</th>
                  <th scope="col">Action</th>
                  <th scope="col">Target user</th>
                  <th scope="col">Reason</th>
                  <th scope="col">Detail</th>
                </tr>
              </thead>
              <tbody id="audit-body"></tbody>
            </table>
          </div>
          <button id="audit-more" class="button button-secondary" type="button" hidden>Load more</button>
        </section>
      </section>
    </main>

    <dialog id="confirm-dialog" class="dialog" aria-labelledby="confirm-title" aria-describedby="confirm-summary">
      <form id="confirm-form" class="stack">
        <h2 id="confirm-title"></h2>
        <p id="confirm-summary"></p>
        <div class="field">
          <label for="confirm-reason">Reason (required, recorded in the audit log)</label>
          <textarea id="confirm-reason" class="input" rows="3" required></textarea>
        </div>
        <div id="confirm-typed-wrap" class="field" hidden>
          <label for="confirm-typed">Type DELETE to confirm</label>
          <input id="confirm-typed" class="input" autocomplete="off" spellcheck="false">
        </div>
        <p id="confirm-error" class="message" role="alert"></p>
        <p id="confirm-result" class="message" role="status"></p>
        <div class="dialog-actions">
          <button id="confirm-cancel" class="button button-secondary" type="button">Cancel</button>
          <button id="confirm-submit" class="button button-primary" type="submit" disabled>Confirm</button>
        </div>
      </form>
    </dialog>
  </div>
</body>
</html>
"""
