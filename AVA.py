import ollama
import speech_recognition as sr
import pyttsx3
import datetime
import time
import webbrowser
import pyautogui
import pyperclip
import threading
import queue
import sys
import os
import subprocess
import re
import json
import requests
import pywhatkit
from pathlib import Path
import winreg
from fuzzywuzzy import fuzz


command_queue = queue.Queue()
speech_queue = queue.Queue()
shutdown_flag = threading.Event()
is_speaking = threading.Event()



def speech_engine_worker():
    """Background thread for text-to-speech"""
    try:
        engine = pyttsx3.init('sapi5')
    except:
        engine = pyttsx3.init()
    
    engine.setProperty('rate', 170)
    voices = engine.getProperty('voices')
    if len(voices) > 1:
        engine.setProperty('voice', voices[1].id)
    
    while not shutdown_flag.is_set():
        try:
            text = speech_queue.get(timeout=1)
            
            if text.strip().startswith('{') or text.strip().startswith('['):
                speech_queue.task_done()
                continue
            
            is_speaking.set()
            print(f"\n🤖 AVA: {text}")
            
            try:
                engine.say(text)
                engine.runAndWait()
            except Exception as e:
                print(f"Speech error: {e}")
            finally:
                time.sleep(2.5)  
                is_speaking.clear()
                print("\n💬 Command (Type or Speak): ", end="", flush=True)
            
            speech_queue.task_done()
        except queue.Empty:
            continue
        except Exception as e:
            print(f"Speech engine error: {e}")
            is_speaking.clear()

def speak(text):
    """Queue text for speech output"""
    if text and isinstance(text, str):
        speech_queue.put(text)


def listen_voice_loop():
    """Background thread for voice recognition"""
    r = sr.Recognizer()
    r.energy_threshold = 400  
    r.dynamic_energy_threshold = True
    r.dynamic_energy_adjustment_damping = 0.15
    r.dynamic_energy_ratio = 1.5
    r.pause_threshold = 0.8  
    r.phrase_threshold = 0.3
    r.non_speaking_duration = 0.5
    
    try:
        with sr.Microphone() as source:
            print("🎤 Microphone initialized. Adjusting for ambient noise...")
            r.adjust_for_ambient_noise(source, duration=2)
            print("✅ Ready for voice commands!")
            
            while not shutdown_flag.is_set():
                
                if is_speaking.is_set(): 
                    time.sleep(1.5)
                    continue
                
              
                if not speech_queue.empty():
                    time.sleep(1.5)
                    continue
                
                
                time.sleep(0.5)
                
                try:
                    audio = r.listen(source, timeout=5, phrase_time_limit=10)
                    
                   
                    if is_speaking.is_set() or not speech_queue.empty():
                        continue
                    
                    try:
                        
                        query = r.recognize_google(audio, language='en-in', show_all=False)
                        if query:
                            query_lower = query.lower().strip()
                            
                            
                            ignore_phrases = [
                                "ava", "eva", "opening", "searching", "calculating", 
                                "checking", "playing", "the result is", "weather in",
                                "let me", "assistant", "application", "google chrome",
                                "i need", "valid", "whatsapp", "creating", "result",
                                "how can i assist", "online", "shutting down",
                                "chat g", "chat gpt", "browser", "music", "yes boss"
                            ]
                            
                            
                            ignore_count = sum(1 for phrase in ignore_phrases if phrase in query_lower)
                            if ignore_count >= 2:
                                continue
                            
                            
                            
                        
                            if query_lower.startswith(("opening", "searching", "checking", "playing", "calculating")):
                                continue
                            
                            print(f"\n🎙️  Heard: {query}")
                            command_queue.put(query)
                    except sr.UnknownValueError:
                        pass
                    except sr.RequestError as e:
                        print(f"Recognition service error: {e}")
                except sr.WaitTimeoutError:
                    pass
                except Exception as e:
                    print(f"Voice listening error: {e}")
                    time.sleep(1)
    except Exception as e:
        print(f"⚠️  Microphone not available: {e}")
        print("📝 Voice input disabled. Text input still available.")

