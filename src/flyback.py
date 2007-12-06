#!/usr/bin/env python

#    FlyBack
#    Copyright (C) 2007 Derek Anderson
#
#    This program is free software; you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation; either version 2 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License along
#    with this program; if not, write to the Free Software Foundation, Inc.,
#    51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

import os, sys, traceback, math

RUN_FROM_DIR = os.path.abspath(os.path.dirname(sys.argv[0])) + '/'
VERSION = 'v0.4.0'
GPL = open( RUN_FROM_DIR + 'GPL.txt', 'r' ).read()

DEFAULT_EXCLUDES = [
    '/**/.thumbnails/',
    '/**/.mozilla/**/Cache/',
    '/**/.cache/tracker/',
    '/**/.Trash/',
    '/**/.emerald/themecache/',
    '/**/.fontconfig/*.cache*',
    '/**/.java/deployment/cache/',
    '/**/amarok/albumcovers/cache/',
    '/**/amarok/albumcovers/large/',
    '/**/.liferea*/mozilla/liferea/Cache/',
    '/**/.liferea*/cache/',
    '/**/.macromedia/Flash_Player/*SharedObjects/',
    '/**/.macromedia/Macromedia/Flash\ Player/*SharedObjects/',
    '/**/.metacity/sessions/',
    '/**/.nautilus/saved*',
    '/**/.mythtv/osdcache/',
    '/**/.mythtv/themecache/',
    '/**/var/cache/',
    '/**/workspace/.metadata/',
    '/**/.openoffice.org2/user/registry/cache/',
    '/**/.openoffice.org2/user/uno_packages/cache/',
    '/**/.grails/*/scriptCache/',
    '/**/.wine/drive_c/windows/temp/',
    '/cdrom',
    '/dev/',
    '/proc/',
    '/sys/',
    '/tmp/',
]




import dircache
import desktop
from datetime import datetime
from time import strptime
import threading
import help_data
import config_backend
import getopt

try:
    import gconf
except:
    print 'error: could not find python module gconf'
    sys.exit()
try:
    import pygtk
except:
    print 'error: could not find python module pygtk'
    sys.exit()
try:
    pygtk.require("2.0")
except:
    print 'error: pygtk v2.0 or later is required'
    sys.exit()
try:
    import gobject
except:
    print 'error: could not find python module gobject'
    sys.exit()
try:
    import gtk
    import gtk.glade
except:
    print 'error: could not find python module gtk'
    sys.exit()
try:
    import gnome.ui
except:
    print 'error: could not find python module gnome'
    sys.exit()
    

client = config_backend.GConfConfig()

from backup_backend import *

gobject.threads_init()
gtk.gdk.threads_init()

def humanize_bytes(x):
    x = float(x)
    if x > math.pow(2,30):
        return humanize_count(x/math.pow(2,30),'GB','GB')
    if x > math.pow(2,20):
        return humanize_count(x/math.pow(2,20),'MB','MB')
    if x > math.pow(2,10):
        return humanize_count(x/math.pow(2,10),'KB','KB')
    return humanize_count( x, 'byte', 'bytes' )

def humanize_count(x, s, p, places=1):
    x = float(x)*math.pow(10, places)
    x = round(x)
    x = x/math.pow(10, places)
    if x-int(x)==0:
        x = int(x)
    if x==1:
        return str(x) +' ' + s
    else:
        return str(x) +' ' + p
    
def humanize_timedelta(td):
    s = td.seconds
    if s<60:
        return humanize_count( s, 'second', 'seconds' )
    m = s/60.0
    if m<60:
        return humanize_count( m, 'minute', 'minutes' )
    h = m/60.0
    if h<24:
        return humanize_count( h, 'hour', 'hours' )
    d = h/24.0
    return humanize_count( d, 'day', 'days' )

class MainGUI:
    
    xml = None
    selected_backup = None
    backup = None
    cur_dir = '/'
    available_backups = []
    available_backup_list = gtk.ListStore(gobject.TYPE_STRING, gobject.TYPE_PYOBJECT)
    file_list = gtk.ListStore( str, str, str, bool, gtk.gdk.Pixbuf )
    backup_thread = None
    restore_thread = None
        
    def select_subdir(self, treeview, o1, o2):
        selection = treeview.get_selection()
        liststore, rows = selection.get_selected_rows()

        focus_dir = self.get_focus_dir()
#        print 'focus_dir', focus_dir
        
        local_file = liststore[rows[0]][0].rstrip('/')
        
        new_file = focus_dir.rstrip('/') +'/'+ local_file
