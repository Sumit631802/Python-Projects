"""
Voice-Activated Personal Assistant (single-file)

Features:
- Wake-word (simple): say "assistant" or press Enter to start listening
- Speech recognition (speech_recognition library using Google Web Speech by default)
- Text-to-speech using pyttsx3 (offline)
- Set reminders (schedules a local reminder)
- Check weather (OpenWeatherMap API) — requires API key
- Read top news headlines (NewsAPI) — requires API key
- Tell the time / date
- Basic conversation and fallback to web search (opens browser)

Setup:
1. Create a virtual environment (recommended):
   python -m venv .venv
   source .venv/bin/activate  # Linux/macOS
   .\.venv\Scripts\activate   # Windows (PowerShell: .\.venv\Scripts\Activate.ps1)

2. Install dependencies:
   pip install SpeechRecognition pyttsx3 requests pyaudio
   # On Windows, installing pyaudio may require wheels; on Linux, `sudo apt-get install portaudio19-dev` then pip install pyaudio.

3. Get API keys (optional but required for weather/news):
   - OpenWeatherMap: https://openweathermap.org/api -> set OPENWEATHER_API_KEY
   - NewsAPI: https://newsapi.org -> set NEWSAPI_KEY

4. Run:
   python voice_assistant.py

Notes:
- This script uses the Google Web Speech API by default via `speech_recognition`. That requires internet. You may switch to an offline recognizer (pocketsphinx) but need extra setup.
- pyttsx3 is offline for TTS.

"""

import os
import time
import threading
import webbrowser
from datetime import datetime, timedelta

import requests
import speech_recognition as sr
import pyttsx3

# -------------------- Configuration --------------------
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "")
NEWSAPI_KEY = os.getenv("NEWSAPI_KEY", "")
DEFAULT_CITY = "New Delhi,IN"
WAKE_WORDS = ("assistant", "hey assistant", "ok assistant")

# -------------------- TTS Engine --------------------
engine = pyttsx3.init()
engine.setProperty('rate', 160)
engine.setProperty('volume', 1.0)

def speak(text: str):
    """Speak given text (non-blocking)."""
    def _run(t):
        engine.say(t)
        engine.runAndWait()
    t = threading.Thread(target=_run, args=(text,))
    t.daemon = True
    t.start()

# -------------------- Speech Recognition --------------------
recognizer = sr.Recognizer()
mic = None
try:
    mic = sr.Microphone()
except Exception as e:
    print("Warning: Could not initialize microphone:", e)

def listen(timeout: int = 5, phrase_time_limit: int = 8) -> str:
    """Listen from microphone and return recognized text (lowercased)."""
    if mic is None:
        return ""
    with mic as source:
        recognizer.adjust_for_ambient_noise(source, duration=0.5)
        print("Listening...")
        audio = recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_time_limit)
    try:
        text = recognizer.recognize_google(audio)
        print("Heard:", text)
        return text.lower()
    except sr.WaitTimeoutError:
        return ""
    except sr.UnknownValueError:
        return ""
    except sr.RequestError as e:
        print("Speech recognition error (maybe no internet):", e)
        return ""

# -------------------- Reminders --------------------
reminders = []  # list of (datetime, message)
reminder_lock = threading.Lock()

def reminder_worker():
    while True:
        now = datetime.now()
        with reminder_lock:
            due = [r for r in reminders if r[0] <= now]
            reminders[:] = [r for r in reminders if r[0] > now]
        for when, msg in due:
            speak(f"Reminder: {msg}")
            print(f"[Reminder at {when}]: {msg}")
        time.sleep(1)

threading.Thread(target=reminder_worker, daemon=True).start()

def set_reminder_in(minutes: int, message: str):
    when = datetime.now() + timedelta(minutes=minutes)
    with reminder_lock:
        reminders.append((when, message))
    speak(f"Okay. I will remind you in {minutes} minutes about {message}.")
    print(f"Set reminder at {when} -> {message}")

# -------------------- Weather --------------------

def get_weather(city: str = DEFAULT_CITY):
    if not OPENWEATHER_API_KEY:
        return None, "OpenWeather API key not set. Set OPENWEATHER_API_KEY environment variable."
    url = "https://api.openweathermap.org/data/2.5/weather"
    params = {"q": city, "appid": OPENWEATHER_API_KEY, "units": "metric"}
    try:
        r = requests.get(url, params=params, timeout=8)
        r.raise_for_status()
        j = r.json()
        desc = j['weather'][0]['description']
        temp = j['main']['temp']
        feels = j['main'].get('feels_like')
        return f"{desc}, temperature {temp}°C, feels like {feels}°C", None
    except Exception as e:
        return None, str(e)

# -------------------- News --------------------