def listen_text_loop():
    """Background thread for text input"""
    while not shutdown_flag.is_set():
        try:
            query = sys.stdin.readline().strip()
            if query:
                command_queue.put(query)
        except:
            break


def get_installed_apps():
    """Scan Windows registry and common locations for installed apps"""
    apps = {}
    
    registry_paths = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    ]
    
    for hkey, path in registry_paths:
        try:
            key = winreg.OpenKey(hkey, path)
            for i in range(winreg.QueryInfoKey(key)[0]):
                try:
                    subkey_name = winreg.EnumKey(key, i)
                    subkey = winreg.OpenKey(key, subkey_name)
                    try:
                        name = winreg.QueryValueEx(subkey, "DisplayName")[0]
                        try:
                            exe_path = winreg.QueryValueEx(subkey, "DisplayIcon")[0]
                            if not exe_path:
                                exe_path = winreg.QueryValueEx(subkey, "InstallLocation")[0]
                        except:
                            try:
                                exe_path = winreg.QueryValueEx(subkey, "InstallLocation")[0]
                            except:
                                exe_path = None
                        
                        if name and exe_path:
                            apps[name.lower()] = exe_path.split(',')[0].strip('"')
                    except:
                        pass
                    winreg.CloseKey(subkey)
                except:
                    pass
            winreg.CloseKey(key)
        except:
            pass
    
    common_paths = [
        Path(os.environ.get('ProgramFiles', 'C:\\Program Files')),
        Path(os.environ.get('ProgramFiles(x86)', 'C:\\Program Files (x86)')),
        Path.home() / 'AppData' / 'Local' / 'Programs',
    ]
    
    for base_path in common_paths:
        if base_path.exists():
            try:
                for item in base_path.iterdir():
                    if item.is_dir():
                        for exe in item.rglob('*.exe'):
                            if exe.is_file() and 'unins' not in exe.name.lower():
                                app_name = exe.stem.lower()
                                if app_name not in apps:
                                    apps[app_name] = str(exe)
            except:
                pass
    
    return apps

INSTALLED_APPS = {}

def find_app_path(app_name):
    """Find the executable path for an app using fuzzy matching"""
    app_name_lower = app_name.lower().strip()
    
    if app_name_lower in INSTALLED_APPS:
        return INSTALLED_APPS[app_name_lower]
    
    best_match = None
    best_score = 0
    
    for installed_name, exe_path in INSTALLED_APPS.items():
        score = fuzz.partial_ratio(app_name_lower, installed_name)
        if score > best_score and score > 70:
            best_score = score
            best_match = exe_path
    
    return best_match

def get_argument(arg_name, main_arg, kwargs):
    """Robust argument extraction"""
    if main_arg and main_arg != "None":
        return main_arg
    if arg_name in kwargs and kwargs[arg_name]:
        return kwargs[arg_name]
    for val in kwargs.values():
        if isinstance(val, str) and val and val != "None":
            return val
    return None

