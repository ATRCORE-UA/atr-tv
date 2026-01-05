import flet as ft
import os
import sys
import json
import time
import threading
import requests
import datetime
import copy
import random
import ctypes
import winreg
import subprocess # <--- ДОДАНО ДЛЯ ЗАПУСКУ АПДЕЙТЕРА

# === СИСТЕМА ОНОВЛЕНЬ: КОНФІГУРАЦІЯ ===
# Встав сюди посилання на свій JSON файл (npoint.io або GitHub Raw)
UPDATE_JSON_URL = "https://api.npoint.io/48f00b52f9ec94f921e3" 

# === ВАЖКА АРТИЛЕРІЯ: ФУНКЦІЯ ПРИМУСОВОЇ ІКОНКИ ===
def force_window_icon(window_title, icon_path):
    """
    Знаходить вікно за заголовком і силоміць змінює йому іконку через Windows API.
    """
    WM_SETICON = 0x80
    ICON_SMALL = 0
    ICON_BIG = 1
    LR_LOADFROMFILE = 0x10
    IMAGE_ICON = 1
    
    time.sleep(2.0)
    
    try:
        hwnd = ctypes.windll.user32.FindWindowW(None, window_title)
        if hwnd == 0: return

        if not os.path.exists(icon_path): return
            
        h_icon = ctypes.windll.user32.LoadImageW(
            None, icon_path, IMAGE_ICON, 0, 0, 
            LR_LOADFROMFILE | 0x00002000
        )
        
        if h_icon == 0: return

        ctypes.windll.user32.SendMessageW(hwnd, WM_SETICON, ICON_SMALL, h_icon)
        ctypes.windll.user32.SendMessageW(hwnd, WM_SETICON, ICON_BIG, h_icon)
        
        myappid = 'atrtv.player.force.final'
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        
    except: pass

try:
    app_id = 'atrtv.player'
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
except: pass

# === КОНФІГУРАЦІЯ ===
APP_VERSION_NUM = "v14.14" # <--- ВИНОСИМО НОМЕР ВЕРСІЇ ОКРЕМО
APP_VERSION = f"ATR-TV ({APP_VERSION_NUM} Hotfix)"
BG_COLOR = "#050505"
ACCENT_CYAN = "#00F0FF"
ACCENT_MAGENTA = "#BC13FE"
ACCENT_YELLOW = "#F1C40F"
TEXT_WHITE = "#ffffff"
TEXT_GRAY = "#aaaaaa"
ERROR_COLOR = "#ff4757"
SUCCESS_COLOR = "#2ed573"

BG_GLASS_DARK = "#99000000" 
BG_ACTIVE_ITEM = ft.LinearGradient(
    begin=ft.alignment.center_left,
    end=ft.alignment.center_right,
    colors=["#00F0FF", "#0048ff"],
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_FILE = os.path.join(BASE_DIR, "token.txt")
SETTINGS_FILE = os.path.join(BASE_DIR, "settings.json")
API_URL = "https://portal.ott.pink/playlist.m3u"

# === КЛАСИ ===
class Channel:
    def __init__(self, name, url, logo=""):
        self.name = name
        self.url = url
        self.logo = logo

class AppSettings:
    @staticmethod
    def load():
        default = {
            "volume": 100,
            "mode": "PC",
            "aspect_ratio": "16:9",
            "show_clock": True,
            "idle_enabled": True,
            "fullscreen": False,
            "first_run": True
        }
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, "r") as f:
                    default.update(json.load(f))
            except: pass
        return default

    @staticmethod
    def save(settings):
        try:
            with open(SETTINGS_FILE, "w") as f:
                json.dump(settings, f)
        except: pass

# === UI COMPONENTS ===
def get_logo(size=40):
    return ft.Row(
        [
            ft.Text("ATR", size=size, weight=ft.FontWeight.W_900, color="white", font_family="Arial Black"),
            ft.Text("-", size=size, weight=ft.FontWeight.BOLD, color=ACCENT_CYAN),
            ft.Text("TV", size=size, weight=ft.FontWeight.W_900, color=ACCENT_CYAN, font_family="Arial Black"),
        ],
        alignment=ft.MainAxisAlignment.CENTER,
        spacing=2
    )

