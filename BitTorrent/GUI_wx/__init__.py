# The contents of this file are subject to the BitTorrent Open Source License
# Version 1.1 (the License).  You may not copy or use this file, in either
# source code or executable form, except in compliance with the License.  You
# may obtain a copy of the License at http://www.bittorrent.com/license/.
#
# Software distributed under the License is distributed on an AS IS basis,
# WITHOUT WARRANTY OF ANY KIND, either express or implied.  See the License
# for the specific language governing rights and limitations under the
# License.

# written by Matt Chisholm and Greg Hazel

from __future__ import division

import os

import wx
import wx.grid
import wxPython
import traceback
from BitTorrent.translation import _

from UserDict import UserDict
from BitTorrent import zurllib

from BitTorrent.platform import image_root, desktop
import BitTorrent.stackthreading as threading
from BitTorrent.defer import ThreadedDeferred

vs = wxPython.__version__
min_wxpython = "2.6"
assert vs >= min_wxpython, _("wxPython version %s or newer required") % min_wxpython

text_wrappable = wx.__version__[4] >= '2'

# used in BTApp
profile = False
class Amaturefile(object):
    def start(self):
        pass
    def stop(self):
        pass
if profile:
    import hotshot
    import hotshot.stats
    prof_file_name = 'ui.mainloop.prof'

def gui_wrap(_f, *args, **kwargs):
    wx.the_app.CallAfter(_f, *args, **kwargs)

SPACING = 8  # default pixels between widgets
PORT_RANGE = 5 # how many ports to try

WILDCARD = "Torrent files (*.torrent)|*.torrent|"\
           "All files (*.*)|*.*"



def list_themes():
    def _lt():
        themes = []
        tr = os.path.join(image_root, 'themes')
        ld = os.listdir(tr)
        for d in ld:
            if os.path.isdir(os.path.join(tr, d)):
                themes.append(d)
        return themes
    df = ThreadedDeferred(None, _lt, daemon=True)
    df.start()
    return df


class ImageLibrary(object):

    def __init__(self, image_root):
        self.image_root = image_root
        self._data = {}

    def get(self, key, size=None, base=None):
        if base is None:
            base = self.image_root

        if self._data.has_key((key, size)):
            return self._data[(key, size)]

##        utorrent_toolbar = os.path.join(base, "toolbar.bmp")
##        if os.path.exists(utorrent_toolbar):
##            try:
##                assert False, "Use wx.Bitmap instead"
##                i = wx.Image(utorrent_toolbar, wx.BITMAP_TYPE_BMP)
##                i.SetMaskFromImage(i, 0, 0, 0)
##                iw = 24
##                ih = i.GetHeight()

##                self._data["search"] = i.GetSubImage(wx.Rect(9 * iw, 0, iw, ih))
##                self._data["stop"] = i.GetSubImage(wx.Rect(5 * iw, 0, iw, ih))
##                self._data["start"] = i.GetSubImage(wx.Rect(4 * iw, 0, iw, ih))
##                self._data["info"] = i.GetSubImage(wx.Rect(11 * iw, 0, iw, ih))
##                self._data["launch"] = i.GetSubImage(wx.Rect(0 * iw, 0, iw, ih))
##                self._data["remove"] = i.GetSubImage(wx.Rect(3 * iw, 0, iw, ih))
##            except:
##                pass


##        utorrent_tstatus = os.path.join(base, "tstatus.bmp")
##        if os.path.exists(utorrent_tstatus):
##            try:
##                assert False, "Use wx.Bitmap instead"
##                i = wx.Image(utorrent_tstatus, wx.BITMAP_TYPE_BMP)
##                i.SetMaskFromImage(i, 0, 0, 0)
##                iw = 16
##                ih = i.GetHeight()