def open_website(url=None, **kwargs):
    """Open websites in browser"""
    target = get_argument('url', url, kwargs)
    
    if not target:
        return "I need a website name or URL to open."
    
    target_lower = target.lower().strip()
    
    website_map = {
        "youtube": "https://www.youtube.com",
        "google": "https://www.google.com",
        "gmail": "https://mail.google.com",
        "facebook": "https://www.facebook.com",
        "instagram": "https://www.instagram.com",
        "twitter": "https://www.twitter.com",
        "x": "https://www.x.com",
        "linkedin": "https://www.linkedin.com",
        "reddit": "https://www.reddit.com",
        "github": "https://www.github.com",
        "stackoverflow": "https://stackoverflow.com",
        "amazon": "https://www.amazon.in",
        "flipkart": "https://www.flipkart.com",
        "make my trip": "https://www.makemytrip.com",
        "makemytrip": "https://www.makemytrip.com",
        "booking": "https://www.booking.com",
        "netflix": "https://www.netflix.com",
        "hotstar": "https://www.hotstar.com",
        "prime video": "https://www.primevideo.com",
        "spotify": "https://www.spotify.com",
        "cricbuzz": "https://www.cricbuzz.com",
        "wikipedia": "https://www.wikipedia.org",
        "weather": "https://www.weather.com",
        "maps": "https://www.google.com/maps",
        "google maps": "https://www.google.com/maps",
        "drive": "https://drive.google.com",
        "google drive": "https://drive.google.com",
        "docs": "https://docs.google.com",
        "sheets": "https://sheets.google.com",
        "meet": "https://meet.google.com",
        "zoom": "https://zoom.us",
        "teams": "https://teams.microsoft.com"
    }
    
    for key, url_link in website_map.items():
        if key in target_lower or target_lower in key:
            webbrowser.open(url_link)
            return f"Opening {target}."
    
    if target.startswith("http://") or target.startswith("https://"):
        webbrowser.open(target)
        return f"Opening {target}."
    
    if "." not in target:
        url_link = f"https://www.{target}.com"
    else:
        url_link = f"https://{target}"
    
    webbrowser.open(url_link)
    return f"Opening {target}."

def open_application(app_name=None, **kwargs):
    """Open applications with smart name matching and app discovery"""
    target = get_argument('app_name', app_name, kwargs)
    
    if not target or "open_application" in target.lower() or "opening" in target.lower() or len(target) < 2:
        return "I need a valid app name to open."
        
    name = target.lower().strip()
    
    
    app_name_corrections = {
        "chat gpt": "chatgpt",
        "chat g p t": "chatgpt",
        "chatbot": "chatgpt",
        "perplexity": "perplexity",
        "perplex": "perplexity",
        "vs code": "vscode",
        "visual studio": "vscode",
        "google chrome": "chrome",
        "microsoft edge": "edge",
        "microsoft word": "word",
        "microsoft excel": "excel",
        "microsoft powerpoint": "powerpoint",
        "microsoft teams": "teams",
        "whats app": "whatsapp",
        "what's app": "whatsapp",
    }
    
    
    for variation, corrected in app_name_corrections.items():
        if variation in name:
            name = corrected
            break
    
    app_map = {
        "chrome": "start chrome",
        "google chrome": "start chrome",
        "browser": "start chrome",
        "chatgpt": ["start chatgpt:", r"C:\Users\%USERNAME%\AppData\Local\Programs\ChatGPT\ChatGPT.exe"],
        "chat gpt": ["start chatgpt:", r"C:\Users\%USERNAME%\AppData\Local\Programs\ChatGPT\ChatGPT.exe"],
        "perplexity": ["start perplexity:", r"C:\Users\%USERNAME%\AppData\Local\Programs\Perplexity\Perplexity.exe"],
        "whatsapp": "start whatsapp:",
        "notepad": "notepad.exe",
        "calculator": "calc.exe",
        "calc": "calc.exe",
        "paint": "mspaint.exe",
        "word": "start winword",
        "microsoft word": "start winword",
        "excel": "start excel",
        "microsoft excel": "start excel",
        "powerpoint": "start powerpnt",
        "microsoft powerpoint": "start powerpnt",
        "outlook": "start outlook",
        "microsoft outlook": "start outlook",
        "file explorer": "explorer.exe",
        "explorer": "explorer.exe",
        "cmd": "start cmd",
        "command prompt": "start cmd",
        "spotify": [r"C:\Users\%USERNAME%\AppData\Roaming\Spotify\Spotify.exe"],
        "discord": "start discord:",
        "vscode": "start code",
        "visual studio code": "start code",
        "edge": "start msedge",
        "microsoft edge": "start msedge",
        "teams": "start msteams:",
        "microsoft teams": "start msteams:",
        "telegram": "start telegram:",
        "slack": "start slack:",
        "zoom": "start zoom:",
        "obs": "start obs64:",
        "vlc": "start vlc:",
    }
    
    for key, command in app_map.items():
        if key == name or key in name or name in key:
            try:
                
                if isinstance(command, list):
                    opened = False
                    for cmd_or_path in command:
                       
                        if cmd_or_path.endswith('.exe'):
                            expanded_path = os.path.expandvars(cmd_or_path)
                            if os.path.exists(expanded_path):
                                subprocess.Popen(f'"{expanded_path}"', shell=True)
                                opened = True
                                break
                        
                        else:
                            try:
                                subprocess.Popen(cmd_or_path, shell=True)
                                opened = True
                                break
                            except:
                                continue
                    
                    if opened:
                        return f"Opening {target}."
                    
                    
                    try:
                        subprocess.Popen(f"start {target}", shell=True)
                        return f"Opening {target}."
                    except:
                        pass
                else:
                    subprocess.Popen(command, shell=True)
                    return f"Opening {target}."
            except Exception as e:
                pass
    
    
    try:
        result = subprocess.run(f"start {target}", shell=True, capture_output=True, timeout=3)
        if result.returncode == 0:
            return f"Opening {target}."
    except:
        pass
    
    
    app_path = find_app_path(name)
    if app_path and os.path.exists(app_path):
        try:
            subprocess.Popen(f'"{app_path}"', shell=True)
            return f"Opening {target}."
        except Exception as e:
            return f"Found {target} but failed to open: {str(e)}"
    
   
    try:
        subprocess.Popen(f"start {target}.exe", shell=True)
        return f"Opening {target}."
    except:
        pass
    
    return f"Could not find app: {target}. Make sure it's installed."

