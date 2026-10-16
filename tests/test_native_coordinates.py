"""Output-origin regressions; no native display, input or capture occurs."""
import copy
import unittest
from unittest.mock import patch
from workspace.native_coordinates import match_outputs,translate_point,translate_rectangle,read_layout

MONITORS=[{'name':'LEFT','x':0,'y':0,'width':1920,'height':1080,'scale':1},
          {'name':'MIDDLE','x':1920,'y':0,'width':1920,'height':1080,'scale':1},
          {'name':'RIGHT','x':3840,'y':0,'width':1920,'height':1080,'scale':1}]
RANDR='''LEFT connected 1920x1080+3840+0 (normal)
MIDDLE connected primary 1920x1080+1920+0 (normal)
RIGHT connected 1920x1080+0+0 (normal)
'''

class Coordinates(unittest.TestCase):
    def test_swapped_output_origins_translate_by_name_without_reordering_desktop(self):
        before=copy.deepcopy(MONITORS);layout=match_outputs(MONITORS,RANDR)
        self.assertEqual(translate_point(layout,828,360),(4668,360))
        self.assertEqual(translate_point(layout,2506,377),(2506,377))
        self.assertEqual(translate_point(layout,4668,360),(828,360))
        self.assertEqual(MONITORS,before)

    def test_capture_bounds_use_same_name_mapping_and_exact_size(self):
        self.assertEqual(translate_rectangle(match_outputs(MONITORS,RANDR),[300,90],[1320,900]),((4140,90),(1320,900)))

    def test_window_crossing_coordinate_origins_fails_closed(self):
        with self.assertRaisesRegex(RuntimeError,'spans_different_coordinate_origins'):
            translate_rectangle(match_outputs(MONITORS,RANDR),[1500,90],[1000,900])

    def test_missing_duplicate_or_unknown_output_is_not_guessed(self):
        for randr in [RANDR.replace('LEFT connected','OTHER connected'),RANDR+RANDR.splitlines()[0]+'\n',RANDR.splitlines()[0]+'\n','']:
            with self.subTest(randr=randr),self.assertRaises(RuntimeError):match_outputs(MONITORS,randr)

    def test_unequal_coordinate_units_refused_instead_of_silently_scaled(self):
        monitors=copy.deepcopy(MONITORS);monitors[0]['scale']=2
        with self.assertRaisesRegex(RuntimeError,'units_or_dimensions_differ'):match_outputs(monitors,RANDR)

    def test_nonfinite_and_off_output_points_are_refused(self):
        layout=match_outputs(MONITORS,RANDR)
        for point in [(float('nan'),1),(1,float('inf'))]:
            with self.assertRaises(ValueError):translate_point(layout,*point)
        with self.assertRaises(RuntimeError):translate_point(layout,-1,0)

    def test_negative_output_origins_and_rotated_dimensions_use_observed_units(self):
        monitors=[{'name':'PORTRAIT','x':-1080,'y':0,'width':1920,'height':1080,'scale':1,'transform':1}]
        layout=match_outputs(monitors,'PORTRAIT connected 1080x1920+0+0 (normal)\n')
        self.assertEqual(translate_point(layout,-1000,20),(80,20))

    def test_live_reader_is_only_two_fixed_read_only_commands(self):
        import json
        with patch('workspace.native_coordinates.subprocess.check_output',side_effect=[json.dumps(MONITORS),RANDR]) as read:
            self.assertEqual(read_layout(),match_outputs(MONITORS,RANDR))
        self.assertEqual([call.args[0] for call in read.call_args_list],[['/usr/bin/hyprctl','monitors','-j'],['/usr/bin/xrandr','--query','--current']])

if __name__=='__main__':unittest.main()
