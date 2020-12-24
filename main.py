from dataclasses import dataclass
import sys
import tkinter as tk
from cefpython3 import cefpython as cef
from threading import Thread, Lock, get_ident
import time
import alsaaudio  # apt install python-alsaaudio, libasound2-dev ; pip3 pyalsaaudio
from random import randrange
from serial import Serial  # pyserial
import mouse
import argparse



# https://stackoverflow.com/questions/57974532/why-cant-run-both-tkinter-mainloop-and-cefpython3-messageloop
# TODO slack notification with random room names?
# https://medium.com/@harvitronix/using-python-slack-for-quick-and-easy-mobile-push-notifications-5e5ff2b80aad


def bit_not(n, numbits=8):
    return (1 << numbits) - 1 - n

@dataclass
class Config(object):
    startfullscreen: bool
    username: str
    roomname: str
    server: str
    serialbaud: int
    serialdevice: str
    cache_path: str
    useragent :str
    ignoreserial: bool
    serialretry: bool

    @classmethod
    def default(cls):
        return cls(startfullscreen=False,
                   username='User_'+str(randrange(1000)),
                   roomname='tv_room'+str(randrange(1000)),
                   server='https://meet.jit.si/',  # https://meet.scheible.it/
                   serialbaud=9600,
                   serialdevice='/dev/arduino_nano_clone',  #  HINT: set udev rule for device to be connected to same name every time
                   cache_path='cache',
                   useragent='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/73.0.3683.75 Safari/537.36',
                   ignoreserial=True,
                   serialretry=True)


def get_jitsi_url(cfg: Config):
    url = '%s%s' % (cfg.server, cfg.roomname)
    print('URL: '+url)
    params = '#userInfo.displayName="%s"&config.startWithAudioMuted=false&config.startWithVideoMuted=false' % (cfg.username)
    return url+params

class ComObj(object):

    BUTTON_COUNT = 5

    def __init__(self, cfg: Config):
        self._iolock = Lock()
        self._cfg = cfg
        self._lights: int = 0
        self._buttons: int = 0
        self.signals = {'exit': False}
        try:
            self._ser = Serial(self._cfg.serialdevice, self._cfg.serialbaud, timeout=1)
        except Exception as e:
            if cfg.serialretry:
                pass
            else:
                raise e
        self._comthread = Thread(target=self._com_loop)
        self._comthread.start()
        self._echo_negated = True

    def __del__(self):
        try:
            self.stop()
        except:
            pass


    def _com_loop(self):
        # incoming button states should have their left bits set to 110
        # 110xxxxx
        ex = None
        # outgoing light states should have their left bits set to 101
        # 101xxxxx
        print('com_loop_start', get_ident())
        while not self.signals['exit']:
            #rx
            try:
                if self._ser.in_waiting:
                    rx_bytes = self._ser.read_all() # last
                    #print(rx_byte)
                    rx = rx_bytes[-1] #  int.from_bytes(rx_byte, 'big')
                    if (rx & 0b11000000) == 0b11000000:  # header?
                        self._iolock.acquire()
                        try:
                            self._buttons = rx & 0b00011111  # remove header

                            #tx only on rx:
                            tx = self._lights
                            if self._echo_negated:
                                tx = self._buttons ^ 0b11111111
                            #header
                            tx &= 0b00011111  # header-zero
                            tx |= 0b10100000  # header-value
                            tx_byte = tx.to_bytes(1, 'big')
                            self._ser.write(tx_byte)

                        finally:
                            self._iolock.release()
                time.sleep(0.01)  # @ 100Hz
            except Exception as e:
                if self._cfg.serialretry:
                    self._ser = None
                    print("No connection to buttons. Trying to connect ...")
                    count = 0
                    while (not self._ser) and (not self.signals['exit']):
                        count +=1
                        if count % 5 == 0: # retry every 5 seconds
                            try:
                                self._ser = Serial(self._cfg.serialdevice, self._cfg.serialbaud, timeout=1)
                            except:
                                pass
                        time.sleep(1)  # @ 1Hz
                else:
                    ex = e
                    break

        try:
            self._ser.write(b'/ff')
        except:
            pass
        time.sleep(0.2)
        print('com_loop_end')

        if ex:
            raise ex


    def get_buttons(self):
        res = 0
        self._iolock.acquire()
        try:
            state_int = self._buttons
            res = state_int
        finally:
            self._iolock.release()
        return res

    def set_lights(self, buttonlights_bitfield):
        self._echo_negated = False  # stop mirror tests
        self._iolock.acquire()
        try:
            lights_int = buttonlights_bitfield
            self._lights = lights_int
        finally:
            self._iolock.release()

    def stop(self):
        self.signals['exit'] = True
        self._comthread.join()