def get_weather(city=None, **kwargs):
    """Get weather information using multiple APIs with fallback"""
    target = get_argument('city', city, kwargs) or "London"
    target = target.strip()
    
    try:
        url = f"https://wttr.in/{target}?format=3"
        response = requests.get(url, timeout=10)
        if response.status_code == 200 and len(response.text.strip()) < 100:
            return f"{response.text.strip()}"
    except:
        pass
    
    try:
        url = f"https://wttr.in/{target}?format=%l:+%C+%t"
        response = requests.get(url, timeout=10)
        if response.status_code == 200 and len(response.text.strip()) < 100:
            return response.text.strip()
    except:
        pass
    
    try:
        url = f"http://wttr.in/{target}?format=3"
        response = requests.get(url, timeout=10)
        if response.status_code == 200 and len(response.text.strip()) < 100:
            return response.text.strip()
    except:
        pass
    
    return f"Unable to fetch current weather for {target}. Please try again or check your internet connection."

def search_web(query=None, **kwargs):
    """Search the web using DuckDuckGo and return instant answer"""
    target = get_argument('query', query, kwargs)
    
    if not target:
        return "I need a search query."
    
    
    if "perform_calculation" in target.lower() or "function" in target.lower():
        return "I encountered an error processing that request. Please try rephrasing."
    
    try:
        from duckduckgo_search import DDGS
        
        with DDGS() as ddgs:
            answer_results = list(ddgs.answers(target))
            if answer_results:
                answer = answer_results[0]
                if 'text' in answer:
                    return answer['text']
                elif 'answer' in answer:
                    return answer['answer']
            
            search_results = list(ddgs.text(target, max_results=3))
            if search_results:
                response = "Here's what I found:\n\n"
                for i, result in enumerate(search_results[:2], 1):
                    response += f"{result['title']}\n{result['body'][:200]}...\n\n"
                return response.strip()
        
        return "No results found for that query."
        
    except Exception as e:
        try:
            search_url = f"https://www.google.com/search?q={target.replace(' ', '+')}"
            webbrowser.open(search_url)
            return f"Opening browser to search for: {target}"
        except:
            return f"I couldn't search for that at the moment."

