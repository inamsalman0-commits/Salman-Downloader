[app]
title = Salman Downloader
package.name = salmandownloader
package.domain = org.salman

source.dir = .
source.include_exts = py,png,jpg,kv,atlas

version = 1.0

requirements = python3,kivy==2.2.1,yt-dlp,certifi,pyjnius,openssl,chardet,idna,urllib3,requests

orientation = portrait
fullscreen = 0

icon.filename = %(source.dir)s/icon.png

# Permissions needed: internet access + save files to shared storage
android.permissions = INTERNET,WRITE_EXTERNAL_STORAGE,READ_EXTERNAL_STORAGE,MANAGE_EXTERNAL_STORAGE

android.api = 33
android.minapi = 21
android.ndk = 25b
android.accept_sdk_license = True
android.archs = arm64-v8a, armeabi-v7a

[buildozer]
log_level = 2
warn_on_root = 1