#        print 'new_file', new_file
        if os.path.isdir(new_file):
            self.cur_dir = self.cur_dir.rstrip('/') +'/'+ local_file
            self.xml.get_widget('location_field').set_text(self.cur_dir)
        else:
            print 'not a dir:', new_file
            desktop.open(new_file)
        self.refresh_file_list()

    def go_home(self, o):
        self.cur_dir = os.path.expanduser("~")
        self.xml.get_widget('location_field').set_text(self.cur_dir)
        self.refresh_file_list()

    def select_pardir(self, o):
        self.cur_dir = ('/'.join(self.cur_dir.split('/')[:-1]))
        if not self.cur_dir: self.cur_dir = '/'
        self.xml.get_widget('location_field').set_text(self.cur_dir)
        self.refresh_file_list()

    def select_dir(self, o):
        new_file = o.get_current_folder()
        if os.path.isdir(new_file):
            self.cur_dir = new_file
        else:
            print 'not a dir:', new_file
            desktop.open(new_file)
        self.refresh_file_list()

    def select_backup(self, treeview):
        selection = treeview.get_selection()
        liststore, rows = selection.get_selected_rows()
        self.selected_backup = liststore[rows[0]][1]
        self.xml.get_widget('restore_button').set_sensitive( bool(self.selected_backup) )
        self.refresh_file_list()
        
    def run_backup(self, o):
        self.backup_thread = threading.Thread(target= self.backup.backup)
        self.backup_thread.start()
        
    def run_restore(self, o):
        print o
        self.restore_thread = threading.Thread(target= self.backup.restore)
        self.restore_thread.start()
        
    def refresh_all(self, o):
        self.refresh_available_backup_list()
        self.refresh_file_list()
        
    def refresh_available_backup_list(self):
        self.available_backups = self.backup.get_available_backups()
        self.available_backup_list.clear()
        self.available_backup_list.append( ('now',None) )
        for n in self.available_backups:
            adjusted_for_tz = n + get_tz_offset()
            self.available_backup_list.append( (adjusted_for_tz,n) )
            
    def get_focus_dir(self):
        if self.selected_backup:
            return self.backup.parent_backup_dir +'/'+ self.selected_backup.strftime(BACKUP_DIR_DATE_FORMAT) + self.cur_dir
        else:
            return self.cur_dir

    
    def refresh_file_list(self):
        pardir_button = self.xml.get_widget('pardir_button')
        pardir_button.set_sensitive( self.cur_dir != '/' )
        self.file_list.clear()
        previous_focus_dir = None
        previous_backup = None
        show_hidden_files = client.get_bool("/apps/flyback/show_hidden_files")
        sort_dirs_first = client.get_bool("/apps/flyback/sort_dirs_first")
        if self.selected_backup:
            focus_dir = self.backup.parent_backup_dir +'/'+ self.selected_backup.strftime(BACKUP_DIR_DATE_FORMAT) + self.cur_dir
            i = self.available_backups.index(self.selected_backup)
            if i<len(self.available_backups)-1:
                previous_backup = self.available_backups[i+1]
                previous_focus_dir = self.backup.parent_backup_dir +'/'+ previous_backup.strftime(BACKUP_DIR_DATE_FORMAT) + self.cur_dir
        else:
            if self.available_backups:
                previous_backup = self.available_backups[0]
                previous_focus_dir = self.backup.parent_backup_dir +'/'+ previous_backup.strftime(BACKUP_DIR_DATE_FORMAT) + self.cur_dir
            focus_dir = self.cur_dir
#        print 'previous_backup, previous_focus_dir', previous_backup, previous_focus_dir
        if True:
#        try:
            try:
                files = os.listdir(focus_dir)
            except:
                self.select_pardir(None)
                return
            
            files.sort()
            if sort_dirs_first:
                dirs = []
                not_dirs = []
                for file in files:
                    if os.path.isdir( os.path.join( focus_dir, file ) ):
                        dirs.append(file)
                    else:
                        not_dirs.append(file)
                files = dirs
                files.extend(not_dirs)
            for file in files:
                full_file_name = os.path.join( focus_dir, file )
                file_stats = os.stat(full_file_name)
                color = False
#                print 'full_file_name', full_file_name
#                print 'file_stats', file_stats
                if previous_focus_dir:
                    previous_full_file_name = os.path.join( previous_focus_dir, file )
                    if os.path.isfile(previous_full_file_name):
#                        print 'previous_full_file_name', previous_full_file_name
                        previous_file_stats = os.stat(previous_full_file_name)
#                        print 'previous_file_stats', previous_file_stats
                        if self.selected_backup:
                            if file_stats[1]!=previous_file_stats[1]:
                                color = True
                        else:
                            if file_stats[8]!=previous_file_stats[8]:
                                color = True
                    else:
                        if not os.path.isdir(previous_full_file_name):
                            color = True
                try:
                    if os.path.isdir(full_file_name):
                        size = humanize_count( len(os.listdir(full_file_name)), 'item', 'items' )
                        icon = pardir_button.render_icon(gtk.STOCK_DIRECTORY, gtk.ICON_SIZE_MENU)
#                        color = False
                    else:
                        size = humanize_bytes(file_stats[6])
                        icon = pardir_button.render_icon(gtk.STOCK_FILE, gtk.ICON_SIZE_MENU)
                except:
                    size = ''
                    icon = pardir_button.render_icon(gtk.STOCK_FILE, gtk.ICON_SIZE_MENU)
                if show_hidden_files or not file.startswith('.'):
                    self.file_list.append(( file, size, datetime.fromtimestamp(file_stats[8]), color, icon ))