def get_top_news(count: int = 5):
    if not NEWSAPI_KEY:
        return None, "NewsAPI key not set. Set NEWSAPI_KEY environment variable."
    url = "https://newsapi.org/v2/top-headlines"
    params = {"apiKey": NEWSAPI_KEY, "country": "in", "pageSize": count}
    try:
        r = requests.get(url, params=params, timeout=8)
        r.raise_for_status()
        j = r.json()
        articles = j.get('articles', [])
        headlines = [a['title'] for a in articles]
        return headlines, None
    except Exception as e:
        return None, str(e)

# -------------------- Command Handling --------------------

def handle_command(text: str):
    text = text.lower().strip()
    if not text:
        speak("I didn't catch that. Please repeat.")
        return

    # Reminders
    if "remind me in" in text:
        # e.g. "remind me in 10 minutes to check the oven"
        import re
        m = re.search(r"remind me in (\d+) (minute|minutes|hour|hours) (?:to )?(.*)", text)
        if m:
            value = int(m.group(1))
            unit = m.group(2)
            msg = m.group(3) or "your task"
            if 'hour' in unit:
                minutes = value * 60
            else:
                minutes = value
            set_reminder_in(minutes, msg)
            return
        else:
            speak("Please say: remind me in X minutes to do Y.")
            return

    if text.startswith("set reminder") or text.startswith("remind me to"):
        # fallback simple: ask for time in minutes
        speak("For when should I set the reminder? Say in how many minutes.")
        reply = listen()
        try:
            mins = int(''.join(filter(str.isdigit, reply)))
            speak("What should I remind you about?")
            msg = listen()
            if not msg:
                msg = "your task"
            set_reminder_in(mins, msg)
        except Exception:
            speak("I couldn't parse the time. Reminder cancelled.")
        return

    # Weather
    if 'weather' in text:
        # optional: extract city
        parts = text.split()
        city = DEFAULT_CITY
        # naive city extraction
        if 'in' in parts:
            try:
                idx = parts.index('in')
                city = ' '.join(parts[idx+1:])
            except Exception:
                city = DEFAULT_CITY
        weather_text, err = get_weather(city)
        if err:
            speak(f"Sorry, I couldn't fetch weather. {err}")
        else:
            speak(f"Weather in {city}: {weather_text}")
        return

    # News
    if 'news' in text or 'headlines' in text:
        headlines, err = get_top_news(5)
        if err:
            speak(f"Sorry, can't fetch news: {err}")
        else:
            speak("Here are the top headlines.")
            for h in headlines:
                speak(h)
                time.sleep(0.5)
        return

    # Time and date
    if 'time' in text:
        now = datetime.now().strftime('%I:%M %p')
        speak(f"The time is {now}")
        return
    if 'date' in text:
        today = datetime.now().strftime('%A, %B %d, %Y')
        speak(f"Today is {today}")
        return

    # Open website / search
    if text.startswith('search for') or text.startswith('google') or 'search' in text:
        # open a web browser search
        query = text.replace('search for', '').replace('google', '').replace('search', '')
        query = query.strip()
        if not query:
            speak('What should I search for?')
            query = listen()
        if query:
            speak(f"Searching for {query} on the web.")
            webbrowser.open(f"https://www.google.com/search?q={requests.utils.requote_uri(query)}")
        return

    # Basic small talk
    if any(g in text for g in ['hello', 'hi', 'hey']):
        speak('Hello! How can I help you?')
        return
    if 'thank' in text:
        speak('You are welcome!')
        return

    # fallback
    speak("Sorry, I don't have a built-in action for that. I can search the web if you like. Say 'search' followed by your query.")

# -------------------- Main loop --------------------

def main_loop():
    speak('Assistant is starting. Say "assistant" or press Enter to speak.')
    print('--- Voice Assistant started ---')
    while True:
        # Simple wake-word approach: listen briefly for wake word OR user can press Enter
        print('\nPress Enter to speak or say the wake word... (say "quit" or "exit" to stop)')
        # spawn a short listener in background to catch wake word
        heard = ""
        try:
            # non-blocking: listen with short timeout to check wake word
            heard = listen(timeout=3, phrase_time_limit=3)
        except Exception:
            heard = ""

        if heard and any(w in heard for w in WAKE_WORDS):
            speak('Yes?')
            cmd = listen(timeout=5, phrase_time_limit=10)
            if cmd:
                if any(q in cmd for q in ['quit', 'exit', 'stop assistant']):
                    speak('Goodbye!')
                    break
                handle_command(cmd)
            else:
                speak('I did not hear anything.')
            continue

        # allow user to just press Enter to speak
        try:
            # wait for a short input — non-blocking with timeout using input()
            # If user presses Enter quickly, start a full listen
            _ = input()
            speak('Listening for your command.')
            cmd = listen(timeout=6, phrase_time_limit=12)
            if cmd:
                if any(q in cmd for q in ['quit', 'exit', 'stop assistant']):
                    speak('Goodbye!')
                    break
                handle_command(cmd)
            else:
                speak('I did not hear anything.')
        except KeyboardInterrupt:
            speak('Shutting down. Bye.')
            break

if __name__ == '__main__':
    main_loop()
