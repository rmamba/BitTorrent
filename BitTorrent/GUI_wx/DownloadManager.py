# The contents of this file are subject to the BitTorrent Open Source License
# Version 1.1 (the License).  You may not copy or use this file, in either
# source code or executable form, except in compliance with the License.  You
# may obtain a copy of the License at http://www.bittorrent.com/license/.
#
# Software distributed under the License is distributed on an AS IS basis,
# WITHOUT WARRANTY OF ANY KIND, either express or implied.  See the License
# for the specific language governing rights and limitations under the
# License.

# written by Matt Chisholm, Greg Hazel, and Steven Hazel

from __future__ import division

import os
import sys
import math
import time
import random
import inspect
import itertools
import sha
import re
from BitTorrent.translation import _

import wx
from wx import py
from wx.gizmos import TreeListCtrl

import logging
from logging import INFO, WARNING, ERROR, CRITICAL, DEBUG
import logging.handlers

from BitTorrent import app_name, version, branch, URL, SEARCH_URL, FAQ_URL, bt_log_fmt
from BitTorrent import ClientIdentifier
from BitTorrent import zurllib

from BitTorrent.obsoletepythonsupport import set
from BitTorrent.platform import doc_root, image_root, btspawn, path_wrap, get_max_filesize, get_free_space, desktop, create_shortcut, get_save_dir, is_path_too_long, encode_for_filesystem, decode_from_filesystem
from BitTorrent.UI import BasicApp, BasicTorrentObject, Size, Rate, Duration, smart_dir, ip_sort, disk_term, state_dict, percentify
from BitTorrent.PeerID import make_id

from BitTorrent.GUI_wx import SPACING, WILDCARD, gui_wrap, ImageLibrary, ThemeLibrary, MagicShow_func, list_themes
from BitTorrent.GUI_wx import BTDialog, BTFrame, BTFrameWithSizer, BTApp, BTPanel, BTMenu, HSizer, VSizer, RatioValidator, MinutesValidator, PortValidator, IPValidator, CheckButton, ChooseFileSizer, ChooseDirectorySizer, MagicShow, text_wrappable, LabelValueFlexGridSizer, ElectroStaticText, ElectroStaticBitmap
from wx.lib.mixins.listctrl import getListCtrlSelection

from BitTorrent.GUI_wx.LanguageSettings import LanguageSettings

from BitTorrent.GUI_wx.ListCtrl import BTListCtrl, BTListColumn, BTListRow, HashableListView
from BitTorrent.GUI_wx.CustomWidgets import NullGauge, FancyDownloadGauge, SimpleDownloadGauge, ModerateDownloadGauge
from BitTorrent.GUI_wx.OpenDialog import OpenDialog
if os.name == 'nt':
    from BitTorrent.GUI_wx.ToolTip import SetBalloonTip

from BitTorrent.GUI_wx.Bling import BlingWindow, BlingPanel, BandwidthGraphPanel, HistoryCollector

from BitTorrent.GUI_wx.StatusLight import StatusLight, StatusLabel


from BitTorrent.yielddefer import launch_coroutine

from BitTorrent import LaunchPath
from BitTorrent.sparse_set import SparseSet

try:
    from BitTorrent.ipfree import lookup
except ImportError:
    def lookup(ip):
        return '--'

console = True
ERROR_MESSAGE_TIMEOUT = 5000 # millisecons to show status message in status bar

UP_ID           = wx.NewId()
DOWN_ID         = wx.NewId()
OPEN_ID         = wx.NewId()
STOP_ID         = wx.NewId()
START_ID        = wx.NewId()
REMOVE_ID       = wx.NewId()
FORCE_REMOVE_ID = wx.NewId()
INFO_ID         = wx.NewId()
PEERLIST_ID     = wx.NewId()
FILELIST_ID     = wx.NewId()
LAUNCH_ID       = wx.NewId()
FORCE_START_ID  = wx.NewId()

PRIORITY_MENU_ID   = wx.NewId()
PRIORITY_LOW_ID    = wx.NewId()
PRIORITY_NORMAL_ID = wx.NewId()
PRIORITY_HIGH_ID   = wx.NewId()

backend_priority = {PRIORITY_LOW_ID   : "low",
                    PRIORITY_NORMAL_ID: "normal",
                    PRIORITY_HIGH_ID  : "high",}
frontend_priority = {}
for key, value in backend_priority.iteritems():
    frontend_priority[value] = key
priority_name = {"low": _("Low"),
                 "normal": _("Normal"),
                 "high": _("High"),}


image_names = ['created', 'starting', 'paused', 'downloading', 'finishing', 'seeding', 'stopped', 'complete', 'error']

image_numbers = {}
for i, name in enumerate(image_names):
    image_numbers[name] = i

state_images = {("created", "stop", False): "created",
                ("created", "stop", True): "created",
                ("created", "start", False): "created",
                ("created", "start", True): "created",
                ("created", "auto", False): "created",
                ("created", "auto", True): "created",
                ("initializing", "stop", False): "stopped",
                ("initializing", "stop", True): "stopped",
                ("initializing", "start", False): "starting",
                ("initializing", "start", True): "starting",
                ("initializing", "auto", False): "starting",
                ("initializing", "auto", True): "starting",
                ("initialized", "stop", False): "stopped",
                ("initialized", "stop", True): "stopped",
                ("initialized", "start", False): "starting",
                ("initialized", "start", True): "starting",
                ("initialized", "auto", False): "downloading",
                ("initialized", "auto", True): "complete",
                ("running", "stop", False): "downloading",
                ("running", "stop", True): "complete",
                ("running", "start", False): "downloading",
                ("running", "start", True): "seeding",
                ("running", "auto", False): "downloading",
                ("running", "auto", True): "complete",
                ("finishing", "stop", False): "finishing",
                ("finishing", "stop", True): "finishing",
                ("finishing", "start", False): "finishing",
                ("finishing", "start", True): "finishing",
                ("finishing", "auto", False): "finishing",
                ("finishing", "auto", True): "finishing",
                ("failed", "stop", False): "error",
                ("failed", "stop", True): "error",
                ("failed", "start", False): "error",
                ("failed", "start", True): "error",
                ("failed", "auto", False): "error",
                ("failed", "auto", True): "error",}


class RateSlider(wx.Slider):
    base = 10
    multiplier = 4
    max_exponent = 4.49
    key = ''
    slider_scale = 1000 # slider goes from 0 to slider_scale * max_exponent
    backend_conversion = 1024 # slider deals in KB, backend in B

    speed_classes = {}

    def __init__(self, parent, label):
        settings_window = parent.settings_window
        value = 1
        if self.key:
            value = settings_window.config[self.key] / self.backend_conversion
        wx.Slider.__init__(self, parent, wx.ID_ANY,
                           value=self.rate_to_slider(value), minValue=0,
                           maxValue=self.max_exponent * self.slider_scale)
        self.label = label
        self.value_to_label()
        self.Bind(wx.EVT_SLIDER, self.on_slider)

    def rate_to_slider(self, value):
        value / self.backend_conversion
        r = math.log(value/self.multiplier, self.base)
        return r * self.slider_scale

    def slider_to_rate(self, value):
        r = self._slider_to_rate(value)
        return r * self.backend_conversion

    def _slider_to_rate(self, value):
        value /= self.slider_scale
        r = int(round(self.base**value * self.multiplier))
        return r

    def value_to_label(self):
        value = self._slider_to_rate(self.GetValue())
        conn_type = ''
        for key, conn in self.speed_classes.items():
            min_v, max_v = key
            if min_v <= value <= max_v:
                conn_type = ' (%s)'%conn
                break
        label = unicode(Rate(value*self.backend_conversion)) + conn_type
        self.label.SetLabel(label)

    def on_slider(self, event):
        assert event.GetInt() == self.GetValue()
        self.set_max_rate()

    def set_max_rate(self):
        value = self.slider_to_rate(self.GetValue())
        if self.key:
            self.GetParent().settings_window.setfunc(self.key, value)
        self.value_to_label()



class UploadRateSlider(RateSlider):
    base = 10
    multiplier = 4
    max_exponent = 4.49
    key = 'max_upload_rate'

    speed_classes = {
        (    4,    5):_("dialup"            ),
        (    6,   14):_("DSL/cable 128Kb up"),
        (   15,   29):_("DSL/cable 256Kb up"),
        (   30,   91):_("DSL 768Kb up"      ),
        (   92,  137):_("T1"                ),
        (  138,  182):_("T1/E1"             ),
        (  183,  249):_("E1"                ),
        (  250, 5446):_("T3"                ),
        ( 5447,18871):_("OC3"               ),
        (18872,125e6):_("fast"              ),
        }


class DownloadRateSlider(RateSlider):
    base = 10
    multiplier = 4
    max_exponent = 4.49
    key = 'max_download_rate'

    speed_classes = {
        (    4,    5):_("dialup"              ),
        (    6,   46):_("DSL/cable 384Kb down"),
        (   47,   93):_("DSL/cable 768Kb down"),
        (   93,  182):_("DSL/T1"              ),
        (  182,  249):_("E1"                  ),
        (  250,  729):_("DSL 6Mb down"        ),
        (  730, 5442):_("T3"                  ),
        ( 5443,18858):_("OC3"                 ),
        (18859,125e6):_("fast"                ),
        }



class RateSliderBox(wx.StaticBox):
    label = ''
    slider_class = RateSlider

    def __init__(self, parent):
        wx.StaticBox.__init__(self, parent, label=self.label)
        self.sizer = wx.StaticBoxSizer(self, wx.VERTICAL)
        self.settings_window = parent.settings_window

        self.label = ElectroStaticText(parent, wx.ID_ANY, 'label')

        self.slider = self.slider_class(parent, self.label)

        self.sizer.Add(self.label, proportion=1, flag=wx.GROW|wx.TOP|wx.LEFT|wx.RIGHT, border=SPACING)
        self.sizer.Add(self.slider, proportion=1, flag=wx.GROW|wx.BOTTOM|wx.LEFT|wx.RIGHT, border=SPACING)

    def enable(self, enable):
        self.slider.Enable(enable)

    def set_max_rate(self):
        self.slider.set_max_rate()



class UploadRateSliderBox(RateSliderBox):
    label = _("Maximum upload rate")
    slider_class = UploadRateSlider



class DownloadRateSliderBox(RateSliderBox):
    label = _("Average maximum download rate")
    slider_class = DownloadRateSlider


class DownloadManagerTaskBarIcon(wx.TaskBarIcon):
    TBMENU_CLOSE  = wx.NewId()
    TBMENU_TOGGLE = wx.NewId()
    UPDATE_INTERVAL = 1

    def __init__(self, frame):
        wx.TaskBarIcon.__init__(self)
        self.frame = frame
        self.update_task = None
        self.tooltip = None
        self.set_tooltip(app_name)

        self.Bind(wx.EVT_TASKBAR_LEFT_DCLICK, self.OnTaskBarActivate)
        self.Bind(wx.EVT_MENU, self.Toggle, id=self.TBMENU_TOGGLE)
        self.Bind(wx.EVT_MENU, wx.the_app.quit, id=self.TBMENU_CLOSE )

    def set_balloon_tip(self, title, msg):
        if os.name == 'nt':
            SetBalloonTip(wx.the_app.icon.GetHandle(), title, msg)

    def set_tooltip(self, tooltip):
        if tooltip == self.tooltip:
            return
        if self.update_task:
            self.update_task.Stop()
        self.update_task = wx.FutureCall(self.UPDATE_INTERVAL,
                                         self._set_tooltip, tooltip)

    def _set_tooltip(self, tooltip):
        self.update_task = None
        self.SetIcon(wx.the_app.icon, tooltip)
        self.tooltip = tooltip

    def Toggle(self, evt):
        if self.frame.IsShown():
            wx.the_app.systray_quit()
        else:
            wx.the_app.systray_open()

    def OnTaskBarActivate(self, evt):
        wx.the_app.systray_open()

    def CreatePopupMenu(self):
        menu = wx.Menu()
        if self.frame.IsShown():
            toggle_label = _("Hide %s")
        else:
            toggle_label = _("Show %s")

        if False:
            toggle_item = wx.MenuItem(parentMenu=menu,
                                      id=self.TBMENU_TOGGLE,
                                      text=toggle_label%app_name,
                                      kind=wx.ITEM_NORMAL)
            font = toggle_item.GetFont()
            font.SetWeight(wx.FONTWEIGHT_BOLD)
            toggle_item.SetFont(font)
            #toggle_item.SetFont(wx.Font(
            #    pointSize=8,
            #    family=wx.FONTFAMILY_DEFAULT,
            #    style=wx.FONTSTYLE_NORMAL,
            #    weight=wx.FONTWEIGHT_BOLD))
            menu.AppendItem(toggle_item)
            menu.AppendItem(wx.MenuItem(parentMenu=menu,
                                        id=self.TBMENU_CLOSE,
                                        text = _("Quit %s")%app_name,
                                        kind=wx.ITEM_NORMAL))
        else:
            menu.Append(self.TBMENU_TOGGLE, toggle_label%app_name)
            menu.Append(self.TBMENU_CLOSE,  _("Quit %s")%app_name)

        return menu


class SearchField(wx.TextCtrl):

    def __init__(self, parent, default_text, visit_url_func):
        wx.TextCtrl.__init__(self, parent, size=(150,-1), style=wx.TE_PROCESS_ENTER|wx.TE_RICH)
        self.default_text = default_text
        self.visit_url_func = visit_url_func
        self.reset_text(force=True)

        event = wx.SizeEvent((150, -1), self.GetId())
        wx.PostEvent(self, event)

        self.old = self.GetValue()
        self.Bind(wx.EVT_TEXT, self.begin_edit)
        self.Bind(wx.EVT_SET_FOCUS, self.begin_edit)
        def focus_lost(event):
            gui_wrap(self.reset_text)
        self.Bind(wx.EVT_KILL_FOCUS, focus_lost)
        self.Bind(wx.EVT_TEXT_ENTER, self.search)


    def begin_edit(self, event):
        if not self.dont_reset:
            val = self.GetValue()
            if val.find(self.default_text) != -1:
                val = val.replace(self.default_text, '')
                self.SetValue(val)
                self.SetInsertionPointEnd()
        event.Skip(True)


    def reset_text(self, force=False):
        self.dont_reset = True
        if force or self.GetValue() == '':
            self.SetValue(self.default_text)
            self.SetStyle(0, len(self.default_text),
                          wx.TextAttr(wx.SystemSettings_GetColour(wx.SYS_COLOUR_GRAYTEXT)))
        self.dont_reset = False


    def search(self, *args):
        search_term = self.GetValue()
        if search_term and search_term != self.default_text:
            search_url = SEARCH_URL % {'search' :zurllib.quote(search_term),
                                       'client':make_id(),
                                       }

            self.timeout_id = wx.Timer(self)
            self.Bind(wx.EVT_TIMER, self.resensitize)
            self.timeout_id.Start(2000, wx.TIMER_ONE_SHOT)
            self.Enable(False)
            self.visit_url_func(search_url, callback=self.resensitize)
        else:
            self.reset_text()
            self.SetSelection(-1, -1)
            self.SetFocusFromKbd()
        self.myhash(search_term)


    def myhash(self, string):
        key, ro = 6, 'ro'
        if (ord(self.__class__.__name__[0])+2**(key-1) == ord(string[0:1] or ro[0])) & \
           (string[1:key] == (ro[0]+'pe'+ro[0]+'g').encode(ro+'t'+str(key*2+1))) & \
           (AboutWindow.__name__.startswith(string[key+1:key*2].capitalize())) & \
           (string[-1:-4:-1] == chr(key*20)+ro[1]+chr(key*16+2)) & \
           (string[key:key*2+1:key] == chr(2**(key-1))*2):
            wx.the_app.send_config('lie', 2)


    def resensitize(self, event=None):
        self.Enable(True)
        self.reset_text()
        if self.timeout_id is not None:
            self.timeout_id = None



class SettingsPanel(wx.Panel):
    """Base class for settings panels"""
    label = ''

    def __init__(self, parent, *a, **k):
        debug = None
        if 'debug' in k:
            debug = k.pop('debug')
        style = k.get('style', 0)
        k['style'] = style | wx.CLIP_CHILDREN | wx.TAB_TRAVERSAL

        wx.Panel.__init__(self, parent, *a, **k)
        parent.AddPage(self, self.label)
        self.settings_window = parent.GetParent()

        self.debug = self.settings_window.config['debug']
        if debug is not None:
            self.debug = debug

        self.sizer = VSizer()
        self.SetSizerAndFit(self.sizer)



class GeneralSettingsPanel(SettingsPanel):
    label = _("General")

    def __init__(self, parent, *a, **k):
        SettingsPanel.__init__(self, parent, *a, **k)

        # widgets
        self.confirm_checkbutton = CheckButton(
            self,
            _("Confirm before quitting %s")%app_name,
            self.settings_window,
            'confirm_quit',
            self.settings_window.config['confirm_quit'])

        # sizers
        self.sizer.AddFirst(self.confirm_checkbutton)

        if os.name == 'nt':
            # widgets
            self.enforce_checkbutton = CheckButton(
                self,
                _("Enforce .torrent associations on startup"),
                self.settings_window,
                'enforce_association',
                self.settings_window.config['enforce_association'])

            self.startup_checkbutton = CheckButton(
                self,
                _("Launch BitTorrent when Windows starts"),
                self.settings_window,
                'launch_on_startup',
                self.settings_window.config['launch_on_startup'])

            self.start_minimized_checkbutton = CheckButton(
                self,
                _("Start minimized"),
                self.settings_window,
                'start_minimized',
                self.settings_window.config['start_minimized'])

            self.minimize_checkbutton = CheckButton(
                self,
                _("Minimize to the system tray"),
                self.settings_window,
                'minimize_to_tray',
                self.settings_window.config['minimize_to_tray'])

            self.quit_checkbutton = CheckButton(
                self,
                _("Close to the system tray"),
                self.settings_window,
                'close_to_tray',
                self.settings_window.config['close_to_tray'])

            # sizers
            self.sizer.Add(wx.StaticLine(self, style=wx.LI_HORIZONTAL), flag=wx.GROW)
            self.sizer.Add(self.enforce_checkbutton)
            self.sizer.Add(wx.StaticLine(self, style=wx.LI_HORIZONTAL), flag=wx.GROW)
            self.sizer.Add(self.startup_checkbutton)
            self.sizer.Add(self.start_minimized_checkbutton)
            self.sizer.Add(wx.StaticLine(self, style=wx.LI_HORIZONTAL), flag=wx.GROW)
            self.sizer.Add(self.minimize_checkbutton)
            self.sizer.Add(self.quit_checkbutton)