def answer_question(question=None, **kwargs):
    """Answer general knowledge questions using Ollama AI"""
    target = get_argument('question', question, kwargs)
    
    if not target:
        return "I need a question to answer."
    
    try:
        response = ollama.chat(
            model='llama3.2:1b',
            messages=[
                {
                    "role": "system",
                    "content": "You are AVA, a helpful AI assistant. Answer questions concisely and accurately in 2-3 sentences. Be factual and direct. Never mention your knowledge cutoff date or training data limitations. Just provide the answer naturally."
                },
                {
                    "role": "user",
                    "content": target
                }
            ]
        )
        
        answer = response['message']['content'].strip()
        
        
        cutoff_phrases = [
            "as of my knowledge cutoff",
            "as of my last update",
            "as of march 2023",
            "as of my training data",
            "my knowledge cutoff",
            "my training data",
            "last updated in",
            "as of my last training"
        ]
        
        answer_lower = answer.lower()
        for phrase in cutoff_phrases:
            if phrase in answer_lower:
                
                sentences = answer.split('.')
                filtered_sentences = [s for s in sentences if phrase not in s.lower()]
                answer = '.'.join(filtered_sentences).strip()
                if answer and not answer.endswith('.'):
                    answer += '.'
                break
        
        return answer
        
    except Exception as e:
        return f"I could not process that question: {str(e)}"

def perform_calculation(expression=None, **kwargs):
    """Perform mathematical calculations with enhanced support"""
    target = get_argument('expression', expression, kwargs)
    
    if not target:
        return "I need a math expression to calculate."
    
    expr = target.strip()
    original_expr = expr
    
    word_replacements = {
        ' plus ': '+',
        ' add ': '+',
        ' minus ': '-',
        ' subtract ': '-',
        ' times ': '*',
        ' multiplied by ': '*',
        ' multiply ': '*',
        ' into ': '*',
        ' divided by ': '/',
        ' divide ': '/',
        ' to the power of ': '**',
        ' power ': '**',
        ' percent': '/100',
        ' percentage': '/100',
        'square root of ': 'sqrt(',
        'sqrt ': 'sqrt(',
        ' x ': '*',
        ' X ': '*',
    }
    
    expr_lower = expr.lower()
    for word, symbol in word_replacements.items():
        expr_lower = expr_lower.replace(word, symbol)
    
    
    expr_lower = re.sub(r'(\d+)\s*[xX]\s*(\d+)', r'\1*\2', expr_lower)
    
    if re.search('[a-zA-Z]', expr_lower):
        cleaned = re.findall(r'[\d+\-*/().\s]+', expr_lower)
        if cleaned:
            expr = ''.join(cleaned).strip()
        else:
            return f"I couldn't understand the math expression: {original_expr}"
    else:
        expr = expr_lower
    
    if 'sqrt' in expr:
        expr = expr.replace('sqrt(', '(')
        if expr.count('(') > expr.count(')'):
            expr += ')' * (expr.count('(') - expr.count(')'))
        expr = f"({expr})**0.5"
    
    expr = expr.replace('x', '*').replace('÷', '/').replace('×', '*')
    expr = expr.replace(' ', '')
    
    if not expr or expr == '':
        return "I could not extract a valid math expression."
    
    try:
        import math
        allowed_names = {
            'abs': abs,
            'round': round,
            'min': min,
            'max': max,
            'sum': sum,
            'pow': pow,
            'sqrt': math.sqrt,
            'sin': math.sin,
            'cos': math.cos,
            'tan': math.tan,
            'log': math.log,
            'log10': math.log10,
            'pi': math.pi,
            'e': math.e
        }
        
        result = eval(expr, {"__builtins__": {}}, allowed_names)
        
        if isinstance(result, float):
            if result.is_integer():
                result = int(result)
            else:
                result = round(result, 6)
        
        return f"The result is: {result}"
        
    except ZeroDivisionError:
        return "Cannot divide by zero!"
    except Exception as e:
        return f"Could not calculate '{original_expr}'. Please check the expression."

