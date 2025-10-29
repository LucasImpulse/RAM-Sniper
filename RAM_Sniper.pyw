from math import e
import psutil
import threading
import queue
import os
from timeit import timeit
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import operator
import sys

try:
    import playsound3 as playsound
    import pystray
    from PIL import Image, ImageDraw
except ImportError:
    print("Required modules not found. Please install 'playsound3', 'pystray', and 'Pillow' packages.")
    sys.exit(1)

# RAM Sniper
# Designate sacrificial process, when RAM reaches threshold (my default is 95%), this process will be "sniped".
# User chooses which process to snipe.
# Layman is not expected to provide PID, need to give a list of running processes to choose from.
# When process is sniped, play a sound (default is AWP shot sound).

def get_cpu_usage():
    print(psutil.cpu_percent())

def get_ram_usage():
    print(psutil.virtual_memory().percent)

def test_hundred_times(method):
    return timeit(method, number=100, globals=globals())

class RamSniper:
    def __init__(self, root):
        self.root = root
        self.root.title("RAM Sniper")
        self.root.geometry("600x600")
        self.root.resizable(False, False)
        self.root.configure(bg="#2e2e2e")
        self.font = ("Arial", 12)

        self.target_pid = None
        self.target_name = None

        self.monitoring_enabled = False
        self.threshold_var = tk.IntVar(value=95)

        self.custom_sound_path = "https://www.myinstants.com/media/sounds/190-awp.mp3"

        # thread gaming
        self.data_queue = queue.Queue()
        self.refresh_in_progress = False

        # this or it will throw error because i define tree later but call filter_list down there first which mandates a tree.
        self.tree_initialized = False

        self.master_process_list = []

        self.sort_by_col = 'ram_mb'
        self.sort_reverse = True

        self.search_placeholder = "Search process list..."

        self.style = ttk.Style(self.root)

        # ALL UI HANDLING BELOW

        # -- widgets --

        # search bar
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", self.filter_list)

        self.search_entry = tk.Entry(root,
                                    textvariable=self.search_var,
                                    font=("Helvetica", 10),
                                    borderwidth=0,
                                    highlightthickness=1)

        self.search_entry.bind("<FocusIn>", self.on_search_focus_in)
        self.search_entry.bind("<FocusOut>", self.on_search_focus_out)
        self.set_search_placeholder()

        # refresher
        self.refresh_btn = tk.Button(root, 
                                     text="Refresh", 
                                     command=self.start_refresh_thread,
                                     borderwidth=0,
                                     highlightthickness=0,
                                     activebackground="#777777",
                                     activeforeground="#FFFFFF")

        # process list, incl. tree and scrollbar
        self.tree_frame = tk.Frame(root)

        columns = ("pid", "name", "ram")
        self.tree = ttk.Treeview(self.tree_frame, columns=columns, show="headings", height=15)

        self.tree.heading("pid", text="PID")
        self.tree.heading("name", text="Process Name",
                          command=lambda: self.toggle_sort('name'))
        self.tree.heading("ram", text="RAM (MB)",
                          command=lambda: self.toggle_sort('ram_mb'))

        self.tree.column("pid", width=10, anchor=tk.E)
        self.tree.column("name", width=120)
        self.tree.column("ram", width=80, anchor=tk.E)

        self.scrollbar = ttk.Scrollbar(self.tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=self.scrollbar.set)

        self.tree.bind("<<TreeviewSelect>>", self.on_process_select)

        # ram monitoring and process selection
        self.control_frame = tk.Frame(root)
        self.current_ram_label = tk.Label(self.control_frame,
                                          text="RAM %: --%",
                                          font=("Helvetica", 10, "bold"))

        self.target_label = tk.Label(self.control_frame,
                                     text="Target: No Process Selected",
                                     font=("Helvetica", 10))

        self.threshold_label = tk.Label(self.control_frame,
                                        text=f"Threshold: {self.threshold_var.get()}%",
                                        font=("Helvetica", 10))

        self.threshold_slider = ttk.Scale(self.control_frame,
                                          from_=0, to=100,
                                          orient=tk.HORIZONTAL,
                                          variable=self.threshold_var,
                                          command=self.update_slider_label)

        # sound widgets
        self.sound_label = tk.Label(self.control_frame,
                                    text="Sound: (default)",
                                    font=("Helvetica", 10))
        self.sound_button = tk.Button(self.control_frame,
                                      text="Select Sound",
                                     command=self.select_sound,
                                     borderwidth=0,
                                     highlightthickness=0)

        # on/off buttons
        self.on_button = tk.Button(self.control_frame,
                                   text="ON",
                                   command=self.toggle_monitoring_on,
                                   borderwidth=0,
                                   highlightthickness=0)

        self.off_button = tk.Button(self.control_frame,
                                   text="OFF",
                                   command=self.toggle_monitoring_off,
                                   borderwidth=0,
                                   highlightthickness=0)

        

        self.toggle_monitoring_off()

        # -- placing widgets --

        self.search_entry.place(x=6, y=8, width=200, height=25)

        self.refresh_btn.place(x=210, y=8, width=180, height=25)

        self.tree_frame.place(relx=0.01, rely=0.07, relwidth=0.6, relheight=0.92)

        self.tree.place(relx=0, rely=0, relwidth=0.97, relheight=1)
        self.scrollbar.place(relx=1, rely=0, relheight=1, anchor='ne')

        self.control_frame.place(relx=0.63, rely=0.07, relwidth=0.35, relheight=0.4)
        
        self.current_ram_label.place(relx=0, rely=0.12, relwidth=0.5)
        self.target_label.place(relx=0.02, rely=0.25, relwidth=1)
        
        self.sound_label.place(relx=0.02, rely=0.0, relwidth=0.5)
        self.sound_button.place(relx=0.6, rely=0.0, relwidth=0.38, relheight=0.1)

        self.on_button.place(relx=0.6, rely=0.12, relwidth=0.18, relheight=0.1)
        self.off_button.place(relx=0.8, rely=0.12, relwidth=0.18, relheight=0.1)
        
        self.threshold_label.place(relx=0.02, rely=0.4)
        self.threshold_slider.place(relx=0, rely=0.5, relwidth=1)

        self.setup_style()

        # -- load it all --

        self.refresh_list()

        # okay we're good now (see self.tree_initialized = False)
        self.tree_initialized = True
        
        self.check_data_queue()
        self.start_refresh_thread()
        self.update_global_ram()

        self.root.protocol("WM_DELETE_WINDOW", self.hide_window)

    def hide_window(self):
        """so you can minimise to tray and not delete window"""
        self.root.withdraw()

    def select_sound(self):
        """open file dialog to select sound file"""
        filepath = filedialog.askopenfilename(
            title="Select Sound File",
            filetypes=[("Audio Files", "*.mp3 *.wav *.ogg"), ("All Files", "*.*")]
            )

        if not filepath:
            return

        if not os.path.exists(filepath):
            messagebox.showerror("Error", "Selected file does not exist.")
            return

        try:
            self.custom_sound_path = filepath
            self.sound_label.config(text=f"Sound: {os.path.basename(filepath)}")
        except Exception as e:
            self.custom_sound_path = None
            self.sound_label.config(text="Sound: (default)")
            print(f"Error setting sound file: {e}")

    def play_sound(self):
        try:
            playsound.playsound(self.custom_sound_path, block=False)
            print("Played sound.")
        except Exception as e:
            print(f"Error playing sound: {e}")
            self.root.bell()  # fallback beep

    def on_process_select(self, event):
        """
        when user clicks on item in tree aka a process
        stores selected process
        """
        try:
            selected_item = self.tree.focus()   # item id
            if not selected_item:
                return

            item_values = self.tree.item(selected_item, "values")

            self.target_pid = int(item_values[0])
            self.target_name = item_values[1]

            self.target_label.config(text=f"Target: {self.target_name} (PID: {self.target_pid})",
                                     background="#444444", fg="#FFFFFF")

        except Exception as e:
            print(f"on_process_select failed: {e}")
            self.target_pid = None
            self.target_name = None
            self.reset_target_label()

    def reset_target_label(self):
        """
        resets target label to default state
        """
        self.target_label.config(text="Target: No Process Selected",
                                 background="#333333", fg="#FFFFFF")

    def toggle_monitoring_on(self):
        self.monitoring_enabled = True
        self.on_button.config(state="disabled")
        self.off_button.config(state="normal")
        self.target_label.config(background="#333333", fg="#FFFFFF")
        if self.target_pid:
            self.target_label.config(text=f"Target: {self.target_name} (PID: {self.target_pid})")

    def toggle_monitoring_off(self):
        self.monitoring_enabled = False
        self.on_button.config(state="normal")
        self.off_button.config(state="disabled")
        self.target_label.config(background="#333333", fg="#FFFFFF")
        if self.target_pid:
            self.target_label.config(text=f"Target: {self.target_name} (PID: {self.target_pid})")

    def update_slider_label(self, event):
        """updates threshold label as slider moves"""
        self.threshold_label.config(text=f"Threshold: {self.threshold_var.get():.0f}%")

    def update_global_ram(self):
        """
        fetches global RAM % and kills process if enabled
        polling rate is 2 seconds
        """
        # get RAM
        current_ram = psutil.virtual_memory().percent
        self.current_ram_label.config(text=f"RAM %: {current_ram:.1f}%")
        
        threshold = self.threshold_var.get()

        ram_label_bg = "#444444"

        if current_ram > threshold:

            print(f"threshold breached, ram: {current_ram}% > threshold: {threshold}%")

            if self.monitoring_enabled and self.target_pid is not None:
                print(f"attempting to kill {self.target_name} (PID: {self.target_pid})...")
                ram_label_bg = "#FF0000"
                try:
                    process_to_kill = psutil.Process(self.target_pid)
                    process_to_kill.kill()

                    self.play_sound()

                    # we did it
                    print("yay")
                    self.target_label.config(text=f"Killed {self.target_name}", background="#00FF00", fg="#000000")
                    self.toggle_monitoring_off()

                except psutil.NoSuchProcess:
                    print("womp womp already closed")
                    self.target_label.config(text="Already closed.", background="#00FF00", fg="#000000")
                except psutil.AccessDenied:
                    print("womp womp access denied")
                    self.target_label.config(text="Access Denied.", background="#FF0000", fg="#FFFFFF")
                except Exception as e:
                    print(f"womp womp unknown error: {e}")
                    self.target_label.config(text=f"Error: {e}", background="#FF0000", fg="#FFFFFF")

                # reset
                self.target_pid = None
                self.target_name = None
                self.root.after(3000, self.reset_target_label)

            elif self.monitoring_enabled and self.target_pid is None:
                print("no target, monitoring on")
                ram_label_bg = "#FFA500"    # no target selected

        self.current_ram_label.config(background=ram_label_bg)

        # schedule to run again
        self.root.after(2000, self.update_global_ram)

    def start_refresh_thread(self):
        """
        when you refresh you don't want it to freeze
        """
        if self.refresh_in_progress:
            return

        self.refresh_in_progress = True
        self.refresh_btn.config(state="disabled", text="Refreshing...")

        threading.Thread(target=self.threaded_get_process_data, daemon=True).start()

    def threaded_get_process_data(self):
        """
        (works on background thread)
        fetches then throws data into queue
        """
        data = self.get_process_data()
        self.data_queue.put(data) # no way

    def check_data_queue(self):
        """
        (works on main thread)
        checks queue for new data, when it arrives the UI is updated, every 100 ms, not very resource intensive still.
        """
        try:
            new_data = self.data_queue.get_nowait()

            # error by now, if no, we got data
            self.master_process_list = new_data
            self.filter_list()
            self.update_headings()

            self.refresh_btn.config(state="normal", text="Refresh")
            self.refresh_in_progress = False
        except queue.Empty:
            pass
        finally:
            self.root.after(100, self.check_data_queue)

    # i don't like all elements to be FFFFFF cheers
    def setup_style(self):
        bg_color = "#333333"
        entry_bg = "#555555"
        text_color = "#FFFFFF"
        header_bg = "#444444"
        disabled_fg = "#999999"
        
        self.root.config(bg=bg_color)
        
        # standard widgets (Entry, Button, Frame)
        self.search_entry.config(bg=entry_bg, fg=text_color, insertbackground=text_color, 
                                 highlightbackground=header_bg, highlightcolor=text_color)
        self.refresh_btn.config(bg=header_bg, fg=text_color)
        self.tree_frame.config(bg=bg_color)
        
        self.control_frame.config(bg=bg_color)
        self.current_ram_label.config(bg=header_bg, fg=text_color)
        self.threshold_label.config(bg=bg_color, fg=text_color)

        self.target_label.config(bg=bg_color, fg=text_color)
        self.threshold_label.config(bg=bg_color, fg=text_color)
        
        self.on_button.config(bg=header_bg, fg=text_color, 
                              activebackground="#777777", activeforeground="#FFFFFF",
                              disabledforeground=disabled_fg)
        self.off_button.config(bg=header_bg, fg=text_color, 
                               activebackground="#777777", activeforeground="#FFFFFF",
                               disabledforeground=disabled_fg)

        # ttk widgets (Treeview, Scrollbar)
        self.style.theme_use("clam") # 'clam' or 'alt' are easiest to style
        
        # general treeview style
        self.style.configure("Treeview",
                             background=entry_bg,
                             foreground=text_color,
                             fieldbackground=entry_bg,
                             borderwidth=0,
                             rowheight=25)
        # remove border on focus
        self.style.layout("Treeview", [('Treeview.treearea', {'sticky': 'nswe'})]) 
        
        # treeview heading style
        self.style.configure("Treeview.Heading",
                             background=header_bg,
                             foreground=text_color,
                             font=("Helvetica", 10, "bold"),
                             borderwidth=0)
        
        # make heading active state darker
        self.style.map("Treeview.Heading",
                       background=[('active', '#666666')],
                       foreground=[('active', text_color)])
        
        # selected item style
        self.style.map("Treeview",
                       background=[('selected', '#0078D7')], # blue?
                       foreground=[('selected', text_color)])
        
        # scrollbar style
        self.style.configure("Vertical.TScrollbar",
                             background=header_bg,
                             troughcolor=bg_color,
                             bordercolor=bg_color,
                             arrowcolor=text_color)
        self.style.map("Vertical.TScrollbar",
                       background=[('active', '#666666')])

    def set_search_placeholder(self):
        self.search_var.set(self.search_placeholder)
        self.search_entry.config(fg='grey')

    def on_search_focus_in(self, event):
        if self.search_var.get() == self.search_placeholder:
            self.search_var.set("")
            self.search_entry.config(fg='white')

    def on_search_focus_out(self, event):
        if not self.search_var.get():
            self.set_search_placeholder()

    def toggle_sort(self, column_key):
        """
        when a column header is clicked,
        toggle the sort direction or change the target sorted column
        """
        if self.sort_by_col == column_key:
            # just reverse direction
            self.sort_reverse = not self.sort_reverse
        else:
            # other column is target, but just default to descending for RAM, ascending for Name
            self.sort_by_col = column_key
            self.sort_reverse = (column_key == 'ram_mb') # true for RAM, false for Name
        
        # update heading text with arrows
        self.update_headings()
        
        # apply sort to displayed data
        self.filter_list()

    def update_headings(self):
        """
        adds/removes sorting arrows (▼ ▲) from column headers when you click them
        """
        # reset all headings
        self.tree.heading("name", text="Process Name")
        self.tree.heading("ram", text="RAM (MB)")
        
        # add arrow to active column
        arrow = "▼" if self.sort_reverse else "▲"
        if self.sort_by_col == 'name':
            self.tree.heading("name", text=f"Process Name {arrow}")
        elif self.sort_by_col == 'ram_mb':
            self.tree.heading("ram", text=f"RAM (MB) {arrow}")

    def get_process_data(self):
        """
        use psutil to get all running processes and returns a list of dicts
        """
        processes = []
        for proc in psutil.process_iter():
            pinfo = {}
            try:
                # pid gaming
                pinfo['pid'] = proc.pid

                # name
                try:
                    pinfo['name'] = proc.name() # please
                except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
                    # NOOOO YOU'RE SUPPOSED TO GIVE ME THE NAME!
                    pinfo['name'] = "* But it refused."
                
                # remember
                try:
                    # proc.memory_info() returns a namedtuple. get 'rss'
                    pinfo['ram_mb'] = proc.memory_info().rss / (1024 * 1024)
                except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
                    # if we can't get RAM say 0 and move on
                    pinfo['ram_mb'] = 0.0 
                
                # only add to list if we have at least PID and name
                processes.append(pinfo)
                
            except (psutil.NoSuchProcess, psutil.ZombieProcess):
                # the rare case the process died between process_iter() and getting info
                pass
        return processes

    def populate_treeview(self, data):
        """
        clear treeview and populate with new data
        """
        # clear treeview

        current_focus = self.tree.focus()

        for item in self.tree.get_children():
            self.tree.delete(item)
            
        # and populate with new data
        for i, proc in enumerate(data):
            ram_formatted = f"{proc['ram_mb']:.2f} MB"
            values = (proc['pid'], proc['name'], ram_formatted)
            self.tree.insert("", tk.END, iid=i, values=values)

        if current_focus in self.tree.get_children():
            self.tree.focus(current_focus)
            self.tree.selection_set(current_focus)

    def refresh_list(self):
        """
        fetch new data, store it, and populate treeview
        """
        # fetch new data
        self.master_process_list = self.get_process_data()
        self.filter_list()
        self.update_headings()

    def filter_list(self, *args):
        """
        filters and sorts the master list then updates the treeview
        """
        # i need to link this method to the search box, which is defined before the tree. so this is needed.
        if not self.tree_initialized:
            return

        # --- filter ---
        search_term = self.search_entry.get().lower()
        
        # check if we're using the placeholder
        if not search_term or search_term == self.search_placeholder.lower():
            filtered_data = self.master_process_list
        else:
            filtered_data = []
            for proc in self.master_process_list:
                if search_term in proc['name'].lower():
                    filtered_data.append(proc)
        
        # --- sort ---
        if self.sort_by_col == 'name':
            # sort by name, case-insensitive
            sorted_data = sorted(filtered_data, 
                                 key=lambda p: p['name'].lower(), 
                                 reverse=self.sort_reverse)
        else:
            # sort by ram_mb (numeric)
            sorted_data = sorted(filtered_data, 
                                 key=operator.itemgetter(self.sort_by_col), 
                                 reverse=self.sort_reverse)

        # --- populate ---
        self.populate_treeview(sorted_data)

