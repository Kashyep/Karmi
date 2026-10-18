# Physical-device check (to record by a human)

1. `adb install -r app-release.apk`; open Karmi. Expect: tester notice, then Welcome.
2. Welcome > Server address > your https backend; restart the app.
3. Sign in with an email: Clerk emails a code; enter it. Expect the chat screen.
4. Send "What is 12 x 7?"; expect a reply, thumbs and regenerate under it.
5. Settings > Plans and access code: enter a code; expect "Unlocked ...".
Record device model, date, build checksum, observations.
