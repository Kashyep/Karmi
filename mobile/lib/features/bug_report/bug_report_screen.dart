import 'dart:async';
import 'dart:typed_data';

import 'package:flutter/material.dart';

import '../../api/bug_reports/bug_report_models.dart';
import '../../api/bug_reports/bug_reports_api.dart';
import '../../api/karmi_api.dart';
import '../../auth/session.dart';
import '../../theme/karmi_colors.dart';
import '../../widgets/feedback.dart';
import '../../widgets/karmi_card.dart';
import 'bug_report_queue.dart';
import 'bug_report_service.dart';
import 'diagnostics_collector.dart';
import 'error_mapping.dart';
import 'screenshot_capture.dart';
import 'uuid4.dart';

/// Customer bug report submission form.
class BugReportScreen extends StatefulWidget {
  const BugReportScreen({
    super.key,
    this.api,
    this.queue,
    this.service,
    this.session,
    this.userId,
    this.initialCategory,
    this.initialErrorCode,
    this.initialScreen,
    this.initialRunId,
    this.initialPlan,
    Uint8List? screenshotBytes,
    Uint8List? initialScreenshotBytes,
    this.onDismiss,
  }) : screenshotBytes = screenshotBytes ?? initialScreenshotBytes;

  final KarmiApi? api;
  final BugReportQueue? queue;
  final BugReportService? service;
  final KarmiSession? session;
  final String? userId;
  final BugReportCategory? initialCategory;
  final String? initialErrorCode;
  final String? initialScreen;
  final String? initialRunId;
  final String? initialPlan;
  final Uint8List? screenshotBytes;
  final VoidCallback? onDismiss;

  @override
  State<BugReportScreen> createState() => _BugReportScreenState();
}

class _BugReportScreenState extends State<BugReportScreen> {
  late final String _clientReportId;
  late final BugReportService _service;
  late BugReportCategory _selectedCategory;
  final _descriptionController = TextEditingController();

  bool _includeScreenshot = false;
  Uint8List? _screenshotBytes;
  String? _screenshotError;

  bool _showDiagnostics = false;
  late BugReportDiagnostics _diagnostics;

  bool _isSubmitting = false;
  String? _submissionError;
  BugReportSubmissionResult? _submissionResult;
  String? _initialOwner;

  String? get _currentOwner => widget.userId ?? widget.session?.userId;

  /// Whether the screen currently has a valid, unchanged owner.
  ///
  /// Bug report drafts and queues are bound to a specific user on screen entry.
  /// If the active session or owner changes (user signs out, token expires, or switches
  /// accounts) during report composition, we fail-closed: [hasOwner] evaluates to false,
  /// the submit button is disabled, and submissions are rejected. This prevents cross-user
  /// report leakage into a previous owner's offline retry queue.
  bool get _hasOwner {
    if (widget.service != null && _initialOwner == null) {
      return true;
    }
    final current = _currentOwner;
    if (current == null || current.isEmpty) return false;
    if (_initialOwner == null || _initialOwner!.isEmpty) return false;
    return current == _initialOwner;
  }

  void _onSessionChanged() {
    if (!mounted) return;
    setState(() {
      if (!_hasOwner) {
        _submissionError = 'Sign in again to send reports';
      }
    });
  }

  @override
  void initState() {
    super.initState();
    // Invariant: client_report_id generated ONCE per report draft
    _clientReportId = generateUuidV4();

    _selectedCategory = widget.initialCategory ?? BugReportCategory.chat;
    _screenshotBytes = widget.screenshotBytes;

    _initialOwner = widget.userId ?? widget.session?.userId;
    widget.session?.addListener(_onSessionChanged);

    if (widget.service != null) {
      _service = widget.service!;
    } else {
      final queue = widget.queue ?? BugReportQueue();
      final api = widget.api != null
          ? BugReportsApi.fromApi(widget.api!)
          : BugReportsApi(baseUrl: KarmiApi.defaultBaseUrl);
      _service = BugReportService(
        api: api,
        queue: queue,
        userId: _initialOwner,
      );
      if (_initialOwner == null || _initialOwner!.isEmpty) {
        _submissionError = 'Sign in again to send reports';
      }
    }

    if (_initialOwner != null && _initialOwner!.isNotEmpty) {
      unawaited(_service.flushQueue().catchError((_) => 0));
    }
    _diagnostics = const DiagnosticsCollector().collect(
      screen: widget.initialScreen,
      errorCode: widget.initialErrorCode,
      runId: widget.initialRunId,
      plan: widget.initialPlan,
    );

    _descriptionController.addListener(() {
      setState(() {});
    });
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    // Update context-dependent diagnostics (theme, text scale, locale)
    _diagnostics = const DiagnosticsCollector().collect(
      context: context,
      screen: widget.initialScreen,
      errorCode: widget.initialErrorCode,
      runId: widget.initialRunId,
      plan: widget.initialPlan,
    );
  }