#        except:
#            traceback.print_stack()
        
    def show_about_dialog(self, o):
        about = gtk.AboutDialog()
        about.set_name('FlyBack')
        about.set_version(VERSION)
        about.set_copyright('Copyright (c) 2007 Derek Anderson')
        about.set_comments('''FlyBack is a backup and recovery tool loosely modeled after Apple's new "Time Machine".''')
        about.set_license(GPL)
        about.set_website('http://code.google.com/p/flyback/')
        about.set_authors(['Derek Anderson','http://kered.org'])
        about.connect('response', lambda x,y: about.destroy())
        about.show()
    
    def hide_window(self, window, o2):
        window.hide()
        return True
    
    def check_if_safe_to_quit(self, w, o):
            if self.backup_thread and self.backup_thread.isAlive():
                error = gtk.MessageDialog( type=gtk.MESSAGE_ERROR, buttons=gtk.BUTTONS_OK, flags=gtk.DIALOG_MODAL )
                error.set_markup("""<b>Backup Running</b>\n\nA backup is currently running...\nPlease wait for it to finish before exiting.""")
                error.connect('response', lambda x,y: error.destroy())
                error.show()
                return True
            elif self.restore_thread and self.restore_thread.isAlive():
                error = gtk.MessageDialog( type=gtk.MESSAGE_ERROR, buttons=gtk.BUTTONS_OK, flags=gtk.DIALOG_MODAL )
                error.set_markup("""<b>Restore Running</b>\n\nA restore is currently running...\nPlease wait for it to finish before exiting.""")
                error.connect('response', lambda x,y: error.destroy())
                error.show()
                return True
            else:
                gtk.main_quit()
                
    def show_hide_output(self, o):
        if o.get_active():
            self.xml.get_widget('scrolledwindow_backup_output').show()
        else:
            self.xml.get_widget('scrolledwindow_backup_output').hide()
        client.set_bool("/apps/flyback/show_output", o.get_active())
        
    def show_hide_opengl(self, o):
        if o.get_active():
            self.xml.get_widget("window_opengl").show_all()
        else:
            self.xml.get_widget("window_opengl").hide()
        client.set_bool("/apps/flyback/show_opengl", o.get_active())
    
    def file_list_button_press_event(self, treeview, event):
        if event.button == 3:
            x = int(event.x)
            y = int(event.y)
            time = event.time
            pthinfo = treeview.get_path_at_pos(x, y)
            if pthinfo is not None:
                path, col, cellx, celly = pthinfo
                treeview.grab_focus()
                treeview.set_cursor( path, col, 0)
                menu = gtk.Menu()
                open = gtk.ImageMenuItem(stock_id=gtk.STOCK_OPEN)
#                open.set_image( gtk.image_new_from_stock(gtk.STOCK_OPEN, gtk.ICON_SIZE_MENU) )
                open.connect( 'activate', lambda x: self.select_subdir(self.xml.get_widget('file_list'), None, None) )
                menu.append(open)
                folder = gtk.ImageMenuItem(stock_id='Open Containing _Folder')
                folder.set_image( gtk.image_new_from_stock(gtk.STOCK_DIRECTORY, gtk.ICON_SIZE_MENU) )
                folder.connect( 'activate', lambda x: desktop.open(self.get_focus_dir()) )
                menu.append(folder)
                restore = gtk.ImageMenuItem(stock_id="_Restore this Version")
                restore.set_image( gtk.image_new_from_stock(gtk.STOCK_REVERT_TO_SAVED, gtk.ICON_SIZE_MENU) )
                restore.set_sensitive( bool(self.selected_backup) )
                restore.connect( 'activate', self.run_restore )
                menu.append(restore)
                menu.show_all()
                menu.popup(None, None, None, event.button, event.get_time())
            return True
        return False
   
    def __init__(self):
        
        gnome.init("programname", "version")
        self.xml = gtk.glade.XML(RUN_FROM_DIR + 'viewer.glade')
        o = self
        self.backup = backup(o)
        
        # bind the window events
        main_window = self.xml.get_widget('window1')
        main_window.connect("delete-event", self.check_if_safe_to_quit )
        icon = main_window.render_icon(gtk.STOCK_HARDDISK, gtk.ICON_SIZE_BUTTON)
        main_window.set_icon(icon)
        self.xml.get_widget('prefs_dialog').connect("delete-event", self.hide_window)
        self.xml.get_widget('help_window').connect("delete-event", self.hide_window)
        self.xml.get_widget('window_opengl').connect("delete-event", self.hide_window)
        self.xml.get_widget('history_dialog').connect("delete-event", self.hide_window)
    
        # init opengl frontend
