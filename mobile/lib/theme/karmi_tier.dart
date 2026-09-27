/// The four Karmi tiers (docs/design/karmi_tier_color_palettes.md).
///
/// [id] is the server's integer (`unlocked_tier` / `active_theme`, 1–4) and
/// [planId] the stored plan identifier (`src/daily_agent/plans.py`; Parth's
/// plan id is `part`). The third tier is spelled Trika.
enum KarmiTier {
  ananta(1, 'Ananta', 'ananta', 'The Foundation'),
  yanta(2, 'Yanta', 'yanta', 'The Control'),
  trika(3, 'Trika', 'trika', 'The Trinity'),
  parth(4, 'Parth', 'part', 'The Apex');

  const KarmiTier(this.id, this.label, this.planId, this.tagline);

  final int id;
  final String label;
  final String planId;
  final String tagline;

  /// Null for anything that is not an integer 1–4.
  static KarmiTier? fromId(Object? value) {
    if (value is! int || value is bool) return null;
    for (final tier in values) {
      if (tier.id == value) return tier;
    }
    return null;
  }

  static KarmiTier? fromPlanId(String? planId) {
    for (final tier in values) {
      if (tier.planId == planId) return tier;
    }
    return null;
  }

  bool operator <=(KarmiTier other) => id <= other.id;
  bool operator >(KarmiTier other) => id > other.id;
}