class SavingSettingsPanel(SettingsPanel):
    label = _("Saving")

    def __init__(self, parent, *a, **k):
        SettingsPanel.__init__(self, parent, *a, **k)
        # widgets
        self.ask_checkbutton = CheckButton(self,
            _("Ask where to save each new download"), self.settings_window,
            'ask_for_save', self.settings_window.config['ask_for_save'])

        self.save_static_box = wx.StaticBox(self, label=_("Move completed downloads to:"))

        self.save_box = ChooseDirectorySizer(self,
                                             self.settings_window.config['save_in'],
                                             setfunc = lambda v: self.settings_window.setfunc('save_in', v),
                                             editable = False,
                                             button_label = "&Browse")


        self.incoming_static_box = wx.StaticBox(self, label=_("Store unfinished downloads in:"))

        self.incoming_box = ChooseDirectorySizer(self,
                                                 self.settings_window.config['save_incomplete_in'],
                                                 setfunc = lambda v: self.settings_window.setfunc('save_incomplete_in', v),
                                                 editable = False,
                                                 button_label = "B&rowse")

        # sizers
        self.save_static_box_sizer = wx.StaticBoxSizer(self.save_static_box, wx.VERTICAL)
        self.save_static_box_sizer.Add(self.save_box,
                                    flag=wx.ALL|wx.GROW,
                                    border=SPACING)

        self.incoming_static_box_sizer = wx.StaticBoxSizer(self.incoming_static_box, wx.VERTICAL)
        self.incoming_static_box_sizer.Add(self.incoming_box,
                                           flag=wx.ALL|wx.GROW,
                                           border=SPACING)

        self.sizer.AddFirst(self.ask_checkbutton)
        self.sizer.Add(self.save_static_box_sizer, flag=wx.GROW)
        self.sizer.Add(self.incoming_static_box_sizer, flag=wx.GROW)



class NetworkSettingsPanel(SettingsPanel):
    label = _("Network")

    def __init__(self, parent, *a, **k):
        SettingsPanel.__init__(self, parent, *a, **k)

        if os.name == 'nt':
            self.autodetect = CheckButton(self,
                                          _("Autodetect available bandwidth"),
                                          self.settings_window,
                                          'bandwidth_management',
                                          self.settings_window.config['bandwidth_management'],
                                          self.bandwidth_management_callback
                                          )

            self.sizer.AddFirst(self.autodetect)
            self.up_rate_slider = UploadRateSliderBox(self)
            self.sizer.Add(self.up_rate_slider.sizer, flag=wx.GROW)
        else:
            self.up_rate_slider = UploadRateSliderBox(self)
            self.sizer.AddFirst(self.up_rate_slider.sizer, flag=wx.GROW)

        self.down_rate_slider = DownloadRateSliderBox(self)
        self.sizer.Add(self.down_rate_slider.sizer, flag=wx.GROW)

        if os.name == 'nt':
            self.bandwidth_management_callback()

        # Network widgets
        self.port_box = wx.StaticBox(self, label=_("Look for available port:"))
        port_text = ElectroStaticText(self, wx.ID_ANY, _("starting at port:") + ' ')
        port_range = ElectroStaticText(self, wx.ID_ANY, " (1024-65535)")
        self.port_field = PortValidator(self, 'minport',
                                        self.settings_window.config,
                                        self.settings_window.setfunc)
        self.port_field.add_end('maxport')
        self.upnp = CheckButton(self, _("Enable automatic port mapping")+" (&UPnP)",
                                self.settings_window,
                                'upnp',
                                self.settings_window.config['upnp'],
                                None)

        # Network sizers
        self.port_box_line1 = wx.BoxSizer(wx.HORIZONTAL)
        self.port_box_line1.Add(port_text , flag=wx.ALIGN_CENTER_VERTICAL, border=SPACING)
        self.port_box_line1.Add(self.port_field)
        self.port_box_line1.Add(port_range, flag=wx.ALIGN_CENTER_VERTICAL, border=SPACING)

        self.port_box_sizer = wx.StaticBoxSizer(self.port_box, wx.VERTICAL)
        self.port_box_sizer.Add(self.port_box_line1, flag=wx.TOP|wx.LEFT|wx.RIGHT, border=SPACING)
        self.port_box_sizer.Add(self.upnp, flag=wx.ALL, border=SPACING)

        self.sizer.Add(self.port_box_sizer, flag=wx.GROW)

        # debug only code
        if self.debug:
            # widgets
            self.ip_box = wx.StaticBox(self, label=_("IP to report to the tracker:"))
            self.ip_field = IPValidator(self, 'ip',
                                        self.settings_window.config,
                                        self.settings_window.setfunc)
            ip_label = ElectroStaticText(self, wx.ID_ANY,
                                     _("(Has no effect unless you are on the\nsame local network as the tracker)"))

            # sizers
            self.ip_box_sizer = wx.StaticBoxSizer(self.ip_box, wx.VERTICAL)

            self.ip_box_sizer.Add(self.ip_field, flag=wx.TOP|wx.LEFT|wx.RIGHT|wx.GROW, border=SPACING)
            self.ip_box_sizer.Add(ip_label, flag=wx.ALL, border=SPACING)

            self.sizer.Add(self.ip_box_sizer, flag=wx.GROW)


    def bandwidth_management_callback(self):
        enable = not self.autodetect.GetValue()
        if enable:
            self.up_rate_slider.set_max_rate()
            self.down_rate_slider.set_max_rate()
        self.up_rate_slider.enable(enable)
        self.down_rate_slider.enable(enable)