#        main.show_all()

        # build the model for the available backups list
        self.refresh_available_backup_list()
        # and bind it to the treeview
        available_backup_list_widget = self.xml.get_widget('available_backup_list')
        available_backup_list_widget.set_model(self.available_backup_list)
        available_backup_list_widget.set_headers_visible(True)
        renderer = gtk.CellRendererText()
        column = gtk.TreeViewColumn("system snapshots", renderer, text=0)
        column.set_clickable(True)
        column.set_sort_indicator(True)
        column.set_reorderable(True)
        column.set_sort_column_id(0)
        num = available_backup_list_widget.append_column(column)
        # and add its handlers
        available_backup_list_widget.connect('cursor-changed', self.select_backup)
        
        # build the model for the file list
        self.refresh_file_list()
        # and bind it to the treeview
        file_list_widget = self.xml.get_widget('file_list')
        file_list_widget.set_model(self.file_list)
        file_list_widget.set_headers_visible(True)
        file_list_widget.get_selection().set_mode(gtk.SELECTION_MULTIPLE)
        num = file_list_widget.append_column( gtk.TreeViewColumn("", gtk.CellRendererToggle(), active=3) )
        
        column = gtk.TreeViewColumn()
        column.set_title('file name')
        file_list_widget.append_column(column)
        renderer = gtk.CellRendererPixbuf()
        column.pack_start(renderer, expand=False)
        column.add_attribute(renderer, 'pixbuf', 4)
        renderer = gtk.CellRendererText()
        column.pack_start(renderer, expand=True)
        column.add_attribute(renderer, 'text', 0)        
        
        num = file_list_widget.append_column( gtk.TreeViewColumn("size", gtk.CellRendererText(), text=1) )
        num = file_list_widget.append_column( gtk.TreeViewColumn("last modified", gtk.CellRendererText(), text=2) )
        for num in range(4):
            col = file_list_widget.get_column(num)
            col.set_resizable(True)
            col.set_clickable(True)
            col.set_sort_indicator(True)
            col.set_reorderable(True)
            col.set_sort_column_id(num)
        # and add its handlers
        file_list_widget.connect('row-activated', self.select_subdir)
        file_list_widget.connect('button-press-event', self.file_list_button_press_event)

        # bind toolbar functions
        self.xml.get_widget('backup_button').connect('clicked', self.run_backup)
        self.xml.get_widget('restore_button').connect('clicked', self.run_restore)
        self.xml.get_widget('refresh_button').connect('clicked', self.refresh_all)
        self.xml.get_widget('pardir_button').connect('clicked', self.select_pardir)
        self.xml.get_widget('home_button').connect('clicked', self.go_home)
        # self.xml.get_widget('location_field').connect('current-folder-changed', self.select_dir)
        
        # bind menu functions
        self.xml.get_widget('menuitem_about').connect('activate', self.show_about_dialog)
        self.xml.get_widget('menuitem_prefs').connect('activate', lambda w: PrefsGUI(self) )
        self.xml.get_widget('menuitem_backup_history').connect('activate', lambda w: HistoryGUI(self) )
        self.xml.get_widget('menuitem_quit').connect('activate', gtk.main_quit)
        menuitem_show_output = self.xml.get_widget('menuitem_show_output')
        menuitem_show_output.connect('activate', self.show_hide_output )
        menuitem_show_output.set_active(client.get_bool("/apps/flyback/show_output"))
        self.show_hide_output(menuitem_show_output)
        menuitem_show_opengl = self.xml.get_widget('menuitem_show_opengl')
        menuitem_show_opengl.set_active(client.get_bool("/apps/flyback/show_opengl"))
        menuitem_show_opengl.connect('activate', self.show_hide_opengl )
        self.show_hide_opengl(menuitem_show_opengl)
        menuitem_show_hidden_files = self.xml.get_widget('menuitem_show_hidden_files')
        menuitem_show_hidden_files.set_active(client.get_bool("/apps/flyback/show_hidden_files"))
        menuitem_show_hidden_files.connect('activate', lambda x: client.set_bool('/apps/flyback/show_hidden_files',x.get_active())==self.refresh_file_list() )
        menuitem_sort_dirs_first = self.xml.get_widget('menuitem_sort_dirs_first')
        menuitem_sort_dirs_first.set_active(client.get_bool("/apps/flyback/sort_dirs_first"))
        menuitem_sort_dirs_first.connect('activate', lambda x: client.set_bool('/apps/flyback/sort_dirs_first',x.get_active())==self.refresh_file_list() )
        
        # set current folder
        self.xml.get_widget('location_field').set_text(self.cur_dir)
        
        main_window.show()
        
        # if no external storage defined, show prefs
        if not client.get_string("/apps/flyback/external_storage_location"):
            PrefsGUI(self)


