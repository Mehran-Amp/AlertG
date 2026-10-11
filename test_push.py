#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SignalAlert Instant Push Notification Terminal CLI Tester
Usage:
    python test_push.py
    python test_push.py "App is connected to server 🚀"
    python test_push.py "My Title" "My Body Message"
    python test_push.py "My Title" "My Body Message" "YOUR_FCM_TOKEN"
    python test_push.py --token "YOUR_FCM_TOKEN"
"""

import sys
import os
import json
import time
from datetime import datetime, timedelta

print("\n" + "="*60)
print("🚀 SignalAlert Terminal Push Notification Tester")
print("="*60 + "\n")

# 1. Initialize Firebase Admin SDK
SERVICE_ACCOUNT_FILE = "serviceAccountKey.json"

try:
    import firebase_admin
    from firebase_admin import credentials, messaging

    if not firebase_admin._apps:
        if os.path.exists(SERVICE_ACCOUNT_FILE):
            cred = credentials.Certificate(SERVICE_ACCOUNT_FILE)
            firebase_admin.initialize_app(cred)
            print("✅ Firebase Admin SDK Initialized from local serviceAccountKey.json.")
        elif os.getenv("FIREBASE_SERVICE_ACCOUNT"):
            cred_dict = json.loads(os.getenv("FIREBASE_SERVICE_ACCOUNT"))
            cred = credentials.Certificate(cred_dict)
            firebase_admin.initialize_app(cred)
            print("✅ Firebase Admin SDK Initialized from FIREBASE_SERVICE_ACCOUNT environment variable.")
        else:
            print("❌ ERROR: 'serviceAccountKey.json' not found in current directory!")
            print("👉 Please place your 'serviceAccountKey.json' in this folder (it is protected by .gitignore).")
            print("   Or set the FIREBASE_SERVICE_ACCOUNT environment variable.")
            sys.exit(1)
except Exception as e:
    print(f"❌ Failed to initialize Firebase Admin: {e}")
    sys.exit(1)


# 3. Find Device FCM Token
TOKEN_CACHE_FILE = ".last_fcm_token"
alerts_file = "alerts_data.json"
target_token = None
title = "🔔 [SignalAlert Live Connection]"
body = "✅ App is connected to server! Live Push Channel Active."

# Parse CLI arguments
args = sys.argv[1:]

if "--token" in args:
    idx = args.index("--token")
    if idx + 1 < len(args):
        target_token = args[idx + 1]
        args = [a for i, a in enumerate(args) if i not in (idx, idx + 1)]

if not target_token:
    if len(args) == 3:
        title = args[0]
        body = args[1]
        target_token = args[2]
    elif len(args) == 2:
        if len(args[1]) > 50 and " " not in args[1]:
            body = args[0]
            target_token = args[1]
        else:
            title = args[0]
            body = args[1]
    elif len(args) == 1:
        if len(args[0]) > 50 and " " not in args[0]:
            target_token = args[0]
        else:
            body = args[0]

# Check Token Cache File
if not target_token and os.path.exists(TOKEN_CACHE_FILE):
    try:
        with open(TOKEN_CACHE_FILE, "r", encoding="utf-8") as f:
            cached = f.read().strip()
            if cached and len(cached) > 20:
                target_token = cached
                print(f"📱 Using Cached Device FCM Token: {target_token[:14]}...{target_token[-6:]}")
    except Exception:
        pass

# Check alerts_data.json DB
if not target_token and os.path.exists(alerts_file):
    try:
        with open(alerts_file, "r", encoding="utf-8") as f:
            alerts = json.load(f)
            for a in alerts:
                tok = a.get("fcm_token", "")
                if tok and not any(k in tok.lower() for k in ["sample", "pending", "device_token_"]):
                    target_token = tok
                    print(f"📱 Found Real Device FCM Token from Alert DB: {tok[:14]}...{tok[-6:]}")
                    break
            if not target_token and alerts:
                target_token = alerts[0].get("fcm_token", "")
                if target_token:
                    print(f"📱 Using Active Device Token from DB: {target_token}")
    except Exception as e:
        print(f"⚠️ Error reading alerts_data.json: {e}")

# If still not found, prompt interactively
if not target_token:
    print("⚠️ No saved FCM device token found.")
    print("👉 You can find your device token in the app:")
    print("   1) Open SignalAlert App on phone -> Settings (⚙️) -> Debug Diagnostics (🛠️) -> Test Push (🔔)")
    print("   2) Tap 'Copy Token' and paste it here.\n")
    try:
        if sys.stdin.isatty():
            user_input = input("🔑 Paste FCM Device Token (or press Enter to cancel): ").strip()
            if user_input:
                target_token = user_input
    except Exception:
        pass

if not target_token:
    print("\n❌ No FCM token provided. Cannot send notification.")
    print("💡 Example command with token:")
    print("   python test_push.py \"App Connected! 🚀\" \"Test Message\" \"YOUR_FCM_TOKEN\"\n")
    sys.exit(1)

# Save valid token to cache for next runs
try:
    with open(TOKEN_CACHE_FILE, "w", encoding="utf-8") as f:
        f.write(target_token.strip())
except Exception:
    pass

# Check if token is local device ID or real Google FCM token
if target_token.startswith("dev_") or len(target_token) < 40:
    print("\n" + "="*60)
    print(f"ℹ️ توجه: توکن '{target_token}' شناسه محلی دستگاه (Local Device ID) است.")
    print("📌 سرور Google FCM برای ارسال پیام از راه دور، توکن صادرشده توسط گوگل (۱۵۰+ کاراکتر) را می‌پذیرد.")
    print("\n💡 نحوه تست اعلان و آلارم صفحه قفل:")
    print("   • در گوشی وارد اپ شوید -> تنظیمات (⚙️) -> مرکز عیب‌یابی (🛠️) -> تست پوش (🔔)")
    print("   • دکمه سبز «⚡ تست فوری اعلان و آلارم در صفحه قفل گوشی» را لمس کنید تا فوراً هشدار با صدای آژیر و ویبره در صفحه قفل تست شود.")
    print("   • اپلیکیشن به صورت Local-First و مستقیم روی خود گوشی قیمت‌ها را پایش می‌کند و مستقل از فایربیس کار می‌کند.")
    print("="*60 + "\n")
    sys.exit(0)

print(f"\n📤 Sending High-Priority Test Notification:")
print(f"   • Title: {title}")
print(f"   • Body:  {body}")
print(f"   • Target: {target_token[:15]}...{target_token[-6:]}")
print(f"   • Time:  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

# 5. Dispatch High-Priority Push via FCM
try:
    message = messaging.Message(
        notification=messaging.Notification(
            title=title,
            body=body
        ),
        data={
            "type": "test_ping",
            "timestamp": str(time.time()),
            "source": "terminal_cli_test"
        },
        token=target_token,
        android=messaging.AndroidConfig(
            priority="high",
            ttl=timedelta(days=1),
            direct_boot_ok=True,
            notification=messaging.AndroidNotification(
                sound="default",
                channel_id="alarmer_critical_price_alerts",
                priority="max",
                visibility="public",
                default_sound=True,
                default_vibrate_timings=True,
                default_light_settings=True
            )
        ),
        apns=messaging.APNSConfig(
            payload=messaging.APNSPayload(
                aps=messaging.Aps(
                    sound="default",
                    badge=1,
                    content_available=True,
                    custom_data={"interruption-level": "time-sensitive"}
                )
            )
        )
    )

    response = messaging.send(message)
    print("\n" + "="*60)
    print(f"🎉 SUCCESS! Push notification sent successfully.")
    print(f"📨 FCM Message ID: {response}")
    print("📲 Check your phone's lock screen right now!")
    print("="*60 + "\n")

except Exception as e:
    print("\n" + "="*60)
    print(f"❌ FCM Push Delivery Failed: {e}")
    print("="*60 + "\n")
    sys.exit(1)