# === ГОЛОВНА ФУНКЦІЯ ===
def main(page: ft.Page):
    page.title = APP_VERSION
    page.window_icon = "ico.ico" 
    page.bgcolor = BG_COLOR
    page.theme_mode = ft.ThemeMode.DARK
    page.padding = 0
    page.spacing = 0
    
    if getattr(sys, 'frozen', False):
        basedir = sys._MEIPASS
    else:
        basedir = os.path.dirname(os.path.abspath(__file__))
    icon_absolute_path = os.path.join(basedir, "assets", "ico.ico")
    threading.Thread(target=force_window_icon, args=(APP_VERSION, icon_absolute_path), daemon=True).start()

    page.theme = ft.Theme(color_scheme_seed=ACCENT_CYAN, visual_density="comfortable")

    real_settings = AppSettings.load()
    temp_settings = copy.deepcopy(real_settings)
    current_channels = []
    
    # === GLOBAL STATE ===
    state = {
        "playing_index": -1,
        "cursor_index": 0,
        "settings_focus_area": "list", 
        "settings_list_cursor": 0,      
        "view": "login", 
        "menu_open": False,
        "blob_animation_running": False,
        "guide_open": False,
        "guide_close_callback": None,
        "debug_clicks": 0
    }

    SETTINGS_OPTIONS = [
        {"key": "mode", "label": "Режим Інтерфейсу", "type": "select", "options": ["PC", "TV", "PHONE"]},
        {"key": "aspect_ratio", "label": "Формат відео", "type": "select", "options": ["16:9", "4:3", "Original"]},
        {"key": "show_clock", "label": "Годинник", "type": "bool"},
        {"key": "idle_enabled", "label": "Анімація очікування", "type": "bool"},
        {"key": "fullscreen", "label": "Режим відображення", "type": "action_toggle"},
        {"key": "provider", "label": "Провайдер", "type": "info", "value": "ATR-TV (Locked)"},
        {"key": "app_ver", "label": "Версія", "type": "ver", "value": "ATR-TV Player (" + APP_VERSION_NUM + ")"},
        {"key": "reset", "label": "СКИНУТИ НАЛАШТУВАННЯ", "type": "action_red"},
        {"key": "logout", "label": "ВИЙТИ З АКАУНТУ", "type": "action_red"}
    ]

    GUIDES = {
        "PC": {
            "title": "Режим ПК (Миша + Клавіатура)",
            "icon": ft.Icons.COMPUTER,
            "text": "• Використовуйте МИШУ для навігації.\n• Натисніть ENTER щоб відкрити список каналів.\n• F11 для повного екрану."
        },
        "TV": {
            "title": "Режим TV (Пульт / Клавіатура)",
            "icon": ft.Icons.TV,
            "text": "• Стрілки ВГОРУ/ВНИЗ: Вибір каналу.\n• ENTER: Відкрити меню / Вибрати.\n• Натисніть OK зараз, щоб перейти до каналів."
        },
        "PHONE": {
            "title": "Режим Телефону (Сенсор)",
            "icon": ft.Icons.SMARTPHONE,
            "text": "• Інтерфейс збільшено для пальців.\n• Використовуйте кнопки на екрані.\n• Свайпи не підтримуються, тисніть кнопки."
        }
    }
    
    # --- ЕЛЕМЕНТИ UI ---
    token_input = ft.TextField(
        label="Введіть ключ доступу", 
        password=True, 
        can_reveal_password=True,
        width=280, 
        bgcolor="#1A1A1A",
        border_color=ACCENT_CYAN, 
        color=TEXT_WHITE,
        border_radius=15,
        text_align=ft.TextAlign.CENTER,
        height=50,
        focused_border_color=ACCENT_CYAN,
        focused_border_width=2
    )
    
    login_loader = ft.ProgressBar(width=280, color=ACCENT_CYAN, bgcolor="#333", visible=False)

    # Створюємо змінну, але поки вона пуста (None)
    video_player = None
    
    buffering_indicator = ft.Container(
        content=ft.Column([
            ft.ProgressRing(width=60, height=60, stroke_width=5, color=ACCENT_CYAN),
            ft.Text("Завантаження...", color="white", weight="bold", size=14)
        ], alignment="center", horizontal_alignment="center", spacing=15),
        alignment=ft.alignment.center,
        bgcolor="#66000000", 
        visible=False, 
        expand=True
    )
    
    channel_list_col = ft.Column(scroll=ft.ScrollMode.HIDDEN, spacing=5)
    settings_list_col = ft.Column(scroll=ft.ScrollMode.AUTO, spacing=8, height=380)

    settings_save_btn = ft.Container(
        content=ft.Text("ЗБЕРЕГТИ", weight="bold", size=16),
        bgcolor=SUCCESS_COLOR,
        border_radius=10,
        padding=ft.padding.symmetric(vertical=12, horizontal=30),
        on_click=lambda e: None, 
        animate_scale=ft.animation.Animation(200, "bounceOut"),
    )
    
    settings_close_btn = ft.IconButton(ft.Icons.CLOSE, icon_color="white", icon_size=24)

    volume_indicator = ft.Container(
        padding=15, border_radius=15, 
        bgcolor="#CC000000", 
        border=ft.border.all(1, "white"),
        content=ft.Row([
            ft.Icon(ft.Icons.VOLUME_UP, color=ACCENT_CYAN),
            ft.Text("VOL: 100%", color="white", weight="bold", size=18)
        ], spacing=10),
        visible=False, top=30, right=30,
        animate_opacity=300
    )

    clock_text = ft.Text("00:00", size=24, weight="bold", color=TEXT_WHITE, font_family="Monospace")
    
    clock_container = ft.Container(
        content=clock_text, top=30, right=30, 
        visible=real_settings.get("show_clock", True),
        bgcolor=BG_GLASS_DARK,
        padding=ft.padding.symmetric(horizontal=15, vertical=5),
        border_radius=20,
    )

    # --- IDLE ANIMATION ---
    blob1 = ft.Container(
        width=600, height=600,
        border_radius=300,
        gradient=ft.RadialGradient(colors=["#4000F0FF", "transparent"], center=ft.alignment.center, radius=0.8),
        left=0, top=0, 
        animate_position=10000 
    )
    
    blob2 = ft.Container(
        width=500, height=500, 
        border_radius=250, 
        gradient=ft.RadialGradient(colors=["#30BC13FE", "transparent"], center=ft.alignment.center, radius=0.8),
        right=0, bottom=0, 
        animate_position=12000
    )
    
    blob3 = ft.Container(
        width=550, height=550, 
        border_radius=275, 
        gradient=ft.RadialGradient(colors=["#200048ff", "transparent"], center=ft.alignment.center, radius=0.8),
        left=100, bottom=100, 
        animate_position=15000
    )

    idle_bg_stack = ft.Stack([
        ft.Container(expand=True, bgcolor="#050505"), 
        blob1, blob2, blob3, 
        ft.Container(expand=True, bgcolor="#1A000000")
    ])

    idle_content = ft.Container(
        expand=True, alignment=ft.alignment.center,
        content=ft.Stack([
            idle_bg_stack,
            ft.Column([
                get_logo(80),
                ft.Text("NO SIGNAL / SELECT CHANNEL", size=16, weight="bold", color=TEXT_GRAY),
                ft.Container(height=20),
                ft.Container(
                    content=ft.Text("Натисніть ENTER щоб відкрити список", color="black", weight="bold"),
                    bgcolor=ACCENT_CYAN,
                    padding=10,
                    border_radius=5,
                    shadow=ft.BoxShadow(blur_radius=20, color=ACCENT_CYAN)
                )
            ], alignment="center", horizontal_alignment="center")
        ], alignment=ft.alignment.center)
    )
    
    main_stack = ft.Stack(expand=True)

    def animate_blobs_loop():
        while True:
            if not state.get("blob_animation_running", False):
                time.sleep(1)
                continue
            try:
                w = page.width if page.width > 0 else 800
                h = page.height if page.height > 0 else 600
                blob1.left = random.randint(-50, int(w/2))
                blob1.top = random.randint(-50, int(h/2))
                blob2.right = random.randint(-50, int(w/2))
                blob2.bottom = random.randint(-50, int(h/2))
                blob3.left = random.randint(0, int(w - 200))
                blob3.top = random.randint(0, int(h - 200))
                blob1.update()
                blob2.update()
                blob3.update()
            except: pass
            time.sleep(10.0)

    threading.Thread(target=animate_blobs_loop, daemon=True).start()

    # --- КНОПКИ HUD ---
    def show_hud_buttons():
        mode = real_settings.get("mode", "PC")
        
        def hud_btn_style(icon, func):
            return ft.Container(
                content=ft.Icon(icon, color="white", size=24),
                bgcolor=BG_GLASS_DARK,
                padding=10,
                border_radius=12,
                border=ft.border.all(1, "#33ffffff"),
                on_click=func,
                animate_scale=200,
                on_hover=lambda e: (
                    setattr(e.control, 'scale', 1.1 if e.data == "true" else 1.0) or 
                    setattr(e.control, 'border', ft.border.all(1, ACCENT_CYAN if e.data == "true" else "#33ffffff")) or 
                    e.control.update()
                )
            )

        menu_btn = hud_btn_style(ft.Icons.MENU_OPEN, lambda e: open_menu_safe())
        main_stack.controls.append(ft.Container(content=menu_btn, top=30, left=30))

        if mode != "TV":
            settings_btn = hud_btn_style(ft.Icons.TUNE, lambda e: show_settings_overlay())
            main_stack.controls.append(ft.Container(content=settings_btn, top=30, left=90))

        if mode == "PHONE":
            fs_btn = hud_btn_style(ft.Icons.FULLSCREEN, lambda e: toggle_fullscreen())
            main_stack.controls.append(ft.Container(content=fs_btn, bottom=30, right=30))

    # --- ГАЙД / TUTORIAL ---
    def show_guide(mode_key):
        info = GUIDES.get(mode_key, GUIDES["PC"])
        state["guide_open"] = True 
        guide_overlay_ref = None

        def close_guide(e=None):
            state["guide_open"] = False
            state["guide_close_callback"] = None
            if guide_overlay_ref and guide_overlay_ref in main_stack.controls:
                try: main_stack.controls.remove(guide_overlay_ref)
                except: pass
            if real_settings.get("first_run", False):
                real_settings["first_run"] = False
                AppSettings.save(real_settings)
            page.update()
            open_menu_safe()

        state["guide_close_callback"] = close_guide

        guide_overlay_ref = ft.Container(
            expand=True,
            bgcolor="#cc000000",
            alignment=ft.alignment.center,
            on_click=close_guide, 
            content=ft.Container(
                width=450,
                padding=35,
                bgcolor="#151515",
                border=ft.border.all(1, ACCENT_CYAN),
                border_radius=20,
                shadow=ft.BoxShadow(blur_radius=60, color="#4000F0FF"),
                on_click=lambda e: None,
                content=ft.Column([
                    ft.Icon(info["icon"], size=60, color=ACCENT_CYAN),
                    ft.Text(info["title"], size=22, weight="bold", color="white", text_align="center"),
                    ft.Divider(color="#333"),
                    ft.Text(info["text"], size=18, color=TEXT_GRAY, text_align="left"),
                    ft.Container(height=25),
                    ft.ElevatedButton(
                        "ЗРОЗУМІЛО (OK/ENTER)", 
                        width=250, 
                        height=45,
                        bgcolor=ACCENT_CYAN, 
                        color="black", 
                        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10)),
                        on_click=close_guide
                    )
                ], horizontal_alignment="center", tight=True)
            )
        )
        main_stack.controls.append(guide_overlay_ref)
        page.update()

    # --- REGISTRY LOGIC ---
    def register_protocol_handler():
        """Реєструє atrtv:// протокол."""
        try:
            key_path = r"Software\Classes\atrtv"
            
            if getattr(sys, 'frozen', False):
                exe_path = sys.executable
                cmd = f'"{exe_path}" "%1"'
            else:
                python_exe = sys.executable 
                script_path = os.path.abspath(sys.argv[0]) 
                cmd = f'"{python_exe}" "{script_path}" "%1"'

            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
                winreg.SetValue(key, "", winreg.REG_SZ, "ATR-TV Protocol")
                winreg.SetValueEx(key, "URL Protocol", 0, winreg.REG_SZ, "")
            
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path + r"\shell\open\command") as key:
                winreg.SetValue(key, "", winreg.REG_SZ, cmd)
                
            page.open(ft.SnackBar(ft.Text("Успіх! Протокол atrtv:// зареєстровано!", color="black"), bgcolor=SUCCESS_COLOR))
            
        except Exception as e:
            page.open(ft.SnackBar(ft.Text(f"Помилка реєстрації: {e}", color="white"), bgcolor=ERROR_COLOR))

    # --- НАЛАШТУВАННЯ ---
    def on_setting_click(e, idx):
        state["settings_list_cursor"] = idx
        opt = SETTINGS_OPTIONS[idx]
        
        if opt["key"] == "app_ver" and real_settings.get("mode") == "PC":
            state["debug_clicks"] += 1
            if state["debug_clicks"] >= 25:
                state["debug_clicks"] = 0
                register_protocol_handler()
            render_settings_menu()
            return

        if opt["type"] == "info" or opt["type"] == "ver":
            render_settings_menu()
            return

        mode = real_settings.get("mode")
        
        if mode == "TV":
            render_settings_menu() 
            activate_list_item_tv()
        else:
            if opt["type"] == "action_red" or opt["type"] == "action_toggle":
                activate_list_item_tv() 
            else:
                render_settings_menu()

    def render_settings_menu():
        settings_list_col.controls.clear()
        mode = temp_settings.get("mode", "PC")
        is_tv = (real_settings.get("mode") == "TV")
        
        if is_tv:
            if state["settings_focus_area"] == "top":
                settings_close_btn.icon_color = ERROR_COLOR
                settings_close_btn.scale = 1.2
            else:
                settings_close_btn.icon_color = "white"
                settings_close_btn.scale = 1.0

            if state["settings_focus_area"] == "bottom":
                settings_save_btn.bgcolor = ACCENT_YELLOW
                settings_save_btn.scale = 1.05
                settings_save_btn.content.color = "black"
            else:
                settings_save_btn.bgcolor = SUCCESS_COLOR
                settings_save_btn.scale = 1.0
                settings_save_btn.content.color = "white"
        
        for idx, opt in enumerate(SETTINGS_OPTIONS):
            is_focused = (is_tv and state["settings_focus_area"] == "list" and idx == state["settings_list_cursor"])
            
            if is_focused:
                bg_col = ACCENT_CYAN 
                text_col = "black"
                val_col = "black"
                border_c = ACCENT_CYAN
            else:
                bg_col = "#1Affffff"
                text_col = TEXT_WHITE
                val_col = ACCENT_CYAN
                border_c = "transparent"

            if opt["type"] == "action_red":
                if is_focused:
                    bg_col = ERROR_COLOR
                    text_col = "white"
                    border_c = ERROR_COLOR
                else:
                    bg_col = "#1Aff0000"
                    text_col = ERROR_COLOR

            key = opt.get("key")
            trailing = None
            
            if opt["type"] == "bool":
                val = temp_settings.get(key, False)
                if is_tv: 
                    trailing = ft.Text("ON" if val else "OFF", color=val_col, weight="bold")
                else:
                    trailing = ft.Switch(value=val, active_color=ACCENT_CYAN, on_change=lambda e, k=key: update_temp_setting(k, e.control.value))
            
            elif opt["type"] == "select":
                val = temp_settings.get(key, opt["options"][0])
                if is_tv:
                    trailing = ft.Row([
                        ft.Icon(ft.Icons.ARROW_LEFT, size=14, color=val_col if is_focused else "transparent"),
                        ft.Text(str(val), color=val_col, weight="bold"),
                        ft.Icon(ft.Icons.ARROW_RIGHT, size=14, color=val_col if is_focused else "transparent"),
                    ], spacing=5)
                else:
                    trailing = ft.Dropdown(
                        options=[ft.dropdown.Option(o) for o in opt["options"]],
                        value=val, width=140, text_size=13, height=35, content_padding=5,
                        bgcolor="#222222", border_color="#444444",
                        on_change=lambda e, k=key: update_temp_setting(k, e.control.value)
                    )
            
            elif opt["type"] == "action_toggle":
                val = page.window.full_screen
                txt_val = "Повний" if val else "Віконний"
                trailing = ft.Text(txt_val, color=val_col)
                if not is_tv: trailing = ft.ElevatedButton("Switch", bgcolor="#333", color="white", height=30, on_click=lambda e: toggle_fullscreen())

            elif opt["type"] == "info":
                my_color = "#A9A9A9" 
                trailing = ft.Text(str(opt["value"]), color=val_col if is_focused else my_color, size=12, weight="bold")
            elif opt["type"] == "ver":
                my_color = "accent-magenta" 
                trailing = ft.Text(str(opt["value"]), color=val_col if is_focused else my_color, size=12, weight="bold")
            elif opt["type"] == "action_red":
                icon = ft.Icons.DELETE_FOREVER if key == "reset" else ft.Icons.LOGOUT
                trailing = ft.Icon(icon, color=text_col, size=20)

            row_key = f"setting_{idx}"
            row = ft.Container(
                key=row_key,
                padding=ft.padding.symmetric(horizontal=15, vertical=12),
                border_radius=10,
                bgcolor=bg_col,
                border=ft.border.all(1 if is_focused else 0, border_c),
                animate=ft.animation.Animation(150, "easeOut"),
                on_click=lambda e, i=idx: on_setting_click(e, i),
                content=ft.Row([
                    ft.Text(opt["label"], color=text_col, size=15, weight="bold" if is_focused else "w500"),
                    ft.Container(expand=True),
                    trailing if trailing else ft.Container()
                ], alignment="spaceBetween"),
            )
            settings_list_col.controls.append(row)
        
        page.update()

    def update_temp_setting(key, value):
        temp_settings[key] = value
        if key == "idle_enabled":
            page.open(ft.SnackBar(ft.Text("Для застосування анімації потрібен перезапуск програми", color="black"), bgcolor=ACCENT_YELLOW))
        render_settings_menu()

    def apply_settings_now():
        nonlocal real_settings
        old_mode = real_settings.get("mode")
        real_settings = copy.deepcopy(temp_settings)
        AppSettings.save(real_settings)
        
        try:
            ar = 16/9
            if real_settings["aspect_ratio"] == "4:3": ar = 4/3
            elif real_settings["aspect_ratio"] == "Original": ar = -1
            video_player.aspect_ratio = ar
            video_player.update()
        except: pass
        
        clock_container.visible = real_settings["show_clock"]
        close_settings()
        
        page.open(ft.SnackBar(ft.Text("Налаштування збережено!", color="black"), bgcolor=SUCCESS_COLOR))
        
        if state["playing_index"] != -1:
            render_channel_list()
            show_hud_buttons()
        
        if old_mode != real_settings["mode"]:
             show_guide(real_settings["mode"])

        page.update()

    def toggle_fullscreen():
        page.window.full_screen = not page.window.full_screen
        page.update()
        if state["view"] == "settings":
            render_settings_menu()

    def show_settings_overlay():
        nonlocal temp_settings
        temp_settings = copy.deepcopy(real_settings)
        state["view"] = "settings"
        close_menu_safe()
        
        state["settings_focus_area"] = "list"
        state["settings_list_cursor"] = 0
        state["debug_clicks"] = 0
        
        settings_save_btn.on_click = lambda e: apply_settings_now()
        settings_close_btn.on_click = lambda e: close_settings()
        
        overlay = ft.Container(
            expand=True, 
            bgcolor=BG_GLASS_DARK,
            alignment=ft.alignment.center,
            padding=20,
            on_click=lambda e: None,
            content=ft.Container(
                width=550, height=650, 
                border_radius=20, 
                padding=25,
                bgcolor="#121212",
                border=ft.border.all(1, "#333333"),
                shadow=ft.BoxShadow(blur_radius=50, color="#1A00F0FF"),
                content=ft.Column([
                    ft.Row([
                        ft.Text("Налаштування", size=20, weight="bold", color="white", font_family="Arial Black"),
                        ft.Container(expand=True),
                        settings_close_btn
                    ]),
                    ft.Divider(color="#333"),
                    ft.Container(content=settings_list_col, expand=True),
                    ft.Divider(color="#333"),
                    ft.Container(content=settings_save_btn, alignment=ft.alignment.center, padding=10)
                ])
            )
        )
        main_stack.controls.append(overlay)
        render_settings_menu()
        page.update()

    def close_settings():
        state["view"] = "player"
        if len(main_stack.controls) > 0: 
            try: main_stack.controls.pop()
            except: pass
        page.update()

    def reset_settings_full():
        def close_dialog(e):
            page.close(dlg)

        def confirm_reset(e):
            try: os.remove(SETTINGS_FILE)
            except: pass
            
            try: os.remove(TOKEN_FILE)
            except: pass
            
            page.window.close() 

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Скидання налаштувань"),
            content=ft.Text("Ви впевнені? Програму буде закрито, дані та вхід скинуто."),
            actions=[
                ft.TextButton("Ні (Cancel)", on_click=close_dialog),
                ft.TextButton("ТАК (Reset & Exit)", on_click=confirm_reset, style=ft.ButtonStyle(color=ERROR_COLOR)),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        page.open(dlg)

    def handle_settings_navigation(key):
        if real_settings["mode"] != "TV": return

        area = state["settings_focus_area"]
        cursor = state["settings_list_cursor"]
        max_items = len(SETTINGS_OPTIONS) - 1

        if key == "Arrow Down":
            if area == "top":
                state["settings_focus_area"] = "list"
                state["settings_list_cursor"] = 0
            elif area == "list":
                if cursor < max_items:
                    state["settings_list_cursor"] += 1
                    try: settings_list_col.scroll_to(key=f"setting_{state['settings_list_cursor']}", duration=300)
                    except: pass
                else:
                    state["settings_focus_area"] = "bottom"
            elif area == "bottom": pass

        elif key == "Arrow Up":
            if area == "bottom":
                state["settings_focus_area"] = "list"
                state["settings_list_cursor"] = max_items
                try: settings_list_col.scroll_to(key=f"setting_{max_items}", duration=300)
                except: pass
            elif area == "list":
                if cursor > 0:
                    state["settings_list_cursor"] -= 1
                    try: settings_list_col.scroll_to(key=f"setting_{state['settings_list_cursor']}", duration=300)
                    except: pass
                else:
                    state["settings_focus_area"] = "top"
            elif area == "top": pass

        elif key == "Enter" or key == "Select":
            if area == "bottom": apply_settings_now()
            elif area == "top": close_settings()
            elif area == "list": activate_list_item_tv()

        elif key == "Arrow Right" or key == "Arrow Left":
            if area == "list":
                direction = 1 if key == "Arrow Right" else -1
                modify_list_item_tv(direction)

        render_settings_menu()

    def modify_list_item_tv(direction):
        idx = state["settings_list_cursor"]
        opt = SETTINGS_OPTIONS[idx]
        key = opt.get("key")
        
        if opt["type"] == "bool":
            curr = temp_settings.get(key, False)
            update_temp_setting(key, not curr)
        elif opt["type"] == "select":
            options = opt["options"]
            curr_val = temp_settings.get(key, options[0])
            try: curr_idx = options.index(curr_val)
            except: curr_idx = 0
            new_idx = (curr_idx + direction) % len(options)
            update_temp_setting(key, options[new_idx])

    def activate_list_item_tv():
        idx = state["settings_list_cursor"]
        opt = SETTINGS_OPTIONS[idx]
        
        if opt["type"] == "action_red": 
            if opt["key"] == "reset":
                reset_settings_full()
            else:
                close_settings()
                logout_full()
        elif opt["type"] == "action_toggle": 
            toggle_fullscreen()
        elif opt["type"] == "bool": 
            modify_list_item_tv(1)
        elif opt["type"] == "select":
            modify_list_item_tv(1)

    # --- ЛОГІКА ПЛЕЄРА ТА КАНАЛІВ ---
    
    def render_channel_list():
        channel_list_col.controls.clear()
        mode = real_settings.get("mode", "PC")
        is_phone = (mode == "PHONE")
        is_tv = (mode == "TV")

        for idx, ch in enumerate(current_channels):
            is_playing = (idx == state["playing_index"])
            is_cursor = (idx == state["cursor_index"]) and is_tv
            
            bg = "transparent"
            content_color = "white"
            gradient = None
            border = ft.border.all(1, "transparent")
            scale = 1.0
            
            if is_playing:
                gradient = BG_ACTIVE_ITEM 
                
            if is_cursor: 
                if not is_playing:
                    bg = "#33ffffff"
                border = ft.border.all(1, ACCENT_CYAN)
                scale = 1.02
            
            if ch.logo and len(ch.logo) > 5:
                leading_content = ft.Image(src=ch.logo, fit=ft.ImageFit.CONTAIN, error_content=ft.Icon(ft.Icons.BROKEN_IMAGE, size=14, color=ACCENT_CYAN))
                leading_bg = "white" 
            else:
                leading_content = ft.Text(ch.name[0] if ch.name else "?", size=14, weight="bold", color=ACCENT_CYAN if not is_playing else "white")
                leading_bg = "#222" if not is_playing else "transparent"

            leading_icon = ft.Container(
                content=leading_content,
                width=40, height=35, 
                bgcolor=leading_bg, 
                border_radius=5, 
                alignment=ft.alignment.center,
                padding=2
            )

            btn = ft.Container(
                key=f"ch_{idx}",
                padding=ft.padding.only(left=10, right=10, top=12, bottom=12),
                border_radius=10,
                bgcolor=bg,
                gradient=gradient,
                border=border,
                scale=scale,
                animate_scale=ft.animation.Animation(150, "easeOut"),
                on_click=lambda e, i=idx: click_play(i),
                content=ft.Row([
                    leading_icon,
                    ft.Text(ch.name, color=content_color, weight="bold" if is_playing else "normal", size=15, no_wrap=True, overflow=ft.TextOverflow.ELLIPSIS, expand=True),
                    ft.Icon(ft.Icons.EQUALIZER if is_playing else None, color="white" if is_playing else ACCENT_CYAN, size=16)
                ])
            )
            channel_list_col.controls.append(btn)
        
        channel_list_col.controls.append(ft.Container(height=50))
        page.update()

    def click_play(index):
        state["cursor_index"] = index
        play_channel(index)

    def play_channel(index):
        nonlocal video_player # Щоб ми могли записати сюди новий плеєр
        
        if not current_channels: return
        
        # Якщо канал вже грає - просто закриваємо меню
        if index == state["playing_index"] and video_player is not None:
            close_menu_safe()
            return
        
        state["playing_index"] = index
        ch = current_channels[index]
        
        # 1. Очищаємо екран
        main_stack.controls.clear()
        
        # 2. Показуємо лоадер (поки плеєр вантажиться)
        buffering_indicator.visible = True
        main_stack.controls.append(buffering_indicator)
        main_stack.controls.append(clock_container)
        
        # 3. СТВОРЮЄМО НОВИЙ ПЛЕЄР "З НУЛЯ" (Це вирішує проблему чорного екрану)
        # Беремо налаштування гучності та формату
        vol = real_settings.get("volume", 100)
        ar = 16/9
        if real_settings.get("aspect_ratio") == "4:3": ar = 4/3
        elif real_settings.get("aspect_ratio") == "Original": ar = -1

        video_player = ft.Video(
            expand=True,
            playlist_mode=ft.PlaylistMode.SINGLE,
            fill_color="black",
            aspect_ratio=ar,
            autoplay=True, # ВАЖЛИВО: автозапуск увімкнено при створенні
            volume=vol,
            show_controls=False,
            playlist=[ft.VideoMedia(ch.url)], # Одразу даємо лінк!
            on_loaded=lambda e: print("Video Loaded!") # Можна прибрати, для тесту
        )

        # 4. Додаємо плеєр на екран (він опиниться під лоадером)
        # Використовуємо контейнер для центрування
        player_container = ft.Container(
            content=video_player, 
            bgcolor="black", 
            alignment=ft.alignment.center
        )
        
        # Вставляємо плеєр на початок списку (індекс 0), щоб він був фоном, а лоадер зверху
        main_stack.controls.insert(0, player_container)
        main_stack.controls.append(volume_indicator)
        
        state["blob_animation_running"] = False
        show_hud_buttons()
        close_menu_safe()
        render_channel_list()
        page.update()

        # 5. Функція для приховування лоадера
        def hide_loader():
            time.sleep(4) # Даємо 2.5 секунди на буферизацію
            buffering_indicator.visible = False
            try: page.update()
            except: pass

        threading.Thread(target=hide_loader, daemon=True).start()
        
        page.open(ft.SnackBar(ft.Text(f"Відтворюється: {ch.name}", color=TEXT_WHITE), bgcolor="#222"))
        
    def open_menu_safe():
        state["menu_open"] = True
        if page.drawer: page.drawer.open = True
        if state["playing_index"] != -1:
            state["cursor_index"] = state["playing_index"]
            try: channel_list_col.scroll_to(key=f"ch_{state['cursor_index']}", duration=100)
            except: pass
        render_channel_list()
        page.update()

    def close_menu_safe():
        state["menu_open"] = False
        if page.drawer: page.drawer.open = False
        page.update()

    # --- КЛАВІАТУРА ---
    def on_keyboard(e: ft.KeyboardEvent):
        if state["view"] == "settings":
            handle_settings_navigation(e.key)
            return

        if state.get("guide_open", False):
            if e.key in ["Enter", "Select", "Escape", "Back", "Space"]:
                if state["guide_close_callback"]:
                    state["guide_close_callback"]()
            return

        menu_visible = state["menu_open"] or (page.drawer and page.drawer.open)
        
        if menu_visible:
            if e.key == "Escape" or e.key == "Back":
                close_menu_safe()
                return

            if e.key == "Arrow Down":
                state["cursor_index"] = (state["cursor_index"] + 1) % len(current_channels)
                render_channel_list()
                try: channel_list_col.scroll_to(key=f"ch_{state['cursor_index']}", duration=100)
                except: pass
            elif e.key == "Arrow Up":
                state["cursor_index"] = (state["cursor_index"] - 1) % len(current_channels)
                render_channel_list()
                try: channel_list_col.scroll_to(key=f"ch_{state['cursor_index']}", duration=100)
                except: pass
            elif e.key == "Enter" or e.key == "Select":
                play_channel(state["cursor_index"])
            elif e.key == "Arrow Right" or e.key == "Arrow Left":
                close_menu_safe()
        
        else:
            if e.key == "Escape" or e.key == "Back" or e.key == "Menu":
                show_settings_overlay()
                return
            
            if e.key == "Enter" or e.key == "Select":
                open_menu_safe()
                
            elif e.key == "Arrow Up":
                if current_channels:
                    idx = (state["playing_index"] - 1) % len(current_channels)
                    play_channel(idx)
                    
            elif e.key == "Arrow Down":
                if current_channels:
                    idx = (state["playing_index"] + 1) % len(current_channels)
                    play_channel(idx)
                    
            elif e.key == "Arrow Right": change_volume(+5)
            elif e.key == "Arrow Left": change_volume(-5)
            elif e.key == "F11": toggle_fullscreen()

    page.on_keyboard_event = on_keyboard

    # --- СИСТЕМНІ ФУНКЦІЇ ---
    def change_volume(delta):
        vol = real_settings.get("volume", 100)
        vol = max(0, min(100, vol + delta))
        real_settings["volume"] = vol
        AppSettings.save(real_settings)
        
        # ДОДАЙ ЦЮ ПЕРЕВІРКУ:
        if video_player is not None:
            try:
                video_player.volume = vol
                video_player.update()
            except: pass

        volume_indicator.content.controls[1].value = f"VOL: {vol}%"
        volume_indicator.visible = True
        page.update()
        def hide():
            time.sleep(2)
            volume_indicator.visible = False
            try: page.update()
            except: pass
        threading.Thread(target=hide, daemon=True).start()

    def logout_full():
        try: os.remove(TOKEN_FILE)
        except: pass
        state["view"] = "login"
        close_settings()
        show_login_ui()

    def parse_m3u(text):
        channels = []
        lines = text.split('\n')
        name = "Unknown"
        logo = ""
        if not text or "#EXT" not in text:
            return []
        for line in lines:
            line = line.strip()
            if not line: continue 
            
            if line.startswith("#EXTINF"):
                if 'tvg-logo="' in line:
                    try: logo = line.split('tvg-logo="')[1].split('"')[0]
                    except: pass
                name = line.split(',')[-1].strip()
            elif line and not line.startswith("#") and len(line) > 5:
                channels.append(Channel(name, line, logo))
                name = "Unknown"
                logo = ""
        return channels if channels else parse_m3u("")

    def load_channels_thread(token):
        nonlocal current_channels
        try:
            url = f"{API_URL}?token={token}"
            resp = requests.get(url, headers={"User-Agent": "ATR-TV"}, timeout=8)
            current_channels = parse_m3u(resp.text) if resp.status_code == 200 else parse_m3u("")
        except: current_channels = parse_m3u("")
        with open(TOKEN_FILE, "w") as f: f.write(token)
        show_player_ui()

    # --- ЕКРАНИ ---
    def show_splash_screen(next_action):
        page.clean()
        page.add(
            ft.Container(
                expand=True, 
                gradient=ft.LinearGradient(
                    begin=ft.alignment.top_left,
                    end=ft.alignment.bottom_right,
                    colors=["#0f0c29", "#302b63", "#24243e"]
                ),
                alignment=ft.alignment.center, 
                content=ft.Column([
                    get_logo(60),
                    ft.Container(height=20),
                    ft.ProgressBar(width=200, color=ACCENT_CYAN, bgcolor="#333")
                ], 
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER 
                )
            )
        )
        def _boot():
            time.sleep(1.5)
            next_action()
        threading.Thread(target=_boot, daemon=True).start()

    def show_login_ui():
        page.clean()
        state["view"] = "login"
        token_input.value = ""
        token_input.disabled = False
        login_loader.visible = False
        
        def on_click_login(e):
            t = token_input.value.strip().replace("atrtv://", "").rstrip("/")
            if not t: 
                token_input.border_color = ERROR_COLOR
                token_input.update()
                return
            token_input.disabled = True
            login_loader.visible = True
            page.update()
            threading.Thread(target=load_channels_thread, args=(t,), daemon=True).start()
            
        page.add(
            ft.Container(
                expand=True, 
                gradient=ft.LinearGradient(
                    begin=ft.alignment.top_left,
                    end=ft.alignment.bottom_right,
                    colors=["#000428", "#004e92"]
                ),
                alignment=ft.alignment.center, 
                content=ft.Column([
                    ft.Container(
                        width=400,
                        padding=40,
                        border_radius=20,
                        bgcolor=BG_GLASS_DARK,
                        border=ft.border.all(1, "#1Affffff"),
                        shadow=ft.BoxShadow(blur_radius=30, color="black"),
                        content=ft.Column([
                            get_logo(50),
                            ft.Text("Secure Login", color=TEXT_GRAY, size=12),
                            ft.Container(height=10),
                            token_input,
                            login_loader,
                            ft.Container(height=10),
                            ft.ElevatedButton(
                                content=ft.Text("ПІДКЛЮЧИТИСЯ", size=16, weight="bold"),
                                style=ft.ButtonStyle(
                                    color="black",
                                    bgcolor=ACCENT_CYAN,
                                    shape=ft.RoundedRectangleBorder(radius=10),
                                    elevation=10
                                ),
                                width=280, 
                                height=50,
                                on_click=on_click_login
                            )
                        ], horizontal_alignment="center", spacing=10)
                    )
                ], alignment="center")
            )
        )
        page.update()

    def show_player_ui():
        page.clean()
        state["view"] = "player"
        
        page.drawer = ft.NavigationDrawer(
            bgcolor="#09090b",
            elevation=0,
            controls=[
                ft.Container(
                    height=80, 
                    alignment=ft.alignment.center_left, 
                    padding=ft.padding.only(left=20),
                    gradient=ft.LinearGradient(colors=["#000000", "#111111"]),
                    content=get_logo(24)
                ),
                ft.Divider(color="#222", thickness=1, height=1),
                ft.Container(
                    content=channel_list_col, 
                    expand=True,
                    padding=10
                )
            ]
        )
        main_stack.controls.clear()
        
        if state["playing_index"] == -1:
            state["blob_animation_running"] = True
            if real_settings.get("idle_enabled", True):
                main_stack.controls.append(idle_content)
            else:
                main_stack.controls.append(ft.Container(bgcolor="black", expand=True, alignment=ft.alignment.center, content=get_logo(30)))
        else:
             main_stack.controls.append(idle_content)

        show_hud_buttons()
        page.add(main_stack)
        render_channel_list()
        
        if real_settings.get("first_run", True):
             show_guide(real_settings["mode"])
        else:
             if real_settings["mode"] != "TV":
                 open_menu_safe()

        page.update()

    def clock_updater():
        while True:
            now = datetime.datetime.now().strftime("%H:%M")
            clock_text.value = now
            try: page.update()
            except: pass
            time.sleep(5)
            
    threading.Thread(target=clock_updater, daemon=True).start()

    # === UPDATE LOGIC ===
    def check_for_updates():
        try:
            # Анти-кеш параметр
            url_no_cache = f"{UPDATE_JSON_URL}?t={int(time.time())}"
            r = requests.get(url_no_cache, timeout=5)
            if r.status_code != 200: return
            
            data = r.json()
            remote_ver = data.get("version", "v0.0")
            download_url = data.get("url", "")
            notes = data.get("notes", "Оновлення системи")
            
            # Якщо версії різні
            if remote_ver != APP_VERSION_NUM:
                
                def close_dlg(e):
                    page.close(dlg)
                
                def start_updater(e):
                    page.close(dlg)
                    # Визначаємо поточний файл
                    if getattr(sys, 'frozen', False):
                        current_file = sys.executable
                    else:
                        current_file = os.path.abspath(sys.argv[0])
                        
                    # Запускаємо flet-u.py
                    # Аргументи: [url] [файл_який_замінити]
                    updater_script = os.path.join(basedir, "flet-u.py")
                    
                    if os.path.exists(updater_script):
                        subprocess.Popen([sys.executable, updater_script, download_url, current_file])
                        page.window_close() # Закриваємо себе
                    else:
                        page.open(ft.SnackBar(ft.Text("Помилка: flet-u.py не знайдено!", color="white"), bgcolor=ERROR_COLOR))

                dlg = ft.AlertDialog(
                    modal=True,
                    title=ft.Text("🚀 ОНОВЛЕННЯ СИСТЕМИ"),
                    content=ft.Column([
                        ft.Text(f"Доступна версія: {remote_ver}", size=20, weight="bold", color=ACCENT_CYAN),
                        ft.Divider(color="#333"),
                        ft.Text(notes, size=13, color=TEXT_GRAY),
                    ], tight=True, width=400),
                    actions=[
                        ft.TextButton("Пізніше", on_click=close_dlg),
                        ft.ElevatedButton("ОНОВИТИ ЗАРАЗ", on_click=start_updater, bgcolor=ACCENT_CYAN, color="black"),
                    ],
                    actions_alignment=ft.MainAxisAlignment.END,
                )
                page.open(dlg)
                
        except Exception as e:
            print(f"Upd check error: {e}")

    def init_app():
        # Запускаємо перевірку оновлень у фоні, але через thread, 
        # який викличе діалог у головному потоці (через page.open це безпечно у нових версіях Flet)
        # Але краще викликати трохи пізніше
        
        launch_token = None
        if len(sys.argv) > 1:
            arg = sys.argv[1]
            if "atrtv://" in arg:
                launch_token = arg.replace("atrtv://", "").rstrip("/")
                try:
                    with open(TOKEN_FILE, "w") as f: f.write(launch_token)
                except: pass

        if not launch_token and os.path.exists(TOKEN_FILE):
             try: launch_token = open(TOKEN_FILE).read().strip()
             except: pass
             
        if launch_token: 
            threading.Thread(target=load_channels_thread, args=(launch_token,), daemon=True).start()
        else: 
            show_login_ui()
            
        # Запуск перевірки оновлення з затримкою
        def run_upd_check():
            time.sleep(3)
            check_for_updates()
        threading.Thread(target=run_upd_check, daemon=True).start()

    show_splash_screen(init_app)

if __name__ == "__main__":
    if getattr(sys, 'frozen', False):
        basedir = sys._MEIPASS
    else:
        basedir = os.path.dirname(os.path.abspath(__file__))

    assets_path = os.path.join(basedir, "assets")
    

    ft.app(target=main, assets_dir=assets_path)

