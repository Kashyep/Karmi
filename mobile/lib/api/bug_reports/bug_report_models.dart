/// Supported bug report categories.
enum BugReportCategory {
  crash('crash', 'App crash'),
  chat('chat', 'Chat or assistant'),
  ui('ui', 'Visual or layout'),
  account('account', 'Account or sign-in'),
  other('other', 'Other issue');

  const BugReportCategory(this.wireValue, this.displayLabel);

  final String wireValue;
  final String displayLabel;

  static BugReportCategory fromWire(String value) {
    return BugReportCategory.values.firstWhere(
      (c) => c.wireValue == value,
      orElse: () => BugReportCategory.other,
    );
  }

  static BugReportCategory? tryFromWire(String? value) {
    if (value == null) return null;
    for (final c in values) {
      if (c.wireValue == value) return c;
    }
    return null;
  }
}

/// Optional screenshot attachment.
class BugReportScreenshot {
  const BugReportScreenshot({
    required this.contentType,
    required this.dataBase64,
  });

  final String contentType;
  final String dataBase64;

  Map<String, dynamic> toJson() => {
    'content_type': contentType,
    'data_base64': dataBase64,
  };

  factory BugReportScreenshot.fromJson(Map<String, dynamic> json) {
    return BugReportScreenshot(
      contentType: json['content_type'] as String,
      dataBase64: json['data_base64'] as String,
    );
  }
}

/// Strict allowlist of diagnostic fields accepted by the backend.
///
/// Any unknown key is forbidden by the backend (extra="forbid").
/// String values are capped to 128 characters, and list values to 10 items.
class BugReportDiagnostics {
  const BugReportDiagnostics({
    String? appVersion,
    String? buildNumber,
    String? gitSha,
    String? os,
    String? osVersion,
    String? deviceModel,
    String? locale,
    this.textScale,
    String? theme,
    this.reduceTransparency,
    String? plan,
    String? screen,
    List<String>? recentRequestIds,
    List<String>? recentErrorCodes,
    String? runId,
    String? errorCode,
  }) : _appVersion = appVersion,
       _buildNumber = buildNumber,
       _gitSha = gitSha,
       _os = os,
       _osVersion = osVersion,
       _deviceModel = deviceModel,
       _locale = locale,
       _theme = theme,
       _plan = plan,
       _screen = screen,
       _recentRequestIds = recentRequestIds,
       _recentErrorCodes = recentErrorCodes,
       _runId = runId,
       _errorCode = errorCode;

  static const Set<String> allowlistedKeys = {
    'app_version',
    'build_number',
    'git_sha',
    'os',
    'os_version',
    'device_model',
    'locale',
    'text_scale',
    'theme',
    'reduce_transparency',
    'plan',
    'screen',
    'recent_request_ids',
    'recent_error_codes',
    'run_id',
    'error_code',
  };

  final String? _appVersion;
  final String? _buildNumber;
  final String? _gitSha;
  final String? _os;
  final String? _osVersion;
  final String? _deviceModel;
  final String? _locale;
  final double? textScale;
  final String? _theme;
  final bool? reduceTransparency;
  final String? _plan;
  final String? _screen;
  final List<String>? _recentRequestIds;
  final List<String>? _recentErrorCodes;
  final String? _runId;
  final String? _errorCode;

  String? get appVersion => _capString(_appVersion);
  String? get buildNumber => _capString(_buildNumber);
  String? get gitSha => _capString(_gitSha);
  String? get os => _capString(_os);
  String? get osVersion => _capString(_osVersion);
  String? get deviceModel => _capString(_deviceModel);
  String? get locale => _capString(_locale);
  String? get theme => _capString(_theme);
  String? get plan => _capString(_plan);
  String? get screen => _capString(_screen);
  List<String>? get recentRequestIds => _capList(_recentRequestIds);
  List<String>? get recentErrorCodes => _capList(_recentErrorCodes);
  String? get runId => _capString(_runId);
  String? get errorCode => _capString(_errorCode);

  static String? _capString(String? v) {
    if (v == null) return null;
    final runes = v.runes;
    if (runes.length <= 128) return v;
    return String.fromCharCodes(runes.take(128));
  }

  static List<String>? _capList(List<String>? list) {
    if (list == null) return null;
    return list.take(10).map((s) => _capString(s)!).toList();
  }

  /// Deserializes a map, enforcing the strict allowlist.
  ///
  /// If [strict] is true, throws [ArgumentError] if any unknown key is encountered.
  /// Otherwise, unknown keys are omitted.
  factory BugReportDiagnostics.fromMap(
    Map<String, dynamic> map, {
    bool strict = false,
  }) {
    if (strict) {
      for (final key in map.keys) {
        if (!allowlistedKeys.contains(key)) {
          throw ArgumentError('Unknown diagnostics key not allowed: $key');
        }
      }
    }

    List<String>? parseList(dynamic val) {
      if (val is List) {
        return val.map((e) => e.toString()).toList();
      }
      return null;
    }

    double? parseDouble(dynamic val) {
      if (val is num) return val.toDouble();
      if (val is String) return double.tryParse(val);
      return null;
    }

    bool? parseBool(dynamic val) {
      if (val is bool) return val;
      if (val is String) {
        if (val.toLowerCase() == 'true') return true;
        if (val.toLowerCase() == 'false') return false;
      }
      return null;
    }

    return BugReportDiagnostics(
      appVersion: map['app_version'] as String?,
      buildNumber: map['build_number'] as String?,
      gitSha: map['git_sha'] as String?,
      os: map['os'] as String?,
      osVersion: map['os_version'] as String?,
      deviceModel: map['device_model'] as String?,
      locale: map['locale'] as String?,
      textScale: parseDouble(map['text_scale']),
      theme: map['theme'] as String?,
      reduceTransparency: parseBool(map['reduce_transparency']),
      plan: map['plan'] as String?,
      screen: map['screen'] as String?,
      recentRequestIds: parseList(map['recent_request_ids']),
      recentErrorCodes: parseList(map['recent_error_codes']),
      runId: map['run_id'] as String?,
      errorCode: map['error_code'] as String?,
    );
  }

