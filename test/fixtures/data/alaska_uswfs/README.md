# Alaska Lightning Detection Network sample

`strokes_sample.txt` holds 42 rows cut verbatim — bytes, byte-order mark and
header included — from `Historical_Lightning_2012_2026_TOA_WGS84.txt`, the strokes
file of the U.S. Wildland Fire Service release
`Historical_Lightning_2012_forward_as_txt.zip` of 2026-11-06, downloaded on
2026-11-13 from <https://fire.ak.blm.gov/predsvcs/maps.php>.

**Source:** U.S. Wildland Fire Service (USWFS), Alaska Geographic Area: Alaska
Lightning Detection Network (ALDN). The metadata states: "None, these data are
considered public domain", and asks that the USWFS be cited as the source and that
any modification be described. **Modification:** only a selection of the rows; no
value was changed.

The rows were chosen for what the import has to get right (file line numbers of
the release in brackets):

- the first 13 rows of the release, 2012-03-07 and 08 (2-14): the first eight have
  no sequence number, and two lie east of the antimeridian (172.2 E, 170.6 E);
- the 255 ceilings of `GDOP` and `ERRSEMIMAJOR`, with a semi-minor axis of 9 km
  (495), and the ±500 kA saturation (1685, 1688);
- strokes published twice on 2012-06-15, identical but for the sequence number: a
  cloud and a ground stroke at 01:29:15 (39840-39843) and two ground strokes
  (39886-39889);
- three strokes of 2014 with a semi-major axis of 0 (272680-272682);
- a stroke of 2019 with no polarity (1149985) and two whose polarity contradicts
  the amplitude (1175022, 1175040);
- a cloud and a ground stroke at the same millisecond, 2025-05-24 21:27:57.335
  (1896577-1896578), and a lone cloud stroke (2003469);
- two three-stroke ground flashes of 2025-07-01 near the Alaska-Yukon border
  (2003651-2003653, 2003695-2003697);
- the last three rows of the release, 2026-09-27 and 28 (2226184-2226186).

The tests zip it with a minimal FGDC metadata file whose point count matches, as
the release ships them.