class Fullscreen_Window:
    def __init__(self, cfg: Config, comm_obj: ComObj):
        self.comm_obj = comm_obj
        self.cfg = cfg

        self._last_hw_buttons = 0

        self._mixer = alsaaudio.Mixer()

        self.tk = tk.Tk()
        self.tk.protocol('WM_DELETE_WINDOW', self.on_closing)
        self.tk.attributes('-zoomed', True)  # This just maximizes it so we can see the window. It's nothing to do with fullscreen.
        self.mainframe = tk.Frame(self.tk, height=800, width=1200, bg='black')
        self.frame2 = tk.Frame(self.tk, bg='black', height=200, width=200)
        self.mainframe.pack(side='top',  expand=True, fill='both')
        self.frame2.pack(side='top',  expand=False, fill='both')

        photo = tk.PhotoImage(file="media/main.png")
        photo_label = tk.Label(self.mainframe, image=photo, anchor="center")
        photo_label.grid()
        photo_label.image = photo

        self.browser = None
        self.browser_thread_signals = {"have_browser": False, "exit": False}

        self.bt1 = tk.Button(self.frame2, text="VIDEO [F5]", command=lambda: self.button_handler(0), bg='green')
        self.bt1.grid(row=0, column=4, sticky='news')

        self.bt2 = tk.Button(self.frame2, text="STOP [F4]", command=lambda: self.button_handler(1), bg='red')
        self.bt2.grid(row=0, column=3, sticky='news')

        self.bt3 = tk.Button(self.frame2, text="LEISER(video) [F3]", command=lambda: self.button_handler(2), bg='yellow')
        self.bt3.grid(row=0, column=2, sticky='news')

        self.bt4 = tk.Button(self.frame2, text="LAUTER(video) [F2]", command=lambda: self.button_handler(3), bg='white')
        self.bt4.grid(row=0, column=1, sticky='news')

        self.bt5 = tk.Button(self.frame2, text="[BLAU] [F1]", command=lambda: self.button_handler(4), bg='blue', fg='white')
        self.bt5.grid(row=0, column=0, sticky='news')

        self.bt5 = tk.Button(self.frame2, text="Beenden [F10]", command=lambda: self.button_handler(10), bg='grey', fg='white')
        self.bt5.grid(row=0, column=6, sticky='news')

        self.lbl_vol = tk.Label(self.frame2, text="Lautstärke ...")
        self.lbl_vol.grid(row=0, column=5, sticky='news')

        self.lbl_room = tk.Label(self.frame2, text="  SERVER: %s  RAUM: %s  " % (cfg.server, cfg.roomname))
        self.lbl_room.grid(row=0, column=7, sticky='news')

        self.fullscreen_state = False
        self.tk.bind("<F11>", self.toggle_fullscreen)
        self.tk.bind("<Escape>", self.end_fullscreen)

        self.tk.bind("<F1>", self._onF)
        self.tk.bind("<F2>", self._onF)
        self.tk.bind("<F3>", self._onF)
        self.tk.bind("<F4>", self._onF)
        self.tk.bind("<F5>", self._onF)
        self.tk.bind("<F10>", self._onF)

        if cfg.startfullscreen:
            self.toggle_fullscreen()

        self._attach_cef_thread()
        self.tk.after(10, self._process)  # @100Hz

    def __del__(self):
        try:
            self.on_closing()
        except:
            pass

    def on_closing(self):
        self.browser_thread_signals["exit"] = True
        self.cefthread.join()
        self.tk.destroy()
        print("exit")

    def _onF(self, event=None):
        if event:
            k = event.keysym
            if k == "F5":
                self.button_handler(0)
            if k == "F4":
                self.button_handler(1)
            if k == "F3":
                self.button_handler(2)
            if k == "F2":
                self.button_handler(3)
            if k == "F1":
                self.button_handler(4)
            if k == "F10":
                self.button_handler(10)




    def _attach_cef_thread(self):
        self.cefthread = Thread(target=self._cef_thread_loop)
        self.cefthread.start()

    def _process(self):
        # process io and such, called @ ~100Hz
        # TODO button texts according to app-state, instruction image when in base state

        # check hw buttons:
        hwbts_state = self._check_hw_buttons_and_trigger()

        #update gui
        self.lbl_vol['text'] = "Lautstärke: %s %%" % (str(self._mixer.getvolume()[0]))

        # set lights
        self._light_hw_buttons(hwbts_state)

        #give us focus
        self.frame2.focus_force()  # keys only work if also the mouse is not in the browser .... :/

        #repeat
        self.tk.after(10, self._process)  # @~100Hz


    def _check_hw_buttons_and_trigger(self):
        if not self.comm_obj:
            return 0

        hw_bts = self.comm_obj.get_buttons()
        hw_trigger = 0
        # check if newly pressed, then trigger

        # trigger once on rising (e.g. onpress)
        hw_trigger = bit_not(self._last_hw_buttons) & hw_bts

        # TODO special behaviour when multiple pressed (for longer)?
        # restart? update? reboot?

        for i in range(self.comm_obj.BUTTON_COUNT):
            if hw_trigger & (1 << i):
                self.button_handler(i)

        self._last_hw_buttons = hw_bts
        return hw_bts  # current state


    def _light_hw_buttons(self, light_these_anyway):
        if not self.comm_obj:
            return

        state_light = 0
        # todo define states together with button functions and visuals
        # green light when 'in calls'
        # for now:
        if self.browser:
            state_light |= 1 << 0  #  0-> green

        # and additionally:
        state_light |= light_these_anyway

        self.comm_obj.set_lights(state_light)



    def button_handler(self, button_id):
        # print(button_id)
        # TODO group with current state the app is in rather than buttons

        if button_id == 0:  # green
            self.browser_thread_signals["have_browser"] = True
        if button_id == 1:  # red
            self.browser_thread_signals["have_browser"] = False
        if button_id == 2:  # yellow (-)
            if self.browser:
                v = self._mixer.getvolume()[0]
                v -= 10
                v = max(v, 0)
                self._mixer.setvolume(v)

        if button_id == 3:  # white (+)
            if self.browser:
                v = self._mixer.getvolume()[0]
                v += 10
                v = min(v, 100)
                self._mixer.setvolume(v)

        if button_id == 10:  # grey,exit,nonphysical
            self.on_closing()

    def _cef_thread_loop(self):
        print("cef_loop ", get_ident())

        sys.excepthook = cef.ExceptHook
        settings = {}
        #settings["log_severity"] = cef.LOGSEVERITY_INFO
        settings['remote_debugging_port']='-1'
        settings['user_agent'] = self.cfg.useragent
        settings['cache_path'] = self.cfg.cache_path

        switches = {}
        switches['disable-gpu'] = '1'
        #switches['disable-gpu-compositing'] = '1'
        switches['enable-media-stream'] = '1'
        switches['use-fake-ui-for-media-stream'] = '1'
        print("cef init....")
        cef.Initialize(settings, switches)
        print("done")

        while not self.browser_thread_signals["exit"]:
            if self.browser_thread_signals["have_browser"]:
                if not self.browser:
                    # setup
                    window_info = cef.WindowInfo(self.mainframe.winfo_id())
                    rect = [0, 0, self.mainframe.winfo_width(), self.mainframe.winfo_height()]
                    window_info.SetAsChild(self.mainframe.winfo_id(), rect)
                    self.browser = cef.CreateBrowserSync(window_info, url=get_jitsi_url(self.cfg))
                    # browser = cef.CreateBrowserSync(window_info, url='https://meet.jit.si/RuralLibertiesRepeatAlso')
                    # browser = cef.CreateBrowserSync(window_info, url='https://www.whatsmyua.info/')
                    # browser = cef.CreateBrowserSync(window_info, url="http://mitchcapper.com/cookie.html")
                    print("browser_start")

                cef.MessageLoopWork()
                time.sleep(0.02)  # @50Hz  otherwise will take 100% cpu
            else:
                if self.browser:
                    # tear down
                    self.browser.CloseBrowser(True)
                    self.browser = None
                    print("browser_end")
                cef.MessageLoopWork()
                time.sleep(0.02) #  @50Hz otherwise will take 100% cpu

        if self.browser:
            # tear down
            self.browser.CloseBrowser(True)
            self.browser = None
            print("browser_end")
            cef.MessageLoopWork()
        cef.Shutdown()

    def toggle_fullscreen(self, event=None):
        self.fullscreen_state = not self.fullscreen_state  # Just toggling the boolean
        self.tk.attributes("-fullscreen", self.fullscreen_state)
        return "break"

    def end_fullscreen(self, event=None):
        self.fullscreen_state = False
        self.tk.attributes("-fullscreen", False)
        return "break"