  /// Exports ONLY allowlisted keys with non-null values.
  Map<String, dynamic> toJson() {
    final map = <String, dynamic>{};
    if (appVersion != null) map['app_version'] = _capString(appVersion);
    if (buildNumber != null) map['build_number'] = _capString(buildNumber);
    if (gitSha != null) map['git_sha'] = _capString(gitSha);
    if (os != null) map['os'] = _capString(os);
    if (osVersion != null) map['os_version'] = _capString(osVersion);
    if (deviceModel != null) map['device_model'] = _capString(deviceModel);
    if (locale != null) map['locale'] = _capString(locale);
    if (textScale != null) map['text_scale'] = textScale;
    if (theme != null) map['theme'] = _capString(theme);
    if (reduceTransparency != null) {
      map['reduce_transparency'] = reduceTransparency;
    }
    if (plan != null) map['plan'] = _capString(plan);
    if (screen != null) map['screen'] = _capString(screen);
    if (recentRequestIds != null) {
      map['recent_request_ids'] = _capList(recentRequestIds);
    }
    if (recentErrorCodes != null) {
      map['recent_error_codes'] = _capList(recentErrorCodes);
    }
    if (runId != null) map['run_id'] = _capString(runId);
    if (errorCode != null) map['error_code'] = _capString(errorCode);
    return map;
  }

  /// Returns key-value pairs formatted for user display preview.
  /// The strings reflect the exact values sent to the server.
  List<MapEntry<String, String>> toDisplayEntries() {
    final json = toJson();
    return json.entries.map((entry) {
      return MapEntry(entry.key, entry.value.toString());
    }).toList();
  }
}

/// Request body for `POST /v1/bug-reports`.
class BugReportCreateRequest {
  BugReportCreateRequest({
    required this.clientReportId,
    required dynamic category,
    required this.description,
    required this.diagnostics,
    this.screenshot,
  }) : _category = category is BugReportCategory
           ? category.wireValue
           : category.toString();

  final String clientReportId;
  final String _category;
  dynamic get category => BugReportCategory.tryFromWire(_category) ?? _category;
  String get categoryWire => _category;
  final String description;
  final BugReportDiagnostics diagnostics;
  final BugReportScreenshot? screenshot;

  Map<String, dynamic> toJson() => {
    'client_report_id': clientReportId,
    'category': _category,
    'description': description.trim(),
    'diagnostics': diagnostics.toJson(),
    if (screenshot != null) 'screenshot': screenshot!.toJson(),
  };

  factory BugReportCreateRequest.fromJson(Map<String, dynamic> json) {
    return BugReportCreateRequest(
      clientReportId: json['client_report_id'] as String,
      category: json['category'] as String,
      description: json['description'] as String,
      diagnostics: BugReportDiagnostics.fromMap(
        json['diagnostics'] as Map<String, dynamic>,
      ),
      screenshot: json['screenshot'] != null
          ? BugReportScreenshot.fromJson(
              json['screenshot'] as Map<String, dynamic>,
            )
          : null,
    );
  }
}

/// Response from `POST /v1/bug-reports` (201 Created or 200 OK replay).
class BugReportCreated {
  const BugReportCreated({
    required this.id,
    required this.ticket,
    required this.status,
    required this.createdAt,
  });

  final String id;
  final String ticket;
  final String status;
  final String createdAt;

  factory BugReportCreated.fromJson(Map<String, dynamic> json) {
    return BugReportCreated(
      id: json['id'] as String,
      ticket: json['ticket'] as String,
      status: json['status'] as String,
      createdAt: json['created_at'] as String,
    );
  }
}

/// Response from `GET /v1/bug-reports/{id}`.
class BugReportDetail {
  const BugReportDetail({
    required this.id,
    required this.ticket,
    required this.category,
    required this.description,
    required this.diagnostics,
    required this.status,
    required this.hasScreenshot,
    required this.createdAt,
    required this.updatedAt,
  });

  final String id;
  final String ticket;
  final String category;
  final String description;
  final Map<String, dynamic> diagnostics;
  final String status;
  final bool hasScreenshot;
  final String createdAt;
  final String updatedAt;

  factory BugReportDetail.fromJson(Map<String, dynamic> json) {
    return BugReportDetail(
      id: json['id'] as String,
      ticket: json['ticket'] as String,
      category: json['category'] as String,
      description: json['description'] as String,
      diagnostics: json['diagnostics'] is Map
          ? Map<String, dynamic>.from(json['diagnostics'] as Map)
          : <String, dynamic>{},
      status: json['status'] as String,
      hasScreenshot: json['has_screenshot'] as bool? ?? false,
      createdAt: json['created_at'] as String,
      updatedAt: json['updated_at'] as String,
    );
  }
}
