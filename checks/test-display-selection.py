"""Screen count/subset selection; isolated Qt and fake native events only."""
import importlib.util,os,sys,tempfile,unittest
from pathlib import Path
os.environ['QT_QPA_PLATFORM']='offscreen'
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'Source'))
from PyQt6.QtWidgets import QApplication
from core.room_pointer_area import display_target,selected_display_ids
from core.room_display_picker import DisplayPicker
from core.room_gesture_rules import read_settings,save_settings
from types import SimpleNamespace as S


def screens(count):
 return [(f'display:{i+1}',f'Экран {i+1} · 1000 × 800',(i*1000,0,1000,800)) for i in range(count)]


class Selection(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def picker(self,count,target='all'):
  dialog=DisplayPicker(None,target,lambda:screens(count));self.addCleanup(dialog.close);return dialog
 def test_available_counts_follow_connected_hardware_for_one_two_three_and_more(self):
  for count in (1,2,3,8,32):
   d=self.picker(count)
   self.assertEqual([d.count.itemData(i) for i in range(d.count.count())],list(range(count+1)))
   self.assertEqual(len(d.selected_keys()),count);self.assertEqual(d.target(),'all')
 def test_manual_count_preserves_existing_choices_and_selects_exactly_requested_number(self):
  d=self.picker(4,'display:3')
  d.count.setCurrentIndex(d.count.findData(2))
  self.assertEqual(set(d.selected_keys()),{'display:1','display:3'})
  self.assertEqual(d.target(),'displays:1,3')
  d.count.setCurrentIndex(d.count.findData(1));self.assertEqual(d.target(),'display:1')
 def test_checkboxes_update_count_and_empty_selection_cannot_be_saved(self):
  d=self.picker(3)
  d.checks['display:2'].setChecked(False)
  self.assertEqual(d.count.currentData(),2);self.assertEqual(d.target(),'displays:1,3')
  for check in d.checks.values():check.setChecked(False)
  self.assertFalse(d.save.isEnabled());self.assertEqual(d.count.currentIndex(),-1)
  d.refresh();self.assertEqual(d.count.currentIndex(),-1);self.assertFalse(d.save.isEnabled())
  d.count.setCurrentIndex(d.count.findData(1));self.assertTrue(d.save.isEnabled())
 def test_automatic_includes_newly_connected_screens_but_manual_subset_does_not(self):
  values=[screens(2)]
  d=DisplayPicker(None,'all',lambda:values[0]);self.addCleanup(d.close)
  values[0]=screens(3);d.refresh();self.assertEqual(len(d.selected_keys()),3);self.assertEqual(d.target(),'all')
  d.checks['display:2'].setChecked(False)
  values[0]=screens(4);d.refresh();self.assertEqual(set(d.selected_keys()),{'display:1','display:3'});self.assertEqual(d.target(),'displays:1,3')
 def test_disconnect_limits_count_and_never_silently_selects_another_monitor(self):
  values=[screens(3)]
  d=DisplayPicker(None,'displays:2,3',lambda:values[0]);self.addCleanup(d.close)
  values[0]=screens(2);d.refresh();self.assertEqual(d.selected_keys(),['display:2']);self.assertEqual(d.count.currentData(),1)
  values[0]=screens(1);d.refresh();self.assertEqual(d.selected_keys(),[]);self.assertFalse(d.save.isEnabled())
 def test_no_displays_disables_count_and_save(self):
  d=self.picker(0);self.assertFalse(d.count.isEnabled());self.assertFalse(d.save.isEnabled())
 def test_subset_roundtrips_and_invalid_ids_fall_back_safely(self):
  self.assertEqual(display_target('displays:3,1,3'),'displays:1,3')
  self.assertEqual(selected_display_ids('displays:3,1'),{1,3})
  for invalid in ('displays:','displays:1,,3','displays:1,-2','displays:0,3','displays:1,4294967296','displays:²','display:²','display:0'):
   self.assertEqual(display_target(invalid),'all')
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder)/'settings.json';save_settings(path,{'mouse_display':'displays:3,1'})
   self.assertEqual(read_settings(path)['mouse_display'],'displays:1,3')
 def test_native_mapping_uses_only_chosen_subset_and_excludes_middle_monitor(self):
  spec=importlib.util.spec_from_file_location('area_fixture',ROOT/'checks/test-pointer-area.py')
  module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
  mouse,position,rectangles,events=module.Displays().fixture()
  rectangles.clear()
  rectangles.update({i:S(origin=S(x=(i-1)*1000,y=0),size=S(width=1000,height=800)) for i in (1,2,3)})
  mouse.set_display_target('displays:1,3')
  for x in (0,.25,.5,.75,1):
   mouse.send(dict(action='pointer',phase='move',absolute=True,x=x,y=.5))
   self.assertTrue(position[0]<=999 or position[0]>=2000,'unselected center display must be excluded')
  self.assertEqual(position,[2999,399.5]);self.assertEqual(mouse.physical_pauses,0)

if __name__=='__main__':unittest.main()