def setup_window(cfg: Config, com: ComObj):
    window = Fullscreen_Window(cfg, com)
    return window


def main():
    # TODO more params / write/load config file
    cfg = Config.default()
    cfg.startfullscreen = True


    parser = argparse.ArgumentParser(description="TV-Video-Call-Interface")

    parser.add_argument("--server", help="Use this server", type=str, default="")
    parser.add_argument("--room", help="Use this room", type=str, default="")
    parser.add_argument("--user", help="Use this username", type=str, default="")

    args = None
    try:
        args = parser.parse_args()
    except:
        parser.print_help()
        exit(0)

    print("-------------------------------------------")
    print("main ", get_ident())

    if args.server:
        cfg.server = args.server
    if args.room:
        cfg.roomname = args.room
    if args.user:
        cfg.username = args.user

    com = None
    try:
        com = ComObj(cfg)
    except Exception as e:
        print("Cannot connect to serial buttons @ %s" % (cfg.serialdevice))
        if cfg.ignoreserial:
            com = None
        else:
            print(e)
            exit(-1)

    #move mouse to bottom right corner (e.g. far away)
    mouse.move(10000, 10000)

    w = setup_window(cfg, com)
    w.tk.mainloop()

    if com:
        com.stop()

if __name__ == '__main__':
    main()