  @override
  void didUpdateWidget(BugReportScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.session != widget.session) {
      oldWidget.session?.removeListener(_onSessionChanged);
      widget.session?.addListener(_onSessionChanged);
    }
    if (oldWidget.userId != widget.userId ||
        oldWidget.session != widget.session) {
      _onSessionChanged();
    }
  }

  @override
  void dispose() {
    widget.session?.removeListener(_onSessionChanged);
    _descriptionController.dispose();
    super.dispose();
  }

  int get _trimmedLength => _descriptionController.text.trim().length;
  bool get _isTooShort => _trimmedLength < 10;
  bool get _isTooLong => _trimmedLength > 2000;
  bool get _isDescriptionValid => !_isTooShort && !_isTooLong;

  void _onToggleScreenshot(bool value) {
    setState(() {
      _includeScreenshot = value;
      _screenshotError = null;
      if (value && _screenshotBytes != null) {
        if (!isScreenshotSizeValid(_screenshotBytes!.lengthInBytes)) {
          _screenshotError = kScreenshotTooBigMessage;
        }
      }
    });
  }

  Future<void> _submit() async {
    if (!_hasOwner) {
      setState(() {
        _submissionError = 'Sign in again to send reports';
      });
      return;
    }

    if (!_isDescriptionValid) {
      setState(() {
        if (_isTooShort) {
          _submissionError =
              'Please enter at least 10 characters describing the issue.';
        } else {
          _submissionError = 'Description cannot exceed 2000 characters.';
        }
      });
      return;
    }

    BugReportScreenshot? screenshotPayload;
    if (_includeScreenshot && _screenshotBytes != null) {
      if (!isScreenshotSizeValid(_screenshotBytes!.lengthInBytes)) {
        setState(() {
          _screenshotError = kScreenshotTooBigMessage;
          _submissionError = kScreenshotTooBigMessage;
        });
        return;
      }
      screenshotPayload = prepareScreenshotPayload(_screenshotBytes);
    }

    final request = BugReportCreateRequest(
      clientReportId: _clientReportId,
      category: _selectedCategory.wireValue,
      description: _descriptionController.text.trim(),
      diagnostics: _diagnostics,
      screenshot: screenshotPayload,
    );

    setState(() {
      _isSubmitting = true;
    });

    try {
      final result = await _service.submit(request);
      if (!mounted) return;
      setState(() {
        _isSubmitting = false;
        _submissionResult = result;
        if (!result.isSuccess && !result.isQueued) {
          _submissionError = result.userMessage;
        }
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _isSubmitting = false;
        _submissionError = mapBugReportErrorToPlainWords(e);
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final colors = KarmiColors.of(context);
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Report a bug'),
        leading: IconButton(
          icon: const Icon(Icons.close),
          onPressed: widget.onDismiss ?? () => Navigator.of(context).maybePop(),
        ),
      ),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
          child:
              _submissionResult != null &&
                  (_submissionResult!.isSuccess || _submissionResult!.isQueued)
              ? _buildSuccessView(context, colors, theme)
              : _buildForm(context, colors, theme),
        ),
      ),
    );
  }

  Widget _buildSuccessView(
    BuildContext context,
    KarmiColors colors,
    ThemeData theme,
  ) {
    final res = _submissionResult!;
    final isSuccess = res.isSuccess;

    return Center(
      child: KarmiCard(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              isSuccess ? Icons.check_circle_outline : Icons.cloud_queue,
              size: 48,
              color: isSuccess ? colors.success : colors.mutedForeground,
            ),
            const SizedBox(height: 16),
            Text(
              isSuccess ? 'Report Received' : 'Saved for Submission',
              style: theme.textTheme.titleLarge?.copyWith(
                fontWeight: FontWeight.bold,
                color: colors.primaryText,
              ),
            ),
            const SizedBox(height: 12),
            if (isSuccess && res.ticket != null) ...[
              Text(
                'Ticket: ${res.ticket}',
                key: const ValueKey('bug-report-ticket-display'),
                style: theme.textTheme.titleMedium?.copyWith(
                  fontWeight: FontWeight.w600,
                  color: colors.accent,
                ),
              ),
              const SizedBox(height: 4),
              Text(
                'Status: ${res.reportStatus ?? "new"}',
                key: const ValueKey('bug-report-status-display'),
                style: theme.textTheme.bodyMedium?.copyWith(
                  color: colors.mutedForeground,
                ),
              ),
              const SizedBox(height: 16),
              Text(
                'Thank you for helping us improve Karmi. Our team will review your report.',
                textAlign: TextAlign.center,
                style: theme.textTheme.bodyMedium?.copyWith(
                  color: colors.mutedForeground,
                ),
              ),
            ] else ...[
              Text(
                res.userMessage,
                key: const ValueKey('bug-report-offline-message'),
                textAlign: TextAlign.center,
                style: theme.textTheme.bodyMedium?.copyWith(
                  color: colors.mutedForeground,
                ),
              ),
            ],
            const SizedBox(height: 24),
            SizedBox(
              width: double.infinity,
              child: FilledButton(
                key: const ValueKey('bug-report-done-button'),
                onPressed:
                    widget.onDismiss ?? () => Navigator.of(context).maybePop(),
                child: const Text('Done'),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildForm(BuildContext context, KarmiColors colors, ThemeData theme) {
    final hasOwner = _hasOwner;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        // Category Picker
        Text(
          'Category',
          style: theme.textTheme.labelLarge?.copyWith(
            fontWeight: FontWeight.w600,
            color: colors.primaryText,
          ),
        ),
        const SizedBox(height: 8),
        KarmiCard(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
          child: DropdownButtonHideUnderline(
            child: DropdownButton<BugReportCategory>(
              key: const ValueKey('category-picker'),
              value: _selectedCategory,
              isExpanded: true,
              items: BugReportCategory.values.map((category) {
                return DropdownMenuItem<BugReportCategory>(
                  key: ValueKey('category-option-${category.wireValue}'),
                  value: category,
                  child: Text(category.displayLabel),
                );
              }).toList(),
              onChanged: (cat) {
                if (cat != null) {
                  setState(() {
                    _selectedCategory = cat;
                  });
                }
              },
            ),
          ),
        ),
        const SizedBox(height: 16),

        // Description Field
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(
              'Description',
              style: theme.textTheme.labelLarge?.copyWith(
                fontWeight: FontWeight.w600,
                color: colors.primaryText,
              ),
            ),
            Text(
              '$_trimmedLength / 2000',
              key: const ValueKey('char-counter'),
              style: theme.textTheme.bodySmall?.copyWith(
                color: _isTooLong ? colors.destructive : colors.mutedForeground,
              ),
            ),
          ],
        ),
        const SizedBox(height: 8),
        TextField(
          key: const ValueKey('description-field'),
          controller: _descriptionController,
          maxLines: 5,
          minLines: 3,
          decoration: InputDecoration(
            hintText: 'What happened? What did you expect to happen instead?',
            errorText: _isTooLong
                ? 'Description exceeds 2000 characters limit'
                : (_descriptionController.text.isNotEmpty && _isTooShort)
                ? 'Please provide at least 10 characters'
                : null,
            border: const OutlineInputBorder(),
          ),
        ),
        const SizedBox(height: 16),
        // Screenshot Section (only shown when screenshot bytes are captured)
        if (_screenshotBytes != null) ...[
          KarmiCard(
            padding: const EdgeInsets.all(12),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            'Include screenshot',
                            style: theme.textTheme.bodyLarge?.copyWith(
                              fontWeight: FontWeight.w600,
                              color: colors.primaryText,
                            ),
                          ),
                          const SizedBox(height: 2),
                          Text(
                            'Optional screen capture for debugging',
                            style: theme.textTheme.bodySmall?.copyWith(
                              color: colors.mutedForeground,
                            ),
                          ),
                        ],
                      ),
                    ),
                    Switch(
                      key: const ValueKey('screenshot-consent-toggle'),
                      value: _includeScreenshot,
                      onChanged: _onToggleScreenshot,
                    ),
                  ],
                ),
                if (_includeScreenshot) ...[
                  const SizedBox(height: 8),
                  Container(
                    key: const ValueKey('screenshot-notice'),
                    padding: const EdgeInsets.all(8),
                    decoration: BoxDecoration(color: colors.muted),
                    child: Text(
                      'Notice: The screenshot may include on-screen content. Please ensure no sensitive information is shown.',
                      style: theme.textTheme.bodySmall?.copyWith(
                        color: colors.mutedForeground,
                      ),
                    ),
                  ),
                  if (_screenshotError != null) ...[
                    const SizedBox(height: 8),
                    Text(
                      _screenshotError!,
                      key: const ValueKey('screenshot-error-message'),
                      style: theme.textTheme.bodySmall?.copyWith(
                        color: colors.destructive,
                      ),
                    ),
                  ],
                ],
              ],
            ),
          ),
          const SizedBox(height: 16),
        ],
        // Diagnostics Transparency Section
        KarmiCard(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
          child: Column(
            children: [
              InkWell(
                key: const ValueKey('diagnostics-expand-button'),
                onTap: () {
                  setState(() {
                    _showDiagnostics = !_showDiagnostics;
                  });
                },
                child: Padding(
                  padding: const EdgeInsets.symmetric(vertical: 4),
                  child: Row(
                    children: [
                      Icon(
                        _showDiagnostics
                            ? Icons.expand_less
                            : Icons.expand_more,
                        color: colors.mutedForeground,
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          'Diagnostics to be sent (${_diagnostics.toJson().length} items)',
                          style: theme.textTheme.bodyMedium?.copyWith(
                            fontWeight: FontWeight.w600,
                            color: colors.primaryText,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
              if (_showDiagnostics) ...[
                const Divider(),
                Container(
                  key: const ValueKey('diagnostics-table'),
                  padding: const EdgeInsets.symmetric(vertical: 4),
                  child: Column(
                    children: _diagnostics.toDisplayEntries().map((entry) {
                      return Padding(
                        padding: const EdgeInsets.symmetric(vertical: 3),
                        child: Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            SizedBox(
                              width: 130,
                              child: Text(
                                entry.key,
                                style: theme.textTheme.bodySmall?.copyWith(
                                  fontWeight: FontWeight.w600,
                                  color: colors.primaryText,
                                ),
                              ),
                            ),
                            Expanded(
                              child: Text(
                                entry.value,
                                style: theme.textTheme.bodySmall?.copyWith(
                                  color: colors.mutedForeground,
                                ),
                              ),
                            ),
                          ],
                        ),
                      );
                    }).toList(),
                  ),
                ),
              ],
            ],
          ),
        ),
        const SizedBox(height: 16),

        // Error message banner (plain words)
        if (_submissionError != null) ...[
          Container(
            key: const ValueKey('submission-error-banner'),
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: colors.destructive.withValues(alpha: 0.1),
              borderRadius: BorderRadius.circular(8),
              border: Border.all(
                color: colors.destructive.withValues(alpha: 0.3),
              ),
            ),
            child: Text(
              _submissionError!,
              style: theme.textTheme.bodyMedium?.copyWith(
                color: colors.destructive,
              ),
            ),
          ),
          const SizedBox(height: 16),
        ],

        // Submit Button
        FilledButton(
          key: const ValueKey('submit-bug-report-button'),
          onPressed: _isSubmitting || !hasOwner || !_isDescriptionValid
              ? null
              : _submit,
          child: _isSubmitting
              ? const KarmiLoader(label: 'Sending report')
              : const Text('Send bug report'),
        ),
      ],
    );
  }
}