##                self._data[os.path.join("torrentstate", "created")] = i.GetSubImage(
##                    wx.Rect(12 * iw, 0, iw, ih))
##                self._data[os.path.join("torrentstate", "starting")] = i.GetSubImage(
##                    wx.Rect(12 * iw, 0, iw, ih))
##                self._data[os.path.join("torrentstate", "paused")] = i.GetSubImage(
##                    wx.Rect(3 * iw, 0, iw, ih))
##                self._data[os.path.join("torrentstate", "downloading")] = i.GetSubImage(
##                    wx.Rect(0 * iw, 0, iw, ih))
##                self._data[os.path.join("torrentstate", "finishing")] = i.GetSubImage(
##                    wx.Rect(7 * iw, 0, iw, ih))
##                self._data[os.path.join("torrentstate", "seeding")] = i.GetSubImage(
##                    wx.Rect(1 * iw, 0, iw, ih))
##                self._data[os.path.join("torrentstate", "stopped")] = i.GetSubImage(
##                    wx.Rect(2 * iw, 0, iw, ih))
##                self._data[os.path.join("torrentstate", "complete")] = i.GetSubImage(
##                    wx.Rect(7 * iw, 0, iw, ih))
##                self._data[os.path.join("torrentstate", "error")] = i.GetSubImage(
##                    wx.Rect(6 * iw, 0, iw, ih))
##                self._data[os.path.join("torrentstate", "unknown")] = i.GetSubImage(
##                    wx.Rect(6 * iw, 0, iw, ih))
##            except:
##                pass

        name = os.path.join(base, *key)

        ext = '.png'

        if size is not None:
            sized_name = name + '_%d' % size + ext
            if os.path.exists(sized_name):
                name = sized_name
            else:
                name += ext
        else:
            name += ext

        if not os.path.exists(name):
            assert False, "No such image file: %s" % name

        i = wx.Image(name, wx.BITMAP_TYPE_PNG)
        assert i.Ok(), "The image (%s) is not valid." % name

        self._data[(key, size)] = i

        return i



class ThemeLibrary(ImageLibrary):

    def __init__(self, themes_root, theme_name):
        self.themes_root = themes_root
        for t in (theme_name, 'default'):
            image_root = os.path.join(themes_root, 'themes', t)
            if os.path.exists(image_root):
                self.theme_name = t
                ImageLibrary.__init__(self, image_root)
                return
        assert False, 'default theme path "%s" must exist' % image_root


    def get(self, key, size=None):
        try:
            return ImageLibrary.get(self, key, size=size)
        except AssertionError, e:
            # Fall back to default theme.
            # Should probably log this to make theme developers happy.
            return ImageLibrary.get(self, key, size=size,
                                    base=os.path.join(self.themes_root, 'themes', 'default'))



class XSizer(wx.BoxSizer):
    notfirst = wx.ALL
    direction = wx.HORIZONTAL

    def __init__(self, **k):
        wx.BoxSizer.__init__(self, self.direction)

    def Add(self, widget, proportion=0, flag=0, border=SPACING):
        flag = flag | self.notfirst
        wx.BoxSizer.Add(self, widget, proportion=proportion, flag=flag, border=border)

    def AddFirst(self, widget, proportion=0, flag=0, border=SPACING):
        flag = flag | wx.ALL
        self.Add(widget, proportion=proportion, flag=flag, border=border)



class VSizer(XSizer):
    notfirst = wx.BOTTOM|wx.LEFT|wx.RIGHT
    direction = wx.VERTICAL



class HSizer(XSizer):
    notfirst = wx.BOTTOM|wx.RIGHT|wx.TOP
    direction = wx.HORIZONTAL



class LabelValueFlexGridSizer(wx.FlexGridSizer):

    def __init__(self, parent_widget, *a, **k):
        wx.FlexGridSizer.__init__(self, *a, **k)
        self.parent_widget = parent_widget


    def add_label(self, label):
        h = ElectroStaticText(self.parent_widget, label=label)
        f = h.GetFont()
        f.SetWeight(wx.FONTWEIGHT_BOLD)
        h.SetFont(f)
        self.Add(h)


    def add_value(self, value):
        t = ElectroStaticText(self.parent_widget, id=wx.ID_ANY, label=value)
        self.Add(t)
        return t


    def add_pair(self, label, value):
        self.add_label(label)
        t = self.add_value(value)
        return t