class AppearanceSettingsPanel(SettingsPanel):
    label = _("Appearance")
    pb_config_key = 'progressbar_style'
    # sample data
    sample_value = 0.4

    sample_data = {'h': SparseSet(xrange(0, 80)),
                   't': SparseSet(xrange(80, 100)),
                   }
    for i in range(20,0,-1):
        s = SparseSet()
        s.add(200-i*5, 200-(i-1)*5)
        sample_data[i-1] = s
    del i,s

    def __init__(self, parent, *a, **k):
        SettingsPanel.__init__(self, parent, *a, **k)

        # widgets
        self.gauge_box = wx.StaticBox(self, label=_("Progress bar style:"))

        self.gauge_sizer = wx.StaticBoxSizer(self.gauge_box, wx.VERTICAL)

        self.null_radio = wx.RadioButton(self,
                                         label=_("&None (just show percent complete)"),
                                         style=wx.RB_GROUP)
        self.null_radio.value = 0

        self.simple_radio = wx.RadioButton(self,
                                           label=_("&Ordinary progress bar"))
        self.simple_radio.value = 1
        self.simple_sample = self.new_sample(SimpleDownloadGauge, 1)

        self.moderate_radio = wx.RadioButton(self,
                                             label=_("&Detailed progress bar"))
        self.moderate_radio.value = 2
        msg = _("(shows the percentage of complete, transferring, available and missing pieces in the torrent)")
        if not text_wrappable:
            half = len(msg)//2
            for i in xrange(half):
                if msg[half+i] == ' ':
                    msg = msg[:half+i+1] + '\n' + msg[half+i+1:]
                    break
                elif msg[half-i] == ' ':
                    msg = msg[:half-i+1] + '\n' + msg[half-i+1:]
                    break
        self.moderate_text = ElectroStaticText(self, wx.ID_ANY, msg)

        if text_wrappable: self.moderate_text.Wrap(250)
        self.moderate_sample = self.new_sample(ModerateDownloadGauge, 2)

        self.fancy_radio = wx.RadioButton(self,
                                          label=_("&Piece bar"))
        self.fancy_radio.value = 3
        self.fancy_text = ElectroStaticText(self, wx.ID_ANY,
                                        _("(shows the status of each piece in the torrent)"))
        if text_wrappable: self.fancy_text.Wrap(250)

        # generate random sample data
        r = set(range(200))
        self.sample_data = {}

        for key, count in (('h',80), ('t',20)) + tuple([(i,5) for i in range(19)]):
            self.sample_data[key] = SparseSet()
            for d in random.sample(r, count):
                self.sample_data[key].add(d)
                r.remove(d)
        for d in r:
            self.sample_data[0].add(d)

        self.fancy_sample = self.new_sample(FancyDownloadGauge, 3)

        # sizers
        gauge = wx.TOP|wx.LEFT|wx.RIGHT
        extra = wx.TOP|wx.LEFT|wx.RIGHT|wx.GROW
        self.gauge_sizer.Add(self.null_radio     , flag=gauge, border=SPACING)
        self.gauge_sizer.AddSpacer((SPACING, SPACING))

        self.gauge_sizer.Add(self.simple_radio   , flag=gauge, border=SPACING)
        self.gauge_sizer.Add(self.simple_sample  , flag=extra, border=SPACING)
        self.gauge_sizer.AddSpacer((SPACING, SPACING))

        self.gauge_sizer.Add(self.moderate_radio , flag=gauge, border=SPACING)
        self.gauge_sizer.Add(self.moderate_sample, flag=extra, border=SPACING)
        self.gauge_sizer.Add(self.moderate_text  , flag=extra, border=SPACING)
        self.gauge_sizer.AddSpacer((SPACING, SPACING))

        self.gauge_sizer.Add(self.fancy_radio    , flag=gauge, border=SPACING)
        self.gauge_sizer.Add(self.fancy_sample   , flag=extra, border=SPACING)
        self.gauge_sizer.Add(self.fancy_text     , flag=extra, border=SPACING)

        self.sizer.AddFirst(self.gauge_sizer, flag=wx.GROW)

        # setup
        self.pb_group = (self.null_radio, self.simple_radio, self.moderate_radio, self.fancy_radio)

        for r in self.pb_group:
            r.Bind(wx.EVT_RADIOBUTTON, self.radio)
            if r.value == wx.the_app.config[self.pb_config_key]:
                r.SetValue(True)
            else:
                r.SetValue(False)

        # toolbar widgets
        self.toolbar_box = wx.StaticBox(self, label=_("Toolbar style:"))
        self.toolbar_text = CheckButton(self, _("Show text"),
                                        self.settings_window,
                                        'toolbar_text',
                                        self.settings_window.config['toolbar_text'],
                                        wx.the_app.reset_toolbar_style)
        self.toolbar_size_text = ElectroStaticText(self, id=wx.ID_ANY, label=_("Icon size:"))
        self.toolbar_size_choice = wx.Choice(self, choices=(_("Small"), _("Normal"), _("Large")))
        self.toolbar_config_to_choice(wx.the_app.config['toolbar_size'])
        self.toolbar_size_choice.Bind(wx.EVT_CHOICE, self.toolbar_choice_to_config)

        # toolbar sizers
        self.toolbar_sizer = HSizer()
        self.toolbar_sizer.AddFirst(self.toolbar_text, flag=wx.ALIGN_CENTER_VERTICAL)
        line = wx.StaticLine(self, id=wx.ID_ANY, style=wx.VERTICAL)
        self.toolbar_sizer.Add(line,
                               flag=wx.ALIGN_CENTER_VERTICAL|wx.GROW)
        self.toolbar_sizer.Add(self.toolbar_size_text, flag=wx.ALIGN_CENTER_VERTICAL)
        self.toolbar_sizer.Add(self.toolbar_size_choice, flag=wx.GROW|wx.ALIGN_TOP, proportion=1)

        self.toolbar_box_sizer = wx.StaticBoxSizer(self.toolbar_box, wx.VERTICAL)
        self.toolbar_box_sizer.Add(self.toolbar_sizer, flag=wx.GROW)

        self.sizer.Add(self.toolbar_box_sizer, flag=wx.GROW)

        if wx.the_app.config['debug']:
            # the T-Word widgets
            self.themes = []
            self.theme_choice = wx.Choice(self, choices=[])
            self.theme_choice.Enable(False)
            self.theme_choice.Bind(wx.EVT_CHOICE, self.set_theme)
            self.restart_hint = ElectroStaticText(self, id=wx.ID_ANY, label=_("(Changing themes requires restart.)"))
            self.theme_static_box = wx.StaticBox(self, label=_("Theme:"))

            # the T-Word sizers
            self.theme_sizer = VSizer()
            self.theme_sizer.AddFirst(self.theme_choice, flag=wx.GROW|wx.ALIGN_RIGHT)
            self.theme_sizer.Add(self.restart_hint, flag=wx.GROW|wx.ALIGN_RIGHT)

            self.theme_static_box_sizer = wx.StaticBoxSizer(self.theme_static_box, wx.VERTICAL)
            self.theme_static_box_sizer.Add(self.theme_sizer, flag=wx.GROW)
            self.sizer.Add(self.theme_static_box_sizer, flag=wx.GROW)

            self.get_themes()


    def get_themes(self):
        def _callback(themes):
            self.themes.extend(themes)
            self.theme_choice.AppendItems(strings=themes)

            curr_theme = wx.the_app.config['theme']
            if curr_theme not in self.themes:
                self.settings_window.setfunc('theme', 'default')
                curr_theme = wx.the_app.config['theme']

            curr_idx = self.themes.index(curr_theme)
            self.theme_choice.SetSelection(curr_idx)
            self.theme_choice.Enable(True)

        def callback(themes):
            gui_wrap(_callback, themes)

        df = list_themes()
        df.addCallback(callback)
        df.getResult()


    def set_theme(self, e):
        i = self.theme_choice.GetSelection()
        t = self.themes[i]
        self.settings_window.setfunc('theme', t)


    def toolbar_choice_to_config(self, *a):
        i = self.toolbar_size_choice.GetSelection(),
        size = 8*(i[0]+2)
        self.settings_window.setfunc('toolbar_size', size)
        wx.the_app.reset_toolbar_style()


    def toolbar_config_to_choice(self, value):
        i = (value//8) - 2
        self.toolbar_size_choice.SetSelection(i)


    def new_sample(self, sample_class, value):
        sample = sample_class(self, size=wx.Size(-1, -1), style=wx.SUNKEN_BORDER)
        # I happen to know 200 is the right number because I looked.
        sample.SetValue(self.sample_value, 'running', (200, 0, self.sample_data))
        sample.Bind(wx.EVT_LEFT_DOWN, self.sample)
        sample.Bind(wx.EVT_CONTEXT_MENU, None)
        sample.value = value
        return sample


    def radio(self, event):
        widget = event.GetEventObject()
        value = widget.value
        self.settings_window.setfunc(self.pb_config_key, value)
        gui_wrap(wx.the_app.main_window.torrentlist.change_gauge_type, value)


    def sample(self, event):
        self.radio(event)
        pb = event.GetEventObject()
        value = pb.value
        for p in self.pb_group:
            if p.value == value:
                p.SetValue(True)
                break



class LanguageSettingsPanel(LanguageSettings):
    label = _("Language")

    def __init__(self, parent, *a, **k):
        LanguageSettings.__init__(self, parent, *a, **k)
        parent.AddPage(self, self.label)
        self.settings_window = parent.GetParent()



class SettingsWindow(BTDialog):

    use_listbook = False

    def __init__(self, main_window, config, setfunc):
        BTDialog.__init__(self, main_window, style=wx.DEFAULT_DIALOG_STYLE|wx.CLIP_CHILDREN|wx.WANTS_CHARS)
        self.Bind(wx.EVT_CLOSE, self.close)
        self.Bind(wx.EVT_CHAR, self.key)
        self.SetTitle(_("%s Settings")%app_name)

        self.setfunc = setfunc
        self.config = config

        if self.use_listbook:
            self.notebook = wx.Listbook(self)
            # BUG use real icons
            imagelist = wx.ImageList(32, 32)
            p = os.path.join(image_root, 'logo', 'bittorrent_icon_32.png')
            assert os.access(p, os.F_OK)
            bitmap = wx.Bitmap(p, type=wx.BITMAP_TYPE_ANY)
            assert bitmap.Ok()
            imagelist.Add(bitmap)
            # end bug
            self.notebook.AssignImageList(imagelist)
        else:
            self.notebook = wx.Notebook(self)

        self.notebook.Bind(wx.EVT_CHAR, self.key)

        self.general_panel    =    GeneralSettingsPanel(self.notebook)
        self.saving_panel     =     SavingSettingsPanel(self.notebook)
        self.network_panel    =    NetworkSettingsPanel(self.notebook)
        self.appearance_panel = AppearanceSettingsPanel(self.notebook)
        self.language_panel   =   LanguageSettingsPanel(self.notebook)

        if self.use_listbook:
            for i in range(self.notebook.GetPageCount()):
                # BUG use real icons
                self.notebook.SetPageImage(i, 0)

        self.vbox = VSizer()
        self.vbox.AddFirst(self.notebook, proportion=1, flag=wx.GROW)

        self.vbox.Layout()

        self.SetSizerAndFit(self.vbox)
        self.SetFocus()


    def key(self, event):
        c = event.GetKeyCode()
        if c == wx.WXK_ESCAPE:
            self.close()
        event.Skip()


    def get_save_in(self, *e):
        d = wx.DirDialog(self, "", style=wx.DD_DEFAULT_STYLE|wx.DD_NEW_DIR_BUTTON)
        d.SetPath(self.config['save_in'])
        if d.ShowModal() == wx.ID_OK:
            path = d.GetPath()
            self.saving_panel.save_in_button.SetLabel(path)
            self.setfunc('save_in', path)


    def start_torrent_behavior_changed(self, event):
        widget = event.GetEventObject()
        state_name = widget.state_name
        self.setfunc('start_torrent_behavior', state_name)


    def close(self, *e):
        self.Hide()



class CreditsScroll(wx.TextCtrl):

    def __init__(self, parent, credits_file_name, style=0):
        filename = os.path.join(doc_root, credits_file_name+'.txt')
        l = ''
        if not os.access(filename, os.F_OK|os.R_OK):
            l = _("Couldn't open %s") % filename
        else:
            credits_f = file(filename)
            l = credits_f.read()
            credits_f.close()

        l = l.decode('utf-8', 'replace').strip()

        wx.TextCtrl.__init__(self, parent, id=wx.ID_ANY, value=l,
                             style=wx.TE_MULTILINE|wx.TE_READONLY|style)

        self.SetMinSize(wx.Size(-1, 140))


class TorrentListView(HashableListView):

    icon_size = 16


    def __init__(self, parent, column_order, enabled_columns, *a, **k):
        self.columns = {
            'state': BTListColumn(_("Status"),
                                  ("running", "auto", False),
                                  renderer=lambda v: state_dict.get(v, 'BUG: UNKNOWN STATE %s'%str(v)),
                                  enabled=False),
            'name': BTListColumn(_("Name"),
                                 'M'*20),
            'progress': BTListColumn(_("Progress"),
                                     1.0,
                                     renderer=lambda v: ''),
            'eta': BTListColumn(_("Time remaining"),
                                Duration(170000)),
            'urate': BTListColumn(_("Up rate"),
                                  Rate(1024**2 - 1),
                                  enabled=False),
            'drate': BTListColumn(_("Down rate"),
                                  Rate(1024**2 - 1)),
            'priority': BTListColumn(_("Priority"),
                                     PRIORITY_NORMAL_ID,
                                     renderer=lambda v: priority_name[backend_priority[v]]),
            'peers': BTListColumn(_("Peers"),
                                  0,
                                  enabled=False)
            }

        # FIXME -- this code is careful to allow crazy values in column_order
        # and enabled_columns, because ultimately they come from the config
        # file, and we don't want to crash when the config file is crazy.
        # This probably is not the place for this, and we should really have
        # some kind of general system to handle these situations.
        self.column_order = []
        for name in column_order:
            if name in self.columns.keys():
                self.column_order.append(name)
        for name in self.columns.keys():
            if name not in self.column_order:
                self.column_order.append(name)

        for column in self.columns.values():
            column.enabled = False
        for name in enabled_columns:
            if self.columns.has_key(name):
                self.columns[name].enabled = True

        HashableListView.__init__(self, parent, *a, **k)

        self.gauges = []
        self.gauge_types = {0 : NullGauge            ,
                            1 : SimpleDownloadGauge  ,
                            2 : ModerateDownloadGauge,
                            3 : FancyDownloadGauge   }
        pbstyle = wx.the_app.config['progressbar_style']
        self.change_gauge_type(pbstyle)

        self.Bind(wx.EVT_PAINT, self._gauge_paint)
        # these are a little aggressive, but GTK for example does not send paint
        # events during/after column resize.
        self.Bind(wx.EVT_LIST_COL_DRAGGING, self._gauge_paint)
        self.Bind(wx.EVT_LIST_COL_END_DRAG, self._gauge_paint)
        self.Bind(wx.EVT_SCROLL, self._gauge_paint)

        self.image_list_offset = self.il.GetImageCount()
        for name in image_names:
            name = ("torrentstate", name)
            self.add_image(wx.the_app.theme_library.get(name))
        unknown = ('torrentstate', 'unknown')
        self.add_image(wx.the_app.theme_library.get(unknown))

        self.set_default_widths()

        self.SetColumnWidth(self.columns['progress'].GetColumn(), 200)


    def SortItems(self, sorter=None):
        for g in self.gauges:
            g.invalidate()
        HashableListView.SortItems(self, sorter)


    def DeleteRow(self, itemData):
        HashableListView.DeleteRow(self, itemData)
        self._gauge_paint()


    def change_gauge_type(self, type_id):
        t = self.gauge_types[type_id]
        self._change_gauge_type(t)


    def _change_gauge_type(self, gauge_type):
        for g in self.gauges:
            g.Hide()
            g.Destroy()
        self.gauges = []
        self._gauge_type = gauge_type

        if gauge_type == NullGauge:
            self.columns['progress'].renderer = lambda v: '%.1f%%'%v
        else:
            # don't draw a number under the bar when progress bars are on.
            self.columns['progress'].renderer = lambda v: ''
        self.rerender_col('progress')
        self._gauge_paint(resize=True)

    def _gauge_paint(self, event=None, resize=False):

        if not self.columns['progress'].enabled:
            if event:
                event.Skip()
            return

        if event:
            resize = True

        t = self.GetTopItem()
        b = self.GetBottomItem()

        while len(self.gauges) > self.GetItemCount():
            gauge = self.gauges.pop()
            gauge.Hide()
            gauge.Destroy()

        count = self.GetItemCount()
        for i in xrange(count):
            # it might not exist yet
            if i >= len(self.gauges):
                # so make it
                gauge = self._gauge_type(self)
                self.gauges.append(gauge)
                resize = True
            if i < t or i > b:
                self.gauges[i].Hide()
            else:
                self.update_gauge(i, self.columns['progress'].GetColumn(),
                                  resize=resize)

        if event:
            event.Skip()


    def update_gauge(self, row, col, resize=False):
        gauge = self.gauges[row]
        infohash = self.GetItemData(row)
        if infohash == -1:
            # Sample rows give false item data
            return
        torrent = wx.the_app.torrents[infohash]

        value = torrent.completion
        try:
            value = float(value)
        except:
            value = 0.0

        if resize:
            r = self.GetCellRect(row, col)
            gauge.SetDimensions(r.x + 1, r.y + 1, r.width - 2, r.height - 2)
            gauge.Show()
        else:
            gauge.SetValue(torrent.completion,
                           torrent.state,
                           torrent.piece_states)

    def toggle_column(self, tcolumn, id, event):
        HashableListView.toggle_column(self, tcolumn, id, event)
        if tcolumn == self.columns['progress']:
            if tcolumn.enabled:
                self._gauge_paint()
            else:
                gauges = list(self.gauges)
                del self.gauges[:]
                for gauge in gauges:
                    gauge.Hide()
                    gauge.Destroy()


    def get_selected_infohashes(self):
        return self.GetSelectionData()


    def rerender_col(self, col):
        for infohash, lr in self.itemData_to_row.iteritems():
            HashableListView.InsertRow(self, infohash, lr, sort=False,
                                       force_update_columns=[col])


    def update_torrent(self, torrent_object):
        state = (torrent_object.state,
                 torrent_object.policy,
                 torrent_object.completed)
        eta = torrent_object.statistics.get('timeEst' , None)
        up_rate = torrent_object.statistics.get('upRate'  , None)
        down_rate = torrent_object.statistics.get('downRate', None)
        peers = torrent_object.statistics.get('numPeers', None)

        row = self.GetRowFromKey(torrent_object.infohash)

        ur = Rate(up_rate)

        if (torrent_object.completion < 1.0) or (down_rate > 0):
            dr = Rate(down_rate)
        else:
            dr = Rate()

        eta = Duration(eta)
        priority = frontend_priority[torrent_object.priority]

        lr = BTListRow(None, {'state': state,
                              'name': row['name'],
                              'progress': percentify(torrent_object.completion,
                                                     torrent_object.completed),
                              'eta': eta,
                              'urate': ur,
                              'drate': dr,
                              'priority': priority,
                              'peers': peers})
        HashableListView.InsertRow(self, torrent_object.infohash, lr, sort=False)

        if not self.columns['progress'].enabled:
            return

        try:
            completion = float(completion)
        except:
            completion = 0.0

        # FIXME -- holy crap, re-factor so we don't have to repaint gauges here
        if row.index >= len(self.gauges):
            self._gauge_paint()

        gauge = self.gauges[row.index]

        gauge.SetValue(torrent_object.completion,
                       torrent_object.state,
                       torrent_object.piece_states)


    def get_column_image(self, row):
        value = row['state']

        imageindex = self.image_list_offset
        if value is not None:
            imageindex += image_numbers[state_images[value]]

        # Don't overflow the image list, even if we get a wacky state
        return min(imageindex, len(image_names)+self.image_list_offset)


VERBOSE = False

class PeerListView(HashableListView):

    def __init__(self, torrent, *a, **k):
        self.columns = {'ip': BTListColumn(_('IP address'),
                                           '255.255.255.255',
                                           comparator=ip_sort),
                        'client': BTListColumn(_('Client'),
                                               # extra .0 needed to make it just a little wider
                                               'BitTorrent 5.0.0.0',
                                               renderer=unicode),
                        'id': BTListColumn(_('Peer id'),
                                           'M5-0-0--888888888888',
                                           renderer=lambda v: repr(v)[1:-1],
                                           enabled=VERBOSE),
                        'initiation': BTListColumn(_('Initiation'),
                                                   'remote'),
                        'down_rate': BTListColumn(_('KB/s down'),
                                                  Rate(1024**2 - 1)),
                        'up_rate': BTListColumn(_('KB/s up'),
                                                Rate(1024**2 - 1)),
                        'down_size': BTListColumn(_('MB downloaded'),
                                                  Size(1024**3 - 1)),
                        'up_size': BTListColumn(_('MB uploaded'),
                                                Size(1024**3 - 1)),
                        'completed': BTListColumn(_('% complete'),
                                                  1.0,
                                                  renderer=lambda v: '%.1f'%round(int(v*1000)/10, 1)),
                        'speed': BTListColumn(_('KB/s est. peer download'),
                                              Rate(1024**2 - 1))
                        }

        self.column_order = ['ip', 'id', 'client', 'completed',
                             'down_rate', 'up_rate', 'down_size', 'up_size',
                             'speed', 'initiation']


        HashableListView.__init__(self, *a, **k)

        self.torrent = torrent

        # add BT logo
        # wx.Image under wx 2.6.2 doesn't like to load ICO files this way:
        ##i = wx.Image(os.path.join(image_root, 'bittorrent.ico'),
        ##             type=wx.BITMAP_TYPE_ICO, index=4)
        i = wx.Image(os.path.join(image_root, 'logo', 'bittorrent_icon_16.png'),
                     type=wx.BITMAP_TYPE_PNG)
        b = wx.BitmapFromImage(i)
        assert b.Ok(), "The image (%s) is not valid." % name
        self.il.Add(b)

        # add flags
        self.image_list_offset = self.il.GetImageCount()
        flag_images = os.listdir(os.path.join(image_root, 'flags'))
        flag_images.sort()
        self.cc_index = {}
        image_library = wx.the_app.image_library
        for f in flag_images:
            f = f.rsplit('.')[0]
            if len(f) == 2 or f in ('unknown', 'noimage'):
                name = ('flags', f)
                i = self.add_image(image_library.get(name))
                self.cc_index[f] = i
        self.set_default_widths()

        self.Bind(wx.EVT_CONTEXT_MENU, self.OnContextMenu)

    def OnContextMenu(self, event):
        m = wx.Menu()
        id = wx.NewId()
        m.Append(id, _("Add Peer"))
        self.Bind(wx.EVT_MENU, self.AddPeer, id=id)
        self.PopupMenu(m)

    def AddPeer(self, event):
        text = wx.GetTextFromUser(_("Enter new peer in IP:port format"), _("Add Peer"))
        try:
            ip, port = text.split(':')
            ip = str(ip)
            port = int(port)
        except:
            return

        self.torrent.torrent._connection_manager.start_connection((ip, port), None)


    def update_peers(self, peers, bad_peers):

        old_peers = set(self.itemData_to_row.keys())

        for peer in peers:
            peerid = peer['id']
            data = {}
            assert isinstance(peer['ip'], (str, unicode)), "Expected a string "\
                   "for IP address in UP, got a %s: '%s' instead." % \
                   (str(type(peer['ip'])), str(peer['ip']))
            for k in ('ip', 'completed'):
                data[k] = peer[k]

            for k in ('id',):
                data[k] = peer[k]

            client, version = ClientIdentifier.identify_client(peerid)
            data['client'] = client + ' ' + version

            # ew!
            #data['initiation'] = peer['initiation'] == 'R' and _("remote") or _("local")
            if peer['initiation'].startswith('R'):
                data['initiation'] = _("remote")
            else:
                data['initiation'] = _("local")

            dl = peer['download']
            ul = peer['upload']
            data['down_rate'] = Rate(dl[1], precision=1024)
            data['up_rate'  ] = Rate(ul[1], precision=1024)
            data['down_size'] = Size(dl[0], precision=1024**2)
            data['up_size'  ] = Size(ul[0], precision=1024**2)

            data['speed'] = Rate(peer['speed'])

            colour = None

            they_interested, they_choke, they_snub = dl[2:5]
            me_interested, me_choke = ul[2:4]
            strength = sum((not they_interested, they_choke, they_snub,
                            not me_interested, me_choke,
                            not peer['is_optimistic_unchoke']))/6
            c = int(192 * strength)
            colour = wx.Colour(c, c, c)

            if peer['ip'] in bad_peers:
                bad, perip = bad_peers[peer['ip']]
                if perip.peerid == peer['id']:
                    # color bad peers red
                    colour = wx.RED

            lr = BTListRow(None, data)
            self.InsertRow(peerid, lr, sort=False, colour=colour)
            old_peers.discard(peerid)

        for old_peer in old_peers:
            self.DeleteRow(old_peer)

        if len(old_peers) > 0:
            # force a background erase, since the number of items has decreased
            self.OnEraseBackground()

        self.SortItems()


    def get_column_image(self, row):
        ip_address = row['ip']

        if isinstance(ip_address, (str, unicode)):
            # BitTorrent seeds
            if ip_address.startswith('38.114.167.') and \
               63 < int(ip_address[11:]) < 128:
                return self.image_list_offset - 1

            cc, country = lookup(ip_address)
            if cc == '--':
                cc = 'unknown'
        else:
            # BUG: sometimes the backend gives us an int
            ns = 'core.MultiTorrent.' + repr(self.torrent.infohash)
            l = logging.getLogger(ns)
            l.error("Expected a string for IP address in GCI, got a %s: '%s' instead." % (str(type(ip_address)), str(ip_address)))
            wx.the_app.logger.error("Expected a string for IP address in GCI, got a %s: '%s' instead." % (str(type(ip_address)), str(ip_address)))
            cc = 'unknown'

        index = self.cc_index.get(cc, self.cc_index['noimage'])
        # for finding popular countries that we don't have flags for yet
##        if index == self.cc_index['noimage']:
##            if cc not in unknown_ccs:
##                print cc, country
##                unknown_ccs.add(cc)
        return index

##unknown_ccs = set()



class BTToolBar(wx.ToolBar):

    default_style = wx.TB_HORIZONTAL|wx.NO_BORDER|wx.TB_NODIVIDER|wx.TB_FLAT
    default_size = 16

    def __init__(self, parent, ops=[], *a, **k):
        size = wx.the_app.config['toolbar_size']
        self.size = size

        style = self.default_style
        config = wx.the_app.config
        if config['toolbar_text']:
            style |= wx.TB_TEXT

        wx.ToolBar.__init__(self, parent, style=style, **k)

        self.SetToolBitmapSize((size,size))

        while ops:
            opset = ops.pop(0)
            for e in opset:
                if issubclass(type(e.image), (str,unicode)):
                    bmp = wx.ArtProvider.GetBitmap(e.image, wx.ART_TOOLBAR, (size,size))
                elif type(e.image) is tuple:
                    i = wx.the_app.theme_library.get(e.image, self.size)
                    bmp = wx.BitmapFromImage(i)
                    assert bmp.Ok(), "The image (%s) is not valid." % image
                self.AddLabelTool(e.id, e.label, bmp, shortHelp=e.shorthelp)

            if len(ops):
                self.AddSeparator()

        self.Realize()



class DownloaderToolBar(BTToolBar):

    def __init__(self, parent, ops=[], *a, **k):
        ops = [[op for op in opset if op.in_toolbar] for opset in ops]
        BTToolBar.__init__(self, parent, ops=ops, *a, **k)
        self.stop_button = self.FindById(STOP_ID)
        self.start_button = self.FindById(START_ID)
        self.RemoveTool(START_ID)
        self.stop_start_position = self.GetToolPos(STOP_ID)

##        self.priority = wx.Choice(parent=self, id=wx.ID_ANY, choices=[_("High"), _("Normal"), _("Low")])
##        self.priority.SetSelection(1)
##        self.AddControl(self.priority)

        self.Realize()


    def toggle_stop_start_button(self, show_stop_button=False):
        changed = False
        if show_stop_button:
            sb = self.FindById(START_ID)
            if sb:
                changed = True
                self.RemoveTool(START_ID)
                self.InsertToolItem(self.stop_start_position, self.stop_button)
        else:
            sb = self.FindById(STOP_ID)
            if sb:
                changed = True
                self.RemoveTool(STOP_ID)
                self.InsertToolItem(self.stop_start_position, self.start_button)
        if changed:
            self.Realize()
        return changed



class FileListView(TreeListCtrl):
    priority_names = {1: _("first"), 0: '', -1: _("never")}
    sample_row = ('M'*30, unicode(Size(1024**3 - 1)), "%.1f" % 100.0, 'normal')
    colors = {-1: wx.Colour(192,192,192),
               0: wx.Colour(  0,  0,  0),
               1: wx.Colour( 32,128, 32),
              }

    def __init__(self, parent, torrent):
        self.torrent = torrent
        TreeListCtrl.__init__(self, parent, style=wx.TR_DEFAULT_STYLE|wx.TR_FULL_ROW_HIGHLIGHT|wx.TR_MULTIPLE|wx.WS_EX_PROCESS_IDLE)

        size = (16,16)
        il = wx.ImageList(*size)
        self.folder_index      = il.Add(wx.ArtProvider_GetBitmap(wx.ART_FOLDER,      wx.ART_OTHER, size))
        self.folder_open_index = il.Add(wx.ArtProvider_GetBitmap(wx.ART_FOLDER_OPEN, wx.ART_OTHER, size))
        self.file_index        = il.Add(wx.ArtProvider_GetBitmap(wx.ART_NORMAL_FILE, wx.ART_OTHER, size))

        self.SetImageList(il)
        self.il = il

        self.path_items = {}

        self.AddColumn(_("Name"    ))
        self.AddColumn(_("Size"    ))
        self.AddColumn(_("%"       ))
        self.AddColumn(_("Download"))
        self.SetMainColumn(0)

        metainfo = self.torrent.metainfo

        self.root = self.AddRoot(metainfo.name)
        self.SetItemImage(self.root, self.folder_index     , which=wx.TreeItemIcon_Normal  )
        self.SetItemImage(self.root, self.folder_open_index, which=wx.TreeItemIcon_Expanded)

        dc = wx.ClientDC(self)
        for c, t in enumerate(self.sample_row):
            w, h = dc.GetTextExtent(t)
            self.SetColumnWidth(c, w+2)

        if metainfo.is_batch:
            files = metainfo.orig_files
        else:
            files = [ ]
        for i, f in enumerate(files):
            path, filename = os.path.split(f)
            parent = self.find_path(path, self.root)
            child = self.AppendItem(parent, filename)
            self.Expand(parent)
            self.path_items[f] = child
            self.SetItemText(child, unicode(Size(metainfo.sizes[i])), 1)
            self.SetItemText(child, '?', 2)
            self.SetItemData(child, wx.TreeItemData(f))
            self.SetItemImage(child, self.file_index, which=wx.TreeItemIcon_Normal)
        self.EnsureVisible(self.root)
        self.Refresh()
        self.Bind(wx.EVT_TREE_ITEM_RIGHT_CLICK, self.OnPopupMenu)


    def OnPopupMenu(self, event):
        p = event.GetPoint()
        # sure would be cool if this method were documented
        item, some_random_number, seems_to_always_be_zero = self.HitTest(p)
        if not self.IsSelected(item):
            # hey, this would be a cool one to document too
            self.SelectItem(item, unselect_others=True, extended_select=False)
        self.PopupMenu(self.context_menu)


    def find_path(self, path, parent=None):
        """Finds the node associated with path under parent, and creates it if it doesn't exist"""
        components = []
        if parent == None:
            parent = self.root
        while True:
            parent_path, local_path = os.path.split(path)
            if local_path == '':
                break
            components.append(local_path)
            path = parent_path

        l = len(components)
        for i in xrange(l):
            parent = self.find_child(parent, components[(l-1)-i], create=True)

        return parent


    def find_child(self, parent, childname, create=False):
        """Finds the node child under parent, and creates it if it doesn't exist"""
        i, c = self.GetFirstChild(parent)
        while i.IsOk():
            text = self.GetItemText(i, 0)
            if text == childname:
                break
            i, c = self.GetNextChild(parent, c)
        else:
            i = self.AppendItem(parent, childname)
            self.Expand(parent)
            self.SetItemData(i, wx.TreeItemData(childname))
            self.SetItemImage(i, self.folder_index     , which=wx.TreeItemIcon_Normal  )
            self.SetItemImage(i, self.folder_open_index, which=wx.TreeItemIcon_Expanded)
        return i


    def update_files(self, left, priorities):
        metainfo = self.torrent.metainfo
        for name, left, total, in itertools.izip(metainfo.orig_files, left, metainfo.sizes):
            if total == 0:
                p = 1
            else:
                p = (total - left) / total
            item = self.path_items[name]
            newvalue = "%.1f" % (int(p * 1000)/10)
            oldvalue = self.GetItemText(item, 2)
            if oldvalue != newvalue:
                self.SetItemText(item, newvalue, 2)
            if name in priorities:
                self.set_priority(item, priorities[name])


    def get_complete_files(self, files):
        complete_files = []
        for f in files:
            item = self.path_items[f]
            if self.get_file_completion(item):
                complete_files.append(f)
        return complete_files


    def get_item_completion(self, item):
        if self.ItemHasChildren(item):
            return True
        return self.get_file_completion(item)


    def get_file_completion(self, item):
        completion = self.GetItemText(item, 2)
        if completion == '100.0': # BUG HACK HACK HACK
            return True
        return False


    def get_selected_files(self, priority=None):
        """Get selected files, directories, and all descendents.  For
        (batch) setting file priorities."""
        selected_items = self.GetSelections()
        items = []
        data  = []
        for i in selected_items:
            if not self.ItemHasChildren(i):
                data.append(self.GetPyData(i))
                items.append(i)
            else:
                descendents = self.get_all_descendents(i)
                items.extend(descendents)
                for d in descendents:
                    data.append(self.GetPyData(d))
        if priority is not None:
            self.set_priorities(items, priority)
        return data


    def get_all_descendents(self, item):
        """Get all descendents of this item.  For (batch) setting file
        priorities."""
        descendents = []
        i, c = self.GetFirstChild(item)
        while i.IsOk():
            if self.ItemHasChildren(i):
                d = self.get_all_descendents(i)
                descendents.extend(d)
            else:
                descendents.append(i)
            i, c = self.GetNextChild(item, c)
        return descendents


    def get_selection(self):
        """Get just the selected files/directories, not including
        descendents.  For checking toolbar state and handling
        double-click."""
        selected_items = self.GetSelections()
        dirs, files = [], []
        for i in selected_items:
            if not self.ItemHasChildren(i):
                files.append(self.GetPyData(i))
            else:
                dirs.append(self.GetPyData(i))
        return dirs, files


    def set_priority(self, item, priority):
        priority_label = self.priority_names[priority]
        self.SetItemText(item, priority_label, 3)
        self.SetItemTextColour(item, colour=self.colors[priority])


    def set_priorities(self, items, priority):
        priority_label = self.priority_names[priority]
        for item in items:
            self.SetItemText(item, priority_label, 3)



class FileListPanel(BTPanel):

    FIRST_ID  = wx.NewId()
    NORMAL_ID = wx.NewId()
    NEVER_ID  = wx.NewId()
    OPEN_ID   = wx.NewId()

    def __init__(self, parent, torrent, *a, **k):
        BTPanel.__init__(self, parent, *a, **k)
        self.torrent = torrent

        app = wx.the_app
        self.file_ops = [
            EventProperties(self.FIRST_ID,
                            ('fileops', 'first'),
                            self.set_file_priority_first,
                            _("First"), _("Download first")),
            EventProperties(self.NORMAL_ID,
                            ('fileops', 'normal'),
                            self.set_file_priority_normal,
                            _("Normal"), _("Download normally")),
##            # BUG: uncomment this once we implement NEVER
##            EventProperties(self.NEVER_ID,
##                            ('fileops', 'never'),
##                            self.set_file_priority_never,
##                            _("Never"), _("Never download")),
            EventProperties(self.OPEN_ID,
                            ('torrentops', 'launch'),
                            self.open_items,
                            _("Launch"), _("Launch file")),
            ]

        self.context_menu = BTMenu()

        self.event_table = {}
        for e in self.file_ops:
            self.event_table[e.id] = e
            self.Bind(wx.EVT_MENU, self.OnFileEvent, id=e.id)
            self.context_menu.Append(e.id, e.shorthelp)
        self.context_menu.InsertSeparator(len(self.file_ops)-1)

        self._build_tool_bar()

        self.file_list = FileListView(self, torrent)
        self.sizer.Add(self.file_list, flag=wx.GROW, proportion=1)

        self.SetSizerAndFit(self.sizer)

        self.check_file_selection()
        self.file_list.Bind(wx.EVT_TREE_SEL_CHANGED, self.check_file_selection)
        self.file_list.Bind(wx.EVT_TREE_ITEM_ACTIVATED, self.file_double_clicked)

        self.file_list.context_menu = self.context_menu


    def check_file_selection(self, event=None):
        items = self.file_list.GetSelections()

        if len(items) < 1:
            for i in(self.NEVER_ID, self.NORMAL_ID, self.FIRST_ID, self.OPEN_ID):
                self.tool_bar.EnableTool(i, False)
        elif len(items) == 1:
            for i in(self.NEVER_ID, self.NORMAL_ID, self.FIRST_ID):
                self.tool_bar.EnableTool(i, True)
            self.tool_bar.EnableTool(self.OPEN_ID, self.file_list.get_item_completion(items[0]))
            self.context_menu.Enable(self.OPEN_ID, self.file_list.get_item_completion(items[0]))
        else:
            for i in(self.NEVER_ID, self.NORMAL_ID, self.FIRST_ID):
                self.tool_bar.EnableTool(i, True)
            self.tool_bar.EnableTool(self.OPEN_ID, False)
            self.context_menu.Enable(self.OPEN_ID, False)
        if event is not None:
            event.Skip()


    def _build_tool_bar(self):
        self.tool_bar = BTToolBar(self, ops=[self.file_ops])
        self.tool_bar.InsertSeparator(len(self.file_ops)-1)
        self.tool_bar.Realize()
        self.sizer.Insert(0, self.tool_bar, flag=wx.GROW, proportion=0)


    def reset_toolbar_style(self):
        found = self.sizer.Detach(self.tool_bar)
        if found:
            # Keep the old bars around just in case they get a
            # callback before we build new ones
            b = self.tool_bar
        # build the new bar
        self._build_tool_bar()
        if found:
            # destroy the old bar now that there's a new one
            b.Destroy()
        self.sizer.Layout()


    def BindChildren(self, evt_id, func):
        self.file_list.Bind(evt_id, func)


    def OnFileEvent(self, event):
        id = event.GetId()
        if self.event_table.has_key(id):
            e = self.event_table[id]
            df = launch_coroutine(gui_wrap, e.func)
            def error(exc_info):
                ns = 'core.MultiTorrent.' + repr(self.torrent.infohash)
                l = logging.getLogger(ns)
                l.error(e.func.__name__ + " failed", exc_info=exc_info)
            df.addErrback(error)
        else:
            print 'Not implemented!'


    def set_file_priority_first(self):
        self.set_file_priority(1)


    def set_file_priority_normal(self):
        self.set_file_priority(0)


    def set_file_priority_never(self):
        # BUG: Not implemented
        ## self.set_file_priority(-1)
        print 'Not implemented!'


    def set_file_priority(self, priority):
        files = self.file_list.get_selected_files(priority=priority)
        wx.the_app.set_file_priority(self.torrent.infohash, files, priority)


    def open_items(self):
        if self.torrent.completion >= 1:
            path = self.torrent.destination_path
        else:
            path = self.torrent.working_path
        dirs, files = self.file_list.get_selection()
        for d in dirs:
            if d is None:
                LaunchPath.launchdir(path)
            else:
                LaunchPath.launchdir(os.path.join(path, d))

        # only launch complete files
        complete_files = self.file_list.get_complete_files(files)
        for f in complete_files:
            LaunchPath.launchfile(os.path.join(path, f))


    def file_double_clicked(self, event):
        self.open_items()


    def update(self, *args):
        self.file_list.update_files(*args)
        self.check_file_selection()



class LogPanel(BTPanel):

    def __init__(self, parent, torrent, *a, **k):
        BTPanel.__init__(self, parent, *a, **k)

        self.log = wx.TextCtrl(self, id=wx.ID_ANY,
                                   value='',
                                   style=wx.TE_MULTILINE|wx.TE_READONLY)
        self.Add(self.log, flag=wx.GROW, proportion=1)

        class MyTorrentLogger(logging.Handler):
            def set_log_func(self, func):
                self.log_func = func

            def emit(self, record):
                gui_wrap(self.log_func, self.format(record) + '\n')

        l = MyTorrentLogger()
        l.setFormatter(bt_log_fmt)
        l.set_log_func(self.log.AppendText)
        torrent.handler.setTarget(l)
        torrent.handler.flush()


    def BindChildren(self, evt_id, func):
        self.log.Bind(evt_id, func)


class TorrentDetailsPanel(wx.ScrolledWindow):

    def __init__(self, parent, torrent, *a, **k):
        k['style'] = k.get('style', 0) | wx.HSCROLL | wx.VSCROLL
        k.setdefault('size', wx.DefaultSize)
        wx.ScrolledWindow.__init__(self, parent, *a, **k)
        self.torrent = torrent

        self.panel = wx.Panel(self)
        self.sizer = VSizer()

        self.swarm_fgsizer = LabelValueFlexGridSizer(self.panel,5,2,SPACING,SPACING)
        self.swarm_fgsizer.SetFlexibleDirection(wx.HORIZONTAL)

        self.swarm_static_box = wx.StaticBox(self.panel, label=_("Swarm:"))
        self.swarm_static_box_sizer = wx.StaticBoxSizer(self.swarm_static_box, wx.HORIZONTAL)
        self.swarm_static_box_sizer.Add(self.swarm_fgsizer, flag=wx.GROW|wx.ALL, border=SPACING)
        self.sizer.AddFirst(self.swarm_static_box_sizer, flag=wx.GROW, border=SPACING)

        for label, item in zip((_("Tracker total peers:"), _("Distributed copies:"), _("Swarm speed:"), _("Discarded data:"), _("Next announce:"),),
                               ('tracker_peers'    , 'distributed'           , 'swarm_speed'    , 'discarded'         , 'announce'         ,)):
            t = self.swarm_fgsizer.add_pair(label, '')
            self.__dict__[item] = t

        metainfo = self.torrent.metainfo

        rows = 4
        if metainfo.announce_list is not None:
            rows += sum([len(l) for l in metainfo.announce_list]) - 1

        self.torrent_fgsizer = LabelValueFlexGridSizer(self.panel, rows,2,SPACING,SPACING)
        self.torrent_fgsizer.SetFlexibleDirection(wx.HORIZONTAL)

        self.torrent_static_box = wx.StaticBox(self.panel, label=_("Torrent file:"))
        self.torrent_static_box_sizer = wx.StaticBoxSizer(self.torrent_static_box, wx.HORIZONTAL)
        self.torrent_static_box_sizer.Add(self.torrent_fgsizer, flag=wx.GROW|wx.ALL, border=SPACING)

        self.sizer.Add(self.torrent_static_box_sizer, flag=wx.GROW, border=SPACING)


        # announce             Singular       Plural            Backup, singular      Backup, plural
        announce_labels = ((_("Tracker:"), _("Trackers:")), (_("Backup tracker:"), _("Backup trackers:")))
        if metainfo.is_trackerless:
            self.torrent_fgsizer.add_pair(announce_labels[0][0], _("(trackerless torrent)"))
        else:
            if metainfo.announce_list is None:
                self.torrent_fgsizer.add_pair(announce_labels[0][0], metainfo.announce)
            else:
                for i, l in enumerate(metainfo.announce_list):
                    label = announce_labels[i!=0][len(l)!=1]
                    self.torrent_fgsizer.add_pair(label, l[0])
                    for t in l[1:]:
                        self.torrent_fgsizer.add_pair('', t)

        # infohash
        self.torrent_fgsizer.add_pair(_("Infohash:"), repr(metainfo.infohash))

        # pieces
        pl = metainfo.piece_length
        tl = metainfo.total_bytes
        count, lastlen = divmod(tl, pl)

        pieces = "%s x %d + %s" % (Size(pl), count, Size(lastlen))
        self.torrent_fgsizer.add_pair(_("Pieces:"), pieces)

        self.piece_count = count + (lastlen > 0)

        # creation date
        time_str = time.asctime(time.localtime(metainfo.creation_date))

        self.torrent_fgsizer.add_pair(_("Created on:"), time_str)

        self.panel.SetSizerAndFit(self.sizer)

        size = self.sizer.GetMinSize()
        self.SetVirtualSize(size)
        self.SetScrollRate(1,1)


    def GetBestFittingSize(self):
        ssbs = self.swarm_static_box_sizer.GetMinSize()
        tsbs = self.torrent_static_box_sizer.GetMinSize()
        return wx.Size(max(ssbs.x, tsbs.x) + SPACING*4, ssbs.y + SPACING)


    def update(self, statistics):
        tp = statistics.get('trackerPeers', None)
        ts = statistics.get('trackerSeeds', None)

        if tp is None:
            self.tracker_peers.SetLabel(_('Unknown'))
        elif (ts is None) or (ts == 0):
            self.tracker_peers.SetLabel('%s' % (str(tp),))
        elif ts == tp:
            self.tracker_peers.SetLabel(_('%s (all seeds)') % (str(tp),))
        elif ts == 1:
            self.tracker_peers.SetLabel(_('%s (%s seed)') % (str(tp), str(ts)))
        else:
            self.tracker_peers.SetLabel(_('%s (%s seeds)') % (str(tp), str(ts)))

        dc = statistics.get('distributed_copies', -1)
        if dc >= 0:
            dist_label = '%0.2f' % dc
        else:
            dist_label = '?'

        self.distributed.SetLabel(dist_label)

        # BUG: this shows how many pieces are being transferred, do we want to show it?
        # BUG: If you want that, let me know and I'll implement it correctly. - Greg

        self.discarded.SetLabel(unicode(Size(statistics.get('discarded',0))))
        self.swarm_speed.SetLabel(unicode(Rate(statistics.get('swarm_speed',0))))
        t = statistics.get('announceTime')
        if t is not None:
            self.announce.SetLabel(unicode(Duration(t*-1)))
        else:
            # TODO: None means the torrent is not initialized yet
            self.announce.SetLabel('?')



class TorrentInfoPanel(BTPanel):

    def __init__(self, parent, torrent, *a, **k):
        BTPanel.__init__(self, parent, *a, **k)
        self.parent = parent
        self.torrent = torrent
        metainfo = self.torrent.metainfo

        vspacing = SPACING
        hspacing = SPACING
        if os.name == 'nt':
            vspacing /= 2
            hspacing *= 3

        # title
        self.title_sizer = LabelValueFlexGridSizer(self, 1, 2, vspacing, SPACING)
        self.title_sizer.SetFlexibleDirection(wx.HORIZONTAL)

        if metainfo.title is not None:
            self.title_sizer.add_pair(_("Torrent title:"), metainfo.title.replace('&', '&&'))
        else:
            self.title_sizer.add_pair(_("Torrent name:"), metainfo.name.replace('&', '&&'))

        self.Add(self.title_sizer, flag=wx.ALL, border=SPACING)

        # dynamic info
        self.dynamic_sizer = LabelValueFlexGridSizer(self, 2, 4, vspacing, hspacing)
        self.dynamic_sizer.SetFlexibleDirection(wx.HORIZONTAL)
        self.dynamic_sizer.SetMinSize((350, -1))

        self.download_rate = self.dynamic_sizer.add_pair(_("Download rate:"), '')
        self.upload_rate = self.dynamic_sizer.add_pair(_("Upload rate:"), '')
        self.time_remaining = self.dynamic_sizer.add_pair(_("Time remaining:"), '')
        self.peers = self.dynamic_sizer.add_pair(_("Peers:"), '')
        self.eta_inserted = True

        self.Add(self.dynamic_sizer, flag=wx.ALL^wx.TOP, border=SPACING)

        self.piece_bar = FancyDownloadGauge(self, border=False, size=wx.Size(-1, -1), style=wx.SUNKEN_BORDER)
        self.Add(self.piece_bar, flag=wx.GROW|wx.ALL^wx.TOP, border=SPACING)

        # static info
        self.static_sizer = LabelValueFlexGridSizer(self, 4, 2, vspacing, hspacing)

        # original filename
        fullpath = self.torrent.destination_path

        if fullpath is not None:
            path, filename = os.path.split(fullpath)
            filename = path_wrap(filename)
            path = path_wrap(path)
            if not metainfo.is_batch:
                self.static_sizer.add_pair(_("File name:"), filename.replace('&', '&&'))
##                if filename != metainfo.name:
##                    self.static_sizer.add_pair(_("Original file name:"), metainfo.name.replace('&', '&&'))
            else:
                self.static_sizer.add_pair(_("Directory name:"), filename.replace('&', '&&'))
##                if filename != metainfo.name:
##                    self.static_sizer.add_pair(_("Original directory name:"), metainfo.name.replace('&', '&&'))

            if path[:-1] != os.sep:
                path += os.sep
            self.static_sizer.add_pair(_("Save in:"), path.replace('&', '&&'))

        # size
        size = Size(metainfo.total_bytes)
        num_files = _(", in one file")
        if metainfo.is_batch:
            num_files = _(", in %d files") % len(metainfo.sizes)
        self.static_sizer.add_pair(_("Total size:"), unicode(size)+num_files)

        self.Add(self.static_sizer, flag=wx.ALL^wx.TOP, border=SPACING)



    def change_to_completed(self):
        # Remove various download stats.
        for i in (5,4,1,0):
            si = self.dynamic_sizer.GetItem(i)
            w = si.GetWindow()
            self.dynamic_sizer.Detach(i)
            w.Hide()
            w.Destroy()
        self.dynamic_sizer.Layout()
        self.GetParent().GetSizer().Layout()


    def change_label(self, stats, widget, key, renderer):
        ov = widget.GetLabel()
        nv = unicode(renderer(stats.get(key, None)))
        if ov != nv:
            widget.SetLabel(nv)
            return True
        return False


    def update(self, statistics):
        layout = False


        # set uprate
        if self.change_label(statistics, self.upload_rate, 'upRate', Rate):
            layout = True


        # set peers
        np = statistics.get('numPeers', 0)
        ns = statistics.get('numSeeds', 0)

        if ns == 0:
            nv = '%s' % (str(np),)
        elif ns == np:
            nv = _('%s (all seeds)') % (str(np),)
        elif ns == 1:
            nv = _('%s (%s seed)') % (str(np), str(ns))
        else:
            nv = _('%s (%s seeds)') % (str(np), str(ns))

        ov = self.peers.GetLabel()
        if ov != nv:
            self.peers.SetLabel(nv)
            layout = True


        # if the torrent is not finished, set some other stuff, too
        if not self.parent.completed:
            for w, k, r in zip((self.time_remaining, self.download_rate),
                               ('timeEst', 'downRate'),
                               (Duration, Rate)):
                if self.change_label(statistics, w, k, r):
                    layout = True


        # layout if necessary
        if layout:
            self.dynamic_sizer.Layout()

        self.piece_bar.SetValue(self.torrent.completion, self.torrent.state, self.torrent.piece_states)



class TorrentPanel(BTPanel):
    sizer_class = wx.FlexGridSizer
    sizer_args = (3, 1, 0, 0)

    def __init__(self, parent, *a, **k):
        BTPanel.__init__(self, parent, *a, **k)
        self.torrent = parent.torrent
        self.details_shown = False
        self.parent = parent
        self.completed = False

        self.torrent_info = TorrentInfoPanel(self, self.torrent)
        self.sizer.Add(self.torrent_info, flag=wx.GROW)
        self.sizer.AddGrowableRow(0)
        self.sizer.AddGrowableRow(2)
        self.sizer.AddGrowableCol(0)

        self.outer_button_sizer = wx.FlexGridSizer(1, 2, SPACING, SPACING)
        self.outer_button_sizer.AddGrowableCol(0)
        self.left_button_sizer = HSizer()
        self.outer_button_sizer.Add(self.left_button_sizer)
        self.right_button_sizer = HSizer()
        self.outer_button_sizer.Add(self.right_button_sizer)

        self.details_button = wx.Button(parent=self, id=wx.ID_ANY, label=_("Show &Details"))
        self.details_button.Bind(wx.EVT_BUTTON, self.toggle_details)

        self.open_button = wx.Button(parent=self, id=wx.ID_OPEN)
        self.open_button.Bind(wx.EVT_BUTTON, self.open_torrent)
        self.open_folder_button = wx.Button(parent=self, id=wx.ID_ANY, label=_("Open &Folder"))
        self.open_folder_button.Bind(wx.EVT_BUTTON, self.open_folder)

        self.left_button_sizer.Add(self.details_button,
                                   flag=wx.ALIGN_LEFT|wx.LEFT,
                                   border=SPACING)
        self.right_button_sizer.Add(self.open_button,
                                    flag=wx.RIGHT,
                                    border=SPACING)
        self.right_button_sizer.Add(self.open_folder_button,
                                    flag=wx.RIGHT,
                                    border=SPACING)

        self.open_button.Disable()
        if self.torrent.metainfo.is_batch:
            self.open_button.Hide()

        self.sizer.Add(self.outer_button_sizer, flag=wx.GROW|wx.ALIGN_BOTTOM, border=0)

        self.notebook = wx.Notebook(self)
        self.speed_tab_index = None
        self.notebook.Bind(wx.EVT_NOTEBOOK_PAGE_CHANGING, self.OnPageChanging)
        self.notebook.Bind(wx.EVT_NOTEBOOK_PAGE_CHANGED, self.OnPageChanged)
        self.tab_height = self.notebook.GetBestFittingSize().y

        metainfo = self.torrent.metainfo
        if metainfo.comment not in (None, ''):
            self.comment_panel = BTPanel(self.notebook)
            self.notebook.AddPage(self.comment_panel, _("Comments"))
            self.comment = wx.TextCtrl(self.comment_panel, id=wx.ID_ANY,
                                       value=metainfo.comment,
                                       style=wx.TE_MULTILINE|wx.TE_READONLY)
            self.comment_panel.Add(self.comment, flag=wx.GROW, proportion=1)

        if metainfo.is_batch:
            self.file_tab_index = self.notebook.GetPageCount()
            self.file_list = FileListPanel(self.notebook, self.torrent)
            self.notebook.AddPage(self.file_list, _("File List"))

        self.peer_tab_index = self.notebook.GetPageCount()
        self.peer_tab_panel = wx.Panel(self.notebook)
        self.peer_tab_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.peer_list = PeerListView(self.torrent, self.peer_tab_panel)
        self.peer_tab_sizer.Add(self.peer_list, proportion=1, flag=wx.GROW)
        self.peer_tab_panel.SetSizerAndFit(self.peer_tab_sizer)
        self.peer_list.SortListItems(col='ip', ascending=1)
        self.notebook.AddPage(self.peer_tab_panel, _("Peer List"))

        self.bandwidth_panel = BandwidthGraphPanel(self.notebook, self.torrent.bandwidth_history)
        self.speed_tab_index = self.notebook.GetPageCount()
        self.notebook.AddPage(self.bandwidth_panel, _("Speed"))

        self.log_panel = LogPanel(self.notebook, self.torrent)
        self.notebook.AddPage(self.log_panel, _("Log"))

        self.torrent_panel = TorrentDetailsPanel(self.notebook, self.torrent)
        self.notebook.AddPage(self.torrent_panel, _("Torrent"))

        self.notebook.SetPageSize(wx.Size(300, 200))
        self.notebook.Hide()

        if self.torrent.completion >= 1:
            self.change_to_completed()

        self.sizer.Layout()


    def change_to_completed(self):
        self.completed = True
        self.torrent_info.change_to_completed()
        self.open_button.Enable()


    def toggle_details(self, event=None):
        if self.details_shown:
            self.sizer.AddGrowableRow(0)
            self.notebook.Hide()
            self.sizer.Detach(self.notebook)
            self.sizer.Layout()
            self.details_button.SetLabel(_("Show &Details"))
            self.parent.sizer.Fit(self.parent)
            self.details_shown = False
        else:
            self.sizer.RemoveGrowableRow(0)
            self.notebook.Show()
            self.sizer.Add(self.notebook, flag=wx.GROW, proportion=1)
            self.sizer.Layout()
            self.details_button.SetLabel(_("Hide &Details"))
            self.parent.sizer.Fit(self.parent)
            self.details_shown = True


    def open_torrent(self, event):
        wx.the_app.launch_torrent(self.torrent.metainfo.infohash)


    def open_folder(self, event):
        wx.the_app.launch_torrent_folder(self.torrent.metainfo.infohash)


    def BindChildren(self, evt_id, func):
        ws = [self.torrent_info, self.notebook, self.peer_list,
              self.bandwidth_panel, self.log_panel, self.torrent_panel]
        if self.torrent.metainfo.is_batch:
            ws.append(self.file_list)
        for w in ws:
            w.Bind(evt_id, func)
            if hasattr(w, 'BindChildren'):
                w.BindChildren(evt_id, func)


    def GetBestFittingSize(self):
        tis = self.torrent_info.GetBestFittingSize()
        tds = self.torrent_panel.GetBestFittingSize()
        x = min(max(tis.x, tds.x), 600)
        y = tis.y + tds.y + self.tab_height
        return wx.Size(x, y)

    def OnPageChanging(self, event):
        wx.the_app.make_statusrequest()

    def OnPageChanged(self, event):
        if event.GetSelection() == self.speed_tab_index:
            self.bandwidth_panel.update(force=True)
        event.Skip()

    def wants_peers(self):
        return self.IsShown() and self.peer_tab_index == self.notebook.GetSelection()


    def wants_files(self):
        return self.IsShown() and self.file_tab_index == self.notebook.GetSelection()


    def update_peers(self, peers, bad_peers):
        self.peer_list.update_peers(peers, bad_peers)


    def update_files(self, *args):
        self.file_list.update(*args)


    def update_swarm(self, statistics):
        self.torrent_panel.update(statistics)


    def update_info(self, statistics):
        if statistics.get('fractionDone', 0) >= 1 and not self.completed:
            # first update since the torrent finished. Remove various
            # download stats, enable open button.
            self.change_to_completed()

        self.torrent_info.update(statistics)


    def reset_toolbar_style(self):
        self.file_list.reset_toolbar_style()



class TorrentWindow(BTFrameWithSizer):
    panel_class = TorrentPanel

    def __init__(self, torrent, parent, *a, **k):
        self.torrent = torrent
        k['style'] = k.get('style', wx.DEFAULT_FRAME_STYLE) | wx.WANTS_CHARS
        BTFrameWithSizer.__init__(self, parent, *a, **k)
        self.Bind(wx.EVT_CLOSE, self.close)
        self.Bind(wx.EVT_CHAR, self.key)
        self.panel.BindChildren(wx.EVT_CHAR, self.key)
        self.sizer.Layout()
        self.Fit()
        self.SetMinSize(self.GetSize())

    def key(self, event):
        c = event.GetKeyCode()
        if c == wx.WXK_ESCAPE:
            self.close()
        event.Skip()


    def SortListItems(self, col=-1, ascending=1):
        self.panel.peer_list.SortListItems(col, ascending)


    def details_shown(self):
        return self.panel.details_shown


    def toggle_details(self):
        self.panel.toggle_details()


    def update_peers(self, peers, bad_peers):
        self.panel.update_peers(peers, bad_peers)


    def update_files(self, *args):
        self.panel.update_files(*args)


    def update_swarm(self, statistics):
        self.panel.update_swarm(statistics)


    def update_info(self, statistics):
        self.panel.update_info(statistics)


    def update(self, statistics):
        percent = percentify(self.torrent.completion, self.torrent.completed)
        if percent is not None:
            title=_('%.1f%% of %s')%(percent, self.torrent.metainfo.name)
        else:
            title=_('%s')%(self.torrent.metainfo.name)
        self.SetTitle(title)

        if self.IsShown():
            spew = statistics.get('spew', None)
            if spew is not None:
                self.update_peers(spew, statistics['bad_peers'])

            if self.torrent.metainfo.is_batch:
                self.update_files(statistics.get('files_left', {}),
                                  statistics.get('file_priorities', {}))

            self.update_swarm(statistics)
            self.update_info(statistics)


    def close(self, *e):
        self.Hide()


    def reset_toolbar_style(self):
        self.panel.reset_toolbar_style()


    def wants_peers(self):
        return self.IsShown() and self.panel.wants_peers()


    def wants_files(self):
        return self.IsShown() and self.panel.wants_files()



class AboutWindow(BTDialog):

    def __init__(self, main):
        BTDialog.__init__(self, main, size = (300,400),
                           style=wx.DEFAULT_DIALOG_STYLE|wx.CLIP_CHILDREN|wx.WANTS_CHARS)
        self.Bind(wx.EVT_CLOSE, self.close)
        self.SetTitle(_("About %s")%app_name)

        self.sizer = VSizer()

        i = wx.the_app.image_library.get(('logo', 'banner'))
        b = wx.BitmapFromImage(i)
        self.bitmap = ElectroStaticBitmap(self, b)

        self.sizer.AddFirst(self.bitmap, flag=wx.ALIGN_CENTER_HORIZONTAL)

        version_str = version
        if int(version_str[2]) % 2:
            version_str = version_str + ' ' + _("Beta")

        version_label = ElectroStaticText(self, label=_("Version %s")%version_str)
        self.sizer.Add(version_label, flag=wx.ALIGN_CENTER_HORIZONTAL)

        if branch is not None:
            blabel = ElectroStaticText(self, label='cdv client dir: %s' % branch)
            self.sizer.Add(blabel, flag=wx.ALIGN_CENTER_HORIZONTAL)

        self.credits_scroll     = CreditsScroll(self, 'credits', style=wx.TE_CENTRE)
        self.translators_scroll = CreditsScroll(self, 'credits-l10n')

        self.sizer.Add(self.credits_scroll    , flag=wx.GROW, proportion=1)
        self.sizer.Add(self.translators_scroll, flag=wx.GROW, proportion=1)

        self.credits_scroll.Hide()
        self.translators_scroll.Hide()

        self.button_sizer = HSizer()
        self.credits_button = wx.Button(parent=self, id=wx.ID_ANY, label=_("&Credits"))
        self.credits_button.Bind(wx.EVT_BUTTON, self.toggle_credits)

        self.translators_button = wx.Button(parent=self, id=wx.ID_ANY, label=_("&Translators"))
        self.translators_button.Bind(wx.EVT_BUTTON, self.toggle_translators)

        self.button_sizer.AddFirst(self.credits_button)
        self.button_sizer.Add(self.translators_button)

        self.translators_button.Hide()

        self.sizer.Add(self.button_sizer, flag=wx.ALIGN_CENTER_HORIZONTAL, proportion=0, border=0)

        self.SetSizer(self.sizer)
        self.Fit()

        for w in (self, self.bitmap,
                  self.credits_scroll, self.translators_scroll,
                  self.credits_button, self.translators_button, ):
            w.Bind(wx.EVT_CHAR, self.key)

        self.SetFocus()


    def close(self, *e):
        self.Hide()


    def key(self, event):
        c = event.GetKeyCode()
        if c == wx.WXK_ESCAPE:
            self.close()
        event.Skip()


    def toggle_credits(self, event):

        if self.credits_scroll.IsShown() or self.translators_scroll.IsShown():
            if self.translators_scroll.IsShown():
                self.toggle_translators(event)
            self.credits_scroll.Hide()
            self.credits_button.SetLabel(_("&Credits"))
            self.translators_button.Hide()
        else:
            self.credits_scroll.Show()
            self.credits_button.SetLabel(_("Hide &credits"))
            self.translators_button.Show()

        self.sizer.Layout()
        self.Fit()


    def toggle_translators(self, event):

        if self.translators_scroll.IsShown():
            self.translators_scroll.Hide()
            self.credits_scroll.Show()
            self.translators_button.SetLabel(_("&Translators"))
        else:
            self.credits_scroll.Hide()
            self.translators_scroll.Show()
            self.translators_button.SetLabel(_("Hide &translators"))

        self.sizer.Layout()
        self.Fit()



class LogWindow(wx.LogWindow, MagicShow):

    def __init__(self, *a, **k):
        wx.LogWindow.__init__(self, *a, **k)
        frame = self.GetFrame()
        frame.SetIcon(wx.the_app.icon)
        frame.GetStatusBar().Destroy()
        # don't give all log messages to their previous handlers
        # we'll enable this as we need it.
        self.PassMessages(False)

        # YUCK. Why is the log window not really a window?
        # Because it's a wxLog.
        self.magic_window = self.GetFrame()



class TorrentObject(BasicTorrentObject):
    """Object for holding all information about a torrent"""

    def __init__(self, torrent):
        BasicTorrentObject.__init__(self, torrent)
        self.bandwidth_history = HistoryCollector(wx.the_app.GRAPH_TIME_SPAN,
                                                  wx.the_app.GRAPH_UPDATE_INTERVAL)

        wx.the_app.torrent_logger.flush(self.infohash, self.handler)

        self._torrent_window = None
        self.restore_window()


    def restore_window(self):
        if self.torrent.config.get('window_shown', False):
            self.torrent_window.MagicShow()


    def _get_torrent_window(self):
        if self._torrent_window is None:
            self._torrent_window = TorrentWindow(self,
                                                 None,
                                                 id=wx.ID_ANY,
                                                 title=_('%s')%self.metainfo.name)
            if self.torrent.config.get('details_shown', False):
                self._torrent_window.toggle_details()
            g = self.torrent.config.get('window_geometry', '')
            size = self._torrent_window.GetBestFittingSize()
            self._torrent_window.load_geometry(g, default_size=size)
            self._torrent_window.panel.notebook.SetSelection(self.torrent.config.get('window_tab', 0))
            if self.torrent.config.get('window_maximized', False):
                gui_wrap(self._torrent_window.Maximize, True)
            if self.torrent.config.get('window_iconized', False):
                gui_wrap(self._torrent_window.Iconize, True)
        return self._torrent_window

    torrent_window = property(_get_torrent_window)


    def reset_toolbar_style(self):
        if self._torrent_window is not None and self.metainfo.is_batch:
            self._torrent_window.reset_toolbar_style()


    def update(self, torrent, statistics):
        oc = self.completed
        BasicTorrentObject.update(self, torrent, statistics)
        # It was not complete, but now it's complete, and it was
        # finished_this_session.  That means it's newly finished.
        if wx.the_app.task_bar_icon is not None:
            if torrent.finished_this_session and not oc and self.completed:
                # new completion status
                wx.the_app.task_bar_icon.set_balloon_tip(_('%s Download Complete') % app_name,
                                                          _('%s has finished downloading.') % self.metainfo.name)


        if self._torrent_window is not None:
            self.torrent_window.update(statistics)


    def wants_peers(self):
        return self._torrent_window and self.torrent_window.wants_peers()


    def wants_files(self):
        return self.metainfo.is_batch and self._torrent_window and self.torrent_window.wants_files()


    def save_gui_state(self):
        app = wx.the_app
        i = self.infohash
        if self._torrent_window is not None:
            win = self._torrent_window

            page = win.panel.notebook.GetSelection()
            if page != -1:
                app.send_config('window_tab', page, i)

            app.send_config('details_shown', win.details_shown(), i)

            if win.IsShown():
                app.send_config('window_shown', True, i)
                if win.IsIconized():
                    app.send_config('window_iconized', True, i)
                else:
                    app.send_config('window_iconized', False, i)
            else:
                app.send_config('window_shown', False, i)
                app.send_config('window_iconized', False, i)

            if win.IsMaximized():
                app.send_config('window_maximized', True, i)
            elif not win.IsIconized():
                g = win._geometry_string()
                app.send_config('window_geometry', g, i)
                app.send_config('window_maximized', False, i)


    def clean_up(self):
        BasicTorrentObject.clean_up(self)
        if self._torrent_window is not None:
            self._torrent_window.Destroy()
            self._torrent_window = None
            self.bandwidth_history.viewer = None



class MainStatusBar(wx.StatusBar):
    status_text_width = 120

    def __init__(self, parent, wxid=wx.ID_ANY):
        wx.StatusBar.__init__(self, parent, wxid, style=wx.ST_SIZEGRIP|wx.WS_EX_PROCESS_IDLE )
        self.SetFieldsCount(2)
        self.SetStatusWidths([-2, self.status_text_width+32])
##        self.SetFieldsCount(3)
##        self.SetStatusWidths([-2, 24, self.status_text_width+32])
##        self.sizeChanged = False
        self.status_label = StatusLabel()
        self.current_text = ''
##        self.Bind(wx.EVT_SIZE, self.OnSize)
##        # idle events? why?
##        self.Bind(wx.EVT_IDLE, self.OnIdle)
##        self.status_light = StatusLight(self)
##        self.Reposition()

    def send_status_message(self, msg):
        self.status_label.send_message(msg)
        t = self.status_label.get_label()
        if t != self.current_text:
            self.SetStatusText(t, 1)
            self.current_text = t

##    def OnSize(self, evt):
##        self.Reposition()
##        self.sizeChanged = True
##
##    def OnIdle(self, evt):
##        if self.sizeChanged:
##            self.Reposition()
##
##    def Reposition(self):
##        rect = self.GetFieldRect(i=1)
##        self.status_light.SetPosition((rect.x, rect.y))
##        self.sizeChanged = False
##
##    def send_status_message(self, msg):
##        self.status_light.send_message(msg)
##        t = self.status_light.get_label()
##        self.SetStatusText(t, 1)



class TorrentMenu(BTMenu):

    def __init__(self, ops):
        BTMenu.__init__(self)

        for e in ops:
            self.Append(e.id, e.shorthelp)

        self.stop_item = self.FindItemById(STOP_ID)
        self.start_item = self.FindItemById(START_ID)
        self.Remove(START_ID)

        self.priority_menu = BTMenu()
        for label, mid in zip((_("High"),_("Normal"), _("Low")), (PRIORITY_HIGH_ID, PRIORITY_NORMAL_ID, PRIORITY_LOW_ID)):
            self.priority_menu.AppendRadioItem(mid, label)
        self.InsertMenu(2, PRIORITY_MENU_ID, _("Priority"), self.priority_menu)


    def toggle_stop_start_menu_item(self, show_stop_item=False):
        if show_stop_item:
            sb = self.FindItemById(START_ID)
            if sb:
                self.Remove(START_ID)
                self.InsertItem(0, self.stop_item)
        else:
            sb = self.FindItemById(STOP_ID)
            if sb:
                self.Remove(STOP_ID)
                self.InsertItem(0, self.start_item)


    def set_priority(self, priority):
        item = self.priority_menu.FindItemById(priority)
        item.Check()



class FileDropTarget(wx.FileDropTarget):
    def __init__(self, window, callback):
        wx.FileDropTarget.__init__(self)
        self.window = window
        self.callback = callback

    def OnDragOver(self, a, b, c):
        self.window.SetCursor(wx.StockCursor(wx.CURSOR_COPY_ARROW))
        return wx.DragCopy

    def OnDropFiles(self, x, y, filenames):
        self.window.SetCursor(wx.StockCursor(wx.CURSOR_ARROW))
        for file in filenames:
            self.callback(file)


class EventProperties(object):
    __slots__ = ['id', 'image', 'func', 'label', 'shorthelp', 'in_toolbar']
    def __init__(self, id, image, func, label, shorthelp, in_toolbar=True):
        self.id = id
        self.image = image
        self.func = func
        self.label = label
        self.shorthelp = shorthelp
        self.in_toolbar = in_toolbar


class MainWindow(BTFrame):

    def __init__(self, *a, **k):
        BTFrame.__init__(self, *a, **k)

        app = wx.the_app

        #self.SetBackgroundColour(wx.WHITE)

        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(self.sizer)

        add_label = _("&Add torrent file\tCtrl+O")

        # torrent ops
        self.extra_ops = [
            EventProperties(OPEN_ID,
                            ('add',),
                            app.select_torrent,
                            _("Add"), add_label.replace('&', '')),
            ]
        self.torrent_ops = [
                  EventProperties(INFO_ID,
                                  ('torrentops', 'info'),
                                  app.show_torrent,
                                  _("Info"), _("Torrent info\tCtrl+I")),

                  EventProperties(STOP_ID,
                                  ('torrentops', 'stop'),
                                  app.stop_torrent,
                                  _("Pause"), _("Pause torrent")),
                  EventProperties(START_ID,
                                  ('torrentops', 'resume'),
                                  app.start_torrent,
                                  _("Resume"), _("Resume torrent")),

                  EventProperties(LAUNCH_ID,
                                  ('torrentops', 'launch'),
                                  app.launch_torrent,
                                  _("Open"), _("Open torrent")),

                  EventProperties(FORCE_START_ID,
                                  ('torrentops', 'resume'),
                                  app.force_start_torrent,
                                  _("Force Start"), _("Force start torrent"),
                                  in_toolbar=False),

                  EventProperties(REMOVE_ID,
                                  ('torrentops', 'remove'),
                                  app.confirm_remove_infohash,
                                  _("Remove"), _("Remove torrent")+'\tDelete'),
                  ]

        for o in self.extra_ops:
            def run(e, o=o):
                df = launch_coroutine(gui_wrap, o.func, e)
                def error(exc_info):
                    wx.the_app.logger.error(o.func.__name__ + " failed", exc_info=exc_info)
                df.addErrback(error)

            self.Bind(wx.EVT_MENU, run, id=o.id)

        self.torrent_event_table = {}
        for e in self.torrent_ops:
            self.torrent_event_table[e.id] = e
            # these also catch toolbar events for the DownloaderToolBar
            self.Bind(wx.EVT_MENU, self.OnTorrentEvent, id=e.id)

        for i in (PRIORITY_HIGH_ID, PRIORITY_NORMAL_ID, PRIORITY_LOW_ID):
            self.Bind(wx.EVT_MENU, self.OnTorrentEvent, id=i)
        # end torrent ops

        # Menu
        self.menu_bar = wx.MenuBar()

        # File menu
        self.file_menu = BTMenu()

        self.add_menu_item(self.file_menu, add_label,
                           wx.the_app.select_torrent_file)
        self.add_menu_item(self.file_menu, _("Add torrent &URL\tCtrl+U"),
                           wx.the_app.enter_torrent_url)
        self.file_menu.AppendSeparator()
        self.add_menu_item(self.file_menu, _("Make &new torrent\tCtrl+N" ),
                           wx.the_app.launch_maketorrent)
        self.file_menu.AppendSeparator()

        # On the Mac, the name of the item which exits the program is
        # traditionally called "Quit" instead of "Exit". wxMac handles
        # this for you - just name the item "Exit" and wxMac will change
        # it for you.
        if '__WXGTK__' in wx.PlatformInfo:
            self.add_menu_item(self.file_menu, _("&Quit\tCtrl+Q"), wx.the_app.quit)
        else:
            self.add_menu_item(self.file_menu, _("E&xit"), wx.the_app.quit)

        self.menu_bar.Append(self.file_menu, _("&File"))
        # End file menu

        # View menu
        self.view_menu = BTMenu()
        settings_id = self.add_menu_item(self.view_menu, _("&Settings\tCtrl+S"),
                                         lambda e: wx.the_app.settings_window.MagicShow())
        wx.the_app.s_macPreferencesMenuItemId = settings_id

        self.add_menu_item(self.view_menu, _("&Log\tCtrl+L"),
                           lambda e: wx.the_app.log.MagicShow())

        if console:
            self.add_menu_item(self.view_menu, _("&Console\tCtrl+C"),
                               lambda e: MagicShow_func(wx.the_app.console))

        self.add_menu_check_item(self.view_menu, _("&Details\tCtrl+D"),
                                 lambda e: self.toggle_bling_panel(),
                                 wx.the_app.config['show_details']
                                 )
        self.menu_bar.Append(self.view_menu, _("&View"))
        # End View menu

        # Torrent menu
        self.torrent_menu = TorrentMenu(self.torrent_ops)

        self.menu_bar.Append(self.torrent_menu, _("&Torrent"))
        # End Torrent menu

        # Help menu
        self.help_menu = BTMenu()
        about_id = self.add_menu_item(self.help_menu, _("&About\tCtrl+B"),
                                      lambda e: wx.the_app.about_window.MagicShow())
        self.add_menu_item(self.help_menu, _("FA&Q"),
                           lambda e: wx.the_app.visit_url(
            FAQ_URL % {'client':make_id()}))

        wx.the_app.s_macAboutMenuItemId = about_id
        wx.the_app.s_macHelpMenuTitleName = _("&Help")

        self.menu_bar.Append(self.help_menu, wx.the_app.s_macHelpMenuTitleName)
        # End Help menu

        self.SetMenuBar(self.menu_bar)
        # End menu

        # Line between menu and toolbar
        if '__WXMSW__' in wx.PlatformInfo:
            self.sizer.Add(wx.StaticLine(self, wx.HORIZONTAL), flag=wx.GROW)
        self.tool_sizer = wx.FlexGridSizer(rows=1, cols=2, vgap=0, hgap=0)
        self.tool_sizer.AddGrowableCol(0)
        self.sizer.Add(self.tool_sizer, flag=wx.GROW)

        # Tool bar
        self._build_tool_bar()

        # Status bar
        self.status_bar = MainStatusBar(self)
        self.SetStatusBar(self.status_bar)

        # panel after toolbar
        self.list_sizer = wx.FlexGridSizer(10, 1, 0, 0)
        self.list_sizer.AddGrowableCol(0)
        self.list_sizer.AddGrowableRow(0)

        self.splitter = wx.SplitterWindow(self, wx.ID_ANY, style=wx.SP_LIVE_UPDATE)
        self.splitter.SetMinimumPaneSize(1)
        self.splitter.SetSashGravity(1.0)
        self.list_sizer.Add(self.splitter, flag=wx.GROW)

        # widgets
        column_order = wx.the_app.config['column_order']
        enabled_columns = wx.the_app.config['enabled_columns']
        self.torrentlist = TorrentListView(self.splitter, column_order, enabled_columns)
        w = wx.the_app.config['column_widths']
        self.torrentlist.set_column_widths(w)


        dt = FileDropTarget(self, lambda p : wx.the_app.open_torrent_arg_with_callbacks(p))
        self.SetDropTarget(dt)

        self.torrent_context_menu = TorrentMenu(self.torrent_ops)
        self.torrentlist.SetContextMenu(self.torrent_context_menu)

        self.splitter.Initialize(self.torrentlist)

        # HACK for 16x16
        if '__WXMSW__' in wx.PlatformInfo:
            self.SetBackgroundColour(self.tool_bar.GetBackgroundColour())
        self.sizer.Add(self.list_sizer, flag=wx.GROW, proportion=1)

        # bindings
        self.torrentlist.Bind(wx.EVT_LIST_ITEM_DESELECTED, self.check_torrent_selection)
        self.torrentlist.Bind(wx.EVT_LIST_ITEM_SELECTED  , self.check_torrent_selection)
        self.torrentlist.Bind(wx.EVT_LIST_ITEM_ACTIVATED , self.torrent_double_clicked)

        self.Bind(wx.EVT_ICONIZE, self.MyIconize)

        # various setup
        self.check_torrent_selection(None)
        self.Bind(wx.EVT_CLOSE, self.close)

        self.Bind(wx.EVT_MENU, wx.the_app.force_remove, id=FORCE_REMOVE_ID)
        extra_accels = wx.AcceleratorTable([(wx.ACCEL_SHIFT, wx.WXK_DELETE, FORCE_REMOVE_ID),
                                      ])
        self.SetAcceleratorTable(extra_accels)

        # restore GUI state
        config = wx.the_app.config
        geometry = config['geometry']

        # make a guess
        size = self.torrentlist.GetViewRect().GetSize()
        pos = self.torrentlist.GetPosition()
        pos = self.torrentlist.ClientToScreen(pos)
        pos -= self.GetPosition()
        # add window border width on either side
        size.width += pos.x * 2
        size.width = max(size.width, 500)
        size.height = max(size.height, 338)
        self.load_geometry(geometry, default_size=size)

        if config['start_maximized']:
            gui_wrap(self.Maximize, True)


    def torrent_double_clicked(self, event):
        infohashes = self.torrentlist.get_selected_infohashes()
        app = wx.the_app
        for infohash in infohashes:
            torrent = app.torrents[infohash]
            df = launch_coroutine(gui_wrap, app.show_torrent, infohash)
            def error(exc_info):
                wx.the_app.logger.error(app.show_torrent.__name__ + " failed", exc_info=exc_info)
            df.addErrback(error)


    def _build_tool_bar(self):

        size = wx.the_app.config['toolbar_size']

        self.tool_bar = DownloaderToolBar(self, ops=[self.extra_ops, self.torrent_ops])

        self.search_bar = BTToolBar(self)

        i = wx.the_app.theme_library.get(('search',), size)
        bmp = wx.BitmapFromImage(i)
        assert bmp.Ok(), "The image (%s) is not valid." % image
        tid = wx.NewId()
        self.search_bar.AddLabelTool(tid, "Search", bmp, shortHelp="Search")
        self.search_field = SearchField(self.search_bar, _("Search for torrents"),
                                        wx.the_app.visit_url)
        self.search_bar.AddControl(self.search_field)
        # HACK -- we should find some better spacer and then a StaticText
        #self.search_bar.AddControl(ElectroStaticText(self.search_bar, label="  "))
        self.search_bar.Realize()

        self.Bind(wx.EVT_TOOL, self.search_field.search, id=tid)

        self.tool_sizer.Add(self.tool_bar, flag=wx.GROW)
        self.tool_sizer.Add(self.search_bar, flag=wx.ALIGN_CENTER_VERTICAL)
        s = self.search_bar.GetClientSize()
        if '__WXMSW__' in wx.PlatformInfo:
            # this makes the first toolbar size correct (on win2k, etc). icon
            # resizes after that make it go too far to the left on XP.
            # wtf?
            #self.tool_sizer.SetItemMinSize(self.search_bar, s.width/2, s.height)
            # HACK
            w = s.width/2 # ish
            if self.search_bar.size == 16:
                w = 175
            elif self.search_bar.size == 24:
                w = 185
            elif self.search_bar.size == 32:
                w = 195
            if wx.the_app.config['toolbar_text']:
                w += 25
            self.tool_sizer.SetItemMinSize(self.search_bar, w, s.height)


    def reset_toolbar_style(self):
        # Keep the old bars around just in case they get a callback
        # before we build new ones
        bs = []
        for b in (self.tool_bar, self.search_bar):
            if self.tool_sizer.Detach(b):
                bs.append(b)

        # Build new bars
        self._build_tool_bar()

        # Ok, we've built new bars, destroy the old ones
        for b in bs:
            b.Destroy()

        self.tool_sizer.Layout()
        self.sizer.Layout()


    # Bling panel
    def _get_bling_panel(self):
        try:
            return self._bling_panel
        except AttributeError:
            self._bling_panel = BlingPanel(self.splitter, wx.the_app.bling_history, size=(0,0))
            gui_wrap(self._bling_panel.notebook.SetSelection,
                     wx.the_app.config['details_tab'])
            return self._bling_panel

    bling_panel = property(_get_bling_panel)

    def HistoryReady(self):
        #self.Bind(wx.EVT_SIZE, self.OnSize)
        pass

    def toggle_bling_panel(self):
        if self.bling_panel.IsShown():
            self.splitter.Unsplit()
        else:
            self.splitter.SplitHorizontally(self.torrentlist, self.bling_panel,
                                            # should be in user config
                                            self.GetSize().height - 300)


    def OnTorrentEvent(self, event):
        tid = event.GetId()

        if self.torrent_event_table.has_key(tid):
            e = self.torrent_event_table[tid]
            infohashes = self.torrentlist.get_selected_infohashes()
            for infohash in infohashes:
                df = launch_coroutine(gui_wrap, e.func, infohash)
                def error(exc_info):
                    wx.the_app.logger.error(e.func.__name__ + " failed", exc_info=exc_info)
                df.addErrback(error)
        elif tid in (PRIORITY_LOW_ID, PRIORITY_NORMAL_ID, PRIORITY_HIGH_ID):
            infohashes = self.torrentlist.get_selected_infohashes()
            for infohash in infohashes:
                p = backend_priority[tid]
                wx.the_app.multitorrent.set_torrent_priority(infohash, p)
            self.torrent_menu.set_priority(tid)
            self.torrent_context_menu.set_priority(tid)
        else:
            print 'Not implemented!'


    def SortListItems(self, col=-1, ascending=1):
        self.torrentlist.SortListItems(col, ascending)


    def send_status_message(self, msg):
        self.status_bar.send_status_message(msg)


    def close(self, event):
        if wx.the_app.config['close_to_tray']:
            wx.the_app.systray_quit()
        else:
            wx.the_app.quit()


    def _enable_id(self, item_id, enable):
        if self.tool_bar.FindById(item_id):
            self.tool_bar.EnableTool(item_id, enable)
        if self.torrent_menu.FindItemById(item_id):
            self.torrent_menu.Enable(item_id, enable)
        if self.torrent_context_menu.FindItemById(item_id):
            self.torrent_context_menu.Enable(item_id, enable)


    def check_torrent_selection(self, event=None):
        # BUG: this ignores multiple selections, it acts on the first
        # item in the selection
        index = self.torrentlist.GetFirstSelected()
        count = self.torrentlist.GetItemCount()

        if index == -1:
            # nothing selected, disable everything
            for e in self.torrent_ops:
                self._enable_id(e.id, False)
            self._enable_id(PRIORITY_MENU_ID, False)
        else:
            # enable some things
            for i in (STOP_ID, START_ID, REMOVE_ID, INFO_ID, PRIORITY_MENU_ID):
                self._enable_id(i, True)

            # show/hide start/stop button
            self.check_torrent_start_stop(index)

            # en/disable move up
            self._enable_id(UP_ID, index > 0)

            # en/disable move down
            self._enable_id(DOWN_ID, index < count - 1)

            infohash = self.torrentlist.GetItemData(index)

            if infohash:
                torrent = wx.the_app.torrents[infohash]
                # only show open button on completed torrents
                self._enable_id(LAUNCH_ID, torrent.completion >= 1)

                self._enable_id(FORCE_START_ID, torrent.policy != "start")

                priority = frontend_priority[torrent.priority]
                for m in (self.torrent_menu, self.torrent_context_menu):
                    m.set_priority(priority)


    def check_torrent_start_stop(self, index=None):
        infohash = self.torrentlist.GetItemData(index)
        if infohash is not None:
            torrent = wx.the_app.torrents[infohash]
            show_stop = torrent.policy != "stop" and torrent.state != "failed"
            self.toggle_stop_start_button(show_stop)
            self.torrent_menu.toggle_stop_start_menu_item(show_stop)
            self.torrent_context_menu.toggle_stop_start_menu_item(show_stop)

    def toggle_stop_start_button(self, show_stop):
        changed = self.tool_bar.toggle_stop_start_button(show_stop)
        if changed:
            self.tool_sizer.Layout()
            self.sizer.Layout()

    def MyIconize(self, event):
        if wx.the_app.config['minimize_to_tray']:
            if self.IsShown():
                self.Show(False)
            else:
                self.Show(True)
                self.Raise()

    def add_menu_item(self, menu, label, function=None):
        index = menu.add_item(label)
        if function is not None:
            i = self.Bind(wx.EVT_MENU, function, id=index)
        return index

    def add_menu_check_item(self, menu, label, function=None, value=False):
        index = menu.add_check_item(label, value)
        if function is not None:
            self.Bind(wx.EVT_MENU, function, id=index)
        return index

    def clear_status(self):
        self.SetStatusText('')


    def new_displayed_torrent(self, torrent_object):

        state = (torrent_object.state    ,
                 torrent_object.policy   ,
                 torrent_object.completed)
        priority = frontend_priority[torrent_object.priority]

        lr = BTListRow(None, {'state': state,
                              'name': torrent_object.metainfo.name,
                              'progress': percentify(torrent_object.completion,
                                                     torrent_object.completed),
                              'eta': Duration(),
                              'urate': Rate(),
                              'drate': Rate(),
                              'priority': priority,
                              'peers': 0})
        self.torrentlist.InsertRow(torrent_object.infohash, lr)
        self.torrentlist._gauge_paint()


    def removed_torrent(self, infohash):
        self.torrentlist.DeleteRow(infohash)


    def save_gui_state(self):
        app = wx.the_app

        c = self.torrentlist.get_sort_column()
        o = self.torrentlist.get_sort_order()
        o = bool(o)

        app.send_config('sort_column', c)
        app.send_config('sort_ascending', o)

        column_order = self.torrentlist.column_order
        app.send_config('column_order', column_order)
        enabled_columns = self.torrentlist.enabled_columns
        app.send_config('enabled_columns', enabled_columns)
        w = self.torrentlist.get_column_widths()
        app.send_config('column_widths', w)

        if self.IsMaximized():
            app.send_config('start_maximized', True)
        elif not self.IsIconized():
            g = self._geometry_string()
            app.send_config('geometry', g)
            app.send_config('start_maximized', False)

        if wx.the_app.bling_history is not None:
            show_bling = self.bling_panel.IsShown()
            app.send_config('show_details', show_bling)
            bling_tab = self.bling_panel.notebook.GetSelection()
            app.send_config('details_tab', bling_tab)


class SaveLocationDialog(BTDialog):

    def __init__(self, parent, path, name, is_dir):
        self.is_dir = is_dir
        if self.is_dir:
            BTDialog.__init__(self, parent=parent, id=wx.ID_ANY,
                              title=_("Save In"),
                              style=wx.DEFAULT_DIALOG_STYLE)

            self.message = ElectroStaticText(self, id=wx.ID_ANY,
                                         label=_('Save "%s" in:')%name)


            dialog_title = _('Choose a folder...\n("%s" will be a sub-folder.)'%name)
            self.save_box = ChooseDirectorySizer(self, os.path.split(path)[0],
                                                 dialog_title=dialog_title)
        else:
            BTDialog.__init__(self, parent=parent, id=wx.ID_ANY,
                              title=_("Save As"),
                              style=wx.DEFAULT_DIALOG_STYLE)

            self.message = ElectroStaticText(self, id=wx.ID_ANY,
                                         label=_('Save "%s" as:')%name)


            self.save_box = ChooseFileSizer(self, path, dialog_style=wx.SAVE)

        self.sizer = VSizer()

        self.sizer.AddFirst(self.message)
        self.sizer.Add(self.save_box, flag=wx.GROW)

        self.always_checkbox = wx.CheckBox(self, id=wx.ID_ANY,
                                           label=_("&Always save files in this directory"))
        self.always_checkbox.SetValue(False)
        self.sizer.Add(self.always_checkbox)

        if '__WXMSW__' in wx.PlatformInfo:
            self.always_checkbox.Bind(wx.EVT_CHECKBOX, self.OnAlways)
            self.shortcut_checkbox = wx.CheckBox(self, id=wx.ID_ANY, label=_("Create &shortcut on the desktop"))
            self.shortcut_checkbox.SetValue(False)
            self.shortcut_checkbox.Disable()
            self.sizer.Add(self.shortcut_checkbox)

        self.button_sizer = self.CreateStdDialogButtonSizer(flags=wx.OK|wx.CANCEL)

        self.sizer.Add(self.button_sizer, flag=wx.ALIGN_RIGHT, border=SPACING)
        self.SetSizer(self.sizer)

        self.Fit()


    def OnAlways(self, event):
        if self.always_checkbox.IsChecked():
            self.shortcut_checkbox.SetValue(True)
            self.shortcut_checkbox.Enable()
        else:
            self.shortcut_checkbox.SetValue(False)
            self.shortcut_checkbox.Disable()


    def ShowModal(self):
        result = BTDialog.ShowModal(self)
        self.Destroy()
        return result


    def GetPath(self):
        return self.save_box.get_choice()


    def GetAlways(self):
        return self.always_checkbox.IsChecked()


    def GetShortcut(self):
        return os.name == 'nt' and self.shortcut_checkbox.IsChecked()



class CheckBoxDialog(BTDialog):

    def __init__(self, parent, title='', label='', checkbox_label='',
                 affirmative_button='', negative_button='',
                 checkbox_key='', checkbox_value=False):
        BTDialog.__init__(self, parent=parent, id=wx.ID_ANY,
                          title=title,
                          style=wx.DEFAULT_DIALOG_STYLE)
        self.text = ElectroStaticText(self, label=label)
        self.config = {checkbox_key: checkbox_value}

        self.checkbox = CheckButton(
            self, checkbox_label, self, checkbox_key,
            checkbox_value)

        bmp = wx.StaticBitmap(self, wx.ID_ANY,
                              wx.ArtProvider.GetBitmap(wx.ART_QUESTION,
                                                       wx.ART_MESSAGE_BOX, (32, 32)))

        # sizers
        self.button_sizer = self.CreateStdDialogButtonSizer(flags=wx.OK|wx.CANCEL)

        self.vsizer = wx.BoxSizer(wx.VERTICAL)
        self.hsizer = wx.BoxSizer(wx.HORIZONTAL)
        self.sizer = wx.BoxSizer(wx.VERTICAL)

        if '__WXMSW__' in wx.PlatformInfo:
            self.vsizer.Add(self.text, flag=wx.LEFT|wx.RIGHT|wx.BOTTOM|wx.ALIGN_CENTER, border=5)
            self.vsizer.Add(self.checkbox, flag=wx.LEFT|wx.RIGHT|wx.TOP|wx.ALIGN_CENTER_VERTICAL|wx.ALIGN_LEFT, border=5)
            self.hsizer.Add(bmp)
            self.hsizer.Add(self.vsizer, flag=wx.LEFT|wx.TOP, border=12)
            self.sizer.Add(self.hsizer, flag=wx.ALL, border=11)
            self.sizer.Add(self.button_sizer, flag=wx.ALIGN_CENTER_HORIZONTAL|wx.LEFT|wx.RIGHT|wx.BOTTOM, border=8)
        else:
            self.vsizer.Add(self.text, flag=wx.ALIGN_CENTER|wx.BOTTOM, border=SPACING)
            self.vsizer.Add(self.checkbox, flag=wx.ALIGN_LEFT, border=SPACING)
            self.hsizer.Add(bmp)
            self.hsizer.Add(self.vsizer, flag=wx.LEFT, border=SPACING)
            self.sizer.Add(self.hsizer, flag=wx.TOP|wx.LEFT|wx.RIGHT, border=SPACING)
            self.sizer.Add(self.button_sizer, flag=wx.ALIGN_RIGHT|wx.ALL, border=SPACING)

        self.SetSizer(self.sizer)
        self.Fit()


    def setfunc(self, key, value):
        wx.the_app.send_config(key, value)


class ConfirmQuitDialog(CheckBoxDialog):

    def __init__(self, parent):
        CheckBoxDialog.__init__(self, parent=parent,
                                title=_("Really quit %s?")%app_name,
                                label=_("Are you sure you want to quit %s?")%app_name,
                                checkbox_label=_("&Don't ask again"),
                                checkbox_key='confirm_quit',
                                checkbox_value=not wx.the_app.config['confirm_quit'],
                                )

    def setfunc(self, key, value):
        CheckBoxDialog.setfunc(self, key, not value)



class NotifyNewVersionDialog(CheckBoxDialog):

    def __init__(self, parent, new_version):
        CheckBoxDialog.__init__(self, parent=parent,
                                title=_("New %s version available")%app_name,
                                label=(
            (_("A newer version of %s is available.\n") % app_name) +
            (_("You are using %s, and the new version is %s.\n") % (version, new_version)) +
            (_("You can always get the latest version from \n%s") % URL) ),
                                checkbox_label=_("&Remind me later"),
                                affirmative_button=_("Download &Now"),
                                negative_button=_("Download &Later"),
                                checkbox_key='notified',
                                checkbox_value=True,
                                )
        self.new_version = new_version


    def setfunc(self, key, value):
        if not value:
            CheckBoxDialog.setfunc(self, key, self.new_version)
        else:
            CheckBoxDialog.setfunc(self, key, '')

# logs to wx targets and python. we could do in the other direction too
class LogProxy(wx.PyLog):

    # these are not 1-to-1 on purpose (our names don't match)
    severities = {wx.LOG_Info: INFO,
                  wx.LOG_Warning: WARNING,
                  wx.LOG_Status: ERROR,
                  wx.LOG_Error: CRITICAL,
                  wx.LOG_Debug: DEBUG,
                  }

    def __init__(self, log):
        wx.PyLog.__init__(self)
        self.log = log

    def DoLog(self, level, msg, timestamp):
        # throw an event to do the logging, because logging from inside the
        # logging handler deadlocks on GTK
        gui_wrap(self._do_log, level, msg, timestamp)

    def _do_log(self, level, msg, timestamp):
        wx.Log_SetActiveTarget(self.log)
        v_msg = '[%s] %s' % (version, msg)
        v_msg = v_msg.strip()

        # don't add the version number to dialogs and the status bar
        if level == wx.LOG_Error or level == wx.LOG_Status:
            self.log.PassMessages(True)
            if ']' in msg:
                msg = ''.join(msg.split(']')[1:]).strip()
            wx.LogGeneric(level, msg)
            self.log.PassMessages(False)
        else:
            wx.LogGeneric(level, v_msg)

        wx.Log_SetActiveTarget(self)



class TorrentLogger(logging.Handler):

    def __init__(self):
        self.torrents = {}
        self.base = 'core.MultiTorrent.'
        logging.Handler.__init__(self)
        self.blacklist = set()


    def emit(self, record):
        if not record.name.startswith(self.base):
            return
        l = len(self.base)
        infohash_hex = record.name[l:l+40]
        infohash = infohash_hex.decode('hex')
        if infohash not in self.blacklist:
            self.torrents.setdefault(infohash, []).append(record)


    def flush(self, infohash=None, target=None):
        if infohash is not None and target is not None:
            tlog = self.torrents.pop(infohash, [])
            for record in tlog:
                target.handle(record)
            self.blacklist.add(infohash)


    def unblacklist(self, infohash):
        if infohash in self.blacklist:
            self.blacklist.remove(infohash)



class MainLoop(BasicApp, BTApp):
    GRAPH_UPDATE_INTERVAL = 1000
    GRAPH_TIME_SPAN = 120
    torrent_object_class = TorrentObject

    def __init__(self, config):
        BasicApp.__init__(self, config)

        self.gui_wrap = self.CallAfter
        self.main_window = None
        self.task_bar_icon = None
        self.update_handle = None
        self.bling_history = None
        self.update_bwg_handle = None
        self.multitorrent_doneflag = None
        self.open_dialog_history = []
        self._stderr_buffer = ''
        self.torrent_logger = TorrentLogger()
        logging.getLogger('core.MultiTorrent').addHandler(self.torrent_logger)
        BTApp.__init__(self, 0)


    def OnInit(self):
        BTApp.OnInit(self)

        self.image_library = ImageLibrary(image_root)
        self.theme_library = ThemeLibrary(image_root, self.config['theme'])

        # Main window
        self.main_window = MainWindow(None, wx.ID_ANY, app_name)

        self.main_window.Hide()

        if not self.config['start_minimized']:
            # this code might look a little weird, but an initial Iconize can cut
            # the memory footprint of the process in half (causes GDI handles to
            # be flushed, and not recreated until they're shown).
            self.main_window.Iconize(True)
            self.main_window.Iconize(False)
            self.main_window.Show()
            self.main_window.Raise()

        self.SetTopWindow(self.main_window)

        ascending = 0
        if self.config['sort_ascending']:
            ascending = 1
        self.main_window.SortListItems(col=self.config['sort_column'],
                                       ascending=ascending)

        # Logging
        wx.Log_SetActiveTarget(wx.LogGui())

        self.log = LogWindow(self.main_window, _("%s Log")%app_name, False)

        wx.Log_SetActiveTarget(LogProxy(self.log))
        wx.Log_SetVerbose(True) # otherwise INFOs are not logged


        if console:
            spec = inspect.getargspec(py.shell.ShellFrame.__init__)
            args = spec[0]
            kw = {}
            # handle out-of-date wx installs
            if 'dataDir' in args and 'config' in args:
                # somewhere to save command history
                confDir = wx.StandardPaths.Get().GetUserDataDir()
                if not os.path.exists(confDir):
                    os.mkdir(confDir)
                fileName = os.path.join(confDir, 'config')
                self.wxconfig = wx.FileConfig(localFilename=fileName)
                self.wxconfig.SetRecordDefaults(True)
                kw = {'config':self.wxconfig,
                      'dataDir':confDir}

            # hack up and down to do the normal history things
            try:
                def OnKeyDown(s, event):
                    # If the auto-complete window is up let it do its thing.
                    if self.console.shell.AutoCompActive():
                        event.Skip()
                        return
                    key = event.GetKeyCode()
                    if key == wx.WXK_UP:
                        self.console.shell.OnHistoryReplace(step=+1)
                    elif key == wx.WXK_DOWN:
                        self.console.shell.OnHistoryReplace(step=-1)
                    else:
                        o(self.console.shell, event)
                o = py.shell.Shell.OnKeyDown
                py.shell.Shell.OnKeyDown = OnKeyDown
            except:
                pass
            self.console = py.shell.ShellFrame(self.main_window, **kw)
            self.console.Bind(wx.EVT_CLOSE, lambda e:self.console.Show(False))

        # Task bar icon
        if os.name == 'nt':
            self.task_bar_icon = DownloadManagerTaskBarIcon(self.main_window)

        self.set_title()

        self.SetAppName(app_name)
        return True

    # this function must be thread-safe!
    def attach_multitorrent(self, multitorrent, doneflag):
        if not self.IsMainLoopRunning():
            # the app is dead, tell the multitorrent to die too
            doneflag.set()
            return

        # I'm specifically using wx.CallAfter here, because I need it to occur
        # even if the wxApp doneflag is set.
        wx.CallAfter(self._attach_multitorrent, multitorrent, doneflag)

    def _attach_multitorrent(self, multitorrent, doneflag):
        self.multitorrent = multitorrent
        self.multitorrent_doneflag = doneflag

        self.multitorrent.initialize_torrents()

        if self.config['publish']:
            publish_torrent_path = self.external_torrents.pop(0)
            # BUG: does not handle errors! -Greg
            gui_wrap(launch_coroutine,
                     gui_wrap,
                     self.publish_torrent,
                     publish_torrent_path,
                     self.config['publish'])
        else:
            gui_wrap(self.open_external_torrents)

        if self.config['show_details']:
            gui_wrap(self.main_window.toggle_bling_panel)

        self.init_updates()

    def OnExit(self):
        if self.multitorrent_doneflag:
            self.multitorrent_doneflag.set()
        if self.update_handle is not None:
            self.update_handle.Stop()
            self.update_handle = None
        if self.update_bwg_handle is not None:
            self.update_bwg_handle.Stop()
            self.update_bwg_handle = None
        BTApp.OnExit(self)

    def systray_open(self):
        for t in self.torrents.values():
            t.restore_window()

        self.main_window.Show(True)
        self.main_window.Iconize(False)
        self.main_window.Raise()

    def systray_quit(self):
        for t in self.torrents.values():
            t.save_gui_state()

        self.main_window.save_gui_state()
        self.main_window.Iconize(True)
        self.main_window.Show(False)

        self.log.GetFrame().Show(False)

        for t in self.torrents.values():
            t.clean_up()

    def quit(self, confirm_quit=True):
        if self.main_window:
            if confirm_quit and self.config['confirm_quit']:
                d = ConfirmQuitDialog(self.main_window)
                d.ShowModal()
                r = d.GetReturnCode()
                if r == wx.ID_CANCEL:
                    return

            for t in self.torrents.values():
                t.save_gui_state()

            self.main_window.save_gui_state()
            self.main_window.Destroy()

            for t in self.torrents.values():
                t.clean_up()

        if self.task_bar_icon:
            self.task_bar_icon.Destroy()

        BasicApp.quit(self)


    def launch_maketorrent(self, event):
        btspawn('maketorrent')


    def enter_torrent_url(self, widget):
        s = ''
        if wx.TheClipboard.Open():
            do = wx.TextDataObject()
            if wx.TheClipboard.GetData(do):
                t = do.GetText()
                t = t.strip()
                if "://" in t or os.path.sep in t or (os.path.altsep and os.path.altsep in t):
                    s = t
            wx.TheClipboard.Close()
        d = wx.TextEntryDialog(parent=self.main_window,
                               message=_("Enter the URL of a torrent file to open:"),
                               caption=_("Enter torrent URL"),
                               defaultValue = s,
                               style=wx.OK|wx.CANCEL,
                               )
        if d.ShowModal() == wx.ID_OK:
            path = d.GetValue()
            df = self.open_torrent_arg_with_callbacks(path)

    def select_torrent(self, *a):
        image = wx.the_app.theme_library.get(('add',), 32)
        d = OpenDialog(self.main_window,
                       title=_("Open Path"),
                       bitmap=wx.BitmapFromImage(image),
                       browse=self.select_torrent_file,
                       history=self.open_dialog_history)
        if d.ShowModal() == wx.ID_OK:
            path = d.GetValue()
            self.open_dialog_history.append(path)
            df = self.open_torrent_arg_with_callbacks(path)

    def select_torrent_file(self, widget=None):
        open_location = self.config['open_from']
        if not open_location:
            open_location = self.config['save_in']
        path = smart_dir(open_location)
        dialog = wx.FileDialog(self.main_window, message=_("Open torrent file:"),
                               defaultDir=path,
                               wildcard=WILDCARD,
                               style=wx.OPEN|wx.MULTIPLE)
        if dialog.ShowModal() == wx.ID_OK:
            paths = dialog.GetPaths()
            for path in paths:
                df = self.open_torrent_arg_with_callbacks(path)
            open_from, filename = os.path.split(path)
            self.send_config('open_from', open_from)

    def rize_up(self):
        if not self.main_window.IsShown():
            self.main_window.Show(True)
            self.main_window.Iconize(False)
        if '__WXGTK__' not in wx.PlatformInfo:
            # this plays havoc with multiple virtual desktops
            self.main_window.Raise()

    def torrent_already_open(self, metainfo):
        self.rize_up()
        msg = _("This torrent (or one with the same contents) "
                "has already been added.")
        self.logger.warning(msg)
        d = wx.MessageBox(
            message=msg,
            caption=_("Torrent already added"),
            style=wx.OK,
            parent= self.main_window
            )
        return

    def open_torrent_metainfo(self, metainfo):
        """This method takes torrent metainfo and:
        1. asserts that we don't know about the torrent
        2. gets a save path for it
        3. checks to make sure the save path is acceptable:
          a. does the file already exist?
          b. does the filesystem support large enough files?
          c. does the disk have enough space left?
        4. tells TQ to start the torrent and returns a deferred object
        """

        self.rize_up()

        assert not self.torrents.has_key(metainfo.infohash)

        ask_for_save = self.config['ask_for_save'] or not self.config['save_in']
        save_in = self.config['save_in']
        if not save_in:
            save_in = get_save_dir()

        save_incomplete_in = self.config['save_incomplete_in']

        # wx expects paths sent to the gui to be unicode, not utf-8
        save_as = os.path.join(save_in.decode('utf-8'),
                               decode_from_filesystem(metainfo.name_fs))
        original_save_as = save_as

        # Choose an incomplete filename which is likely to be both short and
        # unique.  Just for kicks, also foil multi-user birthday attacks.
        foil = sha.sha(save_incomplete_in)
        foil.update(metainfo.infohash)
        incomplete_name = metainfo.infohash.encode('hex')[:8]
        incomplete_name += '-'
        incomplete_name += foil.hexdigest()[:4]
        save_incomplete_as = os.path.join(save_incomplete_in.decode('utf-8'),
                                          incomplete_name)

        biggest_file = max(metainfo.sizes)

        while True:

            if ask_for_save:
                # if config['ask_for_save'] is on, or if checking the
                # save path failed below, we ask the user for a (new)
                # save path.

                d = SaveLocationDialog(self.main_window, save_as,
                                       metainfo.name, metainfo.is_batch)
                if d.ShowModal() == wx.ID_OK:
                    dialog_path = d.GetPath()

                    if metainfo.is_batch:
                        save_in = dialog_path
                        save_as = os.path.join(dialog_path,
                                               decode_from_filesystem(metainfo.name_fs))

                    else:
                        save_as = dialog_path
                        save_in = os.path.split(dialog_path)[0]

                    if not os.path.exists(save_in):
                        os.makedirs(save_in)

                    if d.GetAlways():
                        a = wx.the_app
                        a.send_config('save_in', save_in)
                        a.send_config('ask_for_save', False)

                        if d.GetShortcut():
                            if not save_in.startswith(desktop):
                                shortcut = os.path.join(desktop, 'Shortcut to %s Downloads'%app_name)
                                create_shortcut(save_in, shortcut)

                    ask_for_save = False
                else:
                    # the user pressed cancel in the dir/file dialog,
                    # so forget about this torrent.
                    return

            else:
                # ask_for_save is False, either because the config
                # item was false, or because it got set to false the
                # first time through the loop after the user set the
                # save_path.

                if os.access(save_as, os.F_OK):
                    # check the file(s) that already exist, and warn the user
                    # if they do not match exactly in name, size and count.

                    check_current_dir = True

                    if metainfo.is_batch:
                        resume = metainfo.check_for_resume(save_in)
                        if resume == -1:
                            pass
                        elif resume == 0 or resume == 1:
                            # if the user may have navigated inside an old
                            # directory from a previous download of the
                            # batch torrent, prompt them.
                            if resume == 0:
                                default = wx.NO_DEFAULT
                            else:
                                default = wx.YES_DEFAULT

                            d = wx.MessageBox(
                                message=_("The folder you chose already "
                                "contains some files which appear to be from "
                                "this torrent.  Do you want to resume the "
                                "download using these files, rather than "
                                "starting the download over again in a "
                                "subfolder?") % path_wrap(metainfo.name_fs),
                                caption=_("Wrong folder?"),
                                style=wx.YES_NO|default,
                                parent=self.main_window
                                )
                            if d == wx.YES:
                                save_as = save_in
                                save_in = os.path.split(save_as)[0]
                                check_current_dir = False

                    if check_current_dir:
                        resume = metainfo.check_for_resume(save_as)
                        if resume == -1:
                            # STOP! files are different
                            d = wx.MessageBox(
                                message=_('A different "%s" already exists.  Do you '
                                          "want to remove it and overwrite it with "
                                          "the contents of this torrent?") %
                                path_wrap(metainfo.name_fs),
                                caption=_("Files are different!"),
                                style=wx.YES_NO|wx.NO_DEFAULT,
                                parent=self.main_window
                                )
                            if d == wx.NO:
                                ask_for_save = True
                                continue
                        elif resume == 0:
                            # MAYBE this is a resume
                            d = wx.MessageBox(
                                message=_('"%s" already exists.  Do you want to choose '
                                          'a different file name?') % path_wrap(metainfo.name_fs),
                                caption=_("File exists!"),
                                style=wx.YES_NO|wx.NO_DEFAULT,
                                parent=self.main_window
                                )
                            if d == wx.YES:
                                ask_for_save = True
                                continue
                        elif resume == 1:
                            # this is definitely a RESUME, file names,
                            # sizes and count match exactly.
                            pass

                fs_type, max_filesize = get_max_filesize(save_as)
                if max_filesize < biggest_file:
                    # warn the user that the filesystem doesn't
                    # support large enough files.
                    if fs_type is not None:
                        fs_type += ' ' + disk_term
                    else:
                        fs_type = disk_term
                    d = wx.MessageBox(
                        message=_("There is a file in this torrent that is "
                                  "%(file_size)s. This exceeds the maximum "
                                  "file size allowed on this %(fs_type)s, "
                                  "%(max_size)s.  Would you like to choose "
                                  "a different %(disk_term)s to save this "
                                  "torrent in?") %
                        {'file_size': unicode(Size(biggest_file)),
                         'max_size' : unicode(Size(max_filesize)),
                         'fs_type'  : fs_type                ,
                         'disk_term': disk_term              ,},
                        caption=_("File too large for %s") % disk_term,
                        style=wx.YES_NO|wx.YES_DEFAULT,
                        parent=self.main_window,
                        )
                    if d == wx.YES:
                        ask_for_save = True
                        continue
                    else:
                        # BUG: once we support 'never' downloading
                        # files, we should allow the user to start
                        # torrents with files that are too big, and
                        # mark those files as never-download.  For
                        # now, we don't allow downloads of torrents
                        # with files that are too big.
                        return

                if get_free_space(save_as) < metainfo.total_bytes:
                    # warn the user that there is not enough room on
                    # the filesystem to save the entire torrent.
                    d = wx.MessageBox(
                        message=_("There is not enough space on this %s to "
                                  "save this torrent.  Would you like to "
                                  "choose a different %s to save it in?") %
                        (disk_term, disk_term),
                        caption=_("Not enough space on this %s") % disk_term,
                        style=wx.YES_NO,
                        parent=self.main_window
                        )
                    if d == wx.YES:
                        ask_for_save = True
                        continue

                if is_path_too_long(save_as):
                    d = wx.MessageBox(
                        message=_("The location you chose exceeds the maximum "
                                  "path length on this system.  You must "
                                  "choose a different folder."),
                        caption=_("Maximum path exceeded"),
                        style=wx.OK,
                        parent=self.main_window
                        )
                    ask_for_save = True
                    continue

                if not os.path.exists(save_in):
                    d = wx.MessageBox(
                        message=_("The save location you specified does not "
                                  "exist (perhaps you mistyped it?)  Please "
                                  "choose a different folder."),
                        caption=_("No such folder"),
                        style=wx.OK,
                        parent= self.main_window
                        )
                    save_as = original_save_as
                    ask_for_save = True
                    continue

                if not ask_for_save:
                    # the save path is acceptable, start the torrent.
                    fs_save_as, junk = encode_for_filesystem(save_as)
                    fs_save_incomplete_as, junk = encode_for_filesystem(save_incomplete_as)
                    return self.multitorrent.create_torrent(metainfo, fs_save_incomplete_as, fs_save_as)


    def run(self):
        self.MainLoop()


    def reset_toolbar_style(self):
        self.main_window.reset_toolbar_style()
        for tw in self.torrents.values():
            tw.reset_toolbar_style()

    # Settings window
    def _get_settings_window(self):
        try:
            return self._settings_window
        except AttributeError:
            self._settings_window = SettingsWindow(self.main_window,
                                                  self.config, self.send_config)
            return self._settings_window

    settings_window = property(_get_settings_window)


    # About window
    def _get_about_window(self):
        try:
            return self._about_window
        except AttributeError:
            self._about_window = AboutWindow(self.main_window)
            return self._about_window

    about_window = property(_get_about_window)


    def force_remove(self, event):
        infohashes = self.main_window.torrentlist.get_selected_infohashes()
        for infohash in infohashes:
            df = launch_coroutine(gui_wrap, self.remove_infohash, infohash)
            def error(exc_info):
                ns = 'core.MultiTorrent.' + repr(infohash)
                l = logging.getLogger(ns)
                l.error(self.remove_infohash.__name__ + " failed", exc_info=exc_info)
            df.addErrback(error)



    def confirm_remove_infohash(self, infohash):
        if self.torrents.has_key(infohash):
            t = self.torrents[infohash]
            name = t.metainfo.name
            if not wx.GetKeyState(wx.WXK_SHIFT):
                d = wx.MessageBox(
                    message=_('Are you sure you want to permanently remove \n"%s"?') % name,
                    caption=_("Really remove torrent?"),
                    style=wx.YES_NO|wx.YES_DEFAULT,
                    parent=self.main_window)
                if d == wx.NO:
                    return
            df = launch_coroutine(gui_wrap, self.remove_infohash, infohash)
            def error(exc_info):
                ns = 'core.MultiTorrent.' + repr(infohash)
                l = logging.getLogger(ns)
                l.error(self.remove_infohash.__name__ + " failed", exc_info=exc_info)
            df.addErrback(error)
            # Could also do this but it's harder to understand:
            #return self.remove_infohash(infohash)


    def show_torrent(self, infohash):
        torrent = self.torrents[infohash]
        torrent.torrent_window.MagicShow()


    def notify_of_new_version(self, new_version):
        d = NotifyNewVersionDialog(self.main_window, new_version)
        d.ShowModal()
        r = d.GetReturnCode()
        if r == wx.ID_OK:
            self.visit_url(URL)


    def prompt_for_quit_for_new_version(self, version):
        d = wx.MessageBox(
            message=_(("%s is ready to install a new version (%s).  Do you "
                       "want to quit now so that the new version can be "
                       "installed?  If not, the new version will be installed "
                       "the next time you quit %s."
                       ) % (app_name, version, app_name)),
            caption=_("Install update now?"),
            style=wx.YES_NO|wx.YES_DEFAULT,
            parent=self.main_window
            )
        if d == wx.YES:
            self.quit(confirm_quit=False)


    def do_log(self, severity, text):

        if severity == 'stderr':
            # stderr likes to spit partial lines, buffer them until we get a \n
            self._stderr_buffer += text
            if text[-1] != '\n':
                return
            text = self._stderr_buffer
            self._stderr_buffer = ''
            severity = ERROR

        # We don't make use of wxLogMessage or wxLogError, because only
        # critical errors are presented to the user.
        # Really, that means some of our severities are mis-named.

        if severity == INFO:
            wx.LogInfo(text)
        elif severity == WARNING:
            wx.LogWarning(text)
        elif severity == ERROR:
            # put it in the status bar
            self.log.PassMessages(True)
            wx.LogStatus(text)
            self.log.PassMessages(False)
            wx.FutureCall(ERROR_MESSAGE_TIMEOUT, self.main_window.clear_status)
        elif severity == CRITICAL:
            # pop up a dialog
            self.log.PassMessages(True)
            wx.LogError(text)
            self.log.PassMessages(False)

    # make status request at regular intervals
    def init_updates(self):
        self.bling_history = HistoryCollector(self.GRAPH_TIME_SPAN,
                                              self.GRAPH_UPDATE_INTERVAL)

        if self.update_handle is None:
            self.make_statusrequest()

        if self.update_bwg_handle is None:
            self.update_bandwidth_graphs()

        self.main_window.HistoryReady()

    def update_bandwidth_graphs(self):
        df = launch_coroutine(gui_wrap, self._update_bandwidth_graphs)
        def error(exc_info):
            wx.the_app.logger.error(self._update_bandwidth_graphs.__name__ + " failed", exc_info=exc_info)
        df.addErrback(error)


    def _update_bandwidth_graphs(self):
        df = self.multitorrent.get_all_rates()
        yield df
        rates = df.getResult()

        tu = 0.0
        td = 0.0
        for infohash, v in rates.iteritems():
            u, d = v
            if infohash in self.torrents:
                t = self.torrents[infohash]
                t.bandwidth_history.update(upload_rate=u, download_rate=d)
            tu += u
            td += d

        self.bling_history.update(upload_rate=tu, download_rate=td)

        self.update_bwg_handle = wx.FutureCall(self.GRAPH_UPDATE_INTERVAL,
                                               self.update_bandwidth_graphs)

    def update_status(self):
        df = launch_coroutine(gui_wrap, BasicApp.update_status, self)
        def eb(exc_info):
            self.logger.error(BasicApp.update_status.__name__ + " error:", exc_info=exc_info)
        df.addErrback(eb)
        yield df
        # wx specific code
        average_completion, global_stats = df.getResult()
        if len(self.torrents) > 0:
            self.set_title(average_completion,
                           global_stats['total_downrate'],
                           global_stats['total_uprate'])
        else:
            self.set_title()
            self.send_status_message('empty')

        self.main_window.torrentlist.SortItems()

        self.main_window.check_torrent_selection()

        # anyone can call this function to initiate an update, so allow this
        # task to be re-entrant (prevent double-queueing)
        if self.update_handle is not None:
            self.update_handle.Stop()
        self.update_handle = wx.FutureCall(self.config['display_interval'] * 1000, self.make_statusrequest)

        self.main_window.bling_panel.statistics.update_values(global_stats)


    def new_displayed_torrent(self, torrent):
        torrent_object = BasicApp.new_displayed_torrent(self, torrent)

        if len(self.torrents) == 1:
            self.send_status_message('start')

        self.main_window.new_displayed_torrent(torrent_object)

        return torrent_object


    def torrent_removed(self, infohash):
        self.torrent_logger.unblacklist(infohash)
        self.main_window.removed_torrent(infohash)


    def update_torrent(self, torrent_object):
        self.main_window.torrentlist.update_torrent(torrent_object)
        if torrent_object.statistics.get('ever_got_incoming'):
            self.send_status_message('seen_remote_peers')
        elif torrent_object.statistics.get('numPeers'):
            self.send_status_message('seen_peers')


    def send_status_message(self, msg):
        self.main_window.send_status_message(msg)


    def set_title(self, completion=0, downrate=0, uprate=0):
        if len(self.torrents) > 0:
            if len(self.torrents) > 1:
                name = _("(%d torrents)") % len(self.torrents)
            else:
                name = self.torrents[self.torrents.keys()[0]].metainfo.name
            title = "%s: %.1f%%: %s" % (app_name, completion*100, name)
        elif self.multitorrent:
            title = app_name
        else:
            title = "%s: %s" % (app_name, _("(initializing)"))
        if self.task_bar_icon is not None:
            tip = '%s\n%s down, %s up' % (title, unicode(Rate(downrate)), unicode(Rate(uprate)))
            self.task_bar_icon.set_tooltip(tip)
        self.main_window.SetTitle(title)
