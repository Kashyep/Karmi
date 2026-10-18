/// Notice shown to testers on first launch.
///
/// Bumping [kTesterNoticeVersion] causes users to be re-prompted to
/// acknowledge the updated notice before using the app.
const int kTesterNoticeVersion = 1;

/// Constant title for the first-launch tester notice.
const String kTesterNoticeTitle = 'Tester Notice';

/// Text displayed to testers on first launch.
///
/// Discloses the test build status, AI reply limitations, data logging
/// and storage policies, and advises against submitting sensitive information.
const String kTesterNoticeText =
    'This is a test build. AI replies may be wrong. '
    'Messages may be stored and used to evaluate and improve models. '
    'Do not enter sensitive personal information. '
    'Data handling is pending legal review.';
