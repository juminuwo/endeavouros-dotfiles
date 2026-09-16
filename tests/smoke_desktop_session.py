"""Opt-in real i3/GTK round trip on a private Xvfb display.

Run: python tests/smoke_desktop_session.py
Requires the installed i3-resurrect command, Xvfb, and system GTK3 bindings.
Does not restore, close, or save any windows on the user's actual desktop.
"""
import importlib.machinery,importlib.util,tempfile,os,subprocess,time,json
from pathlib import Path
from unittest.mock import patch
script = Path(__file__).resolve().parents[1] / 'config/bin/desktop-session'
loader=importlib.machinery.SourceFileLoader('ds',str(script))
spec=importlib.util.spec_from_loader(loader.name,loader);ds=importlib.util.module_from_spec(spec);loader.exec_module(ds)
processes=[]

def spawn(*args,**kwargs):
 p=subprocess.Popen(*args,**kwargs);processes.append(p);return p

def wait_for(fn):
 for _ in range(150):
  try:
   value=fn()
   if value:return value
  except Exception:pass
  time.sleep(.1)
 raise RuntimeError('fixture timeout')

with tempfile.TemporaryDirectory(prefix='desktop-session-smoke-') as tmp:
 tmp=Path(tmp)
 try:
  r,w=os.pipe();x=spawn(['Xvfb','-displayfd',str(w),'-screen','0','1440x900x24'],pass_fds=[w],stderr=subprocess.DEVNULL);os.close(w)
  with os.fdopen(r) as f:display=f.readline().strip()
  os.environ['DISPLAY']=':'+display;os.environ.pop('I3SOCK',None)
  conf=tmp/'i3.conf';conf.write_text('font pango:monospace 10\nfocus_follows_mouse no\n')
  wm=spawn(['i3','-c',str(conf)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  wait_for(ds.ps.tree)
  fixture=tmp/'app.py';fixture.write_text('import gi,sys\ngi.require_version("Gtk","3.0")\nfrom gi.repository import Gtk\nw=Gtk.Window(title=sys.argv[1]);w.set_wmclass(sys.argv[1],"DesktopFixture");w.set_default_size(360,240);w.connect("destroy",Gtk.main_quit);w.show_all();Gtk.main()\n')
  apps=[]
  for index,name in enumerate(['first','second','third']):
   apps.append(spawn(['/usr/bin/python',str(fixture),name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL))
   wait_for(lambda:len(ds.real_windows(ds.ps.tree()))==index+1)
  for ws,n in ds.real_windows(ds.ps.tree()):
   target='1: work' if n['window_properties']['instance']!='third' else '8'
   ds.ps.i3(f'[con_id={n["id"]}] move container to workspace "{target}"')
  work=next(n for n in ds.nodes(ds.ps.tree()) if n.get('type')=='workspace' and n['name']=='1: work')
  ds.ps.i3(f'[con_id={work["id"]}] layout tabbed')
  ds.STATE=tmp/'state';ds.STATE.mkdir();ds.SCRIPT=str(script)
  ds.ps.atomic_json(ds.STATE/'restore.json',{'desktop':ds.ps.desktop_id(),'complete':True})
  with patch.object(ds.ps,'save'),patch.object(ds.ps,'snapshot',return_value=(None,{})),patch.object(ds.ps,'summary',return_value='fixture projects'),patch.object(ds,'notify'):
   ds.save()
  folder,manifest=ds.pointer()
  # Leave two apps running, with a nested autostart container, to test adoption.
  apps[2].terminate();apps[2].wait()
  wait_for(lambda:len(ds.real_windows(ds.ps.tree()))==2)
  first=next(n for ws,n in ds.real_windows(ds.ps.tree()) if n['window_properties']['instance']=='first')
  ds.ps.i3(f'[con_id={first["id"]}] focus; split v')
  (ds.STATE/'restore.json').unlink()
  real_command=ds.command
  def command(*args,**kwargs):
   if args[0].endswith('/project-switch'):return ''
   return real_command(*args,**kwargs)
  with patch.object(ds,'command',side_effect=command),patch.object(ds,'notify'):
   ds.restore()
   ds.restore()
  windows=ds.real_windows(ds.ps.tree())
  assert len(windows)==3,windows
  assert {ws for ws,n in windows}=={'1: work','8'},windows
  assert all(any(m.startswith('desktop:') for m in n.get('marks',[])) for ws,n in windows),windows
  work=next(n for n in ds.nodes(ds.ps.tree()) if n.get('type')=='workspace' and n['name']=='1: work')
  def shape(n):
   return (n.get('layout'), bool(n.get('window') or n.get('swallows')), [shape(c) for c in n.get('nodes',[]) + n.get('floating_nodes',[])])
  saved_layout=ds.ps.read_json(folder/'0.layout.json')
  assert [shape(n) for n in work['nodes'] + work['floating_nodes']] == [shape(n) for n in saved_layout]
  assert len([n for n in ds.nodes(ds.ps.tree()) if n.get('window') and n.get('swallows') and not n.get('window_properties',{}).get('class')])==0
  print('PASS: desktop round trip with actual GTK apps: renamed workspace, native layouts, adopting nested existing windows, verified launches, no duplicate startup')
  # An app with the new identity must fill an old snapshot's placeholder.
  alias_app={'token':'obsidian-upgrade-fixture','command':['obsidian'],
             'properties':{'class':'obsidian','instance':'obsidian'}}
  alias_layout=tmp/'obsidian.layout.json'
  old_layout=[{'type':'con','marks':[alias_app['token']],
               'swallows':[{'class':'^obsidian$','instance':'^obsidian$'}]}]
  ds.ps.atomic_json(alias_layout,ds.compatible_layout(old_layout,[alias_app]))
  ds.ps.i3('append_layout '+json.dumps(str(alias_layout)))
  new_fixture=tmp/'obsidian.py'
  new_fixture.write_text(fixture.read_text().replace('w.set_wmclass(sys.argv[1],"DesktopFixture")',
      'w.set_wmclass("md.obsidian.obsidian","md.obsidian.Obsidian")'))
  spawn(['/usr/bin/python',str(new_fixture),'obsidian'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  restored=wait_for(lambda:ds.filled(alias_app))
  assert restored['window_properties']['class']=='md.obsidian.Obsidian'
  with patch.object(ds,'command') as repeated:
   assert ds.adopt_existing(alias_app)
   repeated.assert_not_called()
  ds.ps.i3(f'[con_id={restored["id"]}] kill')
  print('PASS: new Obsidian identity fills old compatible layout; retry leaves filled window alone')

 finally:
  # Close only this virtual desktop's fixture apps, including restored children.
  if 'wm' in locals() and wm.poll() is None:
   try:ds.ps.i3('[class="DesktopFixture"] kill')
   except Exception:pass
  for p in reversed(processes):
   if p.poll() is None:
    p.terminate()
    try:p.wait(timeout=5)
    except subprocess.TimeoutExpired:p.kill();p.wait()