class PrefsGUI:
    
    xml = None
    main_gui = None
    
    included_dirs = []
    included_dirs_liststore = gtk.ListStore(gobject.TYPE_STRING)
    excluded_patterns = []
    excluded_patterns_liststore = gtk.ListStore(gobject.TYPE_STRING)
    pref_delete_backups_free_space_units = ['MB','GB']
    pref_delete_backups_after_units = ['days','months','years']
    
    pref_cron_minute_options = [
        ['on the hour', '0'],
        ['15 minutes after the hour', '15'],
        ['30 minutes after the hour', '30'],
        ['45 minutes after the hour', '45'],
        ['every half an hour', '0,30'],
        ['every 15 minutes', '0,15,30,45'],
    ]
    pref_cron_hour_options = [
        ['every hour', '*'],
        ['every other hour', '*/2'],
        ['every hour (8am-8pm)', '8-20'],
        ['every other hour (8am-8pm)', '8,10,12,14,16,18,20'],
        ['at noon and midnight', '0,12'],
        ['at 3am', '3'],
    ]
    pref_cron_day_week_options = [
        ['every day of the week', '*'],
        ['every weekday', '1,2,3,4,5'],
        ['on monday/wednesday/friday', '1,3,5'],
        ['on tuesday/thursday/saturday', '2,4,6'],
        ['only on sunday', '0'],
    ]
    pref_cron_day_month_options = [
        ['every day of the month', '*'],
        ['on the first of the month', '1'],
        ['on the 1st and the 15h', '1,15'],
        ['on the 1st, 10th and 20th', '1,10,20'],
        ['on the 1st, 8th, 16th and 24th', '1,8,16,24'],
    ]
            
    def save_prefs(self, o):
        external_storage_location = self.xml.get_widget('external_storage_location').get_current_folder()
        client.set_string ("/apps/flyback/external_storage_location", external_storage_location )
        if not os.path.isdir(external_storage_location):
            os.mkdir(external_storage_location)
        if not os.path.isdir(external_storage_location + '/flyback'):
            os.mkdir(external_storage_location + '/flyback')
        client.set_list("/apps/flyback/included_dirs", self.included_dirs )
        client.set_bool( '/apps/flyback/prefs_only_one_file_system_checkbutton', self.xml.get_widget('prefs_only_one_file_system_checkbutton').get_active() )
        client.set_list("/apps/flyback/excluded_patterns", self.excluded_patterns )
        if self.xml.get_widget('pref_run_backup_automatically').get_active():
            crontab = self.save_crontab()
            client.set_string ("/apps/flyback/crontab", crontab )
            self.install_crontab(crontab)
        else:
            client.set_string ("/apps/flyback/crontab", '' )
            self.install_crontab(None)
        
        # delete backups
        client.set_bool( '/apps/flyback/pref_delete_backups_free_space', self.xml.get_widget('pref_delete_backups_free_space').get_active() )
        client.set_int( '/apps/flyback/pref_delete_backups_free_space_qty', int( self.xml.get_widget('pref_delete_backups_free_space_qty').get_value() ) )
        widget_pref_delete_backups_free_space_unit = self.xml.get_widget('pref_delete_backups_free_space_unit')
        client.set_string( '/apps/flyback/pref_delete_backups_free_space_unit', widget_pref_delete_backups_free_space_unit.get_model().get_value( widget_pref_delete_backups_free_space_unit.get_active_iter(), 0 ) )
        client.set_bool( '/apps/flyback/pref_delete_backups_after', self.xml.get_widget('pref_delete_backups_after').get_active() )
        client.set_int( '/apps/flyback/pref_delete_backups_after_qty', int( self.xml.get_widget('pref_delete_backups_after_qty').get_value() ) )
        widget_pref_delete_backups_after_unit = self.xml.get_widget('pref_delete_backups_after_unit')
        client.set_string( '/apps/flyback/pref_delete_backups_after_unit', widget_pref_delete_backups_after_unit.get_model().get_value( widget_pref_delete_backups_after_unit.get_active_iter(), 0 ) )
            
        self.xml.get_widget('prefs_dialog').hide()
        self.main_gui.refresh_available_backup_list()
        
    def add_include_dir(self, o):
            new_dir =  self.xml.get_widget('include_dir_filechooser').get_current_folder()
            if new_dir not in self.included_dirs:
                self.included_dirs.append(new_dir)
                self.included_dirs.sort()
                self.refresh_included_dirs_list()

    def refresh_included_dirs_list(self):
        self.included_dirs_liststore.clear()
        for n in self.included_dirs:
            self.included_dirs_liststore.append( (n,) )
            
    def include_dir_key_press(self, treeview, o2):
        if o2.keyval==gtk.keysyms.Delete:
            print 'woot!!!'
            selection = treeview.get_selection()
            liststore, rows = selection.get_selected_rows()
            self.included_dirs.remove( liststore[rows[0]][0] )
            self.refresh_included_dirs_list()

    def add_exclude_dir(self, o):
            new_dir =  self.xml.get_widget('pattern_exclude').get_text()
            if new_dir not in self.excluded_patterns:
                self.excluded_patterns.append(new_dir)
                self.excluded_patterns.sort()
                self.refresh_excluded_patterns_list()

    def refresh_excluded_patterns_list(self):
        self.excluded_patterns_liststore.clear()
        for n in self.excluded_patterns:
            self.excluded_patterns_liststore.append( (n,) )
            
    def exclude_dir_key_press(self, treeview, o2):
        if o2.keyval==gtk.keysyms.Delete:
            print 'woot!!!'
            selection = treeview.get_selection()
            liststore, rows = selection.get_selected_rows()
            self.excluded_patterns.remove( liststore[rows[0]][0] )
            self.refresh_excluded_patterns_list()
            
    def delete_element(self, o, i, a, f):
        a.pop(i)
        f()
            
    def include_dir_button_press_event(self, treeview, event):
        if event.button == 3:
            x = int(event.x)
            y = int(event.y)
            time = event.time
            pthinfo = treeview.get_path_at_pos(x, y)
            if pthinfo is not None:
                path, col, cellx, celly = pthinfo
                treeview.grab_focus()
                treeview.set_cursor( path, col, 0)
                menu = gtk.Menu()
                delete = gtk.ImageMenuItem(stock_id=gtk.STOCK_DELETE)
                delete.connect( 'activate', self.delete_element, pthinfo[0][0], self.included_dirs, self.refresh_included_dirs_list )
                menu.append(delete)
                menu.show_all()
                menu.popup(None, None, None, event.button, event.get_time())
            return True
   
    def exclude_dir_button_press_event(self, treeview, event):
        if event.button == 3:
            x = int(event.x)
            y = int(event.y)
            time = event.time
            pthinfo = treeview.get_path_at_pos(x, y)
            if pthinfo is not None:
                path, col, cellx, celly = pthinfo
                treeview.grab_focus()
                treeview.set_cursor( path, col, 0)
                menu = gtk.Menu()
                delete = gtk.ImageMenuItem(stock_id=gtk.STOCK_DELETE)
                delete.connect( 'activate', self.delete_element, pthinfo[0][0], self.excluded_patterns, self.refresh_excluded_patterns_list )
                menu.append(delete)
                menu.show_all()
                menu.popup(None, None, None, event.button, event.get_time())
            return True
   
    def show_excluded_patterns_help(self, o):
        self.xml.get_widget('help_text').get_buffer().set_text(help_data.EXCLUDED_PATTERNS)
        self.xml.get_widget('help_window').show()
        
    def index_of_in_list_of_lists(self, value, list, column, not_found=-1):
        for i in range(0,len(list)):
            if value==list[i][column]:
                return i
        return not_found
        
    def load_crontab(self, s):
        self.xml.get_widget('pref_run_backup_automatically').set_active( bool(s) )
        self.xml.get_widget('pref_cron_minute').set_sensitive( bool(s) )
        self.xml.get_widget('pref_cron_hour').set_sensitive( bool(s) )
        self.xml.get_widget('pref_cron_day_week').set_sensitive( bool(s) )
        self.xml.get_widget('pref_cron_day_month').set_sensitive( bool(s) )
        min = '0'
        hour = '3'
        day_month = '*'
        month = '*'
        day_week = '*'
        
        try:
            sa = s.split(' ')
            min = sa[0]
            hour = sa[1]
            day_month = sa[2]
            #month = sa[3]
            day_week = sa[4]
        except:
            if s:
                print 'count not parse gconf /apps/flyback/crontab - using defaults'
        
        self.xml.get_widget('pref_cron_minute').set_active( self.index_of_in_list_of_lists( min, self.pref_cron_minute_options, 1, 0 ) )
        self.xml.get_widget('pref_cron_hour').set_active( self.index_of_in_list_of_lists( hour, self.pref_cron_hour_options, 1, 0 ) )
        self.xml.get_widget('pref_cron_day_month').set_active( self.index_of_in_list_of_lists( day_month, self.pref_cron_day_month_options, 1, 0 ) )
        self.xml.get_widget('pref_cron_day_week').set_active( self.index_of_in_list_of_lists( day_week, self.pref_cron_day_week_options, 1, 0 ) )

    def save_crontab(self):
        sa = []
        sa.append( self.pref_cron_minute_options[ self.xml.get_widget('pref_cron_minute').get_active() ][1] )
        sa.append( self.pref_cron_hour_options[ self.xml.get_widget('pref_cron_hour').get_active() ][1] )
        sa.append( self.pref_cron_day_month_options[ self.xml.get_widget('pref_cron_day_month').get_active() ][1] )
        sa.append( '*' )
        sa.append( self.pref_cron_day_week_options[ self.xml.get_widget('pref_cron_day_week').get_active() ][1] )
        return ' '.join(sa)
    
    def install_crontab(self, c):
        existing_crons = []
        
        stdin, stdout = os.popen4('crontab -l')
        for line in stdout:
            if line.startswith('no crontab for'): continue
            if line.endswith('#flyback\n'): continue
            existing_crons.append(line)
        if c:
            existing_crons.append(c + ' python '+ os.getcwd() +'/flyback.py --backup #flyback\n')
        stdin.close()
        stdout.close()

        f = open('/tmp/flyback_tmp_cron', 'w')
        f.writelines( existing_crons )
        f.close()
        os.system('crontab /tmp/flyback_tmp_cron')
    
    def check_crontab_entry(self, s):
        sa = s.replace(' ',',').replace(',,',',').split(',')
        if sa:
            return ','.join(sa)
        else:
            return '*'

    def set_model_from_list (self, cb, items, index=None):
        """Setup a ComboBox or ComboBoxEntry based on a list of strings."""           
        model = gtk.ListStore(str)
        for i in items:
            if index==None:
                model.append((i,))
            else:
                model.append((i[index],))
        cb.set_model(model)

    def __init__(self, o):
        self.xml = o.xml
        self.main_gui = o
        
        # init external_storage_location
        external_storage_location = client.get_string("/apps/flyback/external_storage_location")
        if not external_storage_location:
            external_storage_location = '/external_storage_location'
        self.xml.get_widget('external_storage_location').set_current_folder( external_storage_location )

        self.xml.get_widget('prefs_dialog').show()

        # init includes / excludes
        self.included_dirs = client.get_list("/apps/flyback/included_dirs")
        self.xml.get_widget('prefs_only_one_file_system_checkbutton').set_active( client.get_bool('/apps/flyback/prefs_only_one_file_system_checkbutton') )
        self.excluded_patterns = client.get_list("/apps/flyback/excluded_patterns", DEFAULT_EXCLUDES)
        
        # init backup crontab
        self.set_model_from_list( self.xml.get_widget('pref_cron_minute'), self.pref_cron_minute_options, index=0 )
        self.set_model_from_list( self.xml.get_widget('pref_cron_hour'), self.pref_cron_hour_options, index=0 )
        self.set_model_from_list( self.xml.get_widget('pref_cron_day_week'), self.pref_cron_day_week_options, index=0 )
        self.set_model_from_list( self.xml.get_widget('pref_cron_day_month'), self.pref_cron_day_month_options, index=0 )
        self.xml.get_widget('pref_run_backup_automatically').connect('toggled', lambda x: self.xml.get_widget('pref_cron_minute').set_sensitive(x.get_active()) == self.xml.get_widget('pref_cron_hour').set_sensitive(x.get_active()) == self.xml.get_widget('pref_cron_day_week').set_sensitive(x.get_active()) == self.xml.get_widget('pref_cron_day_month').set_sensitive(x.get_active())  )
        self.load_crontab( client.get_string("/apps/flyback/crontab") )
        
        # init backup auto-delete
        s = client.get_bool('/apps/flyback/pref_delete_backups_free_space')
        widget_pref_delete_backups_free_space = self.xml.get_widget('pref_delete_backups_free_space')
        widget_pref_delete_backups_free_space.set_active(s)
        widget_pref_delete_backups_free_space.connect('toggled', lambda x: self.xml.get_widget('pref_delete_backups_free_space_qty').set_sensitive(x.get_active())==self.xml.get_widget('pref_delete_backups_free_space_unit').set_sensitive(x.get_active())  )
        widget_pref_delete_backups_free_space_qty = self.xml.get_widget('pref_delete_backups_free_space_qty')
        widget_pref_delete_backups_free_space_qty.set_sensitive(s)
        widget_pref_delete_backups_free_space_qty.set_value( client.get_int('/apps/flyback/pref_delete_backups_free_space_qty') )
        widget_pref_delete_backups_free_space_unit = self.xml.get_widget('pref_delete_backups_free_space_unit')
        widget_pref_delete_backups_free_space_unit.set_sensitive(s)
        s = client.get_bool('/apps/flyback/pref_delete_backups_after')
        self.xml.get_widget('pref_delete_backups_after').set_active(s)
        self.xml.get_widget('pref_delete_backups_after').connect('toggled', lambda x: self.xml.get_widget('pref_delete_backups_after_qty').set_sensitive(x.get_active())==self.xml.get_widget('pref_delete_backups_after_unit').set_sensitive(x.get_active())  )
        self.xml.get_widget('pref_delete_backups_after_qty').set_sensitive(s)
        self.xml.get_widget('pref_delete_backups_after_qty').set_value( client.get_int('/apps/flyback/pref_delete_backups_after_qty') )
        widget_pref_delete_backups_after_unit = self.xml.get_widget('pref_delete_backups_after_unit')
        widget_pref_delete_backups_after_unit.set_sensitive(s)
        s = client.get_string('/apps/flyback/pref_delete_backups_free_space_unit', 'GB')
        self.set_model_from_list( widget_pref_delete_backups_free_space_unit, self.pref_delete_backups_free_space_units )
        widget_pref_delete_backups_free_space_unit.set_active_iter( widget_pref_delete_backups_free_space_unit.get_model().iter_nth_child( None, self.pref_delete_backups_free_space_units.index( s ) ) )
        s = client.get_string('/apps/flyback/pref_delete_backups_after_unit', 'years')
        self.set_model_from_list( widget_pref_delete_backups_after_unit, self.pref_delete_backups_after_units )
        widget_pref_delete_backups_after_unit.set_active_iter( widget_pref_delete_backups_after_unit.get_model().iter_nth_child( None, self.pref_delete_backups_after_units.index( s ) ) )
        
        # bind ok/cancel buttons
        self.xml.get_widget('prefs_dialog_ok').connect('clicked', self.save_prefs)
        self.xml.get_widget('prefs_dialog_cancel').connect('clicked', lambda w: self.xml.get_widget('prefs_dialog').hide() )

        # bind include/exclude dir buttons
        self.xml.get_widget('include_dir_add_button').connect('clicked', self.add_include_dir)
        self.xml.get_widget('dirs_include').connect('key-press-event', self.include_dir_key_press)
        self.xml.get_widget('button_add_pattern_exclude').connect('clicked', self.add_exclude_dir)
        self.xml.get_widget('patterns_exclude').connect('key-press-event', self.exclude_dir_key_press)
        self.xml.get_widget('help_pattern_exclude').connect('clicked', self.show_excluded_patterns_help)

        # build include/exclude lists
        dirs_includet_widget = self.xml.get_widget('dirs_include')
        dirs_includet_widget.set_model(self.included_dirs_liststore)
        dirs_includet_widget.set_headers_visible(True)
        dirs_includet_widget.connect('button-press-event', self.include_dir_button_press_event)
        renderer = gtk.CellRendererText()
        column = gtk.TreeViewColumn("included dirs", renderer, text=0)
        if not dirs_includet_widget.get_columns():
            dirs_includet_widget.append_column(column)
        self.refresh_included_dirs_list()
        dirs_excludet_widget = self.xml.get_widget('patterns_exclude')
        dirs_excludet_widget.set_model(self.excluded_patterns_liststore)
        dirs_excludet_widget.set_headers_visible(True)
        dirs_excludet_widget.connect('button-press-event', self.exclude_dir_button_press_event)
        renderer = gtk.CellRendererText()
        column = gtk.TreeViewColumn("exclude patterns", renderer, text=0)
        if not dirs_excludet_widget.get_columns():
            dirs_excludet_widget.append_column(column)
        self.refresh_excluded_patterns_list()

        