def play_music(song_name=None, platform=None, **kwargs):
    """Play music on YouTube or Spotify"""
    target = get_argument('song_name', song_name, kwargs)
    platform_choice = get_argument('platform', platform, kwargs)
    
    if not target:
        return "I need a song name to play."
    
    try:
        if platform_choice and "spotify" in platform_choice.lower():
            search_url = f"spotify:search:{target.replace(' ', '%20')}"
            webbrowser.open(search_url)
            return f"Opening Spotify to play: {target}"
        else:
            pywhatkit.playonyt(target)
            return f"Playing {target} on YouTube."
    except Exception as e:
        search_url = f"https://www.youtube.com/results?search_query={target.replace(' ', '+')}"
        webbrowser.open(search_url)
        return f"Opening YouTube to search for: {target}"

def create_file(filename=None, content=None, **kwargs):
    """Create a new file with optional content"""
    target_name = get_argument('filename', filename, kwargs)
    target_content = get_argument('content', content, kwargs) or ""
    
    if not target_name:
        return "I need a filename to create."
    
    try:
        if '.' not in target_name:
            target_name += '.txt'
        
        desktop = Path.home() / "Desktop"
        if desktop.exists():
            filepath = desktop / target_name
        else:
            filepath = Path(target_name)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(target_content)
        
        return f"File created: {filepath.name}"
    except Exception as e:
        return f"Failed to create file: {str(e)}"

def send_whatsapp(name_or_number=None, message=None, **kwargs):
    """Send WhatsApp message (scheduled)"""
    target = get_argument('name_or_number', name_or_number, kwargs)
    msg = get_argument('message', message, kwargs) or "Hello!"
    
    if not target:
        return "I need a phone number to send a message."
    
    try:
        now = datetime.datetime.now()
        send_time = now + datetime.timedelta(minutes=2)
        
        if not target.startswith('+'):
            target = '+' + target
        
        pywhatkit.sendwhatmsg(target, msg, send_time.hour, send_time.minute)
        return f"WhatsApp message scheduled to {target} at {send_time.strftime('%H:%M')}"
    except Exception as e:
        return f"WhatsApp error: {str(e)}"

def get_time(**kwargs):
    """Get current time"""
    now = datetime.datetime.now()
    return f"The time is {now.strftime('%I:%M %p')}"

def get_date(**kwargs):
    """Get current date"""
    now = datetime.datetime.now()
    return f"Today is {now.strftime('%A, %B %d, %Y')}"