class ElectroStaticText(wx.StaticText):
    def __init__(self, parent, id=wx.ID_ANY, label=''):
        wx.StaticText.__init__(self, parent, id, label)
        self.label = label

    def SetLabel(self, label):
        if label != self.label:
            wx.StaticText.SetLabel(self, label)
        self.label = label



class ElectroStaticBitmap(wx.Window):
    def __init__(self, parent, bitmap, *a, **k):
        wx.Window.__init__(self, parent, *a, **k)
        self.bitmap = bitmap
        self.SetMinSize((self.bitmap.GetWidth(), self.bitmap.GetHeight()))
        self.Bind(wx.EVT_PAINT, self.OnPaint)


    def OnPaint(self, event):
        dc = wx.PaintDC(self)
        dc.SetBackground(wx.Brush(self.GetBackgroundColour()))
        dc.DrawBitmap(self.bitmap, 0, 0, True)


    def GetSize(self):
        return wx.Size(self.bitmap.GetWidth(), self.bitmap.GetHeight())



class Validator(wx.TextCtrl):
    valid_chars = '1234567890'
    minimum = None
    maximum = None
    cast = int

    def __init__(self, parent, option_name, config, setfunc):
        wx.TextCtrl.__init__(self, parent)
        self.option_name = option_name
        self.config      = config
        self.setfunc     = setfunc

        self.SetValue(str(config[option_name]))

        self.SetBestFittingSize((self.width,-1))

        self.Bind(wx.EVT_CHAR, self.text_inserted)
        self.Bind(wx.EVT_KILL_FOCUS, self.focus_out)

    def get_value(self):
        value = None
        try:
            value = self.cast(self.GetValue())
        except ValueError:
            pass
        return value

    def set_value(self, value):
        self.SetValue(str(value))
        self.setfunc(self.option_name, value)

    def focus_out(self, event):
        # guard against the the final focus lost event on wxMAC
        if self.IsBeingDeleted():
            return

        value = self.get_value()

        if value is None:
            self.SetValue(str(self.config[self.option_name]))

        if (self.minimum is not None) and (value < self.minimum):
            value = self.minimum
        if (self.maximum is not None) and (value > self.maximum):
            value = self.maximum

        self.set_value(value)

    def text_inserted(self, event):
        key = event.KeyCode()

        if key < wx.WXK_SPACE or key == wx.WXK_DELETE or key > 255:
            event.Skip()
            return

        if (self.valid_chars is not None) and (chr(key) not in self.valid_chars):
            return

        event.Skip()



class IPValidator(Validator):
    valid_chars = '1234567890.'
    width = 128
    cast = str



class PortValidator(Validator):
    width = 64
    minimum = 1024
    maximum = 65535

    def add_end(self, end_name):
        self.end_option_name = end_name

    def set_value(self, value):
        self.SetValue(str(value))
        self.setfunc(self.option_name, value)
        self.setfunc(self.end_option_name, value+PORT_RANGE)



class RatioValidator(Validator):
    width = 48
    minimum = 0



class MinutesValidator(Validator):
    width = 48
    minimum = 1



class PathDialogButton(wx.Button):

    def __init__(self, parent, gen_dialog, setfunc=None,
                 label=_("&Browse...")):
        wx.Button.__init__(self, parent, label=label)

        self.gen_dialog = gen_dialog
        self.setfunc = setfunc

        self.Bind(wx.EVT_BUTTON, self.choose)


    def choose(self, event):
        """Pop up a choose dialog and set the result if the user clicks OK."""
        dialog = self.gen_dialog()
        result = dialog.ShowModal()

        if result == wx.ID_OK:
            path = dialog.GetPath()

            if self.setfunc:
                self.setfunc(path)