class HistoryGUI:
    
    xml = None
    main_gui = None
    
    treestore = gtk.TreeStore(str, str, str, 'gboolean') # type, start, time, error
    cmd_stdouts = {}
    cmd_stderrs = {}
    
    
    def refresh(self):
        self.treestore.clear()
        self.cmd_stdouts = {}
        self.cmd_stderrs = {}
        conn = get_or_create_db()
        c = conn.cursor()
        d = conn.cursor()
        xx = -1
        c.execute("select type, start_time, end_time, failure, id from operation order by id desc;")
        for x in c:
            xx += 1
            if x[0]=='backup': type = 'backup'
            if x[0]=='restore': type = 'restore'
            if x[0]=='delete_old_backups_to_free_space': type = 'cleanup'
            if x[0]=='delete_too_old_backups': type = 'cleanup'
            try:
                when = datetime(*strptime(x[1], BACKUP_DATE_FORMAT)[0:6])
                time_length = humanize_timedelta( datetime(*strptime(x[2], BACKUP_DATE_FORMAT)[0:6]) - when )
                when = when + get_tz_offset()
            except:
                print 'error:', sys.exc_info()
                when = ''
                time_length = ''
            iter = self.treestore.append(None, (type, when, time_length, not bool(x[3])) )
            
            d.execute("select cmd, stdout, stderr from command where operation_id=? order by id;", (x[4],) )
            yy = -1
            all_stdouts = []
            all_stderrs = []
            for y in d:
                yy += 1
                cmds = y[0].split()
                cmd = cmds[0]
                if cmd=='nice':
                    cmd = cmds[2]
                iter2 = self.treestore.append(iter, (cmd,'','','') )
                self.cmd_stdouts[(xx,yy)] = '$ '+ y[0] +'\n'+ y[1]
                self.cmd_stderrs[(xx,yy)] = '$ '+ y[0] +'\n'+ y[2]
                all_stdouts.append( self.cmd_stdouts[(xx,yy)] )
                all_stderrs.append( self.cmd_stderrs[(xx,yy)] )
            self.cmd_stdouts[(xx,)] = ''.join(all_stdouts)
            self.cmd_stderrs[(xx,)] = ''.join(all_stderrs)
            
        conn.close()
    
    def select_cmd(self, treeview):
        selection = treeview.get_selection()
        liststore, rows = selection.get_selected_rows()
        if rows:
            try:
                text_view = self.xml.get_widget('stdout')
                text_buffer = text_view.get_buffer()