tools_schema = [
    {
        "type": "function",
        "function": {
            "name": "open_website",
            "description": "Open websites in browser (YouTube, MakeMyTrip, Facebook, etc.)",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Website name or URL to open"}
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "open_application",
            "description": "Open desktop applications like Chrome, WhatsApp, Notepad, Calculator, Spotify, etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "app_name": {"type": "string", "description": "Name of the application to open"}
                },
                "required": ["app_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get current weather information for a city",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "City name"}
                },
                "required": ["city"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "perform_calculation",
            "description": "Perform mathematical calculations",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {"type": "string", "description": "Math expression to calculate"}
                },
                "required": ["expression"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "answer_question",
            "description": "Answer general knowledge questions about facts, definitions, people, places, history, science, etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {"type": "string", "description": "The question to answer"}
                },
                "required": ["question"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": "Search the web for current information, news, or topics requiring real-time data",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "play_music",
            "description": "Play music on YouTube or Spotify",
            "parameters": {
                "type": "object",
                "properties": {
                    "song_name": {"type": "string", "description": "Song or artist name"},
                    "platform": {"type": "string", "description": "Platform: youtube or spotify"}
                },
                "required": ["song_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_file",
            "description": "Create a new file with optional content",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string", "description": "Name of the file to create"},
                    "content": {"type": "string", "description": "Content to write in the file"}
                },
                "required": ["filename"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "send_whatsapp",
            "description": "Send WhatsApp message",
            "parameters": {
                "type": "object",
                "properties": {
                    "name_or_number": {"type": "string", "description": "Phone number with country code"},
                    "message": {"type": "string", "description": "Message to send"}
                },
                "required": ["name_or_number", "message"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_time",
            "description": "Get current time",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_date",
            "description": "Get current date",
            "parameters": {"type": "object", "properties": {}}
        }
    }
]

def process_command(user_input):
    """Process user command through AI"""
    
    user_lower = user_input.lower().strip()
    
    
    if any(phrase in user_lower for phrase in ["hey ava", "hi ava", "hello ava", "hey eva", "hi eva"]):
        return "Yes boss!"
    
    
    if any(phrase in user_lower for phrase in ["what does ava stand for", "what is ava", "ava stands for", "meaning of ava"]):
        return "AVA stands for Advanced Virtual Assistant."
    
    if any(phrase in user_lower for phrase in ["who created you", "who made you", "your creator", "who is your creator", "who built you", "who developed you"]):
        return "I was created by Jatin Reddy."
    
    
    capability_phrases = ["what can you do", "what do you do", "your capabilities", "help me", 
                         "what are your features", "what can i ask", "how can you help"]
    if any(phrase in user_lower for phrase in capability_phrases):
        return ("I can help you with many things! I can open websites and applications, "
                "search the web, check weather, answer questions, play music, perform calculations, "
                "create files, tell you the time and date, and much more. Just ask me anything!")
    
    website_keywords = ["youtube", "facebook", "instagram", "twitter", "linkedin", "reddit", 
                       "github", "amazon", "flipkart", "netflix", "hotstar",
                       "makemytrip", "make my trip", "booking", "cricbuzz", "wikipedia",
                       "maps", "drive", "docs", "sheets", "meet", "zoom", ".com", ".in", ".org"]
    
    if user_lower.startswith("open "):
        target = user_input[5:].strip()
        
        if any(keyword in target.lower() for keyword in website_keywords):
            speak(f"Opening {target}...")
            return open_website(url=target)
        
        if target:
            speak(f"Opening {target}...")
            return open_application(app_name=target)
    
    if user_lower.startswith("play "):
        song = user_input[5:].strip()
        if song:
            speak("Playing music...")
            return play_music(song_name=song)
    
    if any(phrase in user_lower for phrase in ["what is", "who is", "what are", "who are", "tell me about", "explain", "define"]):
        realtime_keywords = ["current", "now", "today", "latest", "recent", "price", "stock", "news"]
        if not any(keyword in user_lower for keyword in realtime_keywords):
            speak("Let me answer that...")
            return answer_question(question=user_input)
    
    if user_lower.startswith("search ") or user_lower.startswith("google "):
        query = re.sub(r'(search|google)\s*', '', user_input, flags=re.IGNORECASE).strip()
        if query:
            speak("Searching...")
            return search_web(query=query)
    
    if "weather" in user_lower:
        city_match = re.search(r'weather (?:in |for |at |of )?([a-zA-Z\s]+)', user_input, re.IGNORECASE)
        city = city_match.group(1).strip() if city_match else "London"
        speak("Checking weather...")
        return get_weather(city=city)
    
    if any(word in user_lower for word in ["calculate", "what is", "what's", "compute"]) and any(char in user_input for char in "0123456789+-*/"):
        expr = re.sub(r'(calculate|what is|what\'s|compute)\s*', '', user_input, flags=re.IGNORECASE).strip()
        speak("Calculating...")
        return perform_calculation(expression=expr)
    
    if re.match(r'^[\d+\-*/().\s]+$', user_input):
        speak("Calculating...")
        return perform_calculation(expression=user_input)
    
    if "time" in user_lower and "what" in user_lower:
        return get_time()
    if "date" in user_lower and "what" in user_lower:
        return get_date()
    
    messages = [
        {
            "role": "system",
            "content": "You are AVA, an intelligent assistant. Use the available tools to help users. For general knowledge questions, use answer_question. For real-time info or news, use search_web. Always call the appropriate function. Be concise."
        },
        {
            "role": "user",
            "content": user_input
        }
    ]
    
    try:
        response = ollama.chat(
            model='llama3.2:1b',
            messages=messages,
            tools=tools_schema
        )
        
        content = response['message'].get('content', '')
        tool_calls = response['message'].get('tool_calls')

        if tool_calls:
            tool = tool_calls[0]
            func_name = tool['function']['name']
            func_args = tool['function']['arguments']
            
            if isinstance(func_args, str):
                try:
                    func_args = json.loads(func_args)
                except:
                    func_args = {}

            available_functions = {
                "get_weather": get_weather,
                "perform_calculation": perform_calculation,
                "search_web": search_web,
                "answer_question": answer_question,
                "play_music": play_music,
                "open_website": open_website,
                "open_application": open_application,
                "create_file": create_file,
                "send_whatsapp": send_whatsapp,
                "get_time": get_time,
                "get_date": get_date,
            }
            
            if func_name in available_functions:
                action_phrases = {
                    "open_website": f"Opening {func_args.get('url', 'website')}...",
                    "open_application": f"Opening {func_args.get('app_name', 'application')}...",
                    "search_web": "Searching the web...",
                    "answer_question": "Let me think...",
                    "get_weather": "Checking weather...",
                    "play_music": "Playing music...",
                    "create_file": "Creating file...",
                    "perform_calculation": "Calculating...",
                }
                
                if func_name in action_phrases:
                    speak(action_phrases[func_name])
                
                result = available_functions[func_name](**func_args)
                return str(result)
            else:
                return f"Function {func_name} not implemented."
        
        if content:
            return content
        else:
            return "I'm not sure how to help with that."

    except Exception as e:
        return f"Error processing command: {str(e)}"


def scan_apps_background():
    """Scan for installed apps in background"""
    global INSTALLED_APPS
    try:
        INSTALLED_APPS = get_installed_apps()
        print(f"\n✅ App scan complete: Found {len(INSTALLED_APPS)} applications")
    except Exception as e:
        print(f"\n⚠️  App scan error: {e}")

if __name__ == "__main__":
    os.system('cls' if os.name == 'nt' else 'clear')
    
    print("=" * 60)
    print("   🤖 A.V.A. - Advanced Virtual Assistant")
    print("=" * 60)
    print("\n✨ Initializing systems...\n")
    
    t_app_scan = threading.Thread(target=scan_apps_background, daemon=True)
    t_app_scan.start()
    
    t_speech = threading.Thread(target=speech_engine_worker, daemon=True)
    t_speech.start()
    
    speak("Hi Boss!. What are we working on today?")
    
    t_voice = threading.Thread(target=listen_voice_loop, daemon=True)
    t_voice.start()

    t_text = threading.Thread(target=listen_text_loop, daemon=True)
    t_text.start()

    print("\n📋 Available Commands:")
    print("  • Questions: 'what is [topic]' / 'who is [person]'")
    print("  • Websites: 'open youtube' / 'open makemytrip' / 'open netflix'")
    print("  • Search: 'search for [topic]'")
    print("  • Weather: 'weather in [city]'")
    print("  • Apps: 'open chrome' / 'open whatsapp' / 'open notepad'")
    print("  • Music: 'play [song name]'")
    print("  • Calculate: 'calculate [expression]'")
    print("  • Create File: 'create file [filename]'")
    print("  • Time/Date: 'what time is it' / 'what's the date'")
    print("  • Exit: 'shutdown' or 'exit'\n")
    print("=" * 60)
    print("\n💬 Command (Type or Speak): ", end="", flush=True)

    while True:
        try:
            query = command_queue.get(timeout=1)
            
           
            shutdown_commands = ["exit", "shutdown", "quit", "goodbye", "bye ava", "goodbye ava"]
            query_lower = query.lower().strip()
            
            if query_lower in shutdown_commands or query_lower == "bye":
                speak("Shutting down. Goodbye!")
                shutdown_flag.set()
                time.sleep(2)
                break
            
            reply = process_command(query)
            speak(reply)
            
        except queue.Empty:
            continue
        except KeyboardInterrupt:
            speak("Interrupted. Shutting down.")
            shutdown_flag.set()
            break
        except Exception as e:
            print(f"\nError in main loop: {e}")
            continue
    
    print("\n\n👋 AVA offline.")