class ChooseDirectorySizer(wx.BoxSizer):

    def __init__(self, parent, path='', setfunc=None,
                 editable=True,
                 dialog_title=_("Choose a folder..."),
                 button_label=_("&Browse...")):
        wx.BoxSizer.__init__(self, wx.HORIZONTAL)

        self.parent = parent
        self.setfunc = setfunc
        self.dialog_title = dialog_title
        self.button_label = button_label

        self.pathbox = wx.TextCtrl(self.parent, size=(250, -1))
        self.pathbox.SetEditable(editable)
        self.Add(self.pathbox, proportion=1, flag=wx.RIGHT, border=SPACING)
        self.pathbox.SetValue(path)

        self.button = PathDialogButton(parent,
                                       gen_dialog=self.dialog,
                                       setfunc=self.set_choice,
                                       label=self.button_label)

        self.Add(self.button)


    def set_choice(self, path):
        self.pathbox.SetValue(path)
        if self.setfunc:
            self.setfunc(path)


    def get_choice(self):
        return self.pathbox.GetValue()


    def dialog(self):
        dialog = wx.DirDialog(self.parent,
                              message=self.dialog_title,
                              style=wx.DD_DEFAULT_STYLE|wx.DD_NEW_DIR_BUTTON)
        dialog.SetPath(self.get_choice())
        return dialog



class ChooseFileSizer(ChooseDirectorySizer):

    def __init__(self, parent, path='', setfunc=None,
                 editable=True,
                 dialog_title=_("Choose a file..."),
                 button_label=_("&Browse..."),
                 wildcard=_("All files (*.*)|*.*"),
                 dialog_style=wx.OPEN):
        ChooseDirectorySizer.__init__(self, parent, path=path, setfunc=setfunc,
                                      editable=editable,
                                      dialog_title=dialog_title,
                                      button_label=button_label)
        self.wildcard = wildcard
        self.dialog_style = dialog_style


    def dialog(self):
        directory, file = os.path.split(self.get_choice())
        dialog = wx.FileDialog(self.parent,
                               defaultDir=directory,
                               defaultFile=file,
                               message=self.dialog_title,
                               wildcard=self.wildcard,
                               style=self.dialog_style)
        #dialog.SetPath(self.get_choice())
        return dialog



class ChooseFileOrDirectorySizer(wx.BoxSizer):

    def __init__(self, parent, path='', setfunc=None,
                 editable=True,
                 file_dialog_title=_("Choose a file..."),
                 directory_dialog_title=_("Choose a folder..."),
                 file_button_label=_("Choose &file..."),
                 directory_button_label=_("Choose f&older..."),
                 wildcard=_("All files (*.*)|*.*"),
                 file_dialog_style=wx.OPEN):
        wx.BoxSizer.__init__(self, wx.VERTICAL)

        self.parent = parent
        self.setfunc = setfunc
        self.file_dialog_title = file_dialog_title
        self.directory_dialog_title = directory_dialog_title
        self.file_button_label = file_button_label
        self.directory_button_label = directory_button_label
        self.wildcard = wildcard
        self.file_dialog_style = file_dialog_style

        self.pathbox = wx.TextCtrl(self.parent, size=(250, -1))
        self.pathbox.SetEditable(editable)
        self.Add(self.pathbox, flag=wx.EXPAND|wx.BOTTOM, border=SPACING)
        self.pathbox.SetValue(path)

        self.subsizer = wx.BoxSizer(wx.HORIZONTAL)
        self.Add(self.subsizer, flag=wx.ALIGN_RIGHT, border=0)

        self.fbutton = PathDialogButton(parent,
                                        gen_dialog=self.file_dialog,
                                        setfunc=self.set_choice,
                                        label=self.file_button_label)
        self.subsizer.Add(self.fbutton, flag=wx.LEFT, border=SPACING)

        self.dbutton = PathDialogButton(parent,
                                        gen_dialog=self.directory_dialog,
                                        setfunc=self.set_choice,
                                        label=self.directory_button_label)
        self.subsizer.Add(self.dbutton, flag=wx.LEFT, border=SPACING)


    def set_choice(self, path):
        self.pathbox.SetValue(path)
        if self.setfunc:
            self.setfunc(path)


    def get_choice(self):
        return self.pathbox.GetValue()


    def directory_dialog(self):
        dialog = wx.DirDialog(self.parent,
                              message=self.directory_dialog_title,
                              style=wx.DD_DEFAULT_STYLE|wx.DD_NEW_DIR_BUTTON)
        dialog.SetPath(self.get_choice())
        return dialog

    def file_dialog(self):
        dialog = wx.FileDialog(self.parent,
                               message=self.file_dialog_title,
                               defaultDir=self.get_choice(),
                               wildcard=self.wildcard,
                               style=self.file_dialog_style)
        dialog.SetPath(self.get_choice())
        return dialog