#                text_buffer.delete( text_buffer.get_start_iter(), text_buffer.get_end_iter() )
                text_buffer.set_text( self.cmd_stdouts[rows[0]] )
                text_view = self.xml.get_widget('stderr')
                text_buffer = text_view.get_buffer()
#                text_buffer.delete( text_buffer.get_start_iter(), text_buffer.get_end_iter() )
                text_buffer.set_text( self.cmd_stderrs[rows[0]] )
            except:
                print 'error:', sys.exc_info()
                pass

    def __init__(self, o):
        self.xml = o.xml
        self.main_gui = o
        
        operation_list_widget = self.xml.get_widget('operation_list')
        operation_list_widget.set_model(self.treestore)
        operation_list_widget.set_headers_visible(True)
        #operation_list_widget.connect('button-press-event', self.include_dir_button_press_event)
        operation_list_widget.connect('cursor-changed', self.select_cmd)
        operation_list_widget.append_column( gtk.TreeViewColumn("action", gtk.CellRendererText(), text=0) )
        operation_list_widget.append_column( gtk.TreeViewColumn("when", gtk.CellRendererText(), text=1) )
        operation_list_widget.append_column( gtk.TreeViewColumn("time", gtk.CellRendererText(), text=2) )
        operation_list_widget.append_column( gtk.TreeViewColumn("success", gtk.CellRendererToggle(), active=3) )
        #operation_list_widget.append_column( gtk.TreeViewColumn("success", gtk.CellRendererText(), text=3) )
        self.refresh()

        # bind close button
        self.xml.get_widget('history_dialog_close').connect('clicked', lambda w: self.xml.get_widget('history_dialog').hide() )
        self.xml.get_widget('history_dialog_refresh').connect('clicked', lambda w: self.refresh() )

        self.xml.get_widget('history_dialog').show()



def main():
    # parse command line options
    try:
        opts, args = getopt.getopt(sys.argv[1:], "b", ["backup"])
    except getopt.error, msg:
        print msg
        print "for help use --help"
        sys.exit(2)
    # process options
    for o, a in opts:
        if o in ("-b", "--backup"):
            backup().backup()
            sys.exit(0)

    MainGUI()
    gtk.main()


if __name__ == "__main__":
    main()
        
