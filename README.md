# 🎬 AnyVideo Downloader

**যেকোনো ভিডিও লিংক দিলে সব কোয়ালিটিতে (ভিডিও + অডিও) ডাউনলোড করা যায় — YouTube সহ ১০০০+ সাইট।**

Paste any video link → download video in every quality (360p → 4K) or audio as MP3.
Powered by [yt-dlp](https://github.com/yt-dlp/yt-dlp) + Flask.

---

## ✨ ফিচারসমূহ / Features

| | |
|---|---|
| 🎥 **সব কোয়ালিটি** | 144p থেকে 4K (2160p) পর্যন্ত যত কোয়ালিটি আছে সব দেখায় |
| 🎵 **MP3 অডিও** | যেকোনো ভিডিও থেকে 192kbps MP3 বের করে দেয় (অথবা original m4a/webm) |
| ▶️ **YouTube** | ইউটিউব fully সাপোর্টেড — playlist নয়, শুধু একক ভিডিও |
| 🌐 **১০০০+ সাইট** | Facebook, Instagram, TikTok, Twitter/X, Vimeo, Dailymotion, SoundCloud ইত্যাদি |
| 🔀 **অটো মার্জ** | 720p+ (HD) ফরম্যাটে সার্ভার নিজেই ভিডিও+অডিও merge করে (ffmpeg) |
| 📱 **রেসপন্সিভ UI** | মোবাইল-ফ্রেন্ডলি, বাংলা + ইংরেজি, ডার্ক থিম, রিসেন্ট হিস্ট্রি |

---

## 🚀 চালানোর নিয়ম / Quick Start

```bash
# ১) ভার্চুয়াল এনভায়রনমেন্ট
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# ২) ডিপেন্ডেন্সি
pip install -r requirements.txt  # ffmpeg আলাদা লাগবে না — imageio-ffmpeg থেকে আসে

# ৩) চালু
python app.py                    # http://localhost:5000
```

**প্রোডাকশনে:**
```bash
gunicorn -w 2 -k gthread --threads 8 -b 0.0.0.0:5000 app:app
```

---

## ⚙️ কনফিগারেশন (Environment Variables)

| Variable | Default | কাজ |
|---|---|---|
| `PORT` | `5000` | সার্ভার পোর্ট |
| `HOST` | `0.0.0.0` | বাইন্ড অ্যাড্রেস |
| `MAX_CONCURRENT_JOBS` | `3` | একসাথে কতটা ভারী ডাউনলোড (merge/MP3) |
| `YTDLP_COOKIES_FILE` | — | বট-চেক/age-restricted ভিডিওর জন্য cookies.txt (Netscape format) |
| `YTDLP_COOKIES_FROM_BROWSER` | — | লোকাল টেস্টে ব্রাউজার থেকে cookies, যেমন `chrome` |
| `YTDLP_PROXY` | — | কোনো সাইট ব্লক করলে প্রক্সি, যেমন `socks5://user:pass@host:port` |
| `YTDLP_PLAYER_CLIENT` | — | ইউটিউবের জন্য player client জোর করা, যেমন `android,ios` |
| `ALLOW_PRIVATE_URLS` | `0` | টেস্টের জন্য localhost/private IP অনুমতি (প্রোডাকশনে রাখবেন না!) |

### YouTube "Sign in to confirm you're not a bot" এলে

সার্ভারের IP (ডেটাসেন্টার) ব্লক হলে cookies লাগবে:

1. নিজের কম্পিউটারের ব্রাউজারে YouTube-এ লগইন থাকুন
2. ["Get cookies.txt LOCALLY"](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc) এক্সটেনশন দিয়ে `cookies.txt` নামান
3. সার্ভারে রেখে: `YTDLP_COOKIES_FILE=/path/cookies.txt` সেট করে রিস্টার্ট করুন

---

## 🐳 Docker

```bash
docker build -t anyvideo-downloader .
docker run -p 5000:5000 -v $(pwd)/cookies.txt:/app/cookies.txt:ro \
  -e YTDLP_COOKIES_FILE=/app/cookies.txt anyvideo-downloader
```

---

## 📁 প্রজেক্ট স্ট্রাকচার

```
├── app.py              # Flask ব্যাকএন্ড (yt-dlp: info + download + merge + mp3)
├── templates/index.html # ফ্রন্টএন্ড (বাংলা UI)
├── static/style.css    # স্টাইল
├── static/app.js       # ফ্রন্টএন্ড লজিক
├── requirements.txt
└── Dockerfile
```

### API

| Endpoint | Method | কাজ |
|---|---|---|
| `/` | GET | ওয়েব UI |
| `/api/info` | POST `{url}` | টাইটেল, থাম্বনেইল + সব কোয়ালিটির লিস্ট (JSON) |
| `/download?url=&fid=&mode=video\|audio\|audio-mp3&q=&t=` | GET | ফাইল ডাউনলোড (stream) |
| `/api/health` | GET | হেলথ চেক |

---

## ⚠️ দাবিত্যাগ / Disclaimer

এই টুলটি শুধুমাত্র **ব্যক্তিগত ব্যবহারের** জন্য। কপিরাইটযুক্ত কনটেন্ট মালিকের অনুমতি ছাড়া ডাউনলোড/পুনঃবিতরণ করবেন না — এটি প্ল্যাটফর্মের শর্তাবলী (যেমন YouTube ToS) ও আপনার দেশের আইনের বিরুদ্ধে হতে পারে। নিজের আপলোড করা, Creative Commons, বা অনুমতিপ্রাপ্ত কনটেন্টের জন্য ব্যবহার করুন।