class Grid(wx.grid.Grid):

    def SetColRenderer(self, col, renderer):
        table = self.GetTable()
        attr = table.GetAttr(-1, col, wx.grid.GridCellAttr.Col)

        if (not attr):
            attr = wx.grid.GridCellAttr()

        attr.SetRenderer(renderer)
        self.SetColAttr(col, attr)


    def SetColEditor(self, col, editor):
        table = self.GetTable()
        attr = table.GetAttr(-1, col, wx.grid.GridCellAttr.Col)

        if (not attr):
            attr = wx.grid.GridCellAttr()

        attr.SetEditor(editor)
        self.SetColAttr(col, attr)



class BTMenu(wx.Menu):
    """Base class for menus"""

    def __init__(self, *a, **k):
        wx.Menu.__init__(self, *a, **k)

    def add_item(self, label):
        iid = wx.NewId()
        self.Append(iid, label)
        return iid

    def add_check_item(self, label, value=False):
        iid = wx.NewId()
        self.AppendCheckItem(iid, label)
        self.Check(id=iid, check=value)
        return iid



class CheckButton(wx.CheckBox):
    """Base class for check boxes"""
    def __init__(self, parent, label, main, option_name, initial_value,
                 extra_callback=None):
        wx.CheckBox.__init__(self, parent, label=label)
        self.main = main
        self.option_name = option_name
        self.option_type = type(initial_value)
        self.SetValue(bool(initial_value))
        self.extra_callback = extra_callback
        self.Bind(wx.EVT_CHECKBOX, self.callback)

    def callback(self, *args):
        if self.option_type is not type(None):
            self.main.config[self.option_name] = self.option_type(
                not self.main.config[self.option_name])
            self.main.setfunc(self.option_name, self.main.config[self.option_name])
        if self.extra_callback is not None:
            self.extra_callback()



class BTPanel(wx.Panel):
    sizer_class = wx.BoxSizer
    sizer_args = (wx.VERTICAL,)

    def __init__(self, *a, **k):
        wx.Panel.__init__(self, *a, **k)
        self.sizer = self.sizer_class(*self.sizer_args)
        self.SetSizer(self.sizer)

    def Add(self, widget, *a, **k):
        self.sizer.Add(widget, *a, **k)

    def AddFirst(self, widget, *a, **k):
        if hasattr(self.sizer, 'AddFirst'):
            self.sizer.AddFirst(widget, *a, **k)
        else:
            self.sizer.Add(widget, *a, **k)


def MagicShow_func(win, show=True):
    win.Show(show)
    if show:
        win.Raise()

class MagicShow:
    """You know, like with a guy pulling rabbits out of a hat"""
    def MagicShow(self, show=True):
        if hasattr(self, 'magic_window'):
            # hackery in case we aren't actually a window
            win = self.magic_window
        else:
            win = self

        MagicShow_func(win, show)


class BTDialog(wx.Dialog, MagicShow):
    """Base class for all BitTorrent window dialogs"""

    def __init__(self, *a, **k):
        wx.Dialog.__init__(self, *a, **k)
        self.SetIcon(wx.the_app.icon)