def create_image(width, height, colour1, colour2):
    """2 colours for tray icon"""
    image = Image.new('RGB', (width, height), colour1)
    dc = ImageDraw.Draw(image)
    dc.rectangle(
        (width // 2, 0, width, height // 2),
        fill=colour2)
    dc.rectangle(
        (0, height // 2, width // 2, height),
        fill=colour2)
    return image

def setup_app_thread():
    """tkinter app in own thread"""
    global app, root    # for tray
    root = tk.Tk()
    app = RamSniper(root)
    root.mainloop()

def show_window():
    """guess what it does"""
    if root:
        root.deiconify()
        root.lift()
        root.focus_force()

def quit_app():
    """quits tray and app itself"""
    print("bye")
    if icon:
        icon.stop()
    if root:
        root.quit()
        root.destroy()
    sys.exit()

if __name__ == "__main__":
    app = None
    root = None
    icon = None

    app_thread = threading.Thread(target=setup_app_thread, daemon=True)
    app_thread.start()

    image = create_image(64, 64, 'black', 'gray')
    menu = (
        pystray.MenuItem('Show Window', show_window, default=True),
        pystray.MenuItem('Quit', quit_app)
        )
    icon = pystray.Icon("ram_sniper", image, "RAM Sniper", menu)

    print("RAM Sniper in system tray.")
    icon.run()
