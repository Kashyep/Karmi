import Flutter
import UIKit

@main
@objc class AppDelegate: FlutterAppDelegate, FlutterImplicitEngineDelegate {
  override func application(
    _ application: UIApplication,
    didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?
  ) -> Bool {
    return super.application(application, didFinishLaunchingWithOptions: launchOptions)
  }

  func didInitializeImplicitFlutterEngine(_ engineBridge: FlutterImplicitEngineBridge) {
    GeneratedPluginRegistrant.register(with: engineBridge.pluginRegistry)
    if let registrar = engineBridge.pluginRegistry.registrar(forPlugin: "KarmiAppIconPlugin") {
      KarmiAppIconPlugin.register(with: registrar)
    }
  }
}

/// `ai.karmi.app/app_icon`: switches the home-screen icon to the active tier
/// with `setAlternateIconName` (implementation_plan.md §3.3). Alternate icons
/// are the `AppIcon-<Tier>` sets in Assets.xcassets, compiled in through
/// ASSETCATALOG_COMPILER_ALTERNATE_APPICON_NAMES. Ananta is the primary icon.
final class KarmiAppIconPlugin: NSObject, FlutterPlugin {
  private static let alternates: [String: String?] = [
    "ananta": nil,
    "yanta": "AppIcon-Yanta",
    "trika": "AppIcon-Trika",
    "parth": "AppIcon-Parth",
  ]

  static func register(with registrar: FlutterPluginRegistrar) {
    let channel = FlutterMethodChannel(
      name: "ai.karmi.app/app_icon", binaryMessenger: registrar.messenger())
    registrar.addMethodCallDelegate(KarmiAppIconPlugin(), channel: channel)
  }

  func handle(_ call: FlutterMethodCall, result: @escaping FlutterResult) {
    guard call.method == "setIcon" else {
      result(FlutterMethodNotImplemented)
      return
    }
    guard
      let args = call.arguments as? [String: Any],
      let tier = args["tier"] as? String,
      let name = KarmiAppIconPlugin.alternates[tier]
    else {
      result(FlutterError(code: "invalid_tier", message: "Unknown tier", details: nil))
      return
    }
    let app = UIApplication.shared
    guard app.supportsAlternateIcons else {
      result(false)
      return
    }
    if app.alternateIconName == name {
      result(true)
      return
    }
    app.setAlternateIconName(name) { error in
      DispatchQueue.main.async { result(error == nil) }
    }
  }
}
