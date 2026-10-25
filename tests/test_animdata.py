import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game.sprites.animdata import parse_anim_data

SAMPLE_XML = """<?xml version="1.0" encoding="utf-8"?>
<AnimData>
  <ShadowSize>1</ShadowSize>
  <Anims>
    <Anim>
      <Name>Walk</Name>
      <Index>1</Index>
      <FrameWidth>24</FrameWidth>
      <FrameHeight>32</FrameHeight>
      <Durations>
        <Duration>4</Duration>
        <Duration>4</Duration>
        <Duration>6</Duration>
      </Durations>
    </Anim>
    <Anim>
      <Name>Idle</Name>
      <Index>0</Index>
      <CopyOf>Walk</CopyOf>
    </Anim>
  </Anims>
</AnimData>
"""


class TestAnimData(unittest.TestCase):
    def _parse(self, xml: str):
        with tempfile.NamedTemporaryFile("w", suffix=".xml", delete=False, encoding="utf-8") as f:
            f.write(xml)
            path = f.name
        try:
            return parse_anim_data(path)
        finally:
            os.unlink(path)

    def test_parse_basic(self):
        anims = self._parse(SAMPLE_XML)
        self.assertIn("Walk", anims)
        walk = anims["Walk"]
        self.assertEqual(walk.frame_width, 24)
        self.assertEqual(walk.frame_height, 32)
        self.assertEqual(walk.durations, [4, 4, 6])
        self.assertEqual(walk.frame_count, 3)
        self.assertEqual(walk.sheet_filename, "Walk-Anim.png")

    def test_copy_of_resolution(self):
        anims = self._parse(SAMPLE_XML)
        idle = anims["Idle"]
        # Idle copia dimensioni e durate da Walk.
        self.assertEqual(idle.frame_width, 24)
        self.assertEqual(idle.frame_height, 32)
        self.assertEqual(idle.durations, [4, 4, 6])
        # copy_of punta alla sorgente Walk.
        self.assertEqual(idle.copy_of, "Walk")

    def test_empty_anims(self):
        anims = self._parse(
            '<?xml version="1.0"?><AnimData><Anims></Anims></AnimData>')
        self.assertEqual(anims, {})


if __name__ == "__main__":
    unittest.main()
