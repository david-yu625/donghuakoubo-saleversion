# Scripted Remotion Experiment

This experiment owns its complete video-production flow. It does not import
`src`, read Jianying output directories, reuse Jianying media, or overwrite an
existing video. Stage ownership and artifact contracts are documented in
[ARCHITECTURE.md](ARCHITECTURE.md).

```text
01 copywriting -> 02 Doubao narration -> 03 voice/shot facts -> 04 storyboard
      -> 05 visual direction -> 06 infinite-world layout -> 07 media/manifest
      -> 08 layered Remotion render
```

Every stage writes an inspectable artifact under `runs/<topic>/`. Model or
media generation errors stop the build; failed image requests are not silently
replaced with placeholder diagrams. Images and future video clips share the
same scene contract. Remotion reads only `public/manifest.json` and published
media files. The image contract is `jianying-mg-whiteboard-v1`: opaque white
background, sparse hand-drawn MG illustration, and one composite illustration
per semantic scene. The density audit is written to
`runs/<topic>/density_audit.json`; it never deletes media during rendering.

The infinite canvas is permanent: nodes, grid, route and camera live in world
coordinates; titles, keywords, captions and audio remain screen layers.

```powershell
cd experiments/remotion_scripted
npm install
python scripts/build_project.py --topic "什么是爬虫程序"
npm.cmd run typecheck
npm.cmd run render
```

The rendered video is `out/scripted-canvas.mp4`. Existing `output/` projects
and the Jianying workflow remain untouched. Asset reuse is explicit with
`--reuse-assets` and limited to the matching topic run folder.

The main application's existing `Remotion 无限画布` mode now calls this
renderer through `src.commands.render_infinite_canvas`. It adapts the prepared
landscape project into this manifest contract, then runs the same frame and
encode stages. The Jianying mode continues to use its original renderer.
