# Local replay assets

This directory is a placement guide only. SentinelAI does not ship audio, vision, or
thermal replay binaries.

Create one or more of these ignored directories locally when you need a replay demo:

- `demo_assets/audio/` for explicit `.wav` recordings;
- `demo_assets/vision/` for explicit `.jpg`, `.jpeg`, or `.png` images;
- `demo_assets/thermal/` for explicit thermographic `.jpg`, `.jpeg`, or `.png` images.

Pass a file explicitly with `--asset`. The simulator labels these inputs
`RECORDED REPLAY`; they are not live physical sensor readings. Verify that you have
permission to use each local recording and do not commit proprietary, benchmark, or
personally identifying media.