class BTFrame(wx.Frame, MagicShow):
    """Base class for all BitTorrent window frames"""

    def __init__(self, *a, **k):
        wx.Frame.__init__(self, *a, **k)
        self.SetIcon(wx.the_app.icon)


    def load_geometry(self, geometry, default_size=None):
        if '+' in geometry:
            s, x, y = geometry.split('+')
            x, y = int(x), int(y)
        else:
            x, y = -1, -1
            s = geometry

        if 'x' in s:
            w, h = s.split('x')
            w, h = int(w), int(h)
        else:
            w, h = -1, -1

        i = 0
        if '__WXMSW__' in wx.PlatformInfo:
            i = wx.Display.GetFromWindow(self)
        d = wx.Display(i)
        (x1, y1, x2, y2) = d.GetGeometry()
        x = min(x, x2-64)
        y = min(y, y2-64)

        if (w,h) <= (0,0) and default_size is not None:
            w = default_size.width
            h = default_size.height

        self.SetDimensions(x, y, w, h, sizeFlags=wx.SIZE_USE_EXISTING)


    def _geometry_string(self):
        pos = self.GetPositionTuple()
        size = self.GetSizeTuple()
        g = ''
        g += 'x'.join(map(str, size))
        if pos > (0,0):
            g += '+' + '+'.join(map(str, pos))
        return g


    def SetTitle(self, title):
        if title != self.GetTitle():
            wx.Frame.SetTitle(self, title)



class BTFrameWithSizer(BTFrame):
    """BitTorrent window frames with sizers, which are less flexible than normal windows"""
    panel_class = BTPanel
    sizer_class = wx.BoxSizer
    sizer_args = (wx.VERTICAL,)

    def __init__(self, *a, **k):
        BTFrame.__init__(self, *a, **k)
        self.SetIcon(wx.the_app.icon)
        self.panel = self.panel_class(self)
        self.sizer = self.sizer_class(*self.sizer_args)
        self.Add(self.panel, flag=wx.GROW, proportion=1)
        self.SetSizer(self.sizer)

    def Add(self, widget, *a, **k):
        self.sizer.Add(widget, *a, **k)


class BTApp(wx.App):
    """Base class for all BitTorrent applications"""

    def __init__(self, *a, **k):
        wx.App.__init__(self, *a, **k)

    def OnInit(self):
        self.prof = Amaturefile()
        if profile:
            def start_profile():
                self.prof = hotshot.Profile(prof_file_name)
                try:
                    os.unlink(prof_file_name)
                except:
                    pass
            wx.FutureCall(6, start_profile)

        wx.the_app = self
        self._CallAfterId = wx.NewEventType()
        self.Connect(-1, -1, self._CallAfterId,
                     lambda event: event.callable(*event.args, **event.kw) )
       
        # this breaks TreeListCtrl, and I'm too lazy to figure out why
        #wx.IdleEvent_SetMode(wx.IDLE_PROCESS_SPECIFIED)
        # this fixes 24bit-color toolbar buttons
        wx.SystemOptions_SetOptionInt("msw.remap", 0)
        icon_path = os.path.join(image_root, 'bittorrent.ico')
        self.icon = wx.Icon(icon_path, wx.BITMAP_TYPE_ICO)
        self.doneflag = threading.Event()
        return True

    def OnExit(self):
        if profile:
            self.prof.close()
            stats = hotshot.stats.load(prof_file_name)
            stats.strip_dirs()
            stats.sort_stats('time', 'calls')
            print "UI MainLoop Profile:"
            stats.print_stats(20)
        pass

    def _CallAfter(self, _f, *a, **kw):
        try:
            if self.doneflag.isSet():
                #print "dropping", _f
                return
        except:
            # assume any kind of error means the app is dying
            return
        #def who():
        #    if _f.__name__ == "_recall":
        #        return a[1].gen.gi_frame.f_code.co_name
        #    return _f.__name__
        #print who()

        if profile:
            self.prof.start()
            _f(*a, **kw)
            self.prof.stop()
        else:
            _f(*a, **kw)

#    def CallAfter(self, _f, *a, **kw):
#        wx.CallAfter(self._CallAfter, _f, *a, **kw)
    def CallAfter(self, callable, *args, **kw):
        """
        Call the specified function after the current and pending event
        handlers have been completed.  This is also good for making GUI
        method calls from non-GUI threads.  Any extra positional or
        keyword args are passed on to the callable when it is called.
        """

        evt = wx.PyEvent()
        evt.SetEventType(self._CallAfterId)
        evt.callable = self._CallAfter
        evt.args = (callable, ) + args
        evt.kw = kw
        wx.PostEvent(self, evt)