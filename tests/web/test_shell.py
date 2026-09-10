from daily_agent.web.shell import PLAN_LABELS, TaskState, WebTask, render_shell


def test_shell_has_accessible_navigation_and_pwa_metadata() -> None:
    html = render_shell()
    assert '<main id="main-content" tabindex="-1">' in html
    assert 'Skip to main content' in html
    assert 'aria-label="Primary navigation"' in html
    assert 'rel="manifest"' in html
    assert 'provider' not in html.lower()
    assert 'model picker' not in html.lower()


def test_shell_shows_all_four_plan_labels_without_fake_balances() -> None:
    html = render_shell()
    for label in PLAN_LABELS:
        assert f'<h3>{label}</h3>' in html
    assert 'No balance shown without server data.' in html


def test_task_states_are_truthful_and_escaped() -> None:
    html = render_shell(tasks=(WebTask(TaskState.COMPLETED, '<unsafe>', 'Done & checked'),))
    assert 'Task status: Completed' in html
    assert '&lt;unsafe&gt;' in html
    assert 'Done &amp; checked' in html
    for state in TaskState:
        assert f'state-{state.value}' in render_shell(tasks=(WebTask(state),))
