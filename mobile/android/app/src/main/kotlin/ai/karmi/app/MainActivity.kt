package ai.karmi.app

import android.content.ComponentName
import android.content.Context
import android.content.pm.PackageManager
import androidx.lifecycle.Lifecycle
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

/**
 * Hosts the Flutter UI and the `ai.karmi.app/app_icon` channel.
 *
 * The launcher icon is chosen by enabling exactly one `<activity-alias>`
 * (`.LauncherAnanta` … `.LauncherParth`, see AndroidManifest.xml) and
 * disabling the rest.
 *
 * Android destroys a running task whose launching alias is disabled, even with
 * DONT_KILL_APP (verified on a Pixel 9a, Android 17). So `setIcon` only records
 * the requested tier; the switch is applied in [onStop] (or immediately if the
 * activity is already stopped), when the user has left the app, and the
 * home-screen icon changes then.
 */
class MainActivity : FlutterActivity() {
    private val aliases = mapOf(
        "ananta" to ".LauncherAnanta",
        "yanta" to ".LauncherYanta",
        "trika" to ".LauncherTrika",
        "parth" to ".LauncherParth",
    )

    private val prefs by lazy { getSharedPreferences(PREFS, Context.MODE_PRIVATE) }

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, CHANNEL)
            .setMethodCallHandler { call, result ->
                when (call.method) {
                    "setIcon" -> {
                        val tier = call.argument<String>("tier")
                        if (tier == null || tier !in aliases) {
                            result.error("invalid_tier", "Unknown tier: $tier", null)
                        } else {
                            prefs.edit().putString(KEY_PENDING, tier).apply()
                            // Already in the background: nothing visible to tear down.
                            if (!lifecycle.currentState.isAtLeast(Lifecycle.State.STARTED)) {
                                applyPendingIcon()
                            }
                            result.success(true)
                        }
                    }
                    "currentIcon" -> result.success(currentIcon())
                    else -> result.notImplemented()
                }
            }
    }

    override fun onStop() {
        super.onStop()
        if (!isChangingConfigurations) applyPendingIcon()
    }

    private fun applyPendingIcon() {
        val tier = prefs.getString(KEY_PENDING, null) ?: return
        prefs.edit().remove(KEY_PENDING).apply()
        if (tier !in aliases || currentIcon() == tier) return
        val target = aliases.getValue(tier)
        // Enable the new alias first so the app always has a launcher entry.
        packageManager.setComponentEnabledSetting(
            component(target),
            PackageManager.COMPONENT_ENABLED_STATE_ENABLED,
            PackageManager.DONT_KILL_APP,
        )
        for (alias in aliases.values) {
            if (alias == target) continue
            packageManager.setComponentEnabledSetting(
                component(alias),
                PackageManager.COMPONENT_ENABLED_STATE_DISABLED,
                PackageManager.DONT_KILL_APP,
            )
        }
    }

    private fun component(alias: String) = ComponentName(packageName, packageName + alias)

    private fun isEnabled(alias: String): Boolean {
        val state = packageManager.getComponentEnabledSetting(component(alias))
        // DEFAULT means "as declared in the manifest": only Ananta is enabled there.
        return state == PackageManager.COMPONENT_ENABLED_STATE_ENABLED ||
            (state == PackageManager.COMPONENT_ENABLED_STATE_DEFAULT && alias == ".LauncherAnanta")
    }

    private fun currentIcon(): String? =
        aliases.entries.firstOrNull { isEnabled(it.value) }?.key

    companion object {
        const val CHANNEL = "ai.karmi.app/app_icon"
        private const val PREFS = "karmi_app_icon"
        private const val KEY_PENDING = "pending_tier"
    }
}